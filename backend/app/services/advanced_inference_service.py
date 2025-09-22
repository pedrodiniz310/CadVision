from app.core.config import GEMINI_API_KEY
import google.generativeai as genai
import json
import re
from typing import Dict, Any, List
import logging

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
        'gtin': extracted_data.get("gtin"),
        'title': extracted_data.get("title"),
        'brand': extracted_data.get("brand"),
        'category': _normalize_category(extracted_data.get("category")),
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

def extract_product_info(ocr_text: str, detected_logos: List[str], search_results: List[Dict], vertical: str) -> Dict[str, Any]:
    """
    Extrai informações estruturadas de produto do texto usando Gemini API.
    """
    try:
        prompt = _build_llm_prompt(
            ocr_text, detected_logos, search_results, vertical)

        model = genai.GenerativeModel('gemini-1.5-pro-latest')
        response = model.generate_content(prompt)
        response_text = response.text.strip()
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)

        if json_match:
            json_str = json_match.group()
            return json.loads(json_str)
        else:
            # Fallback para caso a resposta seja um JSON limpo
            return json.loads(response_text)

    except Exception as e:
        logger.error(f"Erro ao extrair informações do produto: {e}")
        return {"title": "Produto não identificado"}


# =============================================================================
# === FUNÇÕES AUXILIARES (HELPERS) ============================================
# =============================================================================

def _build_llm_prompt(ocr_text: str, detected_logos: List[str], search_results: List[Dict], vertical: str) -> str:
    """
    Cria o prompt estruturado para ser enviado ao LLM, adaptado para a vertical do produto.
    """
    # --- INÍCIO DA CORREÇÃO ---
    # Formata os resultados de busca para adicionar contexto ao prompt
    search_context = ""
    if search_results:
        search_context = "\nCONTEXTO ADICIONAL DE BUSCA NA WEB:\n"
        for i, res in enumerate(search_results, 1):
            title = res.get('title', 'N/A')
            snippet = res.get('snippet', 'N/A')
            search_context += f"{i}. {title}: {snippet}\n"
    # --- FIM DA CORREÇÃO ---

    logos_context = ""
    if detected_logos:
        logos_context = f"\nLOGO DETECTADAS: {', '.join(detected_logos)}"

    # Parte dinâmica do prompt
    json_structure = ""
    instructions = ""

    if vertical == 'vestuario':
        json_structure = """
    - "title": nome completo do produto (ex: "Camisa Polo Masculina", "Tênis de Corrida Nike Revolution 6").
    - "brand": marca do produto (ex: "Lacoste", "Nike").
    - "category": "Vestuário".
    - "size": tamanho da peça (ex: "P", "M", "G", "42").
    - "color": cor principal da peça (ex: "Azul Marinho", "Branco").
    - "fabric": tecido ou material principal (ex: "Algodão Piquet", "Poliéster").
    - "gender": gênero (ex: "Masculino", "Feminino", "Unissex").
    - "gtin": código GTIN/EAN de 13 dígitos, se visível.
    - "price": preço do produto, se visível.
    """
        instructions = "Foque em extrair atributos de vestuário como tamanho, cor, tecido e gênero."
    else:  # Default para 'supermercado'
        json_structure = """
    - "title": nome completo do produto, incluindo peso/volume (ex: "Arroz Integral Tipo 1 1kg").
    - "brand": marca do produto (ex: "Tio João").
    - "category": categoria principal (ex: "Alimentos", "Bebidas").
    - "gtin": código GTIN/EAN de 13 dígitos, se visível.
    - "ncm": código NCM no formato 9999.99.99, se visível.
    - "cest": código CEST no formato 99.999.99, se visível.
    - "price": preço do produto, se visível.
    """
        instructions = "Foque em extrair atributos de supermercado como peso/volume, NCM e CEST."

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