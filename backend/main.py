# backend/main.py
import logging
import sqlite3
import time
import csv
import io
from pathlib import Path
from typing import List, Optional
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile, Query, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.encoders import jsonable_encoder

# Correção das importações - adicione IdentifiedProduct
from app.models import ProductCreate, ProductOut, PaginatedResponse, IdentificationResult, APIResponse, ProcessingStats, IdentifiedProduct
from app.database import get_db, init_db, insert_product, log_processing, get_processing_stats, delete_product_by_id
#
from app.database import find_product_by_image_hash
from app.database import delete_product_by_id, get_all_products
from app.services.vision_service import extract_vision_data, get_cache_key
from app.services.product_service import intelligent_text_analysis
from app.services.cosmos_service import fetch_product_by_gtin

# --- CONFIGURAÇÃO DE LOGGING ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("app.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# --- LIFECYCLE DA APLICAÇÃO ---


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gerencia o ciclo de vida da aplicação."""
    # Startup
    logger.info("Iniciando aplicação CadVision API")
    init_db()
    logger.info("Banco de dados inicializado")

    yield

    # Shutdown
    logger.info("Encerrando aplicação CadVision API")

app = FastAPI(
    title="CadVision API",
    description="API para o sistema de cadastro de produtos por visão computacional.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# --- MIDDLEWARES ---
# Configuração completa do CORS
app.add_middleware(
    CORSMiddleware,
    # Permite todas as origens (apenas para desenvolvimento)
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
)

# Middleware de compressão
app.add_middleware(GZipMiddleware, minimum_size=1000)

# --- ENDPOINTS (ROTAS) DA API ---
API_PREFIX = "/api/v1"


# Em backend/main.py

@app.post(
    f"{API_PREFIX}/vision/identify",
    response_model=IdentificationResult,
    summary="Identifica um produto a partir de uma imagem",
    tags=["Visão Computacional"]
)
async def identify_image(
    background_tasks: BackgroundTasks,
    image: UploadFile = File(...,
                             description="Imagem do produto para identificação"),
    db: sqlite3.Connection = Depends(get_db)
):
    """
    Recebe uma imagem, orquestra a extração de dados (OCR + Logo) e a análise
    inteligente para retornar informações estruturadas do produto.
    """
    start_time = time.time()

    # Validações iniciais
    if not image.content_type.startswith('image/'):
        raise HTTPException(
            status_code=400,
            detail="Tipo de arquivo inválido. Envie uma imagem (JPEG, PNG, WebP, BMP, GIF)."
        )

    try:
        image_bytes = await image.read()
    except Exception as e:
        logger.error(f"Erro ao ler imagem: {str(e)}")
        raise HTTPException(
            status_code=400,
            detail="Erro ao processar o arquivo de imagem."
        )

    if len(image_bytes) > 10 * 1024 * 1024:  # 10MB
        raise HTTPException(
            status_code=400,
            detail="Imagem muito grande. Tamanho máximo permitido: 10MB."
        )

    if not image_bytes:
        raise HTTPException(
            status_code=400,
            detail="Imagem vazia ou corrompida."
        )

    image_hash = get_cache_key(image_bytes)

    # --- Lógica de Detecção de Duplicata ---
    product_from_hash = find_product_by_image_hash(image_hash, db)
    if product_from_hash:
        logger.info(f"Imagem duplicada encontrada para o hash: {image_hash}")

        identified_product = IdentifiedProduct(**product_from_hash)

        return IdentificationResult(
            success=True,
            status="duplicate_found",
            product=identified_product,
            image_hash=image_hash,
            # Garante que a confiança seja um float, com 1.0 como fallback para duplicatas
            confidence=identified_product.confidence or 1.0,
            processing_time=0.01
        )

    try:
        # 1. Chama o serviço do Vision se não for duplicata
        vision_data = extract_vision_data(image_bytes)
        raw_text = vision_data.get('raw_text', '')
        detected_logos = [logo['description']
                          for logo in vision_data.get('detected_logos', [])]
        gtin_from_vision = vision_data.get('gtin')
        success = vision_data.get('success', False)

        processing_time = time.time() - start_time

        logger.info(
            f"Dados extraídos - GTIN: {gtin_from_vision}, Texto: {len(raw_text)} chars, "
            f"Logos: {detected_logos}, Sucesso: {success}, "
            f"Tempo: {processing_time:.2f}s"
        )

        # 2. Se a extração falhou
        if not success:
            background_tasks.add_task(
                log_processing,
                image_hash, processing_time, False, 0.0,
                "Falha na extração de dados da imagem"
            )
            return IdentificationResult(
                success=False,
                status="failed",
                product=None,
                image_hash=image_hash,
                raw_text=raw_text,
                detected_logos=detected_logos,
                confidence=0.0,
                processing_time=processing_time,
                error_message="Não foi possível extrair dados suficientes da imagem."
            )

        # 3. Chama o serviço de produto para análise inteligente
        product_info = intelligent_text_analysis(
            raw_text, gtin_from_vision, detected_logos, db)

        # 4. Converte para o modelo IdentifiedProduct
        identified_product = IdentifiedProduct(
            gtin=product_info.get('gtin'),
            title=product_info.get('title', 'Produto não identificado'),
            brand=product_info.get('brand'),
            category=product_info.get('category'),
            price=product_info.get('price'),
            ncm=product_info.get('ncm'),
            cest=product_info.get('cest'),
            # O modelo permite None aqui
            confidence=product_info.get('confidence')
        )

        # --- CORREÇÃO AQUI ---
        # Garante que o valor de 'confidence' seja um float (0.0 se for None)
        # antes de passar para o IdentificationResult, que é mais restrito.
        final_confidence = product_info.get('confidence') or 0.0

        # 5. Prepara e retorna a resposta de sucesso
        background_tasks.add_task(
            log_processing,
            image_hash, processing_time, True, final_confidence, None
        )

        return IdentificationResult(
            success=True,
            status="newly_identified",
            product=identified_product,
            image_hash=image_hash,
            raw_text=raw_text,
            detected_logos=detected_logos,
            confidence=final_confidence,  # Usa a variável corrigida
            processing_time=processing_time
        )

    except Exception as e:
        processing_time = time.time() - start_time
        logger.error(f"Erro interno no processamento: {str(e)}", exc_info=True)
        background_tasks.add_task(
            log_processing,
            image_hash, processing_time, False, 0.0, str(e)
        )
        raise HTTPException(
            status_code=500,
            detail=f"Erro interno no processamento da imagem: {str(e)}"
        )


@app.post(
    f"{API_PREFIX}/products",
    response_model=APIResponse,
    summary="Salva um novo produto",
    status_code=201,
    tags=["Produtos"]
)
async def save_product(
    product: ProductCreate,
    db: sqlite3.Connection = Depends(get_db)
):
    """
    Salva os dados de um produto no banco de dados.
    """
    try:
        # Cria um dicionário com os dados do produto
        product_data = {
            'gtin': product.gtin,
            'title': product.title,
            'brand': product.brand,
            'category': product.category,
            'price': product.price,
            'ncm': product.ncm,
            'cest': product.cest,
            'confidence': product.confidence,
            'image_hash': product.image_hash  # Ajuste conforme necessário
        }

        # Passa os dados e a conexão 'db' para a função
        product_id = insert_product(product_data, db=db)

        if product_id:
            return APIResponse.success_response(
                data={"id": product_id},
                message="Produto salvo com sucesso"
            )
        else:
            raise HTTPException(
                status_code=500,
                detail="Erro ao salvar o produto no banco de dados"
            )

    except sqlite3.IntegrityError:
        raise HTTPException(
            status_code=409,
            detail=f"Produto com GTIN {product.gtin} já existe."
        )
    except Exception as e:
        logger.error(f"Erro ao salvar produto: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Erro interno ao salvar o produto."
        )


@app.get(
    f"{API_PREFIX}/products",
    response_model=PaginatedResponse,
    summary="Lista produtos cadastrados",
    tags=["Produtos"]
)
async def get_products(
    db: sqlite3.Connection = Depends(get_db),
    page: int = Query(1, ge=1, description="Número da página"),
    size: int = Query(20, ge=1, le=100, description="Tamanho da página"),
    category: Optional[str] = Query(None, description="Filtrar por categoria"),
    brand: Optional[str] = Query(None, description="Filtrar por marca")
):
    """
    Retorna uma lista paginada de produtos do banco de dados, 
    dos mais recentes para os mais antigos.
    """
    try:
        # Calcula offset
        offset = (page - 1) * size

        # Constrói query base
        query = "SELECT * FROM products WHERE 1=1"
        count_query = "SELECT COUNT(*) as total FROM products WHERE 1=1"
        params = []

        # Adiciona filtros
        if category:
            query += " AND category = ?"
            count_query += " AND category = ?"
            params.append(category)

        if brand:
            query += " AND brand = ?"
            count_query += " AND brand = ?"
            params.append(brand)

        # Ordenação e paginação
        query += " ORDER BY id DESC LIMIT ? OFFSET ?"
        params.extend([size, offset])

        # Executa contagem total
        total_result = db.execute(
            count_query, params[:-2] if len(params) > 2 else []).fetchone()
        total = total_result['total'] if total_result else 0

        # Executa query principal
        products = db.execute(query, params).fetchall()
        products_list = [dict(p) for p in products]

        # Calcula total de páginas
        pages = (total + size - 1) // size

        return PaginatedResponse(
            items=products_list,
            total=total,
            page=page,
            pages=pages,
            size=size
        )

    except Exception as e:
        logger.error(f"Erro ao buscar produtos: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Erro interno ao buscar produtos."
        )


@app.get(
    f"{API_PREFIX}/stats/processing",
    response_model=ProcessingStats,
    summary="Estatísticas de processamento",
    tags=["Estatísticas"]
)
async def get_processing_stats_route(db: sqlite3.Connection = Depends(get_db)):
    """
    Retorna estatísticas sobre o processamento de imagens.
    """
    try:
        stats = get_processing_stats()
        return stats
    except Exception as e:
        logger.error(f"Erro ao buscar estatísticas: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Erro interno ao buscar estatísticas."
        )


@app.get(
    f"{API_PREFIX}/health",
    summary="Health Check",
    tags=["Sistema"]
)
async def health_check():
    """
    Endpoint para verificar o status da API.
    """
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "version": "1.0.0"
    }

# Adicione esta linha para inicializar o banco de dados na inicialização

# --- SERVIR O FRONTEND ---
# Define o caminho para a pasta 'frontend', que está na pasta-pai da pasta 'backend'
BACKEND_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BACKEND_DIR.parent / "frontend"

# Verifica se o diretório do frontend existe
if FRONTEND_DIR.exists() and (FRONTEND_DIR / "index.html").exists():
    # Monta o diretório de assets (css, js, images)
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIR /
              "assets"), name="assets")

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

        # Verifica se o arquivo existe e é um arquivo estático
        if file_path.exists() and file_path.is_file():
            return FileResponse(file_path)

        # Para qualquer outra rota, serve o index.html (SPA)
        return FileResponse(FRONTEND_DIR / "index.html")
else:
    logger.warning(
        "Diretório do frontend não encontrado. O servidor não irá servir o frontend.")

# --- HANDLER DE ERROS GLOBAL ---


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content=jsonable_encoder({
            "success": False,
            "message": exc.detail,
            "error_code": f"HTTP_{exc.status_code}"
        })
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    logger.error(f"Erro não tratado: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content=jsonable_encoder({
            "success": False,
            "message": "Erro interno do servidor",
            "error_code": "INTERNAL_SERVER_ERROR"
        })
    )


@app.delete(
    f"{API_PREFIX}/products/{{product_id}}",
    summary="Exclui um produto pelo ID",
    status_code=200,
    tags=["Produtos"]
)
async def delete_product(
    product_id: int,
    db: sqlite3.Connection = Depends(get_db)
):
    success = delete_product_by_id(product_id, db)
    if not success:
        raise HTTPException(
            status_code=404, detail=f"Produto com ID {product_id} não encontrado.")

    return {"success": True, "message": "Produto excluído com sucesso."}
# Em backend/main.py


@app.get(
    f"{API_PREFIX}/products/export/csv",
    summary="Exporta todos os produtos para um arquivo CSV",
    tags=["Produtos"]
)
async def export_products_csv(db: sqlite3.Connection = Depends(get_db)):
    """
    Busca todos os produtos no banco de dados e retorna um arquivo CSV para download.
    """
    stream = io.StringIO()
    writer = csv.writer(stream)

    # Cabeçalho do CSV
    headers = ["id", "gtin", "title", "brand", "category",
               "price", "ncm", "cest", "confidence", "created_at"]
    writer.writerow(headers)

    products = get_all_products(db)
    for product in products:
        # Escreve uma linha para cada produto
        writer.writerow([product.get(h) for h in headers])

    # Move o cursor para o início do "arquivo" em memória
    stream.seek(0)

    response = StreamingResponse(iter([stream.read()]), media_type="text/csv")
    response.headers["Content-Disposition"] = "attachment; filename=cadvision_products.csv"

    return response

# --- FIM DO ARQUIVO main.py ---
