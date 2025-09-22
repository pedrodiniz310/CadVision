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
    Extrai texto, logos e outros dados de uma imagem usando a API do Google Vision.
    """
    # Linha de verificação de cache removida daqui

    if not vision_client:
        logger.warning("Serviço do Vision não está disponível.")
        return {'raw_text': "", 'detected_logos': [], 'success': False}

    try:
        # Primeiro tenta com imagem original
        image = vision.Image(content=image_bytes)

        # Se não obter bons resultados, tenta com imagem processada
        enhanced_image_bytes = enhance_image_for_ocr(image_bytes)
        enhanced_image = vision.Image(content=enhanced_image_bytes)

        # Faz detecções em paralelo
        text_response = vision_client.text_detection(image=image)
        logo_response = vision_client.logo_detection(image=image)
        label_response = vision_client.label_detection(image=image)

        # Verifica se há erros nas respostas
        if text_response.error.message:
            logger.error(
                f"Erro na API Vision (texto): {text_response.error.message}")
        if logo_response.error.message:
            logger.error(
                f"Erro na API Vision (logo): {logo_response.error.message}")

        # Processa texto
        raw_text = ""
        full_text_annotation = ""

        if text_response.text_annotations:
            raw_text = text_response.text_annotations[0].description.strip()
            full_text_annotation = str(text_response.full_text_annotation)

        # Processa logos
        detected_logos = []
        if logo_response.logo_annotations:
            detected_logos = [
                {
                    'description': logo.description,
                    'score': logo.score
                }
                for logo in logo_response.logo_annotations
            ]

        # Processa labels (categorias)
        detected_labels = []
        if label_response.label_annotations:
            detected_labels = [
                {
                    'description': label.description,
                    'score': label.score,
                    'topicality': label.topicality
                }
                for label in label_response.label_annotations
            ]

        logger.info(
            f"Vision API: Texto extraído ({len(raw_text)} chars), "
            f"Logos: {len(detected_logos)}, Labels: {len(detected_labels)}"
        )

        # Extrai informações estruturadas
        gtin = extract_gtin_from_text(raw_text)
        brand = extract_brand_from_data(raw_text, detected_logos)
        price = extract_price_from_text(raw_text)
        category = detect_category(raw_text, detected_labels)

        result = {
            'raw_text': raw_text,
            'full_text_annotation': full_text_annotation,
            'detected_logos': detected_logos,
            'detected_labels': detected_labels,
            'gtin': gtin,
            'brand': brand,
            'price': price,
            'category': category,
            'success': len(raw_text) > 10 or len(detected_logos) > 0 or len(detected_labels) > 0
        }

        # Linha de armazenamento em cache removida daqui

        return result

    except GoogleAPICallError as e:
        logger.error(f"Erro de API do Google Vision: {e}")
    except RetryError as e:
        logger.error(f"Erro de repetição na API do Google Vision: {e}")
    except Exception as e:
        logger.error(f"Erro durante a extração de dados do Vision: {e}")

    return {
        'raw_text': "",
        'detected_logos': [],
        'detected_labels': [],
        'gtin': "",
        'brand': "",
        'price': None,
        'category': "",
        'success': False
    }


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


def validate_gtin(gtin: str) -> bool:
    """
    Valida um código GTIN usando o algoritmo de dígito verificador.
    """
    if not gtin or not gtin.isdigit():
        return False

    # GTIN pode ter 8, 12, 13 ou 14 dígitos
    if len(gtin) not in [8, 12, 13, 14]:
        return False

    # Calcula dígito verificador
    total = 0
    for i, digit in enumerate(reversed(gtin[:-1])):
        weight = 3 if i % 2 == 0 else 1
        total += int(digit) * weight

    check_digit = (10 - (total % 10)) % 10
    return check_digit == int(gtin[-1])


def extract_gtin_from_text(text: str) -> str:
    """
    Extrai GTIN do texto com validação de dígito verificador.
    """
    if not text:
        return ""

    # --- LINHA DA CORREÇÃO ---
    # Remove todos os caracteres que não são dígitos (espaços, letras, etc.)
    cleaned_text = re.sub(r'\D', '', text)
    # -------------------------

    logger.info(
        f"Texto bruto: '{text}' -> Texto limpo para análise: '{cleaned_text}'")

    # Padrões para GTIN (8, 12, 13, 14 dígitos)
    # Agora eles vão funcionar no texto limpo
    patterns = [
        r'(\d{13})',   # GTIN-13 (EAN) - Prioridade
        r'(\d{12})',   # GTIN-12 (UPC)
        r'(\d{14})',   # GTIN-14
        r'(\d{8})'     # GTIN-8
    ]

    for pattern in patterns:
        # Busca todas as possíveis sequências no texto limpo
        matches = re.findall(pattern, cleaned_text)
        for gtin_candidate in matches:
            # Valida cada candidato com o dígito verificador
            if validate_gtin(gtin_candidate):
                logger.info(f"GTIN validado com sucesso: {gtin_candidate}")
                return gtin_candidate

    logger.warning(
        f"Nenhum GTIN válido encontrado no texto limpo: '{cleaned_text}'")
    return ""


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
