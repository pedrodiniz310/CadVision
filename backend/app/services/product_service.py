# backend/app/services/product_service.py
import logging
from typing import Dict, Optional, Any, List, Tuple
from datetime import datetime
import sqlite3

from app.services.cosmos_service import fetch_product_by_gtin
from app.services.search_service import search_web_for_product
from app.services.advanced_inference_service import run_advanced_inference, extract_gtin_from_context
from app.services.vector_search_service import get_image_embedding, find_match_in_vector_search
from app.utils import validate_gtin
from app.database import get_product_by_id
from app.core.logging_config import log_structured_event

logger = logging.getLogger(__name__)


class ProductAnalysisPipeline:
    """
    Orquestrador dinâmico que seleciona a melhor estratégia de identificação
    com base nos dados disponíveis, em ordem de prioridade.
    """

    def __init__(self, db_connection: sqlite3.Connection):
        self.db = db_connection
        self.analysis_start_time = datetime.now()

    def _is_result_sufficient(self, result: Optional[Dict]) -> bool:
        """Verifica se o resultado obtido é bom o suficiente para parar."""
        if not result or not result.get("base_data"):
            return False

        base_data = result["base_data"]
        # Um bom resultado tem pelo menos um título e uma marca, ou um GTIN
        has_title_and_brand = base_data.get("title") and base_data.get("brand")
        has_gtin = base_data.get("gtin")

        return has_title_and_brand or has_gtin

    def analyze_product(self, vision_data: Dict, product_image_bytes: Optional[bytes], vertical: str) -> Dict[str, Any]:
        """
        Executa o pipeline com lógica de FUSÃO de dados para máxima precisão.
        """
        log_structured_event("product_analysis", "pipeline_started", {
                             "vertical": vertical})

        # Estratégia 1 (Principal): Sempre executa a Inferência da IA.
        # Ela nos dará uma base de dados completa, buscando na web se necessário.
        log_structured_event("product_analysis", "attempting_strategy", {
                             "strategy": "AI_INFERENCE"})
        ai_result = self._execute_ai_strategy(vision_data, [], vertical)
        ai_base_data = ai_result.get("base_data", {})

        final_result = ai_result
        successful_strategy = "AI_INFERENCE"

        # Estratégia 2 (Refinamento com Cosmos): Se a IA encontrou um GTIN, usamos o Cosmos.
        # Os dados do Cosmos são soberanos e vão sobrescrever os da IA.
        gtin_from_ai = ai_base_data.get("gtin")
        if gtin_from_ai and validate_gtin(str(gtin_from_ai)):
            log_structured_event("product_analysis", "attempting_strategy", {
                                 "strategy": "GTIN_LOOKUP"})
            cosmos_result = self._execute_gtin_strategy(str(gtin_from_ai))

            if self._is_result_sufficient(cosmos_result):
                cosmos_base_data = cosmos_result.get("base_data", {})

                # --- LÓGICA DE FUSÃO DE DADOS ---
                # Começa com os dados completos da IA.
                merged_data = ai_base_data.copy()
                # Sobrescreve com os dados do Cosmos, que são mais confiáveis.
                merged_data.update(cosmos_base_data)
                # Garante que a confiança seja a mais alta.
                merged_data['confidence'] = 0.99

                final_result = {"base_data": merged_data,
                                "attributes": cosmos_result.get("attributes", {})}
                successful_strategy = "GTIN_LOOKUP_MERGED"

        # Se nenhuma estratégia produziu um resultado mínimo, usamos o fallback.
        if not self._is_result_sufficient(final_result):
            log_structured_event("product_analysis",
                                 "all_strategies_failed", {}, "WARNING")
            final_result = self._create_emergency_fallback(
                vision_data, vertical)
            successful_strategy = "fallback"

        return self._finalize_result(final_result, vision_data, successful_strategy)
    # --- Implementação das Estratégias ---

    def _execute_gtin_strategy(self, gtin: str) -> Optional[Dict]:
        """Estratégia 1: Busca direta por GTIN."""
        cosmos_data = fetch_product_by_gtin(gtin)
        if cosmos_data:
            # O Cosmos já retorna no formato { "base_data": ..., "attributes": ... }
            return cosmos_data
        return None

    def _execute_visual_strategy(self, product_image_bytes: bytes) -> Optional[Dict]:
        """Estratégia 2: Busca por similaridade visual."""
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

            # Busca os dados completos do produto encontrado no nosso DB
            # Supondo que get_product_by_id aceite SKU
            product_data = get_product_by_id(
                product_sku, self.db, find_by_sku=True)
            if product_data:
                confidence = visual_match.get('confidence', 0.8)
                # Formata a saída para o padrão
                return {
                    "base_data": {**product_data, "confidence": confidence},
                    "attributes": product_data.get("attributes", {})
                }
        except Exception as e:
            log_structured_event("visual_search", "search_failed", {
                                 "error": str(e)}, "WARNING")
        return None

    def _execute_ai_strategy(self, vision_data: Dict, search_results: List[Dict], vertical: str) -> Dict:
        """Estratégia 3: Inferência via LLM com base no texto OCR."""
        return run_advanced_inference(vision_data, search_results, vertical)

    def _execute_rag_strategy(self, vision_data: Dict, vertical: str) -> Optional[Dict]:
        """Estratégia 4: Busca na web para encontrar um GTIN e re-executar a estratégia GTIN."""
        ocr_text = vision_data.get('raw_text', '')
        if len(ocr_text) < 20:
            return None  # Texto muito curto para uma busca útil

        # Usa os primeiros 100 caracteres do OCR para a busca
        query = f"{ocr_text[:100]} GTIN"
        search_results = search_web_for_product(query)

        if not search_results:
            return None

        # Usa a IA para tentar extrair um GTIN do contexto da busca
        context_gtin_data = extract_gtin_from_context(
            ocr_text[:100], search_results)
        found_gtin = context_gtin_data.get('gtin')

        if found_gtin and validate_gtin(found_gtin):
            # Encontramos um GTIN! Agora re-executamos a estratégia mais confiável.
            log_structured_event("rag_strategy", "gtin_found", {
                                 "gtin": found_gtin})
            return self._execute_gtin_strategy(found_gtin)

        return None

    # --- Funções de Finalização e Fallback ---

    def _finalize_result(self, result: Dict, vision_data: Dict, source: str) -> Dict:
        """Aplica limpeza final e adiciona metadados."""
        base_data = result.get("base_data", {})

        # Limpeza e padronização final
        if base_data.get('title'):
            base_data['title'] = base_data['title'].strip().title()
        if not base_data.get('title'):
            base_data['title'] = "Produto Não Identificado"

        # Adiciona metadados para tracking
        processing_time = (
            datetime.now() - self.analysis_start_time).total_seconds()
        result["metadata"] = {
            "source_strategy": source,
            "processing_time_seconds": round(processing_time, 2),
            "processed_at": datetime.now().isoformat(),
            "confidence": base_data.get('confidence', 0.5)
        }

        log_structured_event("product_analysis",
                             "pipeline_completed", result["metadata"])
        return result

    def _create_emergency_fallback(self, vision_data: Dict, vertical: str) -> Dict:
        """Cria uma resposta mínima quando todas as estratégias falham."""
        ocr_text = vision_data.get('raw_text', '')
        words = [word for word in ocr_text.split() if len(word) > 2][:4]
        fallback_title = f"Produto {' '.join(words)}" if words else "Produto Não Identificado"

        return {
            "base_data": {
                'title': fallback_title, 'brand': None, 'category': "Outros",
                'gtin': None, 'price': None, 'sku': None, 'confidence': 0.1,
                'vertical': vertical
            },
            "attributes": {}
        }


# Função wrapper para manter compatibilidade com o `main.py`
def intelligent_text_analysis(vision_data: Dict, product_image_bytes: Optional[bytes],
                              db: sqlite3.Connection, vertical: str) -> Dict:
    """
    Função wrapper para instanciar e executar o pipeline de análise.
    """
    pipeline = ProductAnalysisPipeline(db)
    return pipeline.analyze_product(vision_data, product_image_bytes, vertical)
