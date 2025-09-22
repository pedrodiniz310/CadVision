import google.generativeai as genai
import logging
import os

# Configuração básica para vermos todas as mensagens
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- SUA NOVA CONFIGURAÇÃO ---
# Cole a chave de API que você gerou no Google AI Studio
# Para mais segurança, é bom colocar isso em um arquivo .env depois, mas para o teste, pode ser direto.
API_KEY = "AIzaSyBiDFX_nDBI37XxATZR9idVLO1cd1iRibE"

def run_direct_ai_studio_test():
    """
    Faz a chamada mais simples possível para a API do Gemini via AI Studio.
    """
    try:
        # 1. Configura a biblioteca com sua chave de API
        logger.info("Configurando a API do Google AI Studio...")
        genai.configure(api_key=API_KEY)
        logger.info("Configuração bem-sucedida.")

        # 2. Carrega o modelo (usamos 'gemini-pro', o padrão para esta API)
        logger.info("Carregando o modelo 'gemini-pro'...")
        model = genai.GenerativeModel('gemini-1.5-pro-latest')
        logger.info("Modelo carregado com sucesso.")

        # 3. Envia um prompt simples
        prompt_simples = "Qual é a capital do Brasil?"
        logger.info(f"Enviando um prompt simples para o modelo: '{prompt_simples}'")
        response = model.generate_content(prompt_simples)
        
        # 4. Imprime a resposta
        logger.info("--- SUCESSO! ---")
        print("\n\n✅ RESPOSTA DA IA:\n", response.text)
        logger.info("--------------------")
        
    except Exception as e:
        logger.error("--- FALHA! ---")
        logger.error("Ocorreu um erro ao tentar se comunicar com a API do Google AI Studio.")
        logger.error("Detalhes do erro:", exc_info=True)
        logger.error("----------------")

if __name__ == "__main__":
    run_direct_ai_studio_test()