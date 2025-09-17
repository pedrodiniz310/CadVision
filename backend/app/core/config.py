# Arquivo: backend/app/core/config.py

import os
from pathlib import Path
from dotenv import load_dotenv

# --- Definição de Caminhos Base ---

# 1. Pega o caminho do diretório onde este arquivo (config.py) está.
# Ex: C:/.../cadvision_app/backend/app/core
CORE_DIR = Path(__file__).resolve().parent

# 2. Pega o caminho do diretório da aplicação ('app')
APP_DIR = CORE_DIR.parent

# 3. Pega o caminho do diretório raiz do backend ('backend')
BACKEND_DIR = APP_DIR.parent

# 4. Carrega o arquivo .env que está na raiz do backend
# Isso garante que ele encontre o .env mesmo quando rodamos de subpastas
env_path = BACKEND_DIR / ".env"
load_dotenv(dotenv_path=env_path)


# --- Variáveis de Configuração Lidas do Ambiente ---

# Lê a chave da API do Cosmos do arquivo .env
COSMOS_API_KEY = os.environ.get("COSMOS_API_KEY")

# Constrói os caminhos para os arquivos usando o pathlib, a partir da raiz do backend
GOOGLE_KEY_PATH = BACKEND_DIR / "keys" / "vision.json"
DB_PATH = BACKEND_DIR / os.environ.get("DB_PATH", "cadvision.db")

# --- Configurações Fixas da Aplicação ---
PROJECT_NAME = "CadVision API"
API_V1_STR = "/api/v1"