## IMAGEM ENVIADA
     |
     v
## [ETAPA 1: EXTRAÇÃO BRUTA - Google Vision]
     |--> a- Extrai TODO o TEXTO (OCR)
     |--> b- Extrai LOGOS detectados
     |
     v
## [ETAPA 2: A CASCATA DE VALIDAÇÃO]
     |
     +--> 2.1 Tenta encontrar um GTIN (Código de Barras) no TEXTO.
     |      |
     |      +--> Se encontrou GTIN? SIM -> [ETAPA 3: A FONTE DA VERDADE]
     |      |
     |      +--> Se encontrou GTIN? NÃO -> [ETAPA 4: A INFERÊNCIA INTELIGENTE]
     |
     v
## [ETAPA 5: RESULTADO CONSOLIDADO]


Estrutura Proposta:

/cadvision_app/
|
├── backend/
|   ├── app/
|   |   ├── __init__.py
|   |   ├── main.py             # Apenas a definição do FastAPI e as rotas (Endpoints)
|   |   ├── database.py         # Funções de conexão com o banco (get_db, init_db)
|   |   ├── models.py           # Modelos Pydantic (SaveIn, ProductOut)
|   |   ├── services/
|   |   |   ├── __init__.py
|   |   |   ├── vision_service.py   # Lógica do Google Vision e OpenCV
|   |   |   └── product_service.py  # Lógica de análise, Cosmos, regras de negócio
|   |   └── core/
|   |       ├── __init__.py
|   |       └── config.py           # Carregamento de variáveis de ambiente (API Keys)
|   |
|   ├── venv/                   # Seu ambiente virtual
|   ├── .env                    # Suas chaves de API secretas
|   └── requirements.txt        # Dependências do Python
|
├── frontend/
|   ├── index.html
|   ├── assets/
|   |   ├── css/
|   |   |   └── style.css
|   |   ├── js/
|   |   |   └── script.js
|   |   └── images/
|   |       └── logo.png
|
└── .gitignore                  # Arquivo .gitignore principal