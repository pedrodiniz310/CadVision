# backend/app/services/advanced_inference_service.py

import logging
import json
import re
from typing import Dict, Any, List, Optional
from datetime import datetime

import google.generativeai as genai
from google.generativeai.types import GenerationConfig

from app.core.config import GEMINI_API_KEY
from app.core.logging_config import log_structured_event
from app.utils import validate_gtin

# Configuração de logging
logger = logging.getLogger(__name__)

# Configuração segura da API
if not GEMINI_API_KEY:
    logger.error(
        "A chave GEMINI_API_KEY não foi encontrada! O serviço de IA não funcionará.")
    raise RuntimeError("GEMINI_API_KEY não está configurada no ambiente.")

genai.configure(api_key=GEMINI_API_KEY)

# Cache de modelo para melhor performance
_MODEL_CACHE = None


def get_model() -> Optional[genai.GenerativeModel]:
    """
    Retorna o modelo de IA, utilizando cache e com tratamento de erro na inicialização.
    """
    global _MODEL_CACHE
    if _MODEL_CACHE is None:
        try:
            logger.info(
                "Inicializando o modelo GenerativeModel (gemini-1.5-pro-latest)...")
            _MODEL_CACHE = genai.GenerativeModel('gemini-1.5-pro-latest')
            logger.info("Modelo GenerativeModel inicializado com sucesso.")
        except Exception as e:
            logger.critical(
                f"Falha CRÍTICA ao inicializar o modelo do Google AI: {e}", exc_info=True)
            return None
    return _MODEL_CACHE


# --- PROMPT OTIMIZADO V2.1 (COM CHAVES ESCAPADAS) ---
PROMPT_SUPERMERCADO_V2 = """
Você é um especialista em catalogação de produtos para varejo, treinado para extrair e inferir informações de textos de embalagens com a máxima precisão.
Sua missão é analisar o texto de uma etiqueta de produto (OCR) e retornar um JSON estritamente formatado.

--- ESTRUTURA JSON OBRIGATÓRIA ---
A resposta DEVE conter TODOS os campos abaixo. Se um valor não puder ser determinado, use `null`.
{{
    "title": "string | null",
    "brand": "string | null",
    "department": "string | null",
    "category": "string | null",
    "subcategory": "string | null",
    "gtin": "string | null",
    "ncm": "string | null"
}}

--- REGRAS CRÍTICAS ---
1.  **JSON ESTRITO:** Sua saída DEVE ser APENAS o código JSON válido. NÃO inclua texto explicativo antes ou depois, nem use marcadores de markdown como ```json.
2.  **INFERÊNCIA OBRIGATÓRIA:** Se o GTIN ou NCM não estiverem explícitos no texto, use o nome e a marca do produto para inferir os códigos mais prováveis. É crucial que estes campos sejam preenchidos.
3.  **HIERARQUIA DE CATEGORIA:** Siga uma estrutura lógica. Exemplo: `department: "Mercearia"`, `category: "Massas"`, `subcategory: "Macarrão Instantâneo"`.
4.  **NÃO OMITA CHAVES:** Todas as chaves da estrutura JSON devem estar presentes na resposta, mesmo que o valor seja `null`.

--- EXEMPLOS ---

## Exemplo 1:
Texto OCR: "ARROZ TIO JOÃO 5KG TIPO 1 7896006700139 NCM 1006.30.21"
Sua Saída:
{{
    "title": "Arroz Tipo 1 5kg",
    "brand": "Tio João",
    "department": "Mercearia",
    "category": "Grãos e Cereais",
    "subcategory": "Arroz Branco",
    "gtin": "7896006700139",
    "ncm": "1006.30.21"
}}

## Exemplo 2:
Texto OCR: "Fini Gelatinas Beijos Morango"
Sua Saída:
{{
    "title": "Gelatinas Beijos Sabor Morango",
    "brand": "Fini",
    "department": "Mercearia",
    "category": "Doces e Sobremesas",
    "subcategory": "Balas e Gomas",
    "gtin": "7898591450538",
    "ncm": "1704.90.90"
}}

## Exemplo 3:
Texto OCR: "LIMP VIDROS BRILHO MAX"
Sua Saída:
{{
    "title": "Limpa Vidros Brilho Max",
    "brand": null,
    "department": "Limpeza",
    "category": "Limpadores Multiuso",
    "subcategory": "Limpa Vidros",
    "gtin": null,
    "ncm": "3402.50.00"
}}

--- DADOS PARA ANÁLISE ---
Texto OCR: "{ocr_text}"
Logos Detectados: "{logos}"
"""

# Configurações de segurança para evitar bloqueios desnecessários da API
SAFETY_SETTINGS = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
]


def _parse_ai_response(response_text: str) -> Dict[str, Any]:
    """
    Parse robusto da resposta da IA, limpando possíveis textos extras e marcadores.
    """
    try:
        # Remove marcadores de código e espaços extras
        cleaned_text = re.sub(r'```json\s*|\s*```', '', response_text).strip()
        # Encontra o JSON principal na string (começa com '{' e termina com '}')
        match = re.search(r'\{.*\}', cleaned_text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        logger.warning(
            f"Nenhum JSON válido encontrado na resposta da IA. Resposta: {response_text[:300]}")
        return {}
    except (json.JSONDecodeError, AttributeError) as e:
        logger.error(
            f"Falha ao parsear JSON da IA: {e}. Resposta: {response_text[:300]}")
        return {}


def run_advanced_inference(vision_data: Dict, search_results: List[Dict], vertical: str) -> Dict:
    """
    Orquestra a inferência de dados do produto usando um prompt otimizado e tratamento de erros robusto.
    """
    start_time = datetime.now()
    log_structured_event("advanced_inference", "processing_started", {
                         "vertical": vertical})

    if vertical != 'supermercado':
        logger.warning(
            f"Vertical '{vertical}' não possui um prompt otimizado. Usando fallback.")
        return {"base_data": {}, "attributes": {}}

    ocr_text = vision_data.get('raw_text', '')
    logos = [logo['description']
             for logo in vision_data.get('detected_logos', [])]

    prompt = PROMPT_SUPERMERCADO_V2.format(
        ocr_text=ocr_text, logos=", ".join(logos))

    try:
        model = get_model()
        if not model:
            raise RuntimeError("Modelo de IA não pôde ser inicializado.")

        # Geração de conteúdo com configurações de segurança
        generation_config = GenerationConfig(temperature=0.1)
        response = model.generate_content(
            prompt,
            generation_config=generation_config,
            safety_settings=SAFETY_SETTINGS
        )

        extracted_data = _parse_ai_response(response.text)

        if not extracted_data:
            raise ValueError(
                "A IA retornou uma resposta vazia ou mal formatada.")

        # --- Bloco de segurança e limpeza para garantir a qualidade dos dados ---
        title = extracted_data.get("title")
        brand = extracted_data.get("brand")
        gtin = extracted_data.get("gtin")
        ncm = extracted_data.get("ncm")

        base_data = {
            'title': str(title).strip().title() if title else "Produto Não Identificado",
            'brand': str(brand).strip().title() if brand else None,
            'department': extracted_data.get("department"),
            'category': extracted_data.get("category"),
            'subcategory': extracted_data.get("subcategory"),
            'gtin': str(gtin) if gtin else None,
            'ncm': str(ncm) if ncm else None,
            'confidence': 0.85,  # Confiança base para inferência bem-sucedida
            'vertical': vertical
        }

        # O CEST não faz parte do prompt principal, pode ser adicionado por outra estratégia
        attributes = {'cest': None}
        processing_time = (datetime.now() - start_time).total_seconds()

        log_structured_event("advanced_inference", "processing_completed", {
            "title": base_data['title'],
            "gtin": base_data['gtin'],
            "processing_time": round(processing_time, 2)
        })

        return {"base_data": base_data, "attributes": attributes}

    except Exception as e:
        processing_time = (datetime.now() - start_time).total_seconds()
        log_structured_event("advanced_inference", "processing_failed", {
            "error": str(e), "processing_time": round(processing_time, 2)
        }, "ERROR")

        # Retorna uma estrutura vazia para permitir que o orquestrador tente outra estratégia
        return {"base_data": {}, "attributes": {}}


def extract_gtin_from_context(title: str, search_results: List[Dict]) -> Dict:
    """
    Função de RAG (Retrieval-Augmented Generation) para extrair um GTIN de resultados de busca.
    Serve como uma estratégia de fallback no orquestrador.
    """
    if not search_results or not title:
        return {"gtin": None}

    try:
        context = "\n".join(
            [f"Título: {res.get('title', '')}, Snippet: {res.get('snippet', '')}" for res in search_results[:3]])
        prompt = f"""
        Baseado no contexto de busca abaixo, encontre o código GTIN-13 mais provável para o produto "{title}".

        Contexto:
        {context}

        Responda APENAS com um JSON no formato: {{"gtin": "1234567890123"}} ou {{"gtin": null}}
        """
        model = get_model()
        if not model:
            raise RuntimeError(
                "Modelo de IA não pôde ser inicializado para RAG.")

        response = model.generate_content(
            prompt, safety_settings=SAFETY_SETTINGS)

        data = _parse_ai_response(response.text)
        found_gtin = data.get("gtin")

        if found_gtin and validate_gtin(str(found_gtin)):
            return {"gtin": str(found_gtin)}

        return {"gtin": None}
    except Exception as e:
        logger.error(f"Erro na extração de GTIN do contexto RAG: {e}")
        return {"gtin": None}
