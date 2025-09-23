# backend/app/services/vision_service.py

import logging
import re
import hashlib
import json
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from functools import lru_cache

import cv2
import numpy as np
from google.cloud import vision
from google.oauth2 import service_account
from google.api_core.exceptions import GoogleAPICallError, RetryError
# Usamos uma versão específica para admin
from google.cloud import vision_v1p4beta1 as vision
from app.core.config import GOOGLE_KEY_PATH

# Defina CACHE_DIR localmente se não estiver disponível no config
try:
    from app.core.config import CACHE_DIR
except ImportError:
    from pathlib import Path
    CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "cache"

logger = logging.getLogger(__name__)
vision_client = None

try:
    credentials = service_account.Credentials.from_service_account_file(
        GOOGLE_KEY_PATH)
    vision_client = vision.ImageAnnotatorClient(credentials=credentials)
    logger.info(
        f"Serviço do Google Vision configurado com {GOOGLE_KEY_PATH}")
except FileNotFoundError:
    logger.warning(
        "Google Vision não configurado - arquivo de chave não encontrado.")
except Exception as e:
    logger.error(f"⚠ Erro ao configurar o serviço do Google Vision: {e}")

# Lista de marcas conhecidas para detecção melhorada
KNOWN_BRANDS = {
    'tio joão', 'nestlé', 'coca cola', 'pepsico', 'ambev', 'sadia', 'perdigão',
    'vale', 'petrobras', 'itau', 'bradesco', 'natura', 'amazon', 'apple',
    'samsung', 'lg', 'sony', 'philips', 'electrolux', 'brahma', 'skol', 'antarctica'
}

# Palavras-chave para categorias
CATEGORY_KEYWORDS = {
    'alimentos': ['arroz', 'feijão', 'macarrão', 'óleo', 'açúcar', 'farinha', 'leite', 'café'],
    'bebidas': ['refrigerante', 'cerveja', 'suco', 'água', 'vinho', 'whisky', 'vodka'],
    'limpeza': ['sabão', 'detergente', 'desinfetante', 'álcool', 'água sanitária', 'amaciante'],
    'higiene': ['shampoo', 'condicionador', 'sabonete', 'pasta de dente', 'papel higiênico'],
    'eletrônicos': ['celular', 'tv', 'notebook', 'tablet', 'fone de ouvido', 'câmera']
}


def get_cache_key(image_bytes: bytes) -> str:
    """Gera uma chave única para cache baseada no conteúdo da imagem."""
    return hashlib.md5(image_bytes).hexdigest()


def enhance_image_for_ocr(image_bytes: bytes) -> bytes:
    """
    Aplica pré-processamento avançado na imagem para melhorar o OCR.
    """
    try:
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return image_bytes

        # Redimensionar imagem se for muito pequena ou muito grande
        height, width = img.shape[:2]
        max_dimension = 2000
        if height > max_dimension or width > max_dimension:
            scale = max_dimension / max(height, width)
            new_width = int(width * scale)
            new_height = int(height * scale)
            img = cv2.resize(img, (new_width, new_height),
                             interpolation=cv2.INTER_AREA)
        elif height < 300 or width < 300:
            img = cv2.resize(img, None, fx=2, fy=2,
                             interpolation=cv2.INTER_CUBIC)

        # Conversão para escala de cinza
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # Redução de ruído usando filtro bilateral
        denoised = cv2.bilateralFilter(gray, 9, 75, 75)

        # Equalização de histograma para melhorar contraste
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        equalized = clahe.apply(denoised)

        # Binarização adaptativa
        binary = cv2.adaptiveThreshold(equalized, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                       cv2.THRESH_BINARY, 11, 2)

        # Operação morfológica para remover ruído
        kernel = np.ones((1, 1), np.uint8)
        processed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
        processed = cv2.medianBlur(processed, 3)

        # Converter para bytes
        success, encoded_image = cv2.imencode('.png', processed)
        if success:
            logger.info("Imagem aprimorada para OCR.")
            return encoded_image.tobytes()
        return image_bytes

    except Exception as e:
        logger.error(f"Erro no aprimoramento da imagem: {e}")
        return image_bytes


# SUBSTITUA a função extract_vision_data por esta:

def extract_vision_data(image_bytes: bytes) -> Dict:
    """
    Extrai texto, logos e labels de uma imagem usando a API do Google Vision.
    Esta é a versão final e simplificada.
    """
    if not vision_client:
        logger.warning("Serviço do Vision não está disponível.")
        return {'raw_text': "", 'detected_logos': [], 'detected_labels': [], 'success': False}

    try:
        image = vision.Image(content=image_bytes)
        
        # Faz detecções
        text_response = vision_client.text_detection(image=image)
        logo_response = vision_client.logo_detection(image=image)
        label_response = vision_client.label_detection(image=image)

        # Processa texto
        raw_text = text_response.text_annotations[0].description.strip() if text_response.text_annotations else ""

        # Processa logos
        detected_logos = [{'description': logo.description, 'score': logo.score} for logo in logo_response.logo_annotations]

        # Processa labels
        detected_labels = [{'description': label.description, 'score': label.score} for label in label_response.label_annotations]

        logger.info(f"Vision API: Texto extraído ({len(raw_text)} chars), Logos: {len(detected_logos)}, Labels: {len(detected_labels)}")
        
        return {
            'raw_text': raw_text,
            'detected_logos': detected_logos,
            'detected_labels': detected_labels,
            'success': bool(raw_text or detected_logos or detected_labels)
        }
    except Exception as e:
        logger.error(f"Erro durante a extração de dados do Vision: {e}")
        return {'raw_text': "", 'detected_logos': [], 'detected_labels': [], 'success': False}


def clean_text(text: str) -> str:
    """
    Limpa e formata o texto para apresentação.
    """
    if not text:
        return text

    # Remove múltiplos espaços e quebras de linha excessivas
    text = re.sub(r'\s+', ' ', text).strip()

    # Remove caracteres especiais problemáticos, mas mantém pontuação básica
    text = re.sub(r'[^\w\s.,;:!?@#$%&*()\-+]', '', text)

    return text


def extract_brand_from_data(text: str, logos: List) -> str:
    """
    Extrai a marca do texto e dos logos detectados.
    """
    # Primeiro verifica se há logos detectados com alta confiança
    for logo in logos:
        if logo.get('score', 0) > 0.7:
            brand_candidate = logo['description'].lower().strip()
            # Verifica se é uma marca conhecida
            if any(brand in brand_candidate for brand in KNOWN_BRANDS):
                return logo['description'].title()

    # Procura no texto por marcas conhecidas
    text_lower = text.lower()
    for brand in KNOWN_BRANDS:
        if brand in text_lower:
            # Encontra a ocorrência exata no texto original
            brand_pattern = re.compile(re.escape(brand), re.IGNORECASE)
            match = brand_pattern.search(text)
            if match:
                return match.group().title()

    # Procura por padrões comuns de marca
    brand_patterns = [
        r'(?i)marca[:\s]+([^\n\r.,;]+)',
        r'(?i)brand[:\s]+([^\n\r.,;]+)',
        r'(?i)(fabricante|manufacturer)[:\s]+([^\n\r.,;]+)'
    ]

    for pattern in brand_patterns:
        matches = re.findall(pattern, text)
        if matches:
            for match in matches:
                if isinstance(match, tuple):
                    brand_candidate = match[1].strip()
                else:
                    brand_candidate = match.strip()

                if len(brand_candidate) > 2:  # Ignora palavras muito curtas
                    return brand_candidate.title()

    return ""


# backend/app/services/vision_service.py

def extract_price_from_text(text: str) -> Optional[float]:
    """
    Extrai o preço mais provável do texto, priorizando valores associados a 'R$'.
    """
    if not text:
        return None

    # Padrões mais abrangentes para capturar números com 2 casas decimais
    # Formatos: R$ 12,99, R$12.99, 12,99, 12.99
    # O regex captura o valor numérico em um grupo
    price_patterns = [
        # Prioriza com R$ ou "preço"
        r'(?:R\$\s*|preço[:\s]*)\s*(\d{1,5}[,.]\d{2})\b',
        # Busca qualquer número no formato X,XX ou X.XX
        r'\b(\d{1,5}[,.]\d{2})\b'
    ]

    candidates = []
    for pattern in price_patterns:
        matches = re.findall(pattern, text)
        for match in matches:
            # Limpa e converte para float
            price_str = match.replace(',', '.')
            try:
                price = float(price_str)
                if price > 0:
                    # Adiciona o preço e um peso de prioridade
                    # Peso 2 para padrões com 'R$' ou 'preço', peso 1 para os outros
                    priority = 2 if 'R$' in pattern or 'preço' in pattern else 1
                    candidates.append({'price': price, 'priority': priority})
            except (ValueError, IndexError):
                continue

    if not candidates:
        return None

    # Escolhe o melhor candidato:
    # 1. Ordena por prioridade (maior primeiro)
    # 2. Se a prioridade for a mesma, ordena pelo maior valor (preços tendem a ser maiores que pesos)
    best_candidate = sorted(candidates, key=lambda x: (
        x['priority'], x['price']), reverse=True)[0]

    logger.info(
        f"Candidatos a preço encontrados: {candidates}. Melhor escolha: {best_candidate['price']}")

    return round(best_candidate['price'], 2)


def detect_category(text: str, labels: List) -> str:
    """
    Detecta a categoria do produto baseado no texto e labels.
    Retorna None se não conseguir detectar.
    """
    text_lower = text.lower()

    # Mapeamento de palavras-chave para categorias
    category_keywords = {
        'Alimentos': ['arroz', 'feijão', 'macarrão', 'óleo', 'açúcar', 'farinha', 'leite', 'café', 'comida', 'alimento'],
        'Bebidas': ['refrigerante', 'cerveja', 'suco', 'água', 'vinho', 'whisky', 'vodka', 'bebida', 'drink'],
        'Limpeza': ['sabão', 'detergente', 'desinfetante', 'álcool', 'água sanitária', 'amaciante', 'limpeza'],
        'Higiene': ['shampoo', 'condicionador', 'sabonete', 'pasta de dente', 'papel higiênico', 'higiene'],
        'Eletrônicos': ['celular', 'tv', 'notebook', 'tablet', 'fone de ouvido', 'câmera', 'eletrônico'],
        'Vestuário': ['camisa', 'calça', 'vestido', 'roupa', 'moda', 'vestuário'],
        'Automotivo': ['carro', 'motor', 'óleo motor', 'pneu', 'automotivo'],
        'Construção': ['cimento', 'tijolo', 'ferro', 'construção', 'obra'],
    }

    # Primeiro verifica os labels da Vision API
    for label in labels:
        if label.get('score', 0) > 0.8:
            label_desc = label['description'].lower()
            for category, keywords in category_keywords.items():
                if any(keyword in label_desc for keyword in keywords):
                    return category

    # Depois verifica no texto
    for category, keywords in category_keywords.items():
        if any(keyword in text_lower for keyword in keywords):
            return category

    return None  # Retorna None em vez de string vazia