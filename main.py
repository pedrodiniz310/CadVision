# main.py
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel
from typing import Optional, List, Dict
import sqlite3
import io
import re
import os
import base64
from PIL import Image
import pytesseract
import json
from datetime import datetime
from google.cloud import vision
from google.oauth2 import service_account
import cv2
import numpy as np
import logging


# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuração do Google Cloud Vision
GOOGLE_KEY_PATH = os.path.join("keys", "vision.json")

vision_client = None
if os.path.exists(GOOGLE_KEY_PATH):
    try:
        credentials = service_account.Credentials.from_service_account_file(
            GOOGLE_KEY_PATH)
        vision_client = vision.ImageAnnotatorClient(credentials=credentials)
        logger.info(f"✓ Google Vision configurado com {GOOGLE_KEY_PATH}")
    except Exception as e:
        logger.error(f"⚠ Erro ao configurar Google Vision: {e}")
        vision_client = None
else:
    logger.warning(
        "⚠ Google Vision não configurado - arquivo não encontrado em keys/vision.json")

# Configuração do Tesseract (fallback)
tesseract_paths = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
]

tesseract_configured = False
for path in tesseract_paths:
    if os.path.exists(path):
        pytesseract.pytesseract.tesseract_cmd = path
        tesseract_configured = True
        logger.info(f"✓ Tesseract encontrado em: {path}")
        break

if not tesseract_configured:
    logger.warning("⚠ Tesseract não encontrado. Usando modo de demonstração.")

DB_PATH = os.environ.get("DB_PATH", "app.db")

app = FastAPI(title="CadVision - Sistema de Cadastro Inteligente")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# A LINHA INCORRETA "app.mount("/static", ...)" FOI REMOVIDA DAQUI

# --------------------- BANCO DE DADOS ---------------------


def get_conn():
    return sqlite3.connect(DB_PATH)


def init_db():
    conn = get_conn()
    cur = conn.cursor()

    # Tabela de produtos
    cur.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            gtin TEXT,
            title TEXT NOT NULL,
            brand TEXT,
            category TEXT,
            price REAL,
            ncm TEXT,
            cest TEXT,
            confidence REAL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()
    logger.info("✓ Banco de dados inicializado com sucesso.")


@app.on_event("startup")
async def startup_event():
    """Função que executa ao iniciar a aplicação."""
    init_db()

# --------------------- BANCO DE DADOS DE PRODUTOS COMUNS ---------------------
COMMON_PRODUCTS_DB = {
    # Alimentos
    "7891000315507": {"title": "Arroz Tio João Tipo 1", "brand": "Tio João", "category": "Alimentos", "ncm": "1006.30.00"},
    "7891000053508": {"title": "Leite Italac Integral", "brand": "Italac", "category": "Laticínios", "ncm": "0401.20.00"},
    "7893000365592": {"title": "Açúcar União Cristal", "brand": "União", "category": "Alimentos", "ncm": "1701.99.00"},
    "7891999010026": {"title": "Café Pilão Tradicional", "brand": "Pilão", "category": "Alimentos", "ncm": "0901.21.00"},
    "7896051111011": {"title": "Óleo de Soja Liza", "brand": "Liza", "category": "Alimentos", "ncm": "1507.90.00"},

    # Bebidas
    "7891991011026": {"title": "Coca-Cola 2L", "brand": "Coca-Cola", "category": "Bebidas", "ncm": "2202.10.00"},
    "7892840222945": {"title": "Guaraná Antarctica 2L", "brand": "Antarctica", "category": "Bebidas", "ncm": "2202.10.00"},
    "7894650060012": {"title": "Suco Del Valle Laranja", "brand": "Del Valle", "category": "Bebidas", "ncm": "2009.11.00"},

    # Limpeza
    "7898903023456": {"title": "Sabão em Pó Omo", "brand": "Omo", "category": "Limpeza", "ncm": "3402.20.00"},
    "7891021006402": {"title": "Detergente Ypê", "brand": "Ypê", "category": "Limpeza", "ncm": "3402.20.00"},
    "7896094908017": {"title": "Amaciante Downy", "brand": "Downy", "category": "Limpeza", "ncm": "3307.90.00"},

    # Higiene
    "7891010031525": {"title": "Pasta de Dente Colgate", "brand": "Colgate", "category": "Higiene", "ncm": "3306.10.00"},
    "7891021006402": {"title": "Sabonete Dove", "brand": "Dove", "category": "Higiene", "ncm": "3401.11.00"},
    "7891150038325": {"title": "Shampoo Head & Shoulders", "brand": "Head & Shoulders", "category": "Higiene", "ncm": "3305.10.00"}
}

COMMON_BRANDS = ["tio joão", "coca-cola", "nestlé", "danone", "ypê", "omo", "dove", "colgate",
                 "unilever", "procter & gamble", "ambev", "heineken", "l'oréal", "nívea", "sadia",
                 "perdigão", "seara", "friboi", "pilão", "melitta", "camil", "bastião", "dona benta"]

# --------------------- MELHORIAS NO PRÉ-PROCESSAMENTO ---------------------


def enhance_image_for_ocr(image_bytes: bytes) -> bytes:
    """Melhora drasticamente a imagem para OCR"""
    try:
        # Converter para array numpy
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if img is None:
            return image_bytes

        # 1. Redimensionar se for muito pequena
        height, width = img.shape[:2]
        if width < 600 or height < 600:
            scale = max(800/width, 800/height)
            new_width = int(width * scale)
            new_height = int(height * scale)
            img = cv2.resize(img, (new_width, new_height),
                             interpolation=cv2.INTER_CUBIC)

        # 2. Converter para escala de cinza
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # 3. Aplicar filtro de nitidez
        kernel = np.array([[-1, -1, -1], [-1, 9, -1], [-1, -1, -1]])
        sharpened = cv2.filter2D(gray, -1, kernel)

        # 4. Redução de ruído
        denoised = cv2.medianBlur(sharpened, 3)

        # 5. Equalização de histograma para melhorar contraste
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        equalized = clahe.apply(denoised)

        # 6. Binarização adaptativa (crucial para OCR)
        thresh = cv2.adaptiveThreshold(equalized, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                       cv2.THRESH_BINARY, 11, 2)

        # 7. Dilatação para unir caracteres quebrados
        kernel = np.ones((1, 1), np.uint8)
        dilated = cv2.dilate(thresh, kernel, iterations=1)

        # Converter de volta para bytes
        success, encoded_image = cv2.imencode('.png', dilated)
        if success:
            return encoded_image.tobytes()
        return image_bytes

    except Exception as e:
        logger.error(f"Erro no enhancement: {e}")
        return image_bytes

# --------------------- OCR MELHORADO ---------------------


def extract_text_with_google_enhanced(image_bytes: bytes) -> Optional[str]:
    """Extrai texto usando Google Vision com configurações otimizadas"""
    try:
        if not vision_client:
            logger.warning("Google Vision client não está configurado")
            return None

        # Primeiro tenta com a imagem original
        image = vision.Image(content=image_bytes)
        response = vision_client.text_detection(image=image)

        if response.error.message:
            logger.error(f"Erro Google Vision: {response.error.message}")
            return None

        text = ""
        if response.text_annotations:
            text = response.text_annotations[0].description
            logger.info(f"[Vision] Texto extraído: {text[:200]}...")

            # Se o texto for muito curto, tenta com imagem melhorada
            if len(text.strip()) < 20:
                enhanced_image = enhance_image_for_ocr(image_bytes)
                if enhanced_image != image_bytes:
                    image_enhanced = vision.Image(content=enhanced_image)
                    response_enhanced = vision_client.text_detection(
                        image=image_enhanced)
                    if response_enhanced.text_annotations:
                        enhanced_text = response_enhanced.text_annotations[0].description
                        if len(enhanced_text) > len(text):
                            text = enhanced_text
                            logger.info(
                                f"[Vision Enhanced] Texto melhorado: {enhanced_text[:200]}...")

        return text.strip() if text else None

    except Exception as e:
        logger.error(f"Erro no Google Vision OCR: {e}")
        return None

# --------------------- ANÁLISE INTELIGENTE DE TEXTO ---------------------


def intelligent_text_analysis(text: str) -> Dict:
    """Análise inteligente do texto com múltiplas estratégias"""
    text_lower = text.lower()
    text_upper = text.upper()
    lines = [line.strip() for line in text.split('\n') if line.strip()]

    result = {
        'title': None,
        'brand': None,
        'gtin': None,
        'category': None,
        'confidence': 0.5,
        'detected_patterns': []
    }

    # ESTRATÉGIA 1: Buscar GTIN primeiro (mais confiável)
    gtin_patterns = [
        r'\b(\d{8,14})\b',  # GTIN básico
        r'GTIN[:]?\s*(\d{13,14})',
        r'EAN[:]?\s*(\d{13,14})',
        r'COD\.?BARRAS[:]?\s*(\d{8,14})'
    ]

    for pattern in gtin_patterns:
        matches = re.findall(pattern, text_upper)
        for match in matches:
            gtin = match if isinstance(match, str) else match[0]
            if gtin.isdigit() and len(gtin) in [8, 12, 13, 14]:
                result['gtin'] = gtin
                result['confidence'] += 0.2
                result['detected_patterns'].append('gtin')

                # Se encontrou GTIN, tenta buscar no banco de produtos
                if gtin in COMMON_PRODUCTS_DB:
                    product_info = COMMON_PRODUCTS_DB[gtin]
                    result.update(
                        {k: v for k, v in product_info.items() if result[k] is None})
                    result['confidence'] += 0.3
                break

    # ESTRATÉGIA 2: Buscar marcas conhecidas
    for brand in COMMON_BRANDS:
        if brand in text_lower:
            result['brand'] = brand.upper()
            result['confidence'] += 0.15
            result['detected_patterns'].append('marca_conhecida')
            break

    # ESTRATÉGIA 3: Buscar padrões estruturados
    patterns = {
        'title': [
            r'(PRODUTO|NOME|DESCRI[CÇ]AO|ITEM|DENOMINAÇÃO)[:]\s*([^\n]+)',
            # Linha toda em maiúsculo com certo comprimento
            r'^([A-Z][A-Z\s]{10,50})$',
        ],
        'brand': [
            r'(MARCA|FABRICANTE|BRAND|INDUSTRIA|EMBALADO POR)[:]\s*([^\n]+)',
            r'\b([A-Z]{2,15}\s?[A-Z]{2,15})\b',  # Palavras todas em maiúsculo
        ]
    }

    for field, field_patterns in patterns.items():
        for pattern in field_patterns:
            matches = re.finditer(pattern, text_upper, re.IGNORECASE)
            for match in matches:
                if field in ['title', 'brand'] and len(match.groups()) >= 2:
                    value = match.group(2).strip()
                else:
                    value = match.group(1).strip(
                    ) if match.groups() else match.group(0)

                if value and (result.get(field) is None or len(value) > len(str(result.get(field)))):
                    result[field] = value
                    result['detected_patterns'].append(field)
                    result['confidence'] += 0.1

    # ESTRATÉGIA 4: Heurística inteligente para título e marca
    if not result['title']:
        # Linhas mais longas geralmente são o título do produto
        candidate_lines = [line for line in lines if 15 <= len(line) <= 80]
        if candidate_lines:
            # Prefere linhas que não sejam apenas números/símbolos
            text_lines = [
                line for line in candidate_lines if re.search(r'[a-zA-Z]', line)]
            if text_lines:
                result['title'] = max(text_lines, key=len).title()
                result['confidence'] += 0.1

    if not result['brand']:
        # Procura por palavras que parecem nomes de marca
        brand_candidates = []
        for line in lines:
            words = line.split()
            for word in words:
                if (len(word) >= 3 and len(word) <= 20 and
                    word.isupper() and not word.isdigit() and
                        not any(char in word for char in '0123456789%$#@!&*()')):
                    brand_candidates.append(word)

        if brand_candidates:
            result['brand'] = max(brand_candidates, key=len)
            result['confidence'] += 0.1

    # ESTRATÉGIA 5: Detecção de categoria baseada em palavras-chave
    category_keywords = {
        'Alimentos': ['arroz', 'feijão', 'açúcar', 'café', 'óleo', 'macarrão', 'farinha', 'fubá'],
        'Bebidas': ['refrigerante', 'suco', 'água', 'cerveja', 'vinho', 'energético', 'isotônico'],
        'Limpeza': ['sabão', 'detergente', 'amaciante', 'água sanitária', 'desinfetante', 'limpa vidros'],
        'Higiene': ['shampoo', 'condicionador', 'sabonete', 'pasta dental', 'desodorante', 'protetor solar'],
        'Laticínios': ['leite', 'queijo', 'iogurte', 'manteiga', 'requeijão', 'coalhada']
    }

    if not result['category']:
        for category, keywords in category_keywords.items():
            if any(keyword in text_lower for keyword in keywords):
                result['category'] = category
                result['confidence'] += 0.1
                break

    # Limitar confiança e garantir valores mínimos
    result['confidence'] = min(max(result['confidence'], 0.1), 0.95)

    # Limpar e formatar os resultados
    if result['title']:
        result['title'] = clean_text(result['title'])
    if result['brand']:
        result['brand'] = clean_text(result['brand'])

    logger.info(f"Análise inteligente: {result}")
    return result


def clean_text(text: str) -> str:
    """Limpa e formata o texto"""
    if not text:
        return text

    # Remove múltiplos espaços
    text = re.sub(r'\s+', ' ', text.strip())

    # Converte para título case (primeira letra maiúscula de cada palavra)
    words = text.split()
    cleaned_words = []
    for word in words:
        if word.isupper() and len(word) > 1:
            # Se a palavra está toda em maiúsculo, converte para título
            cleaned_words.append(word.title())
        else:
            cleaned_words.append(word)

    return ' '.join(cleaned_words)

# --------------------- MODELOS PYDANTIC ---------------------


# --- MODELOS DE DADOS (PYDANTIC) ---
class Product(BaseModel):
    id: int
    name: Optional[str]
    brand: Optional[str]
    gtin: Optional[str]
    price: Optional[float]
    image_path: Optional[str]
    ocr_text: Optional[str]
    created_at: datetime


class SaveIn(BaseModel):
    gtin: Optional[str] = None
    title: str
    brand: Optional[str] = None
    category: Optional[str] = None
    price: Optional[float] = None
    ncm: Optional[str] = None
    cest: Optional[str] = None
    confidence: Optional[float] = None

# --------------------- ROTAS API ---------------------


@app.post("/vision/identify")
async def identify_image(
    image: UploadFile = File(...),
    uf: str = Form("SC"),
    regime: str = Form("SN")
):
    """Identifica produto a partir de imagem com OCR melhorado"""
    try:
        if not image.content_type.startswith('image/'):
            raise HTTPException(400, "Arquivo de imagem inválido")

        image_bytes = await image.read()

        if len(image_bytes) == 0:
            raise HTTPException(400, "Imagem vazia")

        if len(image_bytes) > 10 * 1024 * 1024:
            raise HTTPException(400, "Imagem muito grande (máx. 10MB)")

        # Extrai texto com método melhorado
        text = extract_text_with_google_enhanced(image_bytes)

        if not text or len(text.strip()) < 10:
            return {
                'title': "Texto não detectado",
                'brand': "Melhore a qualidade da imagem",
                'gtin': None,
                'category': None,
                'confidence': 0.1,
                'raw_text': text[:200] if text else "Vazio",
                'detected_patterns': []
            }

        # Análise inteligente do texto
        product_info = intelligent_text_analysis(text)

        return product_info

    except Exception as e:
        logger.error(f"Erro na identificação: {e}")
        raise HTTPException(500, f"Erro na identificação: {str(e)}")


@app.post("/products/save")
async def save_product(product: SaveIn):
    """Salva produto no banco de dados"""
    try:
        if not product.title:
            raise HTTPException(400, "Título do produto é obrigatório")

        conn = get_conn()
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO products 
            (gtin, title, brand, category, price, ncm, cest, confidence, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            product.gtin,
            product.title,
            product.brand,
            product.category,
            product.price,
            product.ncm,
            product.cest,
            product.confidence,
            datetime.now().isoformat()
        ))

        conn.commit()
        product_id = cur.lastrowid
        conn.close()

        return {
            "message": "Produto salvo com sucesso",
            "id": product_id,
            "gtin": product.gtin,
            "title": product.title
        }

    except sqlite3.IntegrityError:
        raise HTTPException(400, "GTIN já existe")
    except Exception as e:
        logger.error(f"Erro ao salvar produto: {e}")
        raise HTTPException(500, f"Erro ao salvar produto: {str(e)}")


@app.get("/products")
async def get_products():
    """Obtém todos os produtos"""
    try:
        conn = get_conn()
        cur = conn.cursor()

        cur.execute("""
            SELECT gtin, title, brand, category, price, ncm, cest, confidence 
            FROM products 
            ORDER BY created_at DESC
        """)

        products = []
        for row in cur.fetchall():
            products.append({
                'gtin': row[0] if row[0] else None,
                'title': row[1] if row[1] else "Sem título",
                'brand': row[2] if row[2] else None,
                'category': row[3] if row[3] else None,
                'price': float(row[4]) if row[4] is not None else None,
                'ncm': row[5] if row[5] else None,
                'cest': row[6] if row[6] else None,
                'confidence': float(row[7]) if row[7] is not None else None
            })

        conn.close()
        return products

    except Exception as e:
        logger.error(f"Erro ao buscar produtos: {e}")
        raise HTTPException(500, f"Erro ao buscar produtos: {str(e)}")


@app.get("/test")
async def test_api():
    """Endpoint de teste"""
    return {
        "status": "OK",
        "message": "API funcionando",
        "tesseract": "Disponível" if tesseract_configured else "Modo demo",
        "google_vision": "Ativo" if vision_client else "Inativo",
        "timestamp": datetime.now().isoformat()
    }


@app.get("/", include_in_schema=False)
async def read_index():
    return FileResponse('index.html')

# IMPORTANTE: Deve vir DEPOIS de todas as outras rotas da API
app.mount("/", StaticFiles(directory="."), name="root-static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
