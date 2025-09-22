import logging
from typing import Optional, Dict, List
from google.cloud import aiplatform
from app.core.config import GOOGLE_PROJECT_ID, GOOGLE_INDEX_ID, GOOGLE_INDEX_ENDPOINT_ID

logger = logging.getLogger(__name__)

# Tenta inicializar a conexão com a Vertex AI
try:
    if GOOGLE_PROJECT_ID:
        aiplatform.init(project=GOOGLE_PROJECT_ID, location='southamerica-east1')
        logger.info("Cliente da Vertex AI inicializado com sucesso.")
    else:
        logger.warning("Vertex AI não inicializada: GOOGLE_PROJECT_ID não encontrado.")
except Exception as e:
    logger.error(f"Erro ao inicializar o cliente da Vertex AI: {e}")

def get_image_embedding(image_bytes: bytes) -> Optional[List[float]]:
    """Usa o modelo multimodal da Vertex AI para transformar uma imagem em um vetor (embedding)."""
    try:
        model = aiplatform.ImageModel.from_pretrained("multimodalembedding@001")
        image = aiplatform.Image(image_bytes=image_bytes)
        embeddings = model.get_embeddings(image=image)
        logger.info("Vetor (embedding) da imagem gerado com sucesso.")
        return embeddings.image_embedding
    except Exception as e:
        logger.error(f"Erro ao gerar o embedding da imagem: {e}")
        return None

def add_image_to_index(sku_id: str, image_embedding: List[float]):
    """Adiciona/atualiza um datapoint (imagem) no nosso índice da Vector Search."""
    if not GOOGLE_INDEX_ID:
        logger.error("Não é possível adicionar ao índice: GOOGLE_INDEX_ID não configurado.")
        return False
    try:
        my_index = aiplatform.MatchingEngineIndex(index_name=GOOGLE_INDEX_ID)
        datapoint = aiplatform.IndexDatapoint(
            datapoint_id=sku_id,
            feature_vector=image_embedding
        )
        my_index.upsert_datapoints(datapoints=[datapoint])
        logger.info(f"SKU '{sku_id}' adicionado/atualizado no índice da Vector Search.")
        return True
    except Exception as e:
        logger.error(f"Erro ao adicionar SKU '{sku_id}' ao índice: {e}")
        return False

def find_match_in_vector_search(image_embedding: List[float]) -> Optional[Dict]:
    """Consulta o índice para encontrar a imagem mais similar."""
    if not GOOGLE_INDEX_ENDPOINT_ID:
        logger.error("Não é possível consultar o índice: GOOGLE_INDEX_ENDPOINT_ID não configurado.")
        return None
    try:
        my_index_endpoint = aiplatform.MatchingEngineIndexEndpoint(
            index_endpoint_name=GOOGLE_INDEX_ENDPOINT_ID
        )
        response = my_index_endpoint.find_neighbors(
            queries=[image_embedding],
            num_neighbors=1
        )
        if not response or not response[0]:
            logger.info("Nenhuma correspondência encontrada na Vector Search.")
            return None
        best_match = response[0][0]
        sku_id = best_match.id
        confidence = best_match.distance
        logger.info(f"Correspondência encontrada na Vector Search! SKU: {sku_id}, Confiança: {confidence:.2f}")
        if confidence > 0.8:
            return {"product_id": sku_id, "confidence": confidence}
        return None
    except Exception as e:
        logger.error(f"Erro ao consultar a Vector Search: {e}")
        return None