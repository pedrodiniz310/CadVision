# 🚀 CadVision - Sistema de Cadastro Inteligente

Sistema avançado de cadastro de produtos utilizando visão computacional e OCR para automatizar a identificação de produtos a partir de imagens.

## ✨ Funcionalidades

- **OCR Inteligente**: Reconhecimento de texto em imagens usando Google Cloud Vision e Tesseract
- **Análise de Produtos**: Identificação automática de GTIN, marca, categoria e preço
- **Banco de Dados**: Armazenamento local com SQLite
- **API REST**: Interface completa para integração com outros sistemas
- **Interface Web**: Frontend moderno e responsivo

## 🛠️ Tecnologias Utilizadas

- **Backend**: FastAPI, Python 3.8+
- **OCR**: Google Cloud Vision API, Tesseract OCR
- **Processamento de Imagens**: OpenCV, Pillow
- **Banco de Dados**: SQLite
- **Frontend**: HTML5, CSS3, JavaScript Vanilla
- **Deploy**: Uvicorn ASGI server

## 📦 Instalação

### Pré-requisitos

- Python 3.8 ou superior
- Tesseract OCR (opcional, mas recomendado)

### Instalação no Windows

1. **Instalar Tesseract**:
   ```bash
   # Download em: https://github.com/UB-Mannheim/tesseract/wiki
   # Adicionar ao PATH: C:\Program Files\Tesseract-OCR\