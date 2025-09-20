# backend/app/database.py
import sqlite3
import logging
import threading
from pathlib import Path
from contextlib import contextmanager
from typing import Generator, Optional, Any, Dict, List
from app.core.config import DB_PATH

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
    """Cria e inicializa as tabelas do banco de dados se elas não existirem."""
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()

            # --- ADICIONE ESTE BLOCO ---
            # 1. Tabela principal de PRODUTOS
            cur.execute("""
                CREATE TABLE IF NOT EXISTS products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    gtin TEXT UNIQUE,
                    title TEXT NOT NULL,
                    brand TEXT,
                    category TEXT,
                    price REAL,
                    ncm TEXT,
                    cest TEXT,
                    confidence REAL,
                    image_hash TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # --- FIM DA ADIÇÃO ---

            # 2. Tabela de LOGS de processamento
            cur.execute("""
                CREATE TABLE IF NOT EXISTS processing_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    image_hash TEXT,
                    processing_time REAL,
                    success BOOLEAN,
                    confidence REAL,
                    error_message TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 3. Tabela de MARCAS conhecidas para cache e inferência
            cur.execute("""
                CREATE TABLE IF NOT EXISTS known_brands (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    category TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 4. Tabela de CATEGORIAS de produtos
            cur.execute("""
                CREATE TABLE IF NOT EXISTS product_categories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    keywords TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # --- ÍNDICES PARA MELHOR PERFORMANCE ---
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_products_gtin ON products(gtin)")
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_logs_image_hash ON processing_logs(image_hash)")

            # --- DADOS INICIAIS (SEMENTE) ---

            # Inserir categorias padrão se a tabela estiver vazia
            cur.execute("SELECT COUNT(*) FROM product_categories")
            if cur.fetchone()[0] == 0:
                default_categories = [
                    ('Alimentos', 'arroz,feijão,macarrão,óleo,açúcar,farinha,leite,café,biscoito,wafer,sêmola'),
                    ('Bebidas', 'refrigerante,cerveja,suco,água,vinho,whisky,vodka'),
                    ('Limpeza', 'sabão,detergente,desinfetante,álcool,água sanitária,amaciante'),
                    ('Higiene', 'shampoo,condicionador,sabonete,pasta de dente,papel higiênico,lenços'),
                    ('Eletrônicos', 'celular,tv,notebook,tablet,fone de ouvido,câmera')
                ]
                cur.executemany(
                    "INSERT INTO product_categories (name, keywords) VALUES (?, ?)",
                    default_categories
                )

            conn.commit()
        logger.info("Banco de dados inicializado com sucesso.")
    except sqlite3.Error as e:
        logger.error(f"Erro ao inicializar o banco de dados: {e}")

# Em backend/app/database.py


def insert_product(product_data: Dict[str, Any], db: sqlite3.Connection) -> Optional[int]:
    """Insere ou atualiza um produto no banco de dados usando a conexão fornecida."""
    try:
        # A lógica de 'with get_db_cursor...' foi removida para usar a conexão 'db' diretamente.
        cur = db.cursor()

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
                """, (  # A vírgula antes de WHERE foi removida
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
                db.commit()  # Realiza o commit da transação
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
        db.commit()  # Realiza o commit da transação
        return cur.lastrowid
    except sqlite3.Error as e:
        logger.error(f"Erro ao inserir produto: {e}")
        db.rollback()  # Desfaz a transação em caso de erro
        return None


def log_processing(image_hash: str, processing_time: float, success: bool,
                   confidence: float = None, error_message: str = None) -> bool:
    """Registra ou atualiza um log de processamento de imagem."""
    try:
        with get_db_cursor(commit=True) as cur:
            # Primeiro verifica se já existe um registro com esse image_hash
            cur.execute(
                "SELECT id FROM processing_logs WHERE image_hash = ?", (image_hash,))
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

# Função para deletar produto pelo ID


def delete_product_by_id(product_id: int, db: sqlite3.Connection) -> bool:
    """Exclui um produto pelo seu ID. Retorna True se bem-sucedido, False caso contrário."""
    try:
        # O 'with db_lock:' FOI REMOVIDO DAQUI
        cursor = db.cursor()
        cursor.execute("DELETE FROM products WHERE id = ?", (product_id,))
        db.commit()
        # rowcount > 0 significa que uma linha foi de fato apagada
        return cursor.rowcount > 0
    except sqlite3.Error as e:
        logger.error(f"Erro ao excluir produto ID {product_id}: {e}")
        db.rollback()
        return False


# Função para recuperar todos os produtos
def get_all_products(db: sqlite3.Connection) -> List[Dict]:
    """Recupera TODOS os produtos do banco de dados."""
    try:
        # O 'with db_lock:' FOI REMOVIDO DAQUI
        cursor = db.cursor()
        cursor.execute("SELECT * FROM products ORDER BY id DESC")
        return [dict(row) for row in cursor.fetchall()]
    except sqlite3.Error as e:
        logger.error(f"Erro ao buscar todos os produtos: {e}")
        return []

# Em backend/app/database.py


def find_product_by_image_hash(image_hash: str, db: sqlite3.Connection) -> Optional[Dict]:
    """
    Busca um produto na tabela 'products' pelo hash da imagem.
    Retorna os dados do produto se encontrado.
    """
    try:
        cursor = db.cursor()
        # --- CORREÇÃO AQUI ---
        # A simples existência do hash já define uma duplicata.
        cursor.execute(
            "SELECT * FROM products WHERE image_hash = ?",
            (image_hash,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None
    except sqlite3.Error as e:
        logger.error(f"Erro ao buscar produto por hash de imagem: {e}")
        return None

# Em backend/app/database.py, no final do arquivo


def get_product_by_id(product_id: int, db: sqlite3.Connection) -> Optional[Dict]:
    """Recupera um único produto pelo seu ID."""
    try:
        cursor = db.cursor()
        cursor.execute("SELECT * FROM products WHERE id = ?", (product_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    except sqlite3.Error as e:
        logger.error(f"Erro ao buscar produto por ID {product_id}: {e}")
        return None


def update_product(product_id: int, product_data: Dict[str, Any], db: sqlite3.Connection) -> bool:
    """Atualiza um produto existente no banco de dados."""
    try:
        # Monta a query de atualização dinamicamente para os campos fornecidos
        fields_to_update = []
        params = []
        for key, value in product_data.items():
            if value is not None:
                fields_to_update.append(f"{key} = ?")
                params.append(value)

        if not fields_to_update:
            return True  # Nenhum campo para atualizar

        # Adiciona o ID no final para a cláusula WHERE
        params.append(product_id)

        query = f"""
            UPDATE products 
            SET {', '.join(fields_to_update)}, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """

        cursor = db.cursor()
        cursor.execute(query, params)
        db.commit()
        return cursor.rowcount > 0
    except sqlite3.Error as e:
        logger.error(f"Erro ao atualizar produto ID {product_id}: {e}")
        db.rollback()
        return False
# Em backend/app/database.py

def get_dashboard_kpis(db: sqlite3.Connection) -> Dict:
    """Busca os principais KPIs para os cards do dashboard."""
    cur = db.cursor()

    cur.execute("SELECT COUNT(*) as total FROM products")
    total_products = cur.fetchone()['total'] or 0

    cur.execute("SELECT COUNT(*) as total FROM processing_logs WHERE success = 1")
    successful_identifications = cur.fetchone()['total'] or 0

    cur.execute("SELECT COUNT(*) as total FROM processing_logs")
    total_identifications = cur.fetchone()['total'] or 0

    success_rate = (successful_identifications / total_identifications * 100) if total_identifications > 0 else 0

    cur.execute("SELECT AVG(processing_time) as avg_time FROM processing_logs WHERE success = 1")
    avg_time = cur.fetchone()['avg_time'] or 0

    return {
        "total_products": total_products,
        "successful_identifications": successful_identifications,
        "success_rate": round(success_rate, 1),
        "average_processing_time": round(avg_time, 2)
    }

def get_products_by_category(db: sqlite3.Connection) -> List[Dict]:
    """Retorna a contagem de produtos por categoria para o gráfico."""
    cur = db.cursor()
    cur.execute("""
        SELECT category, COUNT(*) as count 
        FROM products 
        WHERE category IS NOT NULL AND category != ''
        GROUP BY category 
        ORDER BY count DESC
    """)
    return [dict(row) for row in cur.fetchall()]

def get_recent_activities(db: sqlite3.Connection, limit: int = 5) -> List[Dict]:
    """Busca as últimas atividades (logs de processamento bem-sucedidos)."""
    cur = db.cursor()
    # Esta query é um exemplo, pode ser melhorada para buscar o nome do produto.
    cur.execute("""
        SELECT success, created_at 
        FROM processing_logs
        ORDER BY created_at DESC
        LIMIT ?
    """, (limit,))
    return [dict(row) for row in cur.fetchall()]
# Fim de backend/app/database.py
