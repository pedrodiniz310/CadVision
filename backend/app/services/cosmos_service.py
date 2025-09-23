# backend/app/services/cosmos_service.py

import requests
import logging
from typing import Optional, Dict
from thefuzz import process as fuzzy_process
from app.core.config import COSMOS_API_KEY

logger = logging.getLogger(__name__)
BASE_URL = "https://api.cosmos.bluesoft.com.br"


def extract_value(data, key, subkey=None):
    """
    Extrai valores de forma segura de dicionários, garantindo sempre retornar strings.
    """
    value = data.get(key, {})

    if isinstance(value, dict) and subkey:
        result = value.get(subkey, "")
        return str(result) if result is not None else ""
    elif isinstance(value, str):
        return value
    else:
        return str(value) if value is not None else ""


# Em backend/app/services/cosmos_service.py

# Em backend/app/services/cosmos_service.py

def fetch_product_by_gtin(gtin: str) -> Optional[Dict]:
    """
    Busca dados de um produto no Cosmos e retorna no formato padronizado.
    """
    if not COSMOS_API_KEY:
        logger.error("Chave da API Cosmos não configurada.")
        return None

    url = f"{BASE_URL}/gtins/{gtin}.json"
    headers = {"X-Cosmos-Token": COSMOS_API_KEY,
               "User-Agent": "CadVisionApp/1.0"}

    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
            product_data = response.json()
            # --- LÓGICA DE FALLBACK DO TÍTULO ADICIONADA ---
            title = product_data.get("description", "").strip()
            brand_name = product_data.get("brand", {}).get("name", "").strip()
            if not title and brand_name:
                title = f"{brand_name} - Produto GTIN {gtin}"
            elif not title:
                title = f"Produto GTIN {gtin}"
            # --- FIM DA LÓGICA DE FALLBACK ---

            category_obj = product_data.get("category", {})
            category_name = category_obj.get(
                "description", "") if isinstance(category_obj, dict) else ""

            base_data = {
                "gtin": gtin,
                "title": title,  # <-- Usar a variável 'title' com fallback
                "brand": brand_name,
                "category": category_name,
                "ncm": product_data.get("ncm", {}).get("code", ""),
                "cest": product_data.get("cest", {}).get("code", ""),
                "confidence": 0.99,
                "vertical": "supermercado"
            }

            logger.info(f"📦 Dados formatados do Cosmos: {base_data}")
            return {"base_data": base_data, "attributes": {}}

        # ... (resto do tratamento de erros)
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Erro na requisição ao Cosmos: {e}")
        return None

    # Em backend/app/services/cosmos_service.py
