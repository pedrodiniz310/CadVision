# backend/app/database.py
import sqlite3
import threading
from pathlib import Path
from contextlib import contextmanager
from typing import Generator, Optional, Any, Dict, List
from app.core.config import DB_PATH
import logging
from app.core.logging_config import log_structured_event

logger = logging.getLogger(__name__)
# Garantir que o diretório existe
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


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

            # 1. Tabela principal de PRODUTOS - AGORA COM A COLUNA 'vertical'
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
                    vertical TEXT NOT NULL DEFAULT 'supermercado', -- <- NOVA COLUNA
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # --- NOVA TABELA PARA ATRIBUTOS DE VESTUÁRIO ---
            cur.execute("""
                CREATE TABLE IF NOT EXISTS attributes_clothing (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_id INTEGER UNIQUE NOT NULL,
                    size TEXT,      -- Tamanho (ex: P, M, G, 42)
                    color TEXT,     -- Cor (ex: Azul, Preto)
                    fabric TEXT,    -- Tecido (ex: Algodão, Poliéster)
                    gender TEXT,    -- Gênero (ex: Masculino, Feminino, Unissex)
                    FOREIGN KEY (product_id) REFERENCES products (id) ON DELETE CASCADE
                )
            """)
            # --- FIM DA NOVA TABELA ---

            # O resto da função permanece o mesmo...
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

            cur.execute("""
                CREATE TABLE IF NOT EXISTS known_brands (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    category TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS product_categories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    keywords TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_products_gtin ON products(gtin)")
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_logs_image_hash ON processing_logs(image_hash)")

            # Novo índice para a chave estrangeira
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_clothing_product_id ON attributes_clothing(product_id)")

            cur.execute("SELECT COUNT(*) FROM product_categories")
            if cur.fetchone()[0] == 0:
                default_categories = [
                    ('Alimentos', 'arroz,feijão,macarrão,óleo,açúcar,farinha,leite,café,biscoito,wafer,sêmola'),
                    ('Bebidas', 'refrigerante,cerveja,suco,água,vinho,whisky,vodka'),
                    ('Limpeza', 'sabão,detergente,desinfetante,álcool,água sanitária,amaciante'),
                    ('Higiene', 'shampoo,condicionador,sabonete,pasta de dente,papel higiênico,lenços'),
                    ('Eletrônicos', 'celular,tv,notebook,tablet,fone de ouvido,câmera'),
                    # Novas categorias
                    ('Vestuário', 'camisa,calça,vestido,tênis,sapato,roupa,moda'),
                    ('Automotivo', 'carro,motor,óleo,pneu'),
                    ('Construção', 'cimento,tijolo,ferro,obra')
                ]
                cur.executemany(
                    "INSERT INTO product_categories (name, keywords) VALUES (?, ?)",
                    default_categories
                )

            conn.commit()
        logger.info(
            "Banco de dados inicializado com sucesso (com novo schema).")
    except sqlite3.Error as e:
        logger.error(f"Erro ao inicializar o banco de dados: {e}")

# Em backend/app/database.py


# Em backend/app/database.py

# Em backend/app/database.py

# backend/app/database.py

def insert_product(product_data: Dict[str, Any], db: sqlite3.Connection) -> Optional[int]:
    """
    Insere um novo produto e seus atributos de forma transacional e segura.
    """
    cur = db.cursor()

    # LOG DETALHADO PARA DEBUG
    logger.info(
        f"Tentativa de inserir produto com dados: { {k: v for k, v in product_data.items() if k != 'attributes'} }")

    # Validação defensiva melhorada
    title = product_data.get('title', '').strip()
    if not title:
        logger.error(
            f"Título vazio após todas as validações. Dados: {product_data}")
        raise ValueError(
            "O título do produto não pode ser vazio após validações.")

    # ... resto do código existente ...

    # Separa os atributos específicos (ex: size, color) do dicionário principal
    attributes = product_data.pop('attributes', None)
    vertical = product_data.get('vertical', 'supermercado')

    try:
        # Prepara os campos e valores de forma segura, garantindo a ordem
        fields = list(product_data.keys())
        values = list(product_data.values())

        field_names = ', '.join(fields)
        placeholders = ', '.join(['?'] * len(fields))

        cur.execute(
            f"INSERT INTO products ({field_names}) VALUES ({placeholders})", tuple(values))
        product_id = cur.lastrowid

        # Se for um produto de vestuário e tiver atributos, insere na tabela específica
        if vertical == 'vestuario' and attributes:
            attributes['product_id'] = product_id
            attr_fields = ', '.join(attributes.keys())
            attr_placeholders = ', '.join(['?'] * len(attributes))
            cur.execute(f"INSERT INTO attributes_clothing ({attr_fields}) VALUES ({attr_placeholders})", tuple(
                attributes.values()))

        db.commit()  # Confirma a transação (salva em ambas as tabelas)
        logger.info(
            f"Produto ID {product_id} (Vertical: {vertical}) salvo com sucesso.")
        return product_id

    except (sqlite3.Error, ValueError) as e:
        logger.error(f"Erro ao inserir produto: {e}")
        db.rollback()  # Desfaz tudo se der erro
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


# Em backend/app/database.py

def get_product_by_id(product_id: int, db: sqlite3.Connection) -> Optional[Dict]:
    """
    Recupera um único produto pelo seu ID, juntando os atributos específicos da vertical, se existirem.
    """
    try:
        cursor = db.cursor()
        # Busca os dados base do produto
        cursor.execute("SELECT * FROM products WHERE id = ?", (product_id,))
        row = cursor.fetchone()

        if not row:
            return None

        product_dict = dict(row)

        # Se for um produto de vestuário, busca seus atributos
        if product_dict.get('vertical') == 'vestuario':
            cursor.execute(
                "SELECT size, color, fabric, gender FROM attributes_clothing WHERE product_id = ?", (product_id,))
            attr_row = cursor.fetchone()
            if attr_row:
                product_dict['attributes'] = dict(attr_row)

        return product_dict
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

    cur.execute(
        "SELECT COUNT(*) as total FROM processing_logs WHERE success = 1")
    successful_identifications = cur.fetchone()['total'] or 0

    cur.execute("SELECT COUNT(*) as total FROM processing_logs")
    total_identifications = cur.fetchone()['total'] or 0

    success_rate = (successful_identifications /
                    total_identifications * 100) if total_identifications > 0 else 0

    cur.execute(
        "SELECT AVG(processing_time) as avg_time FROM processing_logs WHERE success = 1")
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

# backend/app/database.py

# ... (código existente)


def get_success_rate_by_date(db: sqlite3.Connection) -> List[Dict]:
    """
    Retorna a taxa de sucesso e o tempo médio de análise por data dos últimos 30 dias.
    """
    cur = db.cursor()
    cur.execute("""
        SELECT
            DATE(created_at) AS date,
            CAST(SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) AS REAL) * 100 / COUNT(*) AS success_rate,
            AVG(processing_time) AS avg_time
        FROM processing_logs
        WHERE created_at >= date('now', '-30 days')
        GROUP BY date
        ORDER BY date ASC
    """)
    return [dict(row) for row in cur.fetchall()]

# backend/app/database.py

# ... (código existente) ...


def get_products_by_period(db: sqlite3.Connection, period: str = 'day') -> List[Dict]:
    """
    Retorna a contagem de produtos cadastrados por período (day, month, year).
    """
    if period == 'month':
        date_format = '%Y-%m'
    elif period == 'year':
        date_format = '%Y'
    else:
        date_format = '%Y-%m-%d'

    cur = db.cursor()
    cur.execute(f"""
        SELECT
            STRFTIME('{date_format}', created_at) AS period,
            COUNT(*) AS count
        FROM products
        GROUP BY period
        ORDER BY period ASC
    """)
    return [dict(row) for row in cur.fetchall()]
# Fim de backend/app/database.py
