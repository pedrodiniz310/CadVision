import google.generativeai as genai
import json
import re
from typing import Dict, Any, List
import logging

# Configurar logging
logger = logging.getLogger(__name__)

# Configure sua API key (deve vir de variáveis de ambiente)
genai.configure(api_key="AIzaSyBiDFX_nDBI37XxATZR9idVLO1cd1iRibE")


# =============================================================================
# === FUNÇÕES PRINCIPAIS (PONTOS DE ENTRADA DO SERVIÇO) =======================
# =============================================================================

def run_advanced_inference(vision_data: Dict, search_results: List[Dict]) -> Dict:
    """
    Orquestra o processo de inferência inicial para extrair dados da imagem.
    É o ponto de entrada principal para a identificação via IA.
    """
    ocr_text = vision_data.get('raw_text', '')
    logos = [logo['description']
             for logo in vision_data.get('detected_logos', [])]

    # Chama a função de extração principal
    extracted_data = extract_product_info(ocr_text, logos, search_results)

    # Valida o GTIN retornado pela IA para garantir que tenha um comprimento válido.
    validated_gtin = extracted_data.get("gtin", "")
    if validated_gtin and isinstance(validated_gtin, str):
        numeric_gtin = re.sub(r'\D', '', validated_gtin)
        if len(numeric_gtin) not in [8, 12, 13, 14]:
            logger.warning(
                f"GTIN inválido retornado pela IA: '{validated_gtin}'. Descartando.")
            validated_gtin = ""  # ou None

    # Formata os dados para o padrão do sistema
    final_product_data = {
        'gtin': validated_gtin,
        'title': extracted_data.get("title", ""),
        'brand': extracted_data.get("brand", ""),
        'category': _normalize_category(extracted_data.get("category", "")),
        'ncm': extracted_data.get("ncm", ""),
        'cest': extracted_data.get("cest", ""),
        'price': extracted_data.get("price") or vision_data.get('price'),
        'confidence': 0.95,
        'detected_patterns': ['generative_ai_inference']
    }

    return final_product_data


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
            # Validação final para garantir que é um GTIN válido
            if gtin and isinstance(gtin, str) and len(re.sub(r'\D', '', gtin)) == 13:
                return {"gtin": re.sub(r'\D', '', gtin)}

        return {"gtin": None}
    except Exception as e:
        logger.error(f"Erro ao extrair GTIN do contexto com a IA: {e}")
        return {"gtin": None}


# =============================================================================
# === FUNÇÕES DE LÓGICA INTERNA ===============================================
# =============================================================================

def extract_product_info(ocr_text: str, detected_logos: List[str], search_results: List[Dict]) -> Dict[str, Any]:
    """
    Extrai informações estruturadas de produto do texto usando Gemini API.
    (Chamada por run_advanced_inference)
    """
    try:
        # Construir prompt
        prompt = _build_llm_prompt(ocr_text, detected_logos, search_results)

        # Configuração do modelo
        model = genai.GenerativeModel('gemini-1.5-pro-latest')

        # Geração de conteúdo
        response = model.generate_content(prompt)

        # Extração do JSON da resposta
        response_text = response.text.strip()

        # Remove possíveis markdown ou código delimitadores
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if json_match:
            json_str = json_match.group()
            product_data = json.loads(json_str)
        else:
            # Fallback: tenta parsear todo o texto como JSON
            product_data = json.loads(response_text)

        return product_data

    except Exception as e:
        logger.error(f"Erro ao extrair informações do produto: {e}")
        # Retorna estrutura vazia em caso de erro
        return {
            "gtin": None,
            "title": "Produto não identificado",
            "brand": None,
            "category": None,
            "ncm": None,
            "cest": None,
            "price": None
        }


# =============================================================================
# === FUNÇÕES AUXILIARES (HELPERS) ============================================
# =============================================================================

def _build_llm_prompt(ocr_text: str, detected_logos: List[str], search_results: List[Dict]) -> str:
    """
    Cria o prompt estruturado para ser enviado ao LLM.
    (Chamada por extract_product_info)
    """
    # Formatar resultados de busca
    search_context = ""
    if search_results:
        search_context = "\nCONTEXTO ADICIONAL DE BUSCA:\n"
        for i, res in enumerate(search_results, 1):
            title = res.get('source_title', 'N/A')
            snippet = res.get('snippet', 'N/A')
            search_context += f"{i}. {title}: {snippet}\n"

    # Formatar logos detectadas
    logos_context = ""
    if detected_logos:
        logos_context = f"\nLOGO DETECTADAS: {', '.join(detected_logos)}"

    prompt = f"""
    Você é um especialista em processamento de dados de produtos. Sua tarefa é analisar o texto extraído de uma imagem de produto e retornar APENAS um objeto JSON com as seguintes chaves:

    - gtin: código GTIN/EAN encontrado (string ou null)
    - title: nome completo e descritivo do produto (string)
    - brand: marca do produto (string ou null)
    - category: categoria do produto (string ou null)
    - ncm: código NCM encontrado (string ou null)
    - cest: código CEST encontrado (string ou null)
    - price: preço do produto (número float ou null)

    INSTRUÇÕES CRÍTICAS:
    1. Para o 'title', use o nome mais completo e descritivo possível, incluindo variações, sabor e volume/peso (ex: "Refrigerante Coca-Cola Sem Açúcar Lata 350ml" ou "Sabão em Pó Omo Lavagem Perfeita Caixa 1.6kg"). Este detalhe é fundamental.
    2. Para a marca, identifique claramente o fabricante.
    3. Extraia o GTIN/EAN (código de barras) se estiver visível no texto.
    4. Para categoria, use uma das opções: "Alimentos", "Bebidas", "Limpeza", "Higiene", "Eletrônicos", "Vestuário", "Automotivo", "Construção" ou "Outros".
    5. Extraia o NCM e o CEST se estiverem presentes.

    TEXTO EXTRAÍDO DA IMAGEM (OCR):
    {ocr_text}
    {logos_context}
    {search_context}

    Retorne APENAS o objeto JSON, sem nenhum texto adicional, comentários ou markdown.
    """

    return prompt


def _normalize_category(category: str) -> str:
    """
    Normaliza a categoria para um conjunto padrão de valores.
    """
    if not category:
        return None

    category = category.lower().strip()

    category_mapping = {
        "alimento": "Alimentos",
        "bebida": "Bebidas",
        "limpeza": "Limpeza",
        "higiene": "Higiene",
        "eletrônico": "Eletrônicos",
        "eletronicos": "Eletrônicos",
        "vestuário": "Vestuário",
        "vestuario": "Vestuário",
        "automotivo": "Automotivo",
        "construção": "Construção",
        "construcao": "Construção"
    }

    for key, value in category_mapping.items():
        if key in category:
            return value

    return "Outros"


# =============================================================================
# === FUNÇÕES DEPRECATED/LEGACY (Manter por compatibilidade se necessário) ====
# =============================================================================

def process_product_data(vision_data, cosmos_data):
    """
    Processa dados de visão computacional e Cosmos para criar estrutura padronizada.
    (Esta função parece ser de uma lógica anterior e pode não ser mais usada no fluxo principal)
    """
    # Se temos dados do Cosmos, priorizamos eles
    if cosmos_data:
        return {
            "gtin": cosmos_data.get("gtin"),
            "title": cosmos_data.get("description"),
            "brand": cosmos_data.get("brand"),
            "category": _normalize_category(cosmos_data.get("category")),
            "ncm": cosmos_data.get("ncm"),
            "cest": cosmos_data.get("cest"),
            "price": vision_data.get('price')
        }

    # Caso contrário, usamos a inferência do Gemini
    return run_advanced_inference(vision_data, [])
