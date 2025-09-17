# backend/app/database.py
import sqlite3
import logging
from app.core.config import DB_PATH

logger = logging.getLogger(__name__)

def get_db():
    db = sqlite3.connect(DB_PATH, check_same_thread=False)
    db.row_factory = sqlite3.Row
    try:
        yield db
    finally:
        db.close()

def init_db():
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, gtin TEXT UNIQUE, title TEXT NOT NULL,
                    brand TEXT, category TEXT, price REAL, ncm TEXT, cest TEXT,
                    confidence REAL, created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
        logger.info("✓ Banco de dados inicializado com sucesso.")
    except sqlite3.Error as e:
        logger.error(f"⚠ Erro ao inicializar o banco de dados: {e}")