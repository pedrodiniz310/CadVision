# -*- coding: utf-8 -*-
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, Literal
import sqlite3, io, re, os
from PIL import Image
import pytesseract

# Configuração do Tesseract (Windows)
try:
    pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
except:
    # Para Linux/Mac, comente a linha acima
    pass

DB_PATH = os.environ.get("DB_PATH", "app.db")

app = FastAPI(title="Cadastro Inteligente - Visao + Fiscal")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Servir arquivos estáticos
app.mount("/static", StaticFiles(directory="."), name="static")

@app.get("/")
async def read_index():
    return FileResponse("index.html")

@app.get("/favicon.ico")
async def favicon():
    return FileResponse("favicon.ico" if os.path.exists("favicon.ico") else "", status_code=404)

# --------------------- DB ---------------------
def get_conn():
    return sqlite3.connect(DB_PATH)

def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            gtin TEXT UNIQUE,
            title TEXT,
            brand TEXT,
            unit TEXT,
            ncm TEXT,
            cest TEXT,
            price REAL
        );
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS tax_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ncm TEXT,
            cest TEXT,
            regime TEXT,
            uf_origem TEXT,
            uf_destino TEXT,
            csosn TEXT,
            cst TEXT,
            icms_aliq REAL,
            icms_st INTEGER,
            pis_aliq REAL,
            cofins_aliq REAL,
            ipi_aliq REAL,
            cfop_sugestao TEXT,
            prioridade INTEGER DEFAULT 100
        );
        """
    )
    # seed de exemplo
    cur.execute(
        """
        INSERT OR IGNORE INTO tax_profiles
        (ncm, cest, regime, uf_origem, uf_destino, csosn, cst,
         icms_aliq, icms_st, pis_aliq, cofins_aliq, ipi_aliq, cfop_sugestao, prioridade)
        VALUES
        ('2202.10.00', '03.001.00', 'SN', 'SC', 'SC', '102', NULL,
         0.0, 0, 0.65, 3.0, 0.0, '5102', 10);
        """
    )
    conn.commit()
    conn.close()

init_db()

# ----------------- MODELOS --------------------
class TaxOut(BaseModel):
    regime: Literal["SN","LP","LR"]
    uf_origem: str
    uf_destino: str
    csosn: Optional[str] = None
    cst: Optional[str] = None
    icms_aliq: Optional[float] = None
    icms_st: bool = False
    pis_aliq: Optional[float] = None
    cofins_aliq: Optional[float] = None
    ipi_aliq: Optional[float] = None
    cfop_sugestao: Optional[str] = None
    observacoes: Optional[str] = None

class ProductOut(BaseModel):
    gtin: Optional[str] = None
    title: Optional[str] = None
    brand: Optional[str] = None
    unit: Optional[str] = None
    ncm: Optional[str] = None
    cest: Optional[str] = None
    tax: Optional[TaxOut] = None
    price: Optional[float] = None

class SaveIn(BaseModel):
    gtin: Optional[str] = None
    title: Optional[str] = None
    brand: Optional[str] = None
    unit: Optional[str] = None
    ncm: Optional[str] = None
    cest: Optional[str] = None
    tax: Optional[TaxOut] = None
    price: Optional[float] = None

class IdentifyOut(BaseModel):
    title: Optional[str] = None
    brand: Optional[str] = None
    unit: Optional[str] = "UN"
    gtin: Optional[str] = None
    ncm: Optional[str] = None
    cest: Optional[str] = None
    tax: Optional[dict] = None
    confidence: Optional[float] = None

# Adicione as rotas da API aqui (se já não tiver)
@app.post("/vision/identify")
async def identify_image(
    image: UploadFile = File(...),
    uf: str = Form("SC"),
    regime: str = Form("SN")
):
    # Sua lógica de identificação aqui
    return {"message": "Identificação funcionando", "uf": uf, "regime": regime}

@app.post("/products/save")
async def save_product(product: SaveIn):
    # Sua lógica de salvamento aqui
    return {"message": "Produto salvo", "product": product.dict()}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)