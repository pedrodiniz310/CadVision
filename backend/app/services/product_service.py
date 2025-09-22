# backend/app/services/product_service.py
import logging
import sqlite3
from typing import Dict, Optional
# Módulo de configuração para verificar a existência de chaves de API
# Serviços especializados que são orquestrados por este módulo
from app.services.cosmos_service import fetch_product_by_gtin
from app.services.search_service import search_web_for_product
from app.services.advanced_inference_service import run_advanced_inference, extract_gtin_from_context
from app.services.vision_service import find_product_by_visual_search
from app.database import get_product_by_id
from datetime import datetime
# Em uma implementação de produção, você usaria uma biblioteca cliente de busca.
# Ex: from some_search_engine_api import SearchClient

logger = logging.getLogger(__name__)


def _post_process_and_validate_data(data: Dict, vision_data: Dict) -> Dict:
    """
    Aplica regras de negócio para limpar, padronizar e validar os dados
    retornados pela IA ou outras fontes.
    """
    # 1. Capitalização e remoção de espaços
    for key in ['title', 'brand', 'department', 'category', 'subcategory']:
        if key in data and isinstance(data[key], str):
            data[key] = data[key].strip().title()

    # 2. Lógica de fallback de Título (regra de negócio crítica)
    if not data.get('title'):
        brand = data.get('brand')
        category = data.get('category')
        if brand and category:
            data['title'] = f"{brand} - {category}"
        elif vision_data.get('raw_text'):
            first_words = ' '.join(vision_data['raw_text'].split()[:4])
            data['title'] = f"Produto {first_words}"
        else:
            data['title'] = f"Produto Não Identificado - {datetime.now().strftime('%H:%M:%S')}"
        logger.warning(
            f"Título ausente, definido por fallback: {data['title']}")

    # 3. Garante que o preço da imagem original tenha prioridade
    data['price'] = data.get('price') or vision_data.get('price')

    # 4. Garante um valor mínimo de confiança
    # Confiança padrão pós-processamento
    data['confidence'] = data.get('confidence', 0.8)

    return data


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

def intelligent_text_analysis(vision_data: Dict, db: sqlite3.Connection, vertical: str) -> Dict:
    """
    Executa o pipeline de análise completo, com busca visual como primeira etapa para vestuário.
    """
    # --- ETAPA 1: TENTATIVA DE BUSCA VISUAL (LÓGICA DA AULA 3) ---
    if vertical == 'vestuario':
        logger.info("Iniciando Etapa 1 (Busca Visual).")
        image_bytes = vision_data.get('original_image_bytes')

        if image_bytes:
            visual_match = find_product_by_visual_search(image_bytes)
            if visual_match:
                product_sku = visual_match.get("product_id")
                # Busca o produto completo no NOSSO banco de dados usando o SKU
                product_data = get_product_by_id(
                    product_sku, db, find_by_sku=True)

                if product_data:
                    logger.info(
                        f"Sucesso! Produto SKU {product_sku} encontrado via busca visual.")
                    product_data['confidence'] = visual_match.get('confidence')
                    # Retorna os dados do produto encontrado visualmente e encerra a função
                    return product_data

    # --- ETAPAS DE FALLBACK (SE A BUSCA VISUAL FALHAR OU NÃO FOR VESTUÁRIO) ---
    logger.info(
        "Busca visual falhou ou não aplicável. Prosseguindo com a análise de texto/GTIN.")

    detected_gtin = vision_data.get('gtin')
    processed_data = None

    if vertical != 'vestuario' and detected_gtin:
        logger.info(
            f"Iniciando Etapa 2 (Via Rápida - GTIN) com GTIN: {detected_gtin}.")
        processed_data = fetch_product_by_gtin(detected_gtin)

    if not processed_data:
        logger.info(
            "Via Rápida falhou ou não aplicável. Iniciando Etapa 3 (Inferência da IA).")
        processed_data = run_advanced_inference(vision_data, [], vertical)

    base_data = processed_data.get("base_data", {})
    attributes = processed_data.get("attributes", {})

    if not base_data:
        logger.error("A análise inicial falhou em gerar dados base.")
        return _post_process_and_validate_data({}, vision_data)

    logger.info(f"Produto pré-identificado: {base_data.get('title')}")

    # ETAPA DE ENRIQUECIMENTO (RAG)
    if not base_data.get('gtin'):
        logger.info("Iniciando Etapa de Enriquecimento com Busca na Web (RAG).")
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
                    cosmos_response = fetch_product_by_gtin(found_gtin)

                    if cosmos_response and cosmos_response.get("base_data"):
                        logger.info(
                            "Sucesso! Dados validados e enriquecidos pelo Cosmos via RAG.")
                        # Atualiza os dados base com as informações mais confiáveis do Cosmos
                        enriched_data = cosmos_response["base_data"]
                        base_data.update(enriched_data)

    # ETAPA FINAL: PÓS-PROCESSAMENTO E RETORNO
    final_product_data = base_data.copy()

    if attributes:
        final_product_data['attributes'] = attributes

    # Aplica a função de validação e limpeza antes de retornar.
    # Esta função centraliza toda a lógica de fallback de título, priorização de preço, etc.
    final_product_data = _post_process_and_validate_data(
        final_product_data, vision_data)

    return final_product_data
