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


def intelligent_text_analysis(vision_data: Dict, db: sqlite3.Connection) -> Dict:
    """
    Executa o pipeline completo de análise inteligente usando a Busca Híbrida.
    """
    # ETAPA 1: VIA RÁPIDA (GTIN da imagem)
    detected_gtin = vision_data.get('gtin')
    if detected_gtin:
        logger.info(
            f"Iniciando Etapa 1 (Via Rápida) com GTIN da imagem: {detected_gtin}.")
        cosmos_data = fetch_product_by_gtin(detected_gtin)
        if cosmos_data and cosmos_data.get("description"):
            logger.info(
                "✅ Sucesso! Dados encontrados via API Cosmos com GTIN da imagem.")
            return {
                "gtin": detected_gtin,
                "title": cosmos_data.get("description"),
                "brand": cosmos_data.get("brand"),
                "category": _normalize_category(cosmos_data.get("category")),
                "ncm": cosmos_data.get("ncm"),
                "cest": cosmos_data.get("cest"),
                "price": vision_data.get('price'),
                "confidence": 0.99,
            }

    # ETAPA 2: VIA INTELIGENTE (IA para extração do título)
    logger.info("Etapa 1 falhou. Iniciando Etapa 2 (Inferência da IA).")
    inferred_product = run_advanced_inference(vision_data, [])
    if not inferred_product or not inferred_product.get('title') or "não identificado" in inferred_product.get('title').lower():
        logger.error(
            "A IA não conseguiu identificar o produto a partir da imagem.")
        return {'title': 'Falha ao analisar o produto', 'confidence': 0.1}

    logger.info(
        f"Produto identificado pela IA: {inferred_product.get('title')}")

    # ETAPA 3: ENRIQUECIMENTO COM BUSCA REAL (RAG)
    if not inferred_product.get('gtin'):
        logger.info("Iniciando Etapa 3 (Enriquecimento com Busca na Web).")
        title = inferred_product.get('title')
        brand = inferred_product.get('brand')

        # 3.1: Busca na Web para encontrar informações
        # Usar "ean" na busca costuma ser mais eficaz
        search_query = f"ean {brand} {title}"
        search_results = search_web_for_product(search_query)

        if search_results:
            # 3.2: IA para extrair o GTIN dos resultados
            gtin_data = extract_gtin_from_context(title, search_results)
            found_gtin = gtin_data.get('gtin')

            if found_gtin:
                logger.info(
                    f"GTIN '{found_gtin}' extraído da busca. Validando...")
                # 3.3: Validação no Cosmos para obter dados canônicos
                cosmos_data = fetch_product_by_gtin(found_gtin)
                if cosmos_data and cosmos_data.get("description"):
                    logger.info(
                        "Sucesso! Dados validados e enriquecidos pelo Cosmos.")
                    return {
                        "gtin": found_gtin,
                        "title": cosmos_data.get("description"),
                        "brand": cosmos_data.get("brand") or brand,
                        "category": _normalize_category(cosmos_data.get("category")),
                        "ncm": cosmos_data.get("ncm"),
                        "cest": cosmos_data.get("cest"),
                        "price": vision_data.get('price'),
                        "confidence": 0.99,
                    }

    # ETAPA 4: FINALIZAÇÃO (Fallback)
    logger.warning(
        "Não foi possível encontrar/validar um GTIN. Retornando dados da inferência inicial.")
    return inferred_product
