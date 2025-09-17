# backend/app/services/vision_service.py

import logging
import re
from typing import Dict

import cv2
import numpy as np
from google.cloud import vision
from google.oauth2 import service_account

# Importa as configurações usando o caminho absoluto a partir do pacote 'app'
from app.core.config import GOOGLE_KEY_PATH

# --- INICIALIZAÇÃO DO SERVIÇO ---

logger = logging.getLogger(__name__)
vision_client = None

# Tenta inicializar o cliente do Google Vision quando este módulo é carregado
try:
    # A verificação 'exists' já está implícita no 'from_service_account_file'
    credentials = service_account.Credentials.from_service_account_file(GOOGLE_KEY_PATH)
    vision_client = vision.ImageAnnotatorClient(credentials=credentials)
    logger.info(f"✓ Serviço do Google Vision configurado com {GOOGLE_KEY_PATH}")
except FileNotFoundError:
    logger.warning("⚠ Google Vision não configurado - arquivo de chave não encontrado.")
except Exception as e:
    logger.error(f"⚠ Erro ao configurar o serviço do Google Vision: {e}")


# --- FUNÇÕES DE PROCESSAMENTO DE IMAGEM ---

def enhance_image_for_ocr(image_bytes: bytes) -> bytes:
    """
    Aplica uma série de filtros OpenCV para melhorar a qualidade da imagem para OCR.
    (Esta é a sua função de aprimoramento, movida para cá)
    """
    try:
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return image_bytes

        # Lógica de correção de perspectiva, upscaling e binarização
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        TARGET_WIDTH = 1600
        height, width = gray.shape
        if width < TARGET_WIDTH:
            scale_ratio = TARGET_WIDTH / width
            new_height = int(height * scale_ratio)
            gray = cv2.resize(gray, (TARGET_WIDTH, new_height), interpolation=cv2.INTER_CUBIC)
        
        denoised = cv2.medianBlur(gray, 3)
        binary = cv2.adaptiveThreshold(denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
        
        success, encoded_image = cv2.imencode('.png', binary)
        if success:
            logger.info("Imagem aprimorada com sucesso para OCR.")
            return encoded_image.tobytes()
        return image_bytes
    except Exception as e:
        logger.error(f"Erro inesperado no aprimoramento da imagem: {e}")
        return image_bytes


def extract_vision_data(image_bytes: bytes) -> Dict:
    """
    Extrai texto e logos de uma imagem usando a API do Google Vision.
    (Esta é a sua função de extração, movida para cá)
    """
    if not vision_client:
        logger.warning("Serviço do Vision não está disponível. Pulando extração.")
        return {'raw_text': None, 'detected_logos': []}
    
    try:
        image = vision.Image(content=image_bytes)
        
        # Otimização: Faz as duas requisições em um único lote para economizar tempo
        features = [
            vision.Feature(type_=vision.Feature.Type.TEXT_DETECTION),
            vision.Feature(type_=vision.Feature.Type.LOGO_DETECTION),
        ]
        request = vision.AnnotateImageRequest(image=image, features=features)
        response = vision_client.annotate_image(request=request)

        # Processa a resposta
        raw_text = response.text_annotations[0].description if response.text_annotations else ""
        logos = [logo.description for logo in response.logo_annotations]
        
        logger.info(f"Vision API: Texto extraído ({len(raw_text)} chars), Logos detectados: {logos}")
        return {'raw_text': raw_text.strip(), 'detected_logos': logos}
    except Exception as e:
        logger.error(f"Erro durante a extração de dados do Vision: {e}")
        return {'raw_text': None, 'detected_logos': []}


def clean_text(text: str) -> str:
    """
    Limpa e formata o texto para apresentação.
    (Esta é a sua função de limpeza, movida para cá)
    """
    if not text:
        return text
    text = re.sub(r'\s+', ' ', text).strip()
    return ' '.join([word.title() if word.isupper() and len(word) > 1 else word for word in text.split()])