# backend/app/services/product_service.py
import logging
import sqlite3
from typing import Dict, Optional
# Módulo de configuração para verificar a existência de chaves de API
from app.core.config import COSMOS_API_KEY
# Serviços especializados que são orquestrados por este módulo
from app.services.cosmos_service import fetch_product_by_gtin
from app.services.search_service import search_web_for_product
from app.services.advanced_inference_service import run_advanced_inference, extract_gtin_from_context

# Em uma implementação de produção, você usaria uma biblioteca cliente de busca.
# Ex: from some_search_engine_api import SearchClient

logger = logging.getLogger(__name__)

# search_client = SearchClient(api_key="SUA_CHAVE_DE_API_DE_BUSCA") # Exemplo


def _normalize_category(category_name: Optional[str]) -> str:
    """
    Garante que a categoria esteja em um formato padrão e consistente.
    Serve como uma camada final de limpeza para a saída do LLM ou de outras APIs.
    """
    if not category_name:
        return "Outros"

    # Mapeamento para garantir consistência (ex: 'Alimento' -> 'Alimentos')
    CATEGORY_MAPPING = {
        "Alimentos": ['alimento', 'comida', 'mercearia', 'grãos', 'laticínio', 'carne'],
        "Bebidas": ['bebida', 'refrigerante', 'suco', 'água', 'cerveja', 'vinho'],
        "Limpeza": ['limpeza', 'sabão', 'detergente', 'amaciante', 'desinfetante'],
        "Higiene": ['higiene', 'pessoal', 'cosmético', 'shampoo', 'sabonete'],
        "Eletrônicos": ['eletrônico', 'eletrodoméstico', 'celular', 'tv'],
    }

    category_lower = category_name.lower()
    for canonical_name, keywords in CATEGORY_MAPPING.items():
        if any(keyword in category_lower for keyword in keywords):
            return canonical_name

    # Se não houver correspondência, apenas capitaliza o nome recebido
    return category_name.strip().title()


# Em backend/app/services/product_service.py

# Em backend/app/services/product_service.py

def intelligent_text_analysis(vision_data: Dict, db: sqlite3.Connection, vertical: str) -> Dict:
    """
    Executa o pipeline de análise. Garante que o formato de dados seja consistente
    independentemente do caminho (rápido ou IA).
    """
    detected_gtin = vision_data.get('gtin')
    processed_data = None

    # Etapa 1: Tenta o Caminho Rápido se houver GTIN
    if detected_gtin:
        logger.info(
            f"Iniciando Etapa 1 (Via Rápida) com GTIN: {detected_gtin}.")
        processed_data = fetch_product_by_gtin(detected_gtin)

    # Etapa 2: Se o Caminho Rápido falhar ou não for aplicável, usa a IA
    if not processed_data:
        logger.info(
            "Etapa 1 falhou ou não aplicável. Iniciando Etapa 2 (Inferência da IA).")
        processed_data = run_advanced_inference(vision_data, [], vertical)

    # A partir daqui, 'processed_data' sempre terá a estrutura {'base_data': ..., 'attributes': ...}
    base_data = processed_data.get("base_data", {})
    attributes = processed_data.get("attributes", {})

    if not base_data or not base_data.get('title'):
        logger.error(
            "A análise não conseguiu identificar um título para o produto.")
        return {'title': 'Falha ao analisar o produto', 'confidence': 0.1}

    logger.info(f"Produto identificado: {base_data.get('title')}")

    # Etapa 3: Enriquece com GTIN via busca na web, se necessário (lógica de RAG)
    if not base_data.get('gtin'):
        logger.info("Iniciando Etapa 3 (Enriquecimento com Busca na Web).")
        title = base_data.get('title')
        brand = base_data.get('brand')

        if title and brand:
            search_query = f"ean {brand} {title}"
            search_results = search_web_for_product(search_query)

            if search_results:
                gtin_data = extract_gtin_from_context(title, search_results)
                found_gtin = gtin_data.get('gtin')

                if found_gtin:
                    logger.info(
                        f"GTIN '{found_gtin}' extraído da busca. Validando...")
                    # Valida o GTIN encontrado no Cosmos para obter dados canônicos
                    cosmos_response = fetch_product_by_gtin(found_gtin)

                    if cosmos_response and cosmos_response.get("base_data"):
                        logger.info(
                            "Sucesso! Dados validados e enriquecidos pelo Cosmos via RAG.")

                        # Usa os dados do Cosmos como a fonte principal de verdade
                        enriched_data = cosmos_response["base_data"]

                        # Mantém o preço da imagem original, que é mais confiável
                        enriched_data['price'] = base_data.get(
                            'price') or vision_data.get('price')

                        # Se for vestuário, anexa os atributos que a IA encontrou na Etapa 2
                        if vertical == 'vestuario' and attributes:
                            enriched_data['attributes'] = attributes

                        # Normaliza a categoria como passo final
                        enriched_data['category'] = _normalize_category(
                            enriched_data.get('category'))

                        return enriched_data  # Retorna os dados enriquecidos e encerra a função

   # --- CORREÇÃO DEFINITIVA ---
    # Etapa 4: Finalização e retorno. Prepara um dicionário 'plano' para o frontend.
    # Cria uma cópia para não modificar o original
    final_product_data = base_data.copy()

    # Adiciona os atributos (se existirem) ao dicionário final
    if attributes:
        final_product_data['attributes'] = attributes

    # Garante que o preço da imagem original seja considerado
    final_product_data['price'] = base_data.get(
        'price') or vision_data.get('price')
    # Normaliza a categoria como passo final
    final_product_data['category'] = _normalize_category(
        final_product_data.get('category'))

    return final_product_data
