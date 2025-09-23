from app.core.config import GEMINI_API_KEY
import google.generativeai as genai
import json
import re
from typing import Dict, Any, List, Optional
import logging
from app.core.logging_config import log_structured_event
from app.services.vision_service import validate_gtin
from datetime import datetime

# Configurar logging
logger = logging.getLogger(__name__)

# Configuração segura da API
if not GEMINI_API_KEY:
    logger.error(
        "GEMINI_API_KEY não encontrada! O serviço de IA não funcionará.")
    raise RuntimeError("GEMINI_API_KEY não configurada")

genai.configure(api_key=GEMINI_API_KEY)

# Cache de modelo para melhor performance
_MODEL_CACHE = None


def get_model():
    """Retorna modelo com cache para melhor performance"""
    global _MODEL_CACHE
    if _MODEL_CACHE is None:
        _MODEL_CACHE = genai.GenerativeModel('gemini-1.5-pro-latest')
    return _MODEL_CACHE


# Mapeamento expandido de categorias
CATEGORY_MAPPING = {
    # Alimentos e Bebidas
    "alimento": "Alimentos", "alimentos": "Alimentos", "comida": "Alimentos",
    "bebida": "Bebidas", "bebidas": "Bebidas", "refrigerante": "Bebidas",
    "água": "Bebidas", "suco": "Bebidas", "cerveja": "Bebidas",

    # Limpeza e Casa
    "limpeza": "Limpeza", "limpeza e casa": "Limpeza", "detergente": "Limpeza",
    "sabão": "Limpeza", "sabonete": "Limpeza", "shampoo": "Limpeza",
    "condicionador": "Limpeza", "higiene": "Higiene", "higiene pessoal": "Higiene",

    # Eletrônicos
    "eletrônico": "Eletrônicos", "eletrônicos": "Eletrônicos", "celular": "Eletrônicos",
    "smartphone": "Eletrônicos", "tablet": "Eletrônicos", "notebook": "Eletrônicos",

    # Vestuário
    "vestuário": "Vestuário", "vestuario": "Vestuário", "roupa": "Vestuário",
    "camisa": "Vestuário", "calça": "Vestuário", "bermuda": "Vestuário",
    "camiseta": "Vestuário", "blusa": "Vestuário", "jaqueta": "Vestuário",

    # Outros
    "automotivo": "Automotivo", "construção": "Construção", "ferramenta": "Construção",
    "pet": "Pet Shop", "animal": "Pet Shop", "brinquedo": "Brinquedos"
}

# Templates de prompt otimizados
PROMPT_TEMPLATES = {
    'vestuario': {
        'json_structure': '''{
    "sku": "código SKU se visível",
    "title": "nome completo do produto",
    "brand": "marca",
    "department": "Masculino/Feminino/Infantil",
    "category": "tipo de peça (Camisas, Calças, etc)",
    "subcategory": "especificação (Camisa Polo, Calça Jeans)",
    "size": "tamanho (M, G, 42)",
    "color": "cor principal",
    "fabric": "tecido/material",
    "gender": "gênero",
    "gtin": "GTIN-13 se visível",
    "price": "preço se visível"
}''',
        'instructions': '''SEJA DETALHISTA NA CATEGORIZAÇÃO. INFIRA:
- Departamento a partir do título/gênero
- Categoria/subcategoria baseado no tipo de peça
- Se não encontrar campo, retorne null
- Priorize informações do OCR sobre busca'''
    },

    'supermercado': {
        'json_structure': '''{
    "sku": "código SKU se visível",
    "title": "nome completo com peso/volume",
    "brand": "marca",
    "department": "Mercearia/Bebidas/Limpeza",
    "category": "categoria principal",
    "subcategory": "subcategoria",
    "gtin": "GTIN-13 se visível",
    "ncm": "código NCM se visível",
    "cest": "código CEST se visível",
    "price": "preço se visível"
}''',
        'instructions': '''SEJA PRECISO COM UNIDADES (kg, g, L, ml). INFIRA:
- Departamento/categoria a partir do título
- Se não encontrar campo, retorne null
- Priorize OCR sobre busca'''
    }
}


def run_advanced_inference(vision_data: Dict, search_results: List[Dict], vertical: str) -> Dict:
    """
    Orquestra inferência com validações robustas e fallback inteligente.
    """
    start_time = datetime.now()

    # Extração de dados base
    ocr_text = vision_data.get('raw_text', '')
    logos = [logo['description']
             for logo in vision_data.get('detected_logos', [])]
    vision_price = vision_data.get('price')

    # Log inicial
    log_structured_event("inference_start", "processing_started", {
        "vertical": vertical,
        "ocr_length": len(ocr_text),
        "logos_count": len(logos),
        "search_results": len(search_results)
    })

    try:
        # Extração principal
        extracted_data = extract_product_info(
            ocr_text, logos, search_results, vertical)

        # Validação robusta do GTIN
        gtin_from_ai = extracted_data.get("gtin")
        if gtin_from_ai:
            if not validate_gtin(str(gtin_from_ai)):
                logger.warning(f"GTIN inválido descartado: '{gtin_from_ai}'")
                extracted_data["gtin"] = None
            else:
                logger.info(f"GTIN válido encontrado: {gtin_from_ai}")

        # Fallback para título
        title = extracted_data.get("title", "").strip()
        if not title:
            title = _generate_fallback_title(ocr_text)
            extracted_data["title"] = title
            log_structured_event("title_fallback", "fallback_applied", {
                "generated_title": title
            })

        # Construção da resposta
        base_data = {
            'sku': extracted_data.get("sku"),
            'gtin': extracted_data.get("gtin"),
            'title': title,
            'brand': extracted_data.get("brand"),
            'department': extracted_data.get("department"),
            'category': _normalize_category(extracted_data.get("category")),
            'subcategory': extracted_data.get("subcategory"),
            'price': extracted_data.get("price") or vision_price,
            'confidence': _calculate_confidence(extracted_data, ocr_text),
            'vertical': vertical,
            'processed_at': datetime.now().isoformat()
        }

        # Atributos específicos por vertical
        attributes = _build_attributes(extracted_data, vertical)

        # Log de sucesso
        processing_time = (datetime.now() - start_time).total_seconds()
        log_structured_event("inference_success", "processing_completed", {
            "processing_time_seconds": processing_time,
            "title_extracted": base_data['title'],
            "brand_extracted": base_data['brand'],
            "has_gtin": base_data['gtin'] is not None
        })

        return {
            "base_data": base_data,
            "attributes": attributes,
            "metadata": {
                "processing_time": processing_time,
                "source": "ai_extraction"
            }
        }

    except Exception as e:
        # Fallback completo em caso de erro
        processing_time = (datetime.now() - start_time).total_seconds()
        log_structured_event("inference_error", "processing_failed", {
            "error": str(e),
            "processing_time_seconds": processing_time
        }, "ERROR")

        return _create_emergency_fallback(ocr_text, vertical, vision_price)


def extract_product_info(ocr_text: str, detected_logos: List[str],
                         search_results: List[Dict], vertical: str) -> Dict[str, Any]:
    """
    Extrai informações com tratamento robusto de erros e fallbacks.
    """
    try:
        prompt = _build_optimized_prompt(
            ocr_text, detected_logos, search_results, vertical)

        log_structured_event("ai_extraction", "prompt_generated", {
            "prompt_length": len(prompt),
            "vertical": vertical
        }, "DEBUG")

        model = get_model()
        response = model.generate_content(prompt)
        response_text = response.text.strip()

        # Parse robusto do JSON
        extracted_data = _parse_ai_response(response_text)

        log_structured_event("ai_extraction", "extraction_success", {
            "title": extracted_data.get("title"),
            "brand": extracted_data.get("brand"),
            "has_gtin": "gtin" in extracted_data
        })

        return extracted_data

    except Exception as e:
        log_structured_event("ai_extraction", "extraction_failed", {
            "error": str(e),
            "vertical": vertical
        }, "ERROR")

        return _create_fallback_response(ocr_text)


def _build_optimized_prompt(ocr_text: str, detected_logos: List[str],
                            search_results: List[Dict], vertical: str) -> str:
    """
    Constrói prompt otimizado para melhor precisão.
    """
    template = PROMPT_TEMPLATES.get(vertical, PROMPT_TEMPLATES['supermercado'])

    # Contexto de busca otimizado
    search_context = ""
    if search_results:
        search_context = "\nCONTEXTO DE BUSCA (use como referência):\n"
        # Limita a 3 resultados
        for i, res in enumerate(search_results[:3], 1):
            title = res.get('title', 'N/A')
            snippet = res.get('snippet', 'N/A')[:200]  # Limita tamanho
            search_context += f"{i}. {title}: {snippet}\n"

    # Contexto de logos
    logos_context = f"\nLOGO DETECTADAS: {', '.join(detected_logos)}" if detected_logos else ""

    return f"""
ANALISTA DE PRODUTOS - EXTRATOR DE DADOS

SUA TAREFA: Analisar texto OCR de produto {vertical.upper()} e retornar JSON estruturado.

INSTRUÇÕES:
{template['instructions']}
- Retorne APENAS JSON válido
- Use null para campos não encontrados
- Seja preciso e consistente

ESTRUTURA EXATA REQUERIDA:
{template['json_structure']}

DADOS DA IMAGEM:
OCR: {ocr_text[:2000]}  # Limita tamanho para eficiência
{logos_context}
{search_context}

RESPONDA APENAS COM O JSON:
"""


def _parse_ai_response(response_text: str) -> Dict[str, Any]:
    """
    Parse robusto da resposta da IA com múltiplas estratégias.
    """
    # Limpeza inicial
    cleaned_text = response_text.strip()

    # Estratégia 1: Busca por JSON com regex flexível
    json_match = re.search(r'\{[^{}]*\}', cleaned_text)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass  # Tenta próxima estratégia

    # Estratégia 2: Remove possíveis marcadores de código
    code_clean = re.sub(r'```json|```', '', cleaned_text)
    try:
        return json.loads(code_clean)
    except json.JSONDecodeError:
        pass

    # Estratégia 3: Fallback para criação manual
    log_structured_event("parse_strategy", "using_fallback_parse", {
        "response_preview": cleaned_text[:500]
    }, "WARNING")

    return _create_fallback_response("")


def _calculate_confidence(extracted_data: Dict, ocr_text: str) -> float:
    """
    Calcula confiança baseada na qualidade da extração.
    """
    base_confidence = 0.7
    bonuses = 0.0

    # Bônus por campos críticos
    if extracted_data.get("title") and extracted_data["title"] != "Produto Não Identificado":
        bonuses += 0.15
    if extracted_data.get("brand"):
        bonuses += 0.10
    if extracted_data.get("gtin"):
        bonuses += 0.05

    # Penalidade por OCR muito curto
    if len(ocr_text) < 20:
        bonuses -= 0.1

    return min(0.95, base_confidence + bonuses)


def _build_attributes(extracted_data: Dict, vertical: str) -> Dict:
    """Constrói atributos específicos por vertical."""
    if vertical == 'vestuario':
        return {
            'size': extracted_data.get("size"),
            'color': extracted_data.get("color"),
            'fabric': extracted_data.get("fabric"),
            'gender': extracted_data.get("gender")
        }
    else:
        return {
            'ncm': extracted_data.get("ncm"),
            'cest': extracted_data.get("cest")
        }


def _normalize_category(category: Optional[str]) -> str:
    """Normaliza categoria com mapeamento expandido."""
    if not category:
        return "Outros"

    category_lower = category.lower().strip()

    for key, value in CATEGORY_MAPPING.items():
        if key in category_lower:
            return value

    return "Outros"


def _generate_fallback_title(ocr_text: str) -> str:
    """Gera título fallback inteligente."""
    words = ocr_text.split()[:8]  # Primeiras 8 palavras
    meaningful_words = [w for w in words if len(
        w) > 2][:5]  # Palavras significativas

    if meaningful_words:
        return f"Produto {' '.join(meaningful_words)}"
    return "Produto Não Identificado"


def _create_fallback_response(ocr_text: str) -> Dict:
    """Cria resposta de fallback padronizada."""
    return {
        "title": _generate_fallback_title(ocr_text),
        "brand": "",
        "category": "Outros",
        "gtin": None,
        "price": None,
        "department": None,
        "subcategory": None,
        "sku": None
    }


def _create_emergency_fallback(ocr_text: str, vertical: str, price: Optional[float]) -> Dict:
    """Fallback de emergência para erros críticos."""
    fallback_title = _generate_fallback_title(ocr_text)

    return {
        "base_data": {
            'sku': None,
            'gtin': None,
            'title': fallback_title,
            'brand': None,
            'department': None,
            'category': "Outros",
            'subcategory': None,
            'price': price,
            'confidence': 0.3,
            'vertical': vertical,
            'processed_at': datetime.now().isoformat()
        },
        "attributes": _build_attributes({}, vertical),
        "metadata": {
            "processing_time": 0,
            "source": "emergency_fallback"
        }
    }

# Mantém função existente para compatibilidade


def extract_gtin_from_context(title: str, search_results: List[Dict]) -> Dict:
    """Versão otimizada da extração de GTIN do contexto."""
    if not search_results or not title.strip():
        return {"gtin": None}

    try:
        context = "\n".join([
            f"Resultado {i}: {res.get('title', '')} - {res.get('snippet', '')}"
            # Limita a 5 resultados
            for i, res in enumerate(search_results[:5], 1)
        ])

        prompt = f"""
        ANALISE O CONTEXTO E IDENTIFIQUE O GTIN-13 para o produto: "{title}"
        
        CONTEXTO DA BUSCA:
        {context}
        
        RETORNE APENAS: {{"gtin": "1234567890123"}} ou {{"gtin": null}}
        """

        model = get_model()
        response = model.generate_content(prompt)
        response_text = response.text.strip()

        # Extração robusta do GTIN
        json_match = re.search(r'\{[^{}]*\}', response_text)
        if json_match:
            data = json.loads(json_match.group())
            gtin = data.get("gtin")
            if gtin and re.match(r'^\d{13}$', str(gtin)):
                return {"gtin": str(gtin)}

        return {"gtin": None}

    except Exception as e:
        logger.error(f"Erro na extração de GTIN: {e}")
        return {"gtin": None}
