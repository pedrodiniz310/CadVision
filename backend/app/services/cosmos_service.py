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


def fetch_product_by_gtin(gtin: str) -> Optional[Dict]:
    """
    Busca os dados de um produto na API do Cosmos usando o GTIN.
    Retorna os dados já formatados para nosso uso.
    """
    if not COSMOS_API_KEY:
        logger.error("❌ Chave da API Cosmos não configurada no arquivo .env")
        logger.error(
            "⚠️  Adicione COSMOS_API_KEY=sua_chave_aqui no arquivo backend/.env")
        return None

    url = f"{BASE_URL}/gtins/{gtin}.json"
    headers = {
        "X-Cosmos-Token": COSMOS_API_KEY,
        "Content-Type": "application/json",
        "User-Agent": "CadVisionApp/1.0"
    }

    try:
        logger.info(f"🌐 Consultando Cosmos API: {url}")
        logger.info(
            f"🔑 Usando chave: {COSMOS_API_KEY[:10]}...{COSMOS_API_KEY[-5:]}")

        response = requests.get(url, headers=headers, timeout=15)
        logger.info(f"📊 Status Code: {response.status_code}")

        if response.status_code == 200:
            product_data = response.json()
            logger.info(f"✅ Resposta da Cosmos: {product_data}")

            # Extrai dados usando a função auxiliar
            description = extract_value(product_data, "description")
            brand = extract_value(product_data, "brand", "name")
            category = extract_value(product_data, "category")
            ncm = extract_value(product_data, "ncm", "code")
            cest = extract_value(product_data, "cest", "code")

            result = {
                "description": description,
                "brand": brand,
                "category": category,
                "ncm": ncm,
                "cest": cest
            }

            logger.info(f"📦 Dados formatados: {result}")
            return result

        elif response.status_code == 404:
            logger.warning(
                f"❌ GTIN {gtin} não encontrado na base de dados do Cosmos")
            return None

        elif response.status_code in [401, 403]:
            logger.error(
                f"🔒 Erro de autenticação: Status {response.status_code}")
            logger.error(
                "⚠️  Verifique se a COSMOS_API_KEY está correta no arquivo .env")
            return None

        else:
            logger.error(f"⚠️  Erro inesperado: Status {response.status_code}")
            logger.error(f"📄 Resposta: {response.text}")
            return None

    except requests.exceptions.Timeout:
        logger.error("⏰ Timeout ao consultar a API Cosmos")
        return None
    except requests.exceptions.ConnectionError:
        logger.error("🌐 Erro de conexão - verifique sua internet")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"⚠️  Erro na requisição: {e}")
        return None
    except Exception as e:
        logger.error(f"❌ Erro inesperado: {e}")
        return None

    # Em backend/app/services/cosmos_service.py

# ... (função fetch_product_by_gtin existente) ...


# --- CÓDIGO ALTERADO ---
def search_product_by_description(query: str, brand: Optional[str] = None) -> Optional[Dict]:
    """
    Busca produtos na API do Cosmos de forma inteligente.
    1. Tenta uma busca específica (marca + título).
    2. Se falhar, tenta uma busca mais ampla (só título).
    3. Usa fuzzy matching para encontrar o melhor resultado na lista retornada.
    """
    if not COSMOS_API_KEY:
        logger.error("❌ Chave da API Cosmos não configurada.")
        return None

    # --- Lógica de busca em funil ---
    search_queries = []
    if brand:
        # 1. Busca específica primeiro
        search_queries.append(f"{brand} {query}")
    # 2. Busca mais genérica como fallback
    search_queries.append(query)

    search_results = None
    for sq in search_queries:
        logger.info(f"🌐 Tentando busca no Cosmos com a query: '{sq}'")
        try:
            response = requests.get(
                f"{BASE_URL}/products",
                headers={"X-Cosmos-Token": COSMOS_API_KEY,
                         "User-Agent": "CadVisionApp/1.0"},
                params={"query": sq.strip()},
                timeout=15
            )
            if response.status_code == 200 and response.json():
                search_results = response.json()
                logger.info(
                    f"✅ Cosmos retornou {len(search_results)} resultado(s) para a busca.")
                break  # Encontramos resultados, podemos parar de tentar outras queries
        except requests.exceptions.RequestException as e:
            logger.error(f"⚠️ Erro na requisição de busca do Cosmos: {e}")
            return None

    if not search_results:
        logger.warning(f"Nenhuma das buscas retornou resultados no Cosmos.")
        return None

    # --- Lógica de seleção com Fuzzy Matching ---
    # Extrai as descrições dos resultados para comparar
    descriptions = [p.get("description", "") for p in search_results]

    # Usa fuzzy matching para encontrar a descrição mais parecida com nossa query original
    # O `scorer` pode ser ajustado. `fuzz.WRatio` é bom para strings de tamanhos diferentes.
    best_match = fuzzy_process.extractOne(query, descriptions)

    # best_match é uma tupla (descrição, score)
    if not best_match or best_match[1] < 75:
        logger.warning(
            f"Nenhum resultado com score de similaridade aceitável (>75). Melhor tentativa: '{best_match[0]}' com score {best_match[1]}.")
        return None

    logger.info(
        f"🎯 Melhor correspondência encontrada: '{best_match[0]}' (Score: {best_match[1]})")

    # Encontra o objeto completo do produto correspondente à melhor descrição
    best_product_data = next(
        (p for p in search_results if p.get("description") == best_match[0]), None)

    if best_product_data and best_product_data.get("gtin"):
        # Finalmente, busca os detalhes completos usando o GTIN do melhor resultado
        return fetch_product_by_gtin(str(best_product_data["gtin"]))

    return None
