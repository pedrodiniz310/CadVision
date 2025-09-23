import logging
import requests
import base64
from typing import Optional, Dict, List
from google.cloud import aiplatform
from google.oauth2 import service_account
from google.auth.transport.requests import Request
from app.core.config import GOOGLE_PROJECT_ID, GOOGLE_INDEX_ID, GOOGLE_INDEX_ENDPOINT_ID, GOOGLE_KEY_PATH, GOOGLE_CLOUD_REGION, GOOGLE_INDEX_PUBLIC_DOMAIN

logger = logging.getLogger(__name__)

credentials = None
vertex_ai_client_initialized = False
try:
    if GOOGLE_KEY_PATH and GOOGLE_KEY_PATH.exists():
        scopes = ["https://www.googleapis.com/auth/cloud-platform"]
        credentials = service_account.Credentials.from_service_account_file(
            GOOGLE_KEY_PATH, scopes=scopes)
        credentials.refresh(Request())
        logger.info("Credenciais do Google Cloud carregadas com sucesso.")
        vertex_ai_client_initialized = True
    else:
        logger.warning(
            f"Arquivo de chave não encontrado. Vertex AI não funcionará.")
except Exception as e:
    logger.error(f"Erro ao carregar credenciais: {e}")

if vertex_ai_client_initialized:
    try:
        aiplatform.init(project=GOOGLE_PROJECT_ID,
                        location=GOOGLE_CLOUD_REGION, credentials=credentials)
        logger.info("Cliente da Vertex AI inicializado para o Matching Engine.")
    except Exception as e:
        logger.error(f"Erro ao inicializar o cliente da Vertex AI: {e}")


def get_image_embedding(image_bytes: bytes) -> Optional[List[float]]:
    if not vertex_ai_client_initialized:
        return None
    try:
        encoded_content = base64.b64encode(image_bytes).decode("utf-8")
        endpoint_url = f"https://{GOOGLE_CLOUD_REGION}-aiplatform.googleapis.com/v1/projects/{GOOGLE_PROJECT_ID}/locations/{GOOGLE_CLOUD_REGION}/publishers/google/models/multimodalembedding@001:predict"
        auth_token = credentials.token
        headers = {"Authorization": f"Bearer {auth_token}",
                   "Content-Type": "application/json; charset=utf-8"}
        request_body = {"instances": [
            {"image": {"bytesBase64Encoded": encoded_content}}]}
        logger.info("Gerando embedding via API REST...")
        response = requests.post(
            endpoint_url, json=request_body, headers=headers)
        response.raise_for_status()
        response_json = response.json()
        image_embedding = response_json['predictions'][0]['imageEmbedding']
        logger.info(
            "Vetor (embedding) da imagem gerado com sucesso via API REST.")
        return image_embedding
    except Exception as e:
        logger.error(
            f"Erro inesperado ao gerar o embedding da imagem: {getattr(e, 'response', e)}")
        return None


def add_image_to_index(sku_id: str, image_embedding: List[float]):
    if not vertex_ai_client_initialized or not GOOGLE_INDEX_ID:
        return False
    try:
        my_index = aiplatform.MatchingEngineIndex(index_name=GOOGLE_INDEX_ID)
        datapoint = aiplatform.IndexDatapoint(
            datapoint_id=sku_id, feature_vector=image_embedding)
        my_index.upsert_datapoints(datapoints=[datapoint])
        logger.info(
            f"SKU '{sku_id}' adicionado/atualizado no índice da Vector Search.")
        return True
    except Exception as e:
        logger.error(f"Erro ao adicionar SKU '{sku_id}' ao índice: {e}")
        return False


def find_match_in_vector_search(image_embedding: List[float]) -> Optional[Dict]:
    """Consulta o índice via API REST para encontrar a imagem mais similar."""
    if not vertex_ai_client_initialized or not GOOGLE_INDEX_ENDPOINT_ID or not GOOGLE_INDEX_PUBLIC_DOMAIN:
        logger.error(
            "Não é possível consultar: Cliente não inicializado ou IDs/Domínio ausentes.")
        return None

    try:
        # --- A CORREÇÃO CRÍTICA ESTÁ AQUI ---
        # Usamos o domínio público dedicado do endpoint
        endpoint_url = f"https://{GOOGLE_INDEX_PUBLIC_DOMAIN}/v1/projects/{GOOGLE_PROJECT_ID}/locations/{GOOGLE_CLOUD_REGION}/indexEndpoints/{GOOGLE_INDEX_ENDPOINT_ID}:findNeighbors"

        # O ID da implantação que descobrimos anteriormente
        deployed_index_id = "idx_vestuario_implantado_v_1758595018034"

        request_body = {
            "deployedIndexId": deployed_index_id,
            "queries": [
                {"datapoint": {"featureVector": image_embedding, "neighborCount": 1}}
            ]
        }

        auth_token = credentials.token
        headers = {"Authorization": f"Bearer {auth_token}",
                   "Content-Type": "application/json; charset=utf-8"}

        logger.info(
            f"Consultando a Vector Search no endpoint público: {GOOGLE_INDEX_PUBLIC_DOMAIN}...")
        response = requests.post(
            endpoint_url, json=request_body, headers=headers)
        response.raise_for_status()

        response_json = response.json()
        neighbors = response_json.get('nearestNeighbors', [{}])[
            0].get('neighbors', [])

        if not neighbors:
            logger.info("Nenhuma correspondência encontrada na Vector Search.")
            return None

        best_match = neighbors[0]
        sku_id = best_match.get('datapoint', {}).get('datapointId')
        confidence = best_match.get('distance')

        logger.info(
            f"Correspondência encontrada! SKU: {sku_id}, Confiança: {confidence:.4f}")

        if confidence > 0.8:
            return {"product_id": sku_id, "confidence": confidence}

        logger.warning(
            f"Correspondência com baixa confiança ({confidence:.4f}) foi descartada.")
        return None

    except requests.exceptions.RequestException as e:
        logger.error(
            f"Erro na chamada REST para consultar a Vector Search: {e.response.text if e.response else e}")
        return None
    except Exception as e:
        logger.error(f"Erro inesperado ao consultar a Vector Search: {e}")
        return None
