# backend/app/services/product_service.py
import logging
import re
import sqlite3
from typing import Dict, List, Optional

from app.services.cosmos_service import fetch_product_by_gtin
from app.services.vision_service import clean_text
# Importar para verificar se a chave existe
from app.core.config import COSMOS_API_KEY

logger = logging.getLogger(__name__)

EXCLUSION_WORDS = [
    'ingredientes', 'contém', 'glúten', 'lactose', 'informação', 'nutricional',
    'validade', 'fabricado', 'lote', 'peso', 'líquido', 'neto', 'indústria',
    'brasileira', 'conservar', 'agite', 'usar', 'manter', 'ambiente', 'não',
    'congelar', 'valor', 'energético', 'diário', 'valores', 'referência',
    'produto', 'registro', 'ms', 'sac', 'consumidor', 'embalagem'
]

CATEGORY_KEYWORDS = {
    'Alimentos': ['biscoito', 'bolacha', 'wafer', 'chocolate', 'snack', 'doce', 'bombom', 'recheado', 'brigadeiro'],
    'Bebidas': ['refrigerante', 'suco', 'água', 'cerveja', 'vinho', 'energético', 'refresco'],
    'Limpeza': ['sabão', 'detergente', 'amaciante', 'água sanitária', 'desinfetante', 'limpeza'],
    'Higiene': ['shampoo', 'sabonete', 'pasta dental', 'desodorante', 'higiene'],
    'Laticínios': ['leite', 'queijo', 'iogurte', 'manteiga', 'requeijão', 'laticínio'],
    'Padaria': ['pão', 'bolo', 'rosquinha', 'croissant', 'bisnaga'],
    'Carnes': ['carne', 'frango', 'peixe', 'bovina', 'suína', 'aves']
}
# Mapeamento de palavras-chave para as categorias que existem no seu frontend
CATEGORY_MAPPING = {
    "Alimentos": ['alimento', 'comida', 'arroz', 'feijão', 'macarrão', 'biscoito', 'bolacha', 'wafer', 'chocolate', 'mercearia', 'padaria', 'laticínio', 'carne', 'sêmola'],
    "Bebidas": ['bebida', 'refrigerante', 'suco', 'água', 'cerveja', 'vinho'],
    "Limpeza": ['limpeza', 'sabão', 'detergente', 'amaciante'],
    "Higiene": ['higiene', 'shampoo', 'sabonete', 'dental'],
    "Eletrônicos": ['eletrônico', 'celular', 'tv', 'eletrodoméstico']
}


def _map_category(raw_category: Optional[str]) -> Optional[str]:
    """Mapeia uma string de categoria bruta para uma das categorias do frontend."""
    if not raw_category:
        return None  # Se não houver categoria, não retorna nada

    raw_category_lower = raw_category.lower()

    # Procura por palavras-chave para encontrar a categoria correspondente
    for canonical_category, keywords in CATEGORY_MAPPING.items():
        if any(keyword in raw_category_lower for keyword in keywords):
            return canonical_category

    # Se não encontrar nenhuma correspondência, retorna "Outros" como padrão
    return "Outros"

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


def _is_valid_gtin13(gtin: str) -> bool:
    """Valida o dígito verificador do GTIN-13."""
    if len(gtin) != 13 or not gtin.isdigit():
        return False

    total = 0
    for i, digit in enumerate(gtin[:-1]):
        num = int(digit)
        total += num * (3 if i % 2 == 0 else 1)

    check_digit = (10 - (total % 10)) % 10
    return check_digit == int(gtin[-1])


def _extract_product_name(text: str, gtin: str = None) -> str:
    """Extrai o nome do produto do texto, removendo o GTIN e informações irrelevantes."""
    if gtin:
        # Remove o GTIN do texto
        text = text.replace(gtin, '')

    lines = [line.strip() for line in text.split('\n') if line.strip()]

    # Remove linhas com palavras de exclusão
    filtered_lines = []
    for line in lines:
        if not any(excl_word in line.lower() for excl_word in EXCLUSION_WORDS):
            if len(line) > 5 and re.search(r'[a-zA-Z]', line):
                filtered_lines.append(line)

    if filtered_lines:
        # Retorna a linha mais longa (provavelmente o nome do produto)
        return max(filtered_lines, key=len)

    return "Produto não identificado"


def _infer_category(text: str) -> str:
    """Infere a categoria do produto com base no texto."""
    text_lower = text.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(keyword in text_lower for keyword in keywords):
            return category
    return ""


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

    # Pega a linha mais longa e que contém letras como o candidato a título.
    clean_lines = [line for line in text_for_analysis.split(
        '\n') if len(line) > 5 and re.search('[a-zA-Z]', line)]
    if clean_lines:
        result['title'] = max(clean_lines, key=len)

    # Inferir categoria
    result['category'] = _infer_category(text)

    return result


def intelligent_text_analysis(text: str, detected_gtin: Optional[str], detected_logos: List[str], db: sqlite3.Connection) -> Dict:
    """
    Executa o pipeline de análise inteligente em cascata.
    Prioridade: 1º GTIN (Cache Local -> API Externa), 2º Inferência (Logo -> Heurísticas).
    """

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

        # 1.2: Se não está no cache, verificar se podemos buscar na API externa (Cosmos)
        if COSMOS_API_KEY:  # Só tenta Cosmos se a chave estiver configurada
            logger.info(f"Consultando API Cosmos para GTIN: {detected_gtin}")
            cosmos_data = fetch_product_by_gtin(detected_gtin)

            if cosmos_data and cosmos_data.get("description"):
                raw_category_from_cosmos = cosmos_data.get("category", "")
                mapped_category = _map_category(raw_category_from_cosmos)
                # CORREÇÃO: cosmos_data já vem formatado corretamente como strings
                parsed_data = {
                    "gtin": detected_gtin,
                    "title": cosmos_data.get("description", ""),
                    "brand": cosmos_data.get("brand", ""),
                    "category": mapped_category,  # <-- Use a categoria mapeada
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
                    logger.error(
                        f"Erro ao salvar produto do Cosmos no DB: {e}")
                return parsed_data
            else:
                logger.warning("API Cosmos não retornou dados válidos")
        else:
            logger.warning(
                "Chave da API Cosmos não configurada. Pulando consulta.")

    # ETAPA 2: INFERÊNCIA INTELIGENTE (SE O GTIN FALHOU OU COSMOS NÃO RETORNOU DADOS)
    logger.info(
        "Prioridade 2: GTIN não validado ou Cosmos sem dados. Partindo para a inferência por logo e texto.")

    brand_from_logo = detected_logos[0] if detected_logos else None

    # Usa a função auxiliar para inferir dados a partir do texto e do logo.
    inferred_data = _infer_data_from_text(text, brand_from_logo)

    # Se não conseguiu inferir um título, tenta extrair o nome do produto
    if not inferred_data.get('title'):
        inferred_data['title'] = _extract_product_name(text, detected_gtin)

    # Se não conseguiu inferir uma categoria, tenta inferir novamente
     # 1. Primeiro, tentamos inferir a categoria "bruta" a partir do texto
    raw_category_inferred = None
    if not inferred_data.get('category'):
        raw_category_inferred = _infer_category(text)
    else:
        raw_category_inferred = inferred_data.get('category')

    # 2. Agora, passamos a categoria bruta pela nossa função de mapeamento
    mapped_category = _map_category(raw_category_inferred)

    result = {
        'gtin': detected_gtin or "",
        'title': inferred_data.get('title', 'Produto não identificado'),
        'brand': inferred_data.get('brand', ''),
        'category': mapped_category,  # <-- AQUI usamos a categoria já mapeada e limpa
        'ncm': "",
        'cest': "",
        'confidence': 0.80 if brand_from_logo else 0.60,
        'detected_patterns': ['logo_detection' if brand_from_logo else 'text_heuristic']
    }

    # Limpeza final dos resultados inferidos
    if result['title']:
        result['title'] = clean_text(result['title'])
    if result['brand']:
        result['brand'] = clean_text(result['brand'])

    logger.info(f"Resultado da inferência: {result}")
    return result
# --- FIM DO ARQUIVO product_service.py ---
