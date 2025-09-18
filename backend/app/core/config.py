# backend/app/core/config.py
import os
import logging
from pathlib import Path
from dotenv import load_dotenv

# Configuração de logging
logger = logging.getLogger(__name__)

# Definição de Caminhos Base
# Ajuste para a estrutura correta: C:\Users\Pedro Diniz\Documents\CadVision\CadVision_app\backend
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

# Carrega o arquivo .env
env_path = BACKEND_DIR / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
    logger.info(f"Arquivo .env carregado: {env_path}")
else:
    logger.warning(f"Arquivo .env não encontrado: {env_path}")

# Variáveis de Configuração
COSMOS_API_KEY = os.environ.get("COSMOS_API_KEY")

# Verifica se a chave da API Cosmos está configurada
if not COSMOS_API_KEY:
    logger.warning("COSMOS_API_KEY não encontrada no ambiente")
else:
    logger.info("COSMOS_API_KEY configurada corretamente")

# Caminhos para arquivos
GOOGLE_KEY_PATH = BACKEND_DIR / "keys" / "vision.json"
DB_PATH = BACKEND_DIR / "cadvision.db"

# Garante que o diretório do banco de dados existe
DB_PATH.parent.mkdir(exist_ok=True, parents=True)

# Garante que o diretório de chaves existe
GOOGLE_KEY_PATH.parent.mkdir(exist_ok=True, parents=True)

# Verifica se o arquivo de chave do Google Vision existe
if not GOOGLE_KEY_PATH.exists():
    logger.warning(
        f"Arquivo de chave Google Vision não encontrado: {GOOGLE_KEY_PATH}")
else:
    logger.info(
        f"Arquivo de chave Google Vision encontrado: {GOOGLE_KEY_PATH}")

# Configurações Fixas
PROJECT_NAME = "CadVision API"
API_V1_STR = "/api/v1"

# Log das configurações carregadas
logger.info(f"BACKEND_DIR: {BACKEND_DIR}")
logger.info(f"DB_PATH: {DB_PATH}")
logger.info(f"GOOGLE_KEY_PATH: {GOOGLE_KEY_PATH}")