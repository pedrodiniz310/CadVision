from app.core.config import GEMINI_API_KEY
import google.generativeai as genai
import json
import re
from typing import Dict, Any, List
import logging
from app.core.logging_config import log_structured_event

# Configurar logging
logger = logging.getLogger(__name__)

# Configura a API key de forma segura a partir da variável importada
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
else:
    logger.error(
        "GEMINI_API_KEY não encontrada! O serviço de IA não funcionará.")


# =============================================================================
# === FUNÇÕES PRINCIPAIS (PONTOS DE ENTRADA DO SERVIÇO) =======================
# =============================================================================

def run_advanced_inference(vision_data: Dict, search_results: List[Dict], vertical: str) -> Dict:
    """
    Orquestra o processo de inferência inicial para extrair dados da imagem.
    É o ponto de entrada principal para a identificação via IA, agora ciente da vertical.
    """
    ocr_text = vision_data.get('raw_text', '')
    logos = [logo['description']
             for logo in vision_data.get('detected_logos', [])]

    extracted_data = extract_product_info(
        ocr_text, logos, search_results, vertical)

    # Retorna uma estrutura padronizada com dados base e atributos específicos
    base_data = {
        'sku': extracted_data.get("sku"),  # NOVO CAMPO
        'gtin': extracted_data.get("gtin"),
        'title': extracted_data.get("title"),
        'brand': extracted_data.get("brand"),
        'department': extracted_data.get("department"),  # NOVO CAMPO
        'category': _normalize_category(extracted_data.get("category")),
        'subcategory': extracted_data.get("subcategory"),  # NOVO CAMPO
        'price': extracted_data.get("price") or vision_data.get('price'),
        'confidence': 0.95,  # Confiança base da IA
        'vertical': vertical
    }

    attributes = {}
    if vertical == 'vestuario':
        attributes = {
            'size': extracted_data.get("size"),
            'color': extracted_data.get("color"),
            'fabric': extracted_data.get("fabric"),
            'gender': extracted_data.get("gender")
        }
    else:  # Default para 'supermercado'
        base_data['ncm'] = extracted_data.get("ncm")
        base_data['cest'] = extracted_data.get("cest")

    return {
        "base_data": base_data,
        "attributes": attributes
    }


def extract_gtin_from_context(title: str, search_results: List[Dict]) -> Dict:
    """
    Usa a IA para extrair um GTIN-13 de um contexto de texto (resultados de busca).
    """
    if not search_results:
        return {"gtin": None}

    context = ""
    for i, result in enumerate(search_results, 1):
        context += f"Fonte {i} Título: {result.get('title', '')}\n"
        context += f"Fonte {i} Conteúdo: {result.get('snippet', '')}\n---\n"

    prompt = f"""
    Sua tarefa é agir como um extrator de dados preciso.
    Analise o texto de contexto abaixo, que contém resultados de uma busca na web para o produto "{title}".
    Encontre o código de barras GTIN-13 (13 dígitos numéricos) que corresponde a este produto.

    Contexto:
    {context}

    Retorne APENAS um objeto JSON com a seguinte chave:
    - "gtin": o GTIN-13 encontrado como uma string, ou null se não houver um GTIN claro no texto.
    """

    try:
        logger.info(f"Extraindo GTIN do contexto de busca para '{title}'")
        model = genai.GenerativeModel('gemini-1.5-pro-latest')
        response = model.generate_content(prompt)
        response_text = response.text.strip()
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)

        if json_match:
            data = json.loads(json_match.group())
            gtin = data.get("gtin")
            if gtin and isinstance(gtin, str) and len(re.sub(r'\D', '', gtin)) == 13:
                return {"gtin": re.sub(r'\D', '', gtin)}

        return {"gtin": None}
    except Exception as e:
        logger.error(f"Erro ao extrair GTIN do contexto com a IA: {e}")
        return {"gtin": None}


# =============================================================================
# === FUNÇÕES DE LÓGICA INTERNA ===============================================
# =============================================================================

# backend/app/services/advanced_inference_service.py

def extract_product_info(ocr_text: str, detected_logos: List[str], search_results: List[Dict], vertical: str) -> Dict[str, Any]:
    """
    Extrai informações com logs detalhados da IA.
    """
    log_structured_event("ai_service", "extraction_started", {
        "vertical": vertical,
        "ocr_text_length": len(ocr_text),
        "logos_count": len(detected_logos),
        "search_results_count": len(search_results)
    }, "DEBUG")

    try:
        prompt = _build_llm_prompt(
            ocr_text, detected_logos, search_results, vertical)

        # Log do prompt (apenas primeiros 500 caracteres para não poluir)
        log_structured_event("ai_service", "prompt_generated", {
            "prompt_preview": prompt[:500] + "..." if len(prompt) > 500 else prompt
        }, "DEBUG")

        model = genai.GenerativeModel('gemini-1.5-pro-latest')
        response = model.generate_content(prompt)
        response_text = response.text.strip()

        log_structured_event("ai_service", "ai_response_received", {
            "response_length": len(response_text),
            "response_preview": response_text[:200] + "..." if len(response_text) > 200 else response_text
        }, "DEBUG")

        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)

        if json_match:
            json_str = json_match.group()
            extracted_data = json.loads(json_str)

            log_structured_event("ai_service", "json_parsed_successfully", {
                "title_extracted": extracted_data.get("title"),
                "brand_extracted": extracted_data.get("brand"),
                "category_extracted": extracted_data.get("category")
            })

            # Validação do título
            if not extracted_data.get("title") or extracted_data["title"].strip() == "":
                log_structured_event("ai_service", "empty_title_from_ai", {
                    # Log parcial para debug
                    "raw_response": response_text[:300]
                }, "WARNING")

                # Fallback
                first_words = ' '.join(ocr_text.split()[:5])
                extracted_data["title"] = f"Produto {first_words}" if first_words else "Produto Não Identificado"

                log_structured_event("ai_service", "title_fallback_applied", {
                    "new_title": extracted_data["title"]
                })

            return extracted_data

        else:
            log_structured_event("ai_service", "json_parse_failed", {
                "response_text": response_text[:300]  # Log parcial
            }, "ERROR")

            # Fallback robusto
            return _create_fallback_response(ocr_text)

    except Exception as e:
        log_structured_event("ai_service", "extraction_failed", {
            "error": str(e),
            "error_type": type(e).__name__
        }, "ERROR")

        return _create_fallback_response(ocr_text)


def _create_fallback_response(ocr_text: str) -> Dict:
    """Cria resposta fallback com log"""
    fallback_data = {
        "title": "Produto Não Identificado",
        "brand": "",
        "category": "Outros",
        "gtin": "",
        "price": None
    }

    log_structured_event("ai_service", "using_fallback_response", {
        "fallback_data": fallback_data
    }, "WARNING")

    return fallback_data
# =============================================================================
# === FUNÇÕES AUXILIARES (HELPERS) ============================================
# =============================================================================


def _build_llm_prompt(ocr_text: str, detected_logos: List[str], search_results: List[Dict], vertical: str) -> str:
    """
    Cria o prompt estruturado para ser enviado ao LLM, adaptado para a vertical do produto.
    """
    search_context = ""
    if search_results:
        search_context = "\nCONTEXTO ADICIONAL DE BUSCA NA WEB:\n"
        for i, res in enumerate(search_results, 1):
            title = res.get('title', 'N/A')
            snippet = res.get('snippet', 'N/A')
            search_context += f"{i}. {title}: {snippet}\n"

    logos_context = ""
    if detected_logos:
        logos_context = f"\nLOGO DETECTADAS: {', '.join(detected_logos)}"

    # Parte dinâmica do prompt
    json_structure = ""
    instructions = ""

    if vertical == 'vestuario':
        json_structure = """
    - "sku": código de referência único do produto (SKU), se visível. Ex: "8806091480130".
    - "title": nome completo do produto. Ex: "Camisa Polo Masculina Piquet".
    - "brand": marca do produto. Ex: "Lacoste".
    - "department": departamento principal. Ex: "Masculino", "Feminino", "Infantil".
    - "category": tipo de peça. Ex: "Camisas", "Calças", "Calçados".
    - "subcategory": especificação da peça. Ex: "Camisa Polo", "Calça Jeans Skinny", "Tênis Casual".
    - "size": tamanho da peça. Ex: "M", "G", "42".
    - "color": cor principal da peça. Ex: "Azul Marinho".
    - "fabric": tecido ou material principal. Ex: "100% Algodão".
    - "gender": gênero. Ex: "Masculino", "Feminino", "Unissex".
    - "gtin": código GTIN/EAN de 13 dígitos, se visível.
    - "price": preço do produto, se visível.
    """
        instructions = "Seja extremamente detalhista na categorização. Se um campo não for encontrado, retorne null. Infira o departamento e a categoria a partir do título, se necessário."
    else:  # Default para 'supermercado'
        json_structure = """
    - "sku": código de referência único (SKU), se visível.
    - "title": nome completo do produto, incluindo peso/volume. Ex: "Arroz Integral Tipo 1 Tio João 1kg".
    - "brand": marca do produto. Ex: "Tio João".
    - "department": departamento principal. Ex: "Mercearia", "Bebidas", "Limpeza".
    - "category": categoria principal. Ex: "Grãos e Cereais", "Refrigerantes", "Lava Roupas".
    - "subcategory": subcategoria do produto. Ex: "Arroz Agulhinha", "Refrigerante Cola", "Sabão em Pó".
    - "gtin": código GTIN/EAN de 13 dígitos, se visível.
    - "ncm": código NCM no formato 9999.99.99, se visível.
    - "cest": código CEST no formato 99.999.99, se visível.
    - "price": preço do produto, se visível.
    """
        instructions = "Seja preciso com as unidades (kg, g, L, ml). Se um campo não for encontrado, retorne null. Infira o departamento e a categoria a partir do título."

    # Montagem do prompt final
    prompt = f"""
    Você é um especialista em processamento de dados de produtos para um sistema de cadastro.
    Sua tarefa é analisar o texto de uma imagem de um produto da vertical '{vertical.upper()}' e retornar APENAS um objeto JSON.

    A estrutura do JSON deve ser a seguinte:
    {json_structure}

    INSTRUÇÕES CRÍTICAS: {instructions}

    TEXTO EXTRAÍDO DA IMAGEM (OCR):
    {ocr_text}
    {logos_context}
    {search_context}

    Retorne APENAS o objeto JSON, sem nenhum texto adicional.
    """
    return prompt


def _normalize_category(category: str) -> str:
    if not category:
        return "Outros"
    category = category.lower().strip()
    category_mapping = {"alimento": "Alimentos", "bebida": "Bebidas", "limpeza": "Limpeza", "higiene": "Higiene",
                        "eletrônico": "Eletrônicos", "vestuário": "Vestuário", "automotivo": "Automotivo", "construção": "Construção"}
    for key, value in category_mapping.items():
        if key in category:
            return value
    return "Outros"
