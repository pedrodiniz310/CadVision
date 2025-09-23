# backend/app/services/product_service.py
import logging
import sqlite3
from typing import Dict, Optional, Any, List
from datetime import datetime
from app.services.cosmos_service import fetch_product_by_gtin
from app.services.search_service import search_web_for_product
from app.services.advanced_inference_service import run_advanced_inference, extract_gtin_from_context
from app.services.vector_search_service import get_image_embedding, find_match_in_vector_search
from app.services.vision_service import extract_vision_data, validate_gtin
from app.database import get_product_by_id
from app.core.logging_config import log_structured_event

logger = logging.getLogger(__name__)

# Mapeamento expandido e consistente com advanced_inference_service
CATEGORY_MAPPING = {
    "Alimentos": ['alimento', 'comida', 'mercearia', 'grãos', 'laticínio', 'carne', 'arroz', 'feijão'],
    "Bebidas": ['bebida', 'refrigerante', 'suco', 'água', 'cerveja', 'vinho', 'refresco'],
    "Limpeza": ['limpeza', 'sabão', 'detergente', 'amaciante', 'desinfetante', 'sabonete', 'limpador'],
    "Higiene": ['higiene', 'pessoal', 'cosmético', 'shampoo', 'condicionador', 'pasta dental'],
    "Eletrônicos": ['eletrônico', 'eletrodoméstico', 'celular', 'tv', 'smartphone', 'notebook'],
    "Vestuário": ['vestuário', 'vestuario', 'roupa', 'camisa', 'calça', 'bermuda', 'camiseta', 'blusa'],
    "Automotivo": ['automotivo', 'carro', 'óleo', 'pneu', 'motor'],
    "Construção": ['construção', 'construcao', 'ferramenta', 'tijolo', 'cimento']
}


class ProductAnalysisPipeline:
    """Pipeline otimizado para análise de produtos com fallbacks hierárquicos."""

    def __init__(self, db_connection: sqlite3.Connection):
        self.db = db_connection
        self.analysis_start_time = datetime.now()

    def analyze_product(self, vision_data: Dict, product_image_bytes: Optional[bytes], vertical: str) -> Dict[str, Any]:
        """
        Executa o pipeline completo de análise de produto com estratégias hierárquicas.
        """
        log_structured_event("product_analysis", "pipeline_started", {
            "vertical": vertical,
            "has_image": product_image_bytes is not None,
            "has_gtin": vision_data.get('gtin') is not None
        })

        try:
            # Estratégia 1: Busca Visual (apenas para vestuário)
            if vertical == 'vestuario' and product_image_bytes:
                result = self._try_visual_search(
                    vision_data, product_image_bytes)
                if result and result.get('confidence', 0) > 0.7:
                    log_structured_event("product_analysis", "visual_search_success", {
                        "sku": result.get('sku'),
                        "confidence": result.get('confidence')
                    })
                    return self._finalize_result(result, vision_data, "visual_search")

            # Estratégia 2: Via Rápida GTIN (não vestuário)
            if vertical != 'vestuario' and vision_data.get('gtin'):
                result = self._try_gtin_fast_lane(vision_data['gtin'])
                if result:
                    log_structured_event("product_analysis", "gtin_fast_lane_success", {
                        "gtin": vision_data['gtin']
                    })
                    return self._finalize_result(result, vision_data, "gtin_fast_lane")

            # Estratégia 3: Inferência Avançada
            result = self._run_advanced_inference(vision_data, vertical)
            if not result.get('base_data'):
                raise ValueError("Inferência avançada retornou dados vazios")

            # Estratégia 4: Enriquecimento com RAG
            enriched_result = self._enrich_with_rag(
                result, vision_data, vertical)

            return self._finalize_result(enriched_result, vision_data, "ai_inference")

        except Exception as e:
            log_structured_event("product_analysis", "pipeline_failed", {
                "error": str(e),
                "vertical": vertical
            }, "ERROR")
            return self._create_emergency_fallback(vision_data, vertical)

    def _try_visual_search(self, vision_data: Dict, product_image_bytes: bytes) -> Optional[Dict]:
        """Tenta busca visual com Vector Search para vestuário."""
        try:
            embedding = get_image_embedding(product_image_bytes)
            if not embedding:
                return None

            visual_match = find_match_in_vector_search(embedding)
            if not visual_match:
                return None

            product_sku = visual_match.get("product_id")
            if not product_sku:
                return None

            product_data = get_product_by_id(
                product_sku, self.db, find_by_sku=True)
            if product_data:
                product_data['confidence'] = visual_match.get(
                    'confidence', 0.8)
                return product_data

        except Exception as e:
            log_structured_event("visual_search", "search_failed", {
                "error": str(e)
            }, "WARNING")

        return None

    def _try_gtin_fast_lane(self, gtin: str) -> Optional[Dict]:
        """Tenta recuperação rápida via GTIN do Cosmos."""
        if not validate_gtin(gtin):
            log_structured_event("gtin_fast_lane", "invalid_gtin", {
                "gtin": gtin
            }, "WARNING")
            return None

        try:
            cosmos_data = fetch_product_by_gtin(gtin)
            if cosmos_data and cosmos_data.get("base_data"):
                return cosmos_data
        except Exception as e:
            log_structured_event("gtin_fast_lane", "cosmos_error", {
                "gtin": gtin,
                "error": str(e)
            }, "ERROR")

        return None

    def _run_advanced_inference(self, vision_data: Dict, vertical: str) -> Dict:
        """Executa inferência avançada com fallback robusto."""
        try:
            # Usa resultados de busca apenas se o OCR for insuficiente
            search_results = []
            ocr_text = vision_data.get('raw_text', '')
            if len(ocr_text) < 50:  # OCR muito curto, busca por contexto
                search_query = self._generate_search_query(vision_data)
                if search_query:
                    search_results = search_web_for_product(search_query)

            return run_advanced_inference(vision_data, search_results, vertical)

        except Exception as e:
            log_structured_event("advanced_inference", "inference_failed", {
                "error": str(e)
            }, "ERROR")
            return {"base_data": {}, "attributes": {}}

    def _enrich_with_rag(self, current_result: Dict, vision_data: Dict, vertical: str) -> Dict:
        """Enriquece resultados com busca na web quando necessário."""
        base_data = current_result.get("base_data", {})

        # Apenas busca se não temos GTIN e temos informações básicas
        if base_data.get('gtin') or not base_data.get('title') or not base_data.get('brand'):
            return current_result

        try:
            search_query = self._generate_rag_query(base_data, vertical)
            search_results = search_web_for_product(search_query)

            if search_results:
                gtin_data = extract_gtin_from_context(
                    base_data['title'], search_results)
                found_gtin = gtin_data.get('gtin')

                if found_gtin and validate_gtin(found_gtin):
                    cosmos_data = fetch_product_by_gtin(found_gtin)
                    if cosmos_data and cosmos_data.get("base_data"):
                        log_structured_event("rag_enrichment", "enrichment_success", {
                            "original_title": base_data.get('title'),
                            "found_gtin": found_gtin
                        })
                        # Mescla dados, priorizando os do Cosmos
                        base_data.update(cosmos_data["base_data"])
                        current_result["base_data"] = base_data

        except Exception as e:
            log_structured_event("rag_enrichment", "enrichment_failed", {
                "error": str(e)
            }, "WARNING")

        return current_result

    def _generate_search_query(self, vision_data: Dict) -> Optional[str]:
        """Gera query de busca baseada nos dados da visão."""
        ocr_text = vision_data.get('raw_text', '')
        if not ocr_text:
            return None

        # Extrai palavras-chave do OCR (primeiras palavras significativas)
        words = [word for word in ocr_text.split() if len(word) > 3][:5]
        return ' '.join(words) if words else None

    def _generate_rag_query(self, base_data: Dict, vertical: str) -> str:
        """Gera query otimizada para enriquecimento RAG."""
        brand = base_data.get('brand', '')
        title = base_data.get('title', '')

        if vertical == 'vestuario':
            return f"{brand} {title} EAN código"
        else:
            return f"{brand} {title} GTIN NCM"

    def _finalize_result(self, result: Dict, vision_data: Dict, source: str) -> Dict:
        """Aplica pós-processamento final e metadados."""
        # Extrai base_data se estiver aninhado
        base_data = result.get("base_data", result)
        attributes = result.get("attributes", {})

        # Aplica validação e limpeza
        processed_data = self._post_process_and_validate_data(
            base_data, vision_data)

        # Adiciona metadados
        processing_time = (
            datetime.now() - self.analysis_start_time).total_seconds()

        final_result = {
            "base_data": processed_data,
            "attributes": attributes,
            "metadata": {
                "source": source,
                "processing_time_seconds": round(processing_time, 2),
                "processed_at": datetime.now().isoformat(),
                "confidence": processed_data.get('confidence', 0.5)
            }
        }

        log_structured_event("product_analysis", "pipeline_completed", {
            "source": source,
            "processing_time": processing_time,
            "final_title": processed_data.get('title'),
            "final_confidence": processed_data.get('confidence')
        })

        return final_result

    def _post_process_and_validate_data(self, data: Dict, vision_data: Dict) -> Dict:
        """Versão otimizada do pós-processamento."""
        # Limpeza básica de campos textuais
        text_fields = ['title', 'brand',
                       'department', 'category', 'subcategory']
        for field in text_fields:
            if data.get(field) and isinstance(data[field], str):
                data[field] = data[field].strip().title()

        # Fallback inteligente para título
        if not data.get('title') or data['title'] == 'Produto Não Identificado':
            data['title'] = self._generate_fallback_title(data, vision_data)

        # Prioridade para preço da visão
        vision_price = vision_data.get('price')
        if vision_price is not None:
            data['price'] = vision_price

        # Normalização de categoria
        data['category'] = self._normalize_category(data.get('category'))

        # Ajuste de confiança baseado na qualidade dos dados
        data['confidence'] = self._calculate_data_confidence(data, vision_data)

        return data

    def _generate_fallback_title(self, data: Dict, vision_data: Dict) -> str:
        """Gera título fallback inteligente."""
        # Tenta usar brand + category
        brand = data.get('brand')
        category = data.get('category')
        if brand and category:
            return f"{brand} {category}"

        # Fallback para OCR
        ocr_text = vision_data.get('raw_text', '')
        if ocr_text:
            words = [word for word in ocr_text.split() if len(word) > 2][:4]
            if words:
                return f"Produto {' '.join(words)}"

        return f"Produto Não Identificado - {datetime.now().strftime('%H:%M:%S')}"

    def _normalize_category(self, category_name: Optional[str]) -> str:
        """Normaliza categoria com mapeamento consistente."""
        if not category_name:
            return "Outros"

        category_lower = category_name.lower()
        for canonical_name, keywords in CATEGORY_MAPPING.items():
            if any(keyword in category_lower for keyword in keywords):
                return canonical_name

        return category_name.strip().title()

    def _calculate_data_confidence(self, data: Dict, vision_data: Dict) -> float:
        """Calcula confiança baseada na qualidade e completude dos dados."""
        base_confidence = 0.5
        score_factors = 0.0

        # Fatores positivos
        if data.get('gtin'):
            score_factors += 0.3
        if data.get('title') and data['title'] != 'Produto Não Identificado':
            score_factors += 0.2
        if data.get('brand'):
            score_factors += 0.15
        if data.get('category') and data['category'] != 'Outros':
            score_factors += 0.1

        # Fatores negativos
        if len(vision_data.get('raw_text', '')) < 20:
            score_factors -= 0.2

        final_confidence = min(0.95, base_confidence + score_factors)
        return round(final_confidence, 2)

    def _create_emergency_fallback(self, vision_data: Dict, vertical: str) -> Dict:
        """Cria fallback de emergência para falhas críticas."""
        fallback_title = self._generate_fallback_title({}, vision_data)

        base_data = {
            'sku': None,
            'gtin': None,
            'title': fallback_title,
            'brand': None,
            'department': None,
            'category': "Outros",
            'subcategory': None,
            'price': vision_data.get('price'),
            'confidence': 0.1,
            'vertical': vertical
        }

        attributes = {}
        if vertical == 'vestuario':
            attributes = {'size': None, 'color': None,
                          'fabric': None, 'gender': None}
        else:
            attributes = {'ncm': None, 'cest': None}

        return {
            "base_data": base_data,
            "attributes": attributes,
            "metadata": {
                "source": "emergency_fallback",
                "processing_time_seconds": (datetime.now() - self.analysis_start_time).total_seconds(),
                "processed_at": datetime.now().isoformat(),
                "confidence": 0.1
            }
        }

# Função de compatibilidade para manter a interface existente


def intelligent_text_analysis(vision_data: Dict, product_image_bytes: Optional[bytes],
                              db: sqlite3.Connection, vertical: str) -> Dict:
    """
    Função wrapper para manter compatibilidade com código existente.
    """
    pipeline = ProductAnalysisPipeline(db)
    return pipeline.analyze_product(vision_data, product_image_bytes, vertical)
