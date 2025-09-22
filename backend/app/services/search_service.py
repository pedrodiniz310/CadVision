# backend/app/services/search_service.py
import requests
import logging
import os
from typing import List, Dict

# Carregue as variáveis de ambiente (ajuste o caminho se necessário)
from app.core.config import GOOGLE_SEARCH_API_KEY, GOOGLE_SEARCH_ENGINE_ID

logger = logging.getLogger(__name__)
SEARCH_URL = "https://www.googleapis.com/customsearch/v1"

def search_web_for_product(query: str) -> List[Dict]:
    """
    Realiza uma busca na web usando a Google Custom Search API.
    Retorna uma lista de dicionários contendo título e snippet dos resultados.
    """
    if not GOOGLE_SEARCH_API_KEY or not GOOGLE_SEARCH_ENGINE_ID:
        logger.warning("API de busca do Google não configurada. Etapa de busca pulada.")
        return []

    params = {
        'key': GOOGLE_SEARCH_API_KEY,
        'cx': GOOGLE_SEARCH_ENGINE_ID,
        'q': query,
        'num': 3  # Os 3 primeiros resultados são suficientes
    }

    try:
        logger.info(f"Buscando na web com a query: '{query}'")
        response = requests.get(SEARCH_URL, params=params, timeout=10)
        response.raise_for_status()
        results = response.json()

        if "items" not in results:
            return []

        # Retorna apenas o título e o snippet, que é o que precisamos
        return [{"title": item.get("title"), "snippet": item.get("snippet")}
                for item in results.get("items", [])]

    except requests.exceptions.RequestException as e:
        logger.error(f"Erro na chamada da API de busca: {e}")
        return []