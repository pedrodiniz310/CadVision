# backend/main.py
import logging
import sqlite3
from pathlib import Path
from typing import List

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

# Correção das importações
from app.database import get_db, init_db
from app.models import SaveProductIn, ProductOut
from app.services.vision_service import extract_vision_data
from app.services.product_service import intelligent_text_analysis
from app.services.cosmos_service import fetch_product_by_gtin

# --- INICIALIZAÇÃO DA APLICAÇÃO ---

logger = logging.getLogger(__name__)

app = FastAPI(
    title="CadVision API",
    description="API para o sistema de cadastro de produtos por visão computacional.",
    version="1.0.0"
)

# Configuração completa do CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000",
                   "http://127.0.0.1:3000", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
)


@app.on_event("startup")
def on_startup():
    """Executa a inicialização do banco de dados quando a API inicia."""
    init_db()
    logger.info("Banco de dados inicializado")

# --- ENDPOINTS (ROTAS) DA API ---


API_PREFIX = "/api/v1"


@app.post(f"{API_PREFIX}/vision/identify", summary="Identifica um produto a partir de uma imagem")
async def identify_image(
    image: UploadFile = File(...),
    db: sqlite3.Connection = Depends(get_db)
):
    """
    Recebe uma imagem, orquestra a extração de dados (OCR + Logo) e a análise
    inteligente para retornar informações estruturadas do produto.
    """
    if not image.content_type.startswith('image/'):
        raise HTTPException(
            status_code=400, detail="Arquivo de imagem inválido")

    image_bytes = await image.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Imagem vazia")

    # 1. Chama o serviço do Vision para extrair dados brutos
    vision_data = extract_vision_data(image_bytes)
    raw_text = vision_data.get('raw_text')
    detected_logos = vision_data.get('detected_logos', [])

    if not raw_text or len(raw_text.strip()) < 10:
        if detected_logos:
            # Se não há texto mas há logo, retorna uma resposta parcial
            return JSONResponse(
                status_code=200,
                content={
                    'brand': detected_logos[0], 'title': 'Texto não detectado', 'confidence': 0.3}
            )
        raise HTTPException(
            status_code=400, detail="Não foi possível detectar texto suficiente na imagem.")

    # 2. Chama o serviço de produto para executar a cascata de confiança
    product_info = intelligent_text_analysis(raw_text, detected_logos, db)
    product_info['raw_text'] = raw_text

    return product_info


@app.post(f"{API_PREFIX}/products", summary="Salva um novo produto", status_code=201)
async def save_product(product: SaveProductIn, db: sqlite3.Connection = Depends(get_db)):
    """Salva os dados de um produto, deixando o DB gerenciar os timestamps."""
    try:
        cursor = db.cursor()

        cursor.execute("""
            INSERT INTO products 
            (gtin, title, brand, category, price, ncm, cest, confidence)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            product.gtin,
            product.title,
            product.brand,
            product.category,
            product.price,
            product.ncm,
            product.cest,
            product.confidence
        ))
        db.commit()
        return {"message": "Produto salvo com sucesso", "id": cursor.lastrowid}
    except sqlite3.IntegrityError:
        raise HTTPException(
            status_code=409, detail=f"Produto com GTIN {product.gtin} já existe.")
    except Exception as e:
        logger.error(f"Erro ao salvar produto: {e}")
        raise HTTPException(
            status_code=500, detail="Erro interno ao salvar o produto.")


@app.get(f"{API_PREFIX}/products", response_model=List[ProductOut], summary="Lista todos os produtos cadastrados")
async def get_products(db: sqlite3.Connection = Depends(get_db)):
    """Retorna uma lista de todos os produtos do banco de dados, dos mais recentes para os mais antigos."""
    products = db.execute("SELECT * FROM products ORDER BY id DESC").fetchall()
    return [dict(p) for p in products]

# --- SERVIR O FRONTEND ---

# Define o caminho para a pasta 'frontend', que está na pasta-pai da pasta 'backend'
BACKEND_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BACKEND_DIR.parent / "frontend"

# Monta o diretório de assets (css, js, images)
app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="assets")

# Serve arquivos estáticos do frontend
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

# Rota principal que serve o index.html


@app.get("/", include_in_schema=False)
async def serve_frontend():
    return FileResponse(FRONTEND_DIR / "index.html")

# Rota para servir outras páginas do frontend


@app.get("/{path:path}", include_in_schema=False)
async def serve_frontend_path(path: str):
    file_path = FRONTEND_DIR / path
    if file_path.exists():
        return FileResponse(file_path)
    return FileResponse(FRONTEND_DIR / "index.html")
