# backend/app/services/product_service.py

import logging
import re
import sqlite3
from typing import Dict, List, Optional

from app.services.cosmos_service import fetch_product_by_gtin
from app.services.vision_service import clean_text

logger = logging.getLogger(__name__)

# --- Constantes de Heurística ---

EXCLUSION_WORDS = [
    'ingredientes', 'contém', 'glúten', 'lactose', 'informação', 'nutricional',
    'validade', 'fabricado', 'lote', 'peso', 'líquido', 'neto', 'indústria',
    'brasileira', 'conservar', 'agite', 'usar', 'manter', 'ambiente', 'não',
    'congelar', 'valor', 'energético', 'diário', 'valores', 'referência'
]

CATEGORY_KEYWORDS = {
    'Alimentos': ['arroz', 'feijão', 'açúcar', 'café', 'óleo', 'macarrão', 'farinha'],
    'Bebidas': ['refrigerante', 'suco', 'água', 'cerveja', 'vinho', 'energético'],
    'Limpeza': ['sabão', 'detergente', 'amaciante', 'água sanitária', 'desinfetante'],
    'Higiene': ['shampoo', 'sabonete', 'pasta dental', 'desodorante'],
    'Laticínios': ['leite', 'queijo', 'iogurte', 'manteiga', 'requeijão']
}

# --- Funções Auxiliares de Análise ---


def _find_gtin_in_text(text: str) -> Optional[str]:
    """Usa regex para encontrar um GTIN válido no texto."""
    # Prioriza GTIN-13, o mais comum no Brasil
    gtin_patterns = [r'\b(\d{13})\b', r'\b(\d{12})\b',
                     r'\b(\d{14})\b', r'\b(\d{8})\b']
    for pattern in gtin_patterns:
        matches = re.findall(pattern, text)
        if matches:
            logger.info(f"GTIN encontrado no texto: {matches[0]}")
            return matches[0]
    return None


def _infer_data_from_text(text: str, brand_from_logo: Optional[str]) -> Dict:
    """Usa heurísticas para adivinhar informações do produto quando o GTIN falha."""
    result = {'title': None, 'brand': brand_from_logo, 'category': None}

    lines = [line.strip() for line in text.split('\n') if line.strip()]
    filtered_lines = [l for l in lines if not any(
        word in l.lower() for word in EXCLUSION_WORDS)]

    text_for_analysis = "\n".join(filtered_lines)
    if result['brand']:
        # Remove a marca do texto para não confundi-la com o título.
        text_for_analysis = re.sub(
            result['brand'], '', text_for_analysis, flags=re.IGNORECASE)

    # Pega a linha mais longe e que contém letras como o candidato a título.
    clean_lines = [line for line in text_for_analysis.split(
        '\n') if len(line) > 5 and re.search('[a-zA-Z]', line)]
    if clean_lines:
        result['title'] = max(clean_lines, key=len)

    # Inferir categoria
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(keyword in text.lower() for keyword in keywords):
            result['category'] = category
            break

    return result

# --- Função Principal do Serviço (O Cérebro) ---


def intelligent_text_analysis(text: str, detected_logos: List[str], db: sqlite3.Connection) -> Dict:
    """
    Executa o pipeline de análise inteligente em cascata.
    Prioridade: 1º GTIN (Cache Local -> API Externa), 2º Inferência (Logo -> Heurísticas).
    """
    # ETAPA 1: TENTAR A "FONTE DA VERDADE" (GTIN)
    detected_gtin = _find_gtin_in_text(text)
    if detected_gtin:
        logger.info(
            f"Prioridade 1: GTIN detectado ({detected_gtin}). Iniciando validação.")

        # 1.1: Verificar cache local (nosso DB).
        cursor = db.cursor()
        cursor.execute(
            "SELECT gtin, title, brand, category, ncm, cest FROM products WHERE gtin = ?", (detected_gtin,))
        product_from_db = cursor.fetchone()

        if product_from_db:
            logger.info(
                f"Sucesso! GTIN {detected_gtin} encontrado no cache local.")
            return {"confidence": 0.99, "detected_patterns": ["gtin_db_lookup"], **dict(product_from_db)}

        # 1.2: Se não está no cache, buscar na API externa (Cosmos).
        cosmos_data = fetch_product_by_gtin(detected_gtin)
        if cosmos_data:
            # CORREÇÃO: cosmos_data já vem formatado corretamente como strings
            parsed_data = {
                "gtin": detected_gtin,
                "title": cosmos_data.get("description", ""),
                "brand": cosmos_data.get("brand", ""),
                "category": cosmos_data.get("category", ""),
                "ncm": cosmos_data.get("ncm", ""),
                "cest": cosmos_data.get("cest", ""),
                "confidence": 0.99,
                "detected_patterns": ["gtin_api_lookup"]
            }

            try:
                cursor.execute(
                    "INSERT INTO products (gtin, title, brand, category, ncm, cest, confidence) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        parsed_data['gtin'],
                        parsed_data['title'],
                        parsed_data['brand'],
                        parsed_data['category'],
                        parsed_data['ncm'],
                        parsed_data['cest'],
                        parsed_data['confidence']
                    )
                )
                db.commit()
                logger.info(
                    f"Novo produto com GTIN {detected_gtin} salvo no cache local.")
            except sqlite3.Error as e:
                logger.error(f"Erro ao salvar produto do Cosmos no DB: {e}")
            return parsed_data

    # ETAPA 2: INFERÊNCIA INTELIGENTE (SE O GTIN FALHOU)
    logger.info(
        "Prioridade 2: GTIN não validado. Partindo para a inferência por logo e texto.")

    brand_from_logo = detected_logos[0].upper() if detected_logos else None

    # Usa a função auxiliar para inferir dados a partir do texto e do logo.
    inferred_data = _infer_data_from_text(text, brand_from_logo)

    result = {
        'gtin': detected_gtin,
        'title': inferred_data.get('title'),
        'brand': inferred_data.get('brand'),
        'category': inferred_data.get('category'),
        'confidence': 0.80 if brand_from_logo else 0.60,
        'detected_patterns': ['logo_detection' if brand_from_logo else 'text_heuristic']
    }

    # Limpeza final dos resultados inferidos
    if result['title']:
        result['title'] = clean_text(result['title'])
    if result['brand']:
        result['brand'] = clean_text(result['brand'])

    return result
