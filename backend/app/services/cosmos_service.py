# backend/app/services/cosmos_service.py

import requests
import logging
from typing import Optional, Dict

from app.core.config import COSMOS_API_KEY

logger = logging.getLogger(__name__)
BASE_URL = "https://api.cosmos.bluesoft.com.br"


def fetch_product_by_gtin(gtin: str) -> Optional[Dict]:
    """
    Busca os dados de um produto na API do Cosmos usando o GTIN.
    Retorna os dados já formatados para nosso uso.
    """
    if not COSMOS_API_KEY:
        logger.warning(
            "Chave da API Cosmos não configurada no .env. Impossível fazer a busca.")
        return None

    url = f"{BASE_URL}/gtins/{gtin}.json"
    headers = {
        "X-Cosmos-Token": COSMOS_API_KEY,
        "Content-Type": "application/json",
        "User-Agent": "CadVisionApp/1.0"
    }

    try:
        logger.info(f"Consultando GTIN {gtin} na API Cosmos...")
        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code == 200:
            product_data = response.json()
            logger.info(
                f"Sucesso! Produto '{product_data.get('description')}' encontrado.")

            # CORREÇÃO: Garantir que todos os valores são strings, não dicionários
            def extract_value(data, key, subkey=None):
                value = data.get(key, {})
                if isinstance(value, dict) and subkey:
                    return value.get(subkey, "")
                return value if isinstance(value, str) else ""

            # Retorna os dados já formatados corretamente
            return {
                "description": extract_value(product_data, "description"),
                "brand": extract_value(product_data, "brand", "name"),
                "category": extract_value(product_data, "category"),
                "ncm": extract_value(product_data, "ncm", "code"),
                "cest": extract_value(product_data, "cest", "code")
            }

        elif response.status_code == 404:
            logger.warning(
                f"GTIN {gtin} não encontrado na base de dados do Cosmos.")
            return None

        elif response.status_code in [401, 403]:
            logger.error(
                "Erro de autenticação na API Cosmos. Verifique se sua COSMOS_API_KEY está correta.")
            return None

        else:
            logger.error(
                f"Erro inesperado na API Cosmos: Status {response.status_code}")
            return None

    except requests.exceptions.RequestException as e:
        logger.error(f"Erro de conexão ao consultar a API Cosmos: {e}")
        return None


# Função auxiliar para garantir compatibilidade com o código existente
def parse_cosmos_response(data: Dict) -> Dict:
    """Formata a resposta JSON da API Cosmos para o nosso modelo de dados."""
    if not data:
        return {}

    return {
        "gtin": data.get("gtin", ""),
        "title": data.get("description", ""),
        "brand": data.get("brand", ""),
        "category": data.get("category", ""),
        "ncm": data.get("ncm", ""),
        "cest": data.get("cest", ""),
        "confidence": 0.99,
        "detected_patterns": ["gtin_api_lookup"]
    }
# --- Serviço Principal do Produto (O Cérebro) ---