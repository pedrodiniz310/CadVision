# backend/app/database.py
import sqlite3
import logging
import threading
from pathlib import Path
from contextlib import contextmanager
from typing import Generator, Optional, Any, Dict, List

# Configuração do caminho do banco de dados
DB_PATH = Path(__file__).resolve().parent.parent.parent / "cadvision.db"

# Garantir que o diretório existe
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger(__name__)

# Lock para operações thread-safe
db_lock = threading.Lock()


def get_db() -> Generator[sqlite3.Connection, None, None]:
    """
    Fornece uma conexão com o banco de dados para injeção de dependência.
    Útil para frameworks como FastAPI.
    """
    with db_lock:
        db = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")  # Ativar chaves estrangeiras

        try:
            yield db
        finally:
            db.close()


@contextmanager
def get_db_connection() -> Generator[sqlite3.Connection, None, None]:
    """
    Gerenciador de contexto para conexões com o banco de dados.
    Útil para operações específicas que não usam injeção de dependência.
    """
    with db_lock:
        conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")

        try:
            yield conn
        except sqlite3.Error as e:
            logger.error(f"Erro de banco de dados: {e}")
            conn.rollback()
            raise
        finally:
            conn.close()


@contextmanager
def get_db_cursor(commit: bool = False) -> Generator[sqlite3.Cursor, None, None]:
    """
    Gerenciador de contexto para obter um cursor de banco de dados.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        try:
            yield cursor
            if commit:
                conn.commit()
        except sqlite3.Error as e:
            conn.rollback()
            logger.error(f"Erro durante operação no banco: {e}")
            raise


def init_db():
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            
            # Tabela de logs de processamento (REMOVA a constraint UNIQUE)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS processing_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    image_hash TEXT,  -- Removido UNIQUE
                    processing_time REAL,
                    success BOOLEAN,
                    confidence REAL,
                    error_message TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Tabela de logs de processamento
            cur.execute("""
                CREATE TABLE IF NOT EXISTS processing_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    image_hash TEXT UNIQUE,
                    processing_time REAL,
                    success BOOLEAN,
                    confidence REAL,
                    error_message TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Tabela de marcas conhecidas para cache
            cur.execute("""
                CREATE TABLE IF NOT EXISTS known_brands (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE,
                    category TEXT,
                    common_products TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Tabela de categorias de produtos
            cur.execute("""
                CREATE TABLE IF NOT EXISTS product_categories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE,
                    keywords TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Índices para melhor performance
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_products_gtin ON products(gtin)")
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_products_category ON products(category)")
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_products_brand ON products(brand)")
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_logs_image_hash ON processing_logs(image_hash)")
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_logs_created_at ON processing_logs(created_at)")

            # Inserir categorias padrão se a tabela estiver vazia
            cur.execute("SELECT COUNT(*) FROM product_categories")
            if cur.fetchone()[0] == 0:
                default_categories = [
                    ('Alimentos', 'arroz,feijão,macarrão,óleo,açúcar,farinha,leite,café'),
                    ('Bebidas', 'refrigerante,cerveja,suco,água,vinho,whisky,vodka'),
                    ('Limpeza', 'sabão,detergente,desinfetante,álcool,água sanitária,amaciante'),
                    ('Higiene', 'shampoo,condicionador,sabonete,pasta de dente,papel higiênico'),
                    ('Eletrônicos', 'celular,tv,notebook,tablet,fone de ouvido,câmera')
                ]
                cur.executemany(
                    "INSERT INTO product_categories (name, keywords) VALUES (?, ?)",
                    default_categories
                )

            # Inserir marcas conhecidas se a tabela estiver vazia
            cur.execute("SELECT COUNT(*) FROM known_brands")
            if cur.fetchone()[0] == 0:
                default_brands = [
                    ('Tio João', 'Alimentos', 'Arroz, Feijão'),
                    ('Nestlé', 'Alimentos', 'Leite, Achocolatado, Iogurte'),
                    ('Coca-Cola', 'Bebidas', 'Refrigerante, Suco'),
                    ('Sadia', 'Alimentos', 'Carne, Frango, Linguiça'),
                    ('Electrolux', 'Eletrodomésticos',
                     'Geladeira, Fogão, Máquina de Lavar')
                ]
                cur.executemany(
                    "INSERT INTO known_brands (name, category, common_products) VALUES (?, ?, ?)",
                    default_brands
                )

            conn.commit()
        logger.info("Banco de dados inicializado com sucesso.")
    except sqlite3.Error as e:
        logger.error(f"Erro ao inicializar o banco de dados: {e}")


def insert_product(product_data: Dict[str, Any]) -> Optional[int]:
    """Insere ou atualiza um produto no banco de dados."""
    try:
        with get_db_cursor(commit=True) as cur:
            # Verifica se o produto já existe pelo GTIN
            if product_data.get('gtin'):
                cur.execute("SELECT id FROM products WHERE gtin = ?",
                            (product_data['gtin'],))
                existing = cur.fetchone()

                if existing:
                    # Atualiza produto existente
                    cur.execute("""
                        UPDATE products 
                        SET title = ?, brand = ?, category = ?, price = ?, ncm = ?, cest = ?, 
                            confidence = ?, image_hash = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE gtin = ?
                    """, (
                        product_data.get('title'),
                        product_data.get('brand'),
                        product_data.get('category'),
                        product_data.get('price'),
                        product_data.get('ncm'),
                        product_data.get('cest'),
                        product_data.get('confidence'),
                        product_data.get('image_hash'),
                        product_data.get('gtin')
                    ))
                    return existing['id']

            # Insere novo produto
            cur.execute("""
                INSERT INTO products 
                (gtin, title, brand, category, price, ncm, cest, confidence, image_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                product_data.get('gtin'),
                product_data.get('title'),
                product_data.get('brand'),
                product_data.get('category'),
                product_data.get('price'),
                product_data.get('ncm'),
                product_data.get('cest'),
                product_data.get('confidence'),
                product_data.get('image_hash')
            ))
            return cur.lastrowid
    except sqlite3.Error as e:
        logger.error(f"Erro ao inserir produto: {e}")
        return None


def log_processing(image_hash: str, processing_time: float, success: bool, 
                  confidence: float = None, error_message: str = None) -> bool:
    """Registra ou atualiza um log de processamento de imagem."""
    try:
        with get_db_cursor(commit=True) as cur:
            # Primeiro verifica se já existe um registro com esse image_hash
            cur.execute("SELECT id FROM processing_logs WHERE image_hash = ?", (image_hash,))
            existing_log = cur.fetchone()
            
            if existing_log:
                # Atualiza o registro existente
                cur.execute("""
                    UPDATE processing_logs 
                    SET processing_time = ?, success = ?, confidence = ?, error_message = ?, created_at = CURRENT_TIMESTAMP
                    WHERE image_hash = ?
                """, (processing_time, success, confidence, error_message, image_hash))
            else:
                # Insere um novo registro
                cur.execute("""
                    INSERT INTO processing_logs 
                    (image_hash, processing_time, success, confidence, error_message)
                    VALUES (?, ?, ?, ?, ?)
                """, (image_hash, processing_time, success, confidence, error_message))
            return True
    except sqlite3.Error as e:
        logger.error(f"Erro ao registrar log de processamento: {e}")
        return False


def get_product_by_gtin(gtin: str) -> Optional[Dict]:
    """Recupera um produto pelo GTIN."""
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM products WHERE gtin = ?", (gtin,))
            row = cur.fetchone()
            return dict(row) if row else None
    except sqlite3.Error as e:
        logger.error(f"Erro ao buscar produto por GTIN: {e}")
        return None


def get_known_brands() -> List[Dict]:
    """Recupera todas as marcas conhecidas."""
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM known_brands ORDER BY name")
            return [dict(row) for row in cur.fetchall()]
    except sqlite3.Error as e:
        logger.error(f"Erro ao buscar marcas conhecidas: {e}")
        return []


def get_categories() -> List[Dict]:
    """Recupera todas as categorias."""
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM product_categories ORDER BY name")
            return [dict(row) for row in cur.fetchall()]
    except sqlite3.Error as e:
        logger.error(f"Erro ao buscar categorias: {e}")
        return []


def get_processing_stats() -> Dict[str, Any]:
    """Recupera estatísticas de processamento."""
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()

            # Total de processamentos
            cur.execute("SELECT COUNT(*) as total FROM processing_logs")
            total = cur.fetchone()['total']

            # Processamentos bem-sucedidos
            cur.execute(
                "SELECT COUNT(*) as success FROM processing_logs WHERE success = 1")
            success = cur.fetchone()['success']

            # Taxa de sucesso
            success_rate = (success / total * 100) if total > 0 else 0

            # Tempo médio de processamento
            cur.execute(
                "SELECT AVG(processing_time) as avg_time FROM processing_logs WHERE processing_time > 0")
            avg_time = cur.fetchone()['avg_time'] or 0

            return {
                'total_processments': total,
                'successful_processments': success,
                'success_rate': round(success_rate, 2),
                'average_processing_time': round(avg_time, 2)
            }
    except sqlite3.Error as e:
        logger.error(f"Erro ao buscar estatísticas: {e}")
        return {}
