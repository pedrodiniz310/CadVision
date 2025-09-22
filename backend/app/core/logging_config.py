# backend/app/core/logging_config.py
import logging
import sys
from pathlib import Path
from datetime import datetime

# Criar diretório de logs
LOG_DIR = Path(__file__).resolve().parent.parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

# Timestamp para o arquivo de log
LOG_TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
LOG_FILE = LOG_DIR / f"cadvision_{LOG_TIMESTAMP}.log"

def setup_logging():
    """Configura o sistema de logging com formatação consistente"""
    
    # Formatação padrão
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Handler para arquivo
    file_handler = logging.FileHandler(LOG_FILE, encoding='utf-8')
    file_handler.setFormatter(formatter)
    
    # Handler para console
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    
    # Configurar logger raiz
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    
    # Loggers específicos com níveis diferentes
    loggers_config = {
        'app': logging.INFO,
        'app.services.vision_service': logging.DEBUG,
        'app.services.product_service': logging.DEBUG,
        'app.services.advanced_inference_service': logging.DEBUG,
        'app.database': logging.DEBUG,
    }
    
    for logger_name, level in loggers_config.items():
        logger = logging.getLogger(logger_name)
        logger.setLevel(level)
    
    logging.info(f"Logging configurado. Arquivo: {LOG_FILE}")
    return LOG_FILE

# Função auxiliar para log estruturado
def log_structured_event(service: str, event: str, data: dict, level: str = "INFO"):
    """Log estruturado para eventos importantes"""
    logger = logging.getLogger(service)
    log_data = {
        'timestamp': datetime.now().isoformat(),
        'service': service,
        'event': event,
        'data': data
    }
    
    message = f"EVENT: {event} - DATA: {log_data}"
    
    if level.upper() == "INFO":
        logger.info(message)
    elif level.upper() == "ERROR":
        logger.error(message)
    elif level.upper() == "WARNING":
        logger.warning(message)
    elif level.upper() == "DEBUG":
        logger.debug(message)