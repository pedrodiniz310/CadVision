# backend/main.py

# --- Imports da Biblioteca Padrão ---
import logging
import sqlite3
import time
import io
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Optional, Union  # <-- ADICIONE ESTA LINHA

# --- Imports de Terceiros ---
import pandas as pd
from fastapi import (
    Depends, FastAPI, File, HTTPException, UploadFile,
    Query, BackgroundTasks, Form  # <-- ADICIONE 'Form' AQUI
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

# --- Configuração de Logging ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("app.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# --- Ciclo de Vida da Aplicação ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gerencia eventos de inicialização e encerramento da API."""
    logger.info("Iniciando aplicação CadVision API...")
    database.init_db()
    logger.info("Banco de dados inicializado com sucesso.")
    yield
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
    # Em produção, restrinja para o seu domínio do frontend
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# --- Constantes da API ---
API_PREFIX = "/api/v1"

# =============================================================================
# === ENDPOINT PRINCIPAL DE VISÃO COMPUTACIONAL ===============================
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
    # --- MUDANÇA PRINCIPAL AQUI ---
    # Adicionamos 'vertical' como um campo de formulário.
    # Se o frontend não enviar nada, o padrão será "supermercado".
    vertical: str = Form(
        "supermercado", description="A vertical do produto (ex: supermercado, vestuario)"),
    db: sqlite3.Connection = Depends(database.get_db)
):
    """
    Recebe uma imagem de produto e a vertical, executa o pipeline de IA e retorna
    os dados estruturados do produto identificado.
    """
    start_time = time.time()

    # 1. Validação do arquivo de imagem
    if not image.content_type or not image.content_type.startswith('image/'):
        raise HTTPException(
            status_code=400, detail="Tipo de arquivo inválido. Envie uma imagem.")

    image_bytes = await image.read()
    if len(image_bytes) > 10 * 1024 * 1024:  # 10MB
        raise HTTPException(
            status_code=400, detail="Imagem excede o tamanho máximo de 10MB.")
    if not image_bytes:
        raise HTTPException(
            status_code=400, detail="Arquivo de imagem vazio ou corrompido.")

    image_hash = vision_service.get_cache_key(image_bytes)

    # 2. Verificação de imagem duplicada para evitar reprocessamento
    product_from_hash = database.find_product_by_image_hash(image_hash, db)
    if product_from_hash:
        logger.info(
            f"Imagem duplicada encontrada para o hash: {image_hash}. Retornando do cache.")
        identified_product = models.IdentifiedProduct(**product_from_hash)
        return models.IdentificationResult(
            success=True,
            status="duplicate_found",
            product=identified_product,
            image_hash=image_hash,
            confidence=identified_product.confidence or 1.0,
            processing_time=round(time.time() - start_time, 2)
        )

    # 3. Extração de pistas da imagem com o Google Vision
    logger.info(
        "Nenhum cache encontrado. Iniciando extração de dados com o Vision API.")
    vision_data = vision_service.extract_vision_data(image_bytes)

    if not vision_data.get("success"):
        logger.warning(
            "Falha na extração de pistas da imagem pelo Vision Service.")
        raise HTTPException(
            status_code=422, detail="Não foi possível extrair dados legíveis da imagem.")

     # 4. Orquestração da análise inteligente
    logger.info(
        f"Pistas extraídas. Acionando serviço de análise para a vertical: '{vertical}'.")
    # --- MUDANÇA IMPORTANTE AQUI ---
    # Passamos a 'vertical' recebida para a próxima camada da nossa lógica.
    product_info = product_service.intelligent_text_analysis(
        vision_data=vision_data, db=db, vertical=vertical
    )

    # 5. Montagem e retorno da resposta
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
        product_id = database.insert_product(product.dict(), db)
        if product_id:
            return models.APIResponse.success_response(
                data={"id": product_id},
                message="Produto salvo com sucesso"
            )
        # A nova função de database pode retornar um erro mais específico
        raise HTTPException(
            status_code=500, detail="Erro ao salvar o produto no banco de dados.")
    except sqlite3.IntegrityError:
        raise HTTPException(
            status_code=409, detail=f"Produto com GTIN {product.gtin} já existe.")
    except ValueError as e:  # Captura o erro de título vazio que adicionamos
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
