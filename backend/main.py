# backend/main.py

# --- Imports da Biblioteca Padrão ---
import logging
import sqlite3
import time
import io
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Optional, Union

# --- Imports de Terceiros ---
import pandas as pd
from fastapi import (
    Depends, FastAPI, File, HTTPException, UploadFile,
    Query, BackgroundTasks, Form
)
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.encoders import jsonable_encoder

# --- Imports da Aplicação Local ---
from app import models
from app import database
from app.services import vision_service, product_service
from app.core.logging_config import setup_logging, log_structured_event

# --- Configuração de Logging ---
LOG_FILE = setup_logging()
logger = logging.getLogger(__name__)

# --- Ciclo de Vida da Aplicação (Versão única e correta) ---


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gerencia eventos de inicialização e encerramento da API."""
    log_structured_event("app", "startup", {"version": "1.1.0"})
    database.init_db()
    log_structured_event("app", "database_initialized", {})
    yield
    log_structured_event("app", "shutdown", {})
    logger.info("Encerrando aplicação CadVision API.")


# --- Instância Principal do FastAPI ---
app = FastAPI(
    title="CadVision API",
    description="API para o sistema de cadastro de produtos por visão computacional.",
    version="1.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# --- Middlewares ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# --- Constantes da API ---
API_PREFIX = "/api/v1"

# =============================================================================
# === ENDPOINTS DA APLICAÇÃO ==================================================
# =============================================================================


@app.post(
    f"{API_PREFIX}/vision/identify",
    response_model=models.IdentificationResult,
    summary="Identifica um produto a partir de uma imagem",
    tags=["Visão Computacional"]
)
async def identify_image(
    background_tasks: BackgroundTasks,
    image: UploadFile = File(...,
                             description="Imagem do produto para identificação (até 10MB)"),
    vertical: str = Form(
        "supermercado", description="A vertical do produto (ex: supermercado, vestuario)"),
    db: sqlite3.Connection = Depends(database.get_db)
):
    """
    Recebe uma imagem de produto e a vertical, executa o pipeline de IA e retorna
    os dados estruturados do produto identificado.
    """
    start_time = time.time()

    log_structured_event("vision/identify", "process_started", {
        "vertical": vertical, "filename": image.filename, "content_type": image.content_type
    })

    # 1. Validação do arquivo
    if not image.content_type or not image.content_type.startswith('image/'):
        log_structured_event("vision/identify", "validation_failed", {
                             "reason": "invalid_file_type", "content_type": image.content_type}, "ERROR")
        raise HTTPException(
            status_code=400, detail="Tipo de arquivo inválido.")

    image_bytes = await image.read()
    if len(image_bytes) > 10 * 1024 * 1024:  # 10MB
        raise HTTPException(
            status_code=400, detail="Imagem excede o tamanho máximo de 10MB.")

    image_hash = vision_service.get_cache_key(image_bytes)
    log_structured_event("vision/identify", "image_loaded",
                         {"size_bytes": len(image_bytes), "hash": image_hash})

    # 2. Verificação de imagem duplicada
    product_from_hash = database.find_product_by_image_hash(image_hash, db)
    if product_from_hash:
        log_structured_event("vision/identify", "cache_hit",
                             {"image_hash": image_hash, "product_id": product_from_hash.get('id')})
        identified_product = models.IdentifiedProduct(**product_from_hash)
        return models.IdentificationResult(
            success=True,
            status="duplicate_found",
            product=identified_product,
            image_hash=image_hash,
            confidence=identified_product.confidence or 1.0,
            processing_time=round(time.time() - start_time, 2)
        )

    # 3. Extração com Vision API
    log_structured_event("vision/identify", "vision_extraction_start", {})
    vision_data = vision_service.extract_vision_data(image_bytes)
    log_structured_event("vision/identify", "vision_extraction_complete", {
        "success": vision_data.get("success"),
        "text_length": len(vision_data.get('raw_text', '')),
        "gtin_found": bool(vision_data.get('gtin'))
    })

    if not vision_data.get("success"):
        log_structured_event("vision/identify", "vision_extraction_failed",
                             {"reason": "no_readable_data"}, "ERROR")
        raise HTTPException(
            status_code=422, detail="Não foi possível extrair dados legíveis da imagem.")

    # 4. Análise inteligente
    log_structured_event(
        "vision/identify", "intelligent_analysis_start", {"vertical": vertical})
    try:
        product_info = product_service.intelligent_text_analysis(
            vision_data=vision_data, db=db, vertical=vertical)
        log_structured_event("vision/identify", "intelligent_analysis_complete", {
            "title": product_info.get('title'), "brand": product_info.get('brand')
        })
    except Exception as e:
        log_structured_event(
            "vision/identify", "intelligent_analysis_failed", {"error": str(e)}, "ERROR")
        raise HTTPException(
            status_code=500, detail="Erro na análise do produto.")

    # 5. Preparar resposta
    processing_time = round(time.time() - start_time, 2)
    identified_product = models.IdentifiedProduct(**product_info)

    background_tasks.add_task(
        database.log_processing,
        image_hash=image_hash,
        processing_time=processing_time,
        success=True,
        confidence=identified_product.confidence,
        error_message=None
    )

    log_structured_event("vision/identify", "process_completed", {
        "processing_time": processing_time, "product_title": product_info.get('title')
    })

    return models.IdentificationResult(
        success=True,
        status="newly_identified",
        product=identified_product,
        image_hash=image_hash,
        raw_text=vision_data.get('raw_text', ''),
        detected_logos=[logo.get('description')
                        for logo in vision_data.get('detected_logos', [])],
        confidence=identified_product.confidence,
        processing_time=processing_time
    )
# =============================================================================
# === ENDPOINTS DE GERENCIAMENTO DE PRODUTOS (CRUD) ===========================
# =============================================================================


@app.get(
    f"{API_PREFIX}/products",
    response_model=models.PaginatedResponse,
    summary="Lista produtos cadastrados com filtros e paginação",
    tags=["Produtos"]
)
async def get_products(
    db: sqlite3.Connection = Depends(database.get_db),
    page: int = Query(1, ge=1, description="Número da página"),
    size: int = Query(10, ge=1, le=100, description="Itens por página"),
    category: Optional[str] = Query(None, description="Filtrar por categoria"),
    brand: Optional[str] = Query(
        None, description="Filtrar por marca (busca parcial)"),
    sort: str = Query("newest", description="Critério de ordenação")
):
    """Retorna uma lista paginada de produtos com opções de filtro e ordenação."""
    # A lógica interna para esta rota já estava robusta e foi mantida.
    params = {}
    query = "SELECT * FROM products WHERE 1=1"
    if category:
        query += " AND category = :category"
        params['category'] = category
    if brand:
        query += " AND brand LIKE :brand"
        params['brand'] = f"%{brand}%"

    count_query = query.replace("SELECT *", "SELECT COUNT(*)")
    total = db.execute(count_query, params).fetchone()[0] or 0

    sort_options = {
        "newest": "ORDER BY created_at DESC", "oldest": "ORDER BY created_at ASC",
        "name": "ORDER BY title ASC", "name_desc": "ORDER BY title DESC"
    }
    order_clause = sort_options.get(sort, "ORDER BY id DESC")

    offset = (page - 1) * size
    query += f" {order_clause} LIMIT :size OFFSET :offset"
    params['size'] = size
    params['offset'] = offset

    products = [dict(p) for p in db.execute(query, params).fetchall()]

    return models.PaginatedResponse(
        items=products, total=total, page=page,
        pages=(total + size - 1) // size if size > 0 else 0,
        size=size
    )


# Em backend/main.py

# Em backend/main.py

# backend/main.py

@app.post(
    f"{API_PREFIX}/products",
    response_model=models.APIResponse,
    summary="Salva um novo produto no banco de dados",
    status_code=201,
    tags=["Produtos"]
)
async def save_product(
    product: Union[models.ProductCreateClothing, models.ProductCreateSupermarket],
    db: sqlite3.Connection = Depends(database.get_db)
):
    """Recebe os dados de um produto (de qualquer vertical) e os persiste no banco."""
    try:
        product_dict = product.dict()

        # VALIDAÇÃO MELHORADA DO TÍTULO
        title = product_dict.get('title', '').strip()
        if not title:
            # Tenta criar um título a partir de outros campos
            brand = product_dict.get('brand', '')
            category = product_dict.get('category', '')
            gtin = product_dict.get('gtin', '')

            if brand and category:
                product_dict['title'] = f"{brand} - {category}"
            elif gtin:
                product_dict['title'] = f"Produto GTIN {gtin}"
            else:
                product_dict['title'] = f"Produto {product_dict.get('vertical', 'Gerado')} - {int(time.time())}"

            logger.warning(
                f"Título estava vazio. Definido como: {product_dict['title']}")

        product_id = database.insert_product(product_dict, db)
        if product_id:
            return models.APIResponse.success_response(
                data={"id": product_id},
                message="Produto salvo com sucesso"
            )
        raise HTTPException(
            status_code=500, detail="Erro ao salvar o produto no banco de dados.")

    except sqlite3.IntegrityError:
        raise HTTPException(
            status_code=409, detail=f"Produto com GTIN {product.gtin} já existe.")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

# Em backend/main.py

# Em backend/main.py


@app.get(
    f"{API_PREFIX}/products/export",
    summary="Exporta produtos para CSV ou Excel",
    tags=["Utilitários"]
)
async def export_products(
    format: str = Query("csv", enum=["csv", "excel"]),
    db: sqlite3.Connection = Depends(database.get_db)
):
    """Gera um arquivo com todos os produtos do banco de dados para download."""
    all_products = database.get_all_products(db)
    if not all_products:
        raise HTTPException(
            status_code=404, detail="Nenhum produto para exportar.")

    df = pd.DataFrame(all_products)

    # Lista de colunas a serem removidas do relatório final
    columns_to_remove = ['image_hash', 'confidence']
    for col in columns_to_remove:
        if col in df.columns:
            df.drop(columns=[col], inplace=True)

    # Dicionário para traduzir os nomes das colunas
    column_mapping = {
        'id': 'ID',
        'gtin': 'GTIN/EAN',
        'title': 'Título do Produto',
        'brand': 'Marca',
        'category': 'Categoria',
        'price': 'Preço (R$)',
        'ncm': 'NCM',
        'cest': 'CEST',
        'created_at': 'Data de Criação',
        'updated_at': 'Última Atualização'
    }
    df.rename(columns=column_mapping, inplace=True)

    # --- INÍCIO DA NOVA ALTERAÇÃO ---

    # Força a coluna GTIN/EAN a ser tratada como TEXTO no Excel
    # Adicionando ="<valor>" em cada célula.
    if 'GTIN/EAN' in df.columns:
        df['GTIN/EAN'] = df['GTIN/EAN'].apply(
            lambda x: f'="{x}"' if pd.notna(x) and x != '' else ''
        )

    # --- FIM DA NOVA ALTERAÇÃO ---

    stream = io.BytesIO() if format == "excel" else io.StringIO()
    filename = f"cadvision_produtos_{time.strftime('%Y-%m-%d')}"

    if format == "excel":
        df.to_excel(stream, index=False)
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        filename += ".xlsx"
    else:
        df.to_csv(stream, index=False)
        media_type = "text/csv"
        filename += ".csv"

    stream.seek(0)

    headers = {'Content-Disposition': f'attachment; filename="{filename}"'}
    return StreamingResponse(iter([stream.getvalue()]), media_type=media_type, headers=headers)


@app.get(
    f"{API_PREFIX}/products/{{product_id}}",  # Mude de f"..." para "..."
    response_model=models.ProductOut,
    summary="Busca um único produto pelo seu ID",
    tags=["Produtos"]
)
async def get_single_product(product_id: int, db: sqlite3.Connection = Depends(database.get_db)):
    """Retorna os detalhes de um produto específico."""
    product = database.get_product_by_id(product_id, db)
    if not product:
        raise HTTPException(status_code=404, detail="Produto não encontrado.")
    return product


@app.put(
    f"{API_PREFIX}/products/{{product_id}}",  # Mude de f"..." para "..."
    response_model=models.APIResponse,
    summary="Atualiza um produto existente",
    tags=["Produtos"]
)
async def update_single_product(
    product_id: int,
    product: models.ProductUpdate,
    db: sqlite3.Connection = Depends(database.get_db)
):
    """Atualiza os campos de um produto existente a partir do seu ID."""
    product_data = product.dict(exclude_unset=True)
    if not product_data:
        raise HTTPException(
            status_code=400, detail="Nenhum dado fornecido para atualização.")

    success = database.update_product(product_id, product_data, db)
    if not success:
        raise HTTPException(
            status_code=404, detail="Produto não encontrado ou falha na atualização.")

    return models.APIResponse.success_response(message="Produto atualizado com sucesso.")


@app.delete(
    f"{API_PREFIX}/products/{{product_id}}",  # Mude de f"..." para "..."
    response_model=models.APIResponse,
    summary="Exclui um produto pelo ID",
    tags=["Produtos"]
)
async def delete_product(product_id: int, db: sqlite3.Connection = Depends(database.get_db)):
    """Exclui permanentemente um produto do banco de dados."""
    success = database.delete_product_by_id(product_id, db)
    if not success:
        raise HTTPException(
            status_code=404, detail=f"Produto com ID {product_id} não encontrado.")
    return models.APIResponse.success_response(message="Produto excluído com sucesso.")

# =============================================================================
# === ENDPOINTS DE DASHBOARD E UTILITÁRIOS ====================================
# =============================================================================


@app.get(
    f"{API_PREFIX}/dashboard/summary",
    summary="Obtém dados consolidados para o dashboard",
    tags=["Dashboard"]
)
async def get_dashboard_summary(db: sqlite3.Connection = Depends(database.get_db)):
    """Coleta e agrega múltiplos KPIs e dados para popular a tela do dashboard."""
    return {
        "kpis": database.get_dashboard_kpis(db),
        "category_distribution": database.get_products_by_category(db),
        "recent_activities": database.get_recent_activities(db),
        "performance_history": database.get_success_rate_by_date(db),
        "products_per_day": database.get_products_by_period(db, 'day'),
        "products_per_month": database.get_products_by_period(db, 'month')
    }


@app.get(f"{API_PREFIX}/health", summary="Verifica a saúde da API", tags=["Sistema"])
async def health_check():
    """Endpoint simples para monitoramento e health checks."""
    return {"status": "healthy", "timestamp": time.time()}

# =============================================================================
# === SERVIR ARQUIVOS DO FRONTEND E TRATAMENTO DE ERROS =======================
# =============================================================================

# --- Servir o Frontend (Arquivos Estáticos) ---
BACKEND_DIR = Path(__file__).resolve().parent
# Aponta para a pasta raiz do frontend, já que não há pasta 'dist'
FRONTEND_DIR = BACKEND_DIR.parent / "frontend"

if FRONTEND_DIR.is_dir() and (FRONTEND_DIR / "index.html").exists():
    # Monta a pasta de assets (js, css, imagens, etc.)
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIR /
              "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_frontend_spa(full_path: str):
        """Serve o index.html para qualquer rota não correspondida (Single Page Application)."""
        return FileResponse(FRONTEND_DIR / "index.html")
else:
    logger.warning(
        f"Diretório do frontend ou index.html não encontrado em '{FRONTEND_DIR}'. A UI não será servida.")

# --- Manipuladores de Exceção Globais ---
# (O resto do seu código de tratamento de exceção permanece o mesmo)
# ...

# --- Manipuladores de Exceção Globais ---


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """Captura exceções não tratadas para evitar que a aplicação quebre."""
    logger.error(
        f"Erro não tratado na rota {request.url}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"success": False,
                 "message": "Ocorreu um erro interno no servidor."}
    )
