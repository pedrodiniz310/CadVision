# backend/app/models.py
from pydantic import BaseModel, Field, validator, HttpUrl
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum
import re


class ProductCategory(str, Enum):
    """Categorias de produtos predefinidas."""
    FOOD = "Alimentos"
    BEVERAGES = "Bebidas"
    CLEANING = "Limpeza"
    HYGIENE = "Higiene"
    ELECTRONICS = "Eletrônicos"
    CLOTHING = "Vestuário"
    AUTOMOTIVE = "Automotivo"
    CONSTRUCTION = "Construção"
    OTHER = "Outros"


class ProcessingStatus(str, Enum):
    """Status do processamento de imagem."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ProductBase(BaseModel):
    """Modelo base para produtos."""
    title: str = Field(
        ...,
        description="Título ou nome do produto",
        max_length=200,
        example="Arroz Integral Tipo 1"
    )
    vertical: str = Field(
        "supermercado",
        description="A vertical do produto, ex: supermercado, vestuario"
    )  # <-- ADICIONE ESTE CAMPO NO INÍCIO
    gtin: Optional[str] = Field(
        None,
        description="Código GTIN/EAN do produto (8, 12, 13 ou 14 dígitos)",
        example="7891234567890"
    )
    brand: Optional[str] = Field(
        None,
        description="Marca do produto",
        max_length=100,
        example="Tio João"
    )
    category: Optional[str] = Field(
        None,
        description="Categoria do produto"
    )
    price: Optional[float] = Field(
        None,
        description="Preço do produto em Reais",
        ge=0,
        example=12.90
    )
    ncm: Optional[str] = Field(
        None,
        description="Código NCM (Nomenclatura Comum do Mercosul)",
        example="1006.30.90"
    )
    cest: Optional[str] = Field(
        None,
        description="Código CEST (Código Especificador da Substituição Tributária)",
        example="13.001.00"
    )

    @validator('gtin')
    def validate_gtin(cls, v):
        """Valida o formato do GTIN."""
        if v is None:
            return v

        # Remove qualquer caractere não numérico
        v = re.sub(r'[^\d]', '', v)

        # Verifica se tem comprimento válido
        if len(v) not in [8, 12, 13, 14]:
            raise ValueError('GTIN deve ter 8, 12, 13 ou 14 dígitos')

        return v

    @validator('ncm')
    def validate_ncm(cls, v):
        """Valida o formato do NCM."""
        if v is None:
            return v

        # Formato básico do NCM: 8 dígitos (podem ter pontos)
        if not re.match(r'^\d{4}\.?\d{2}\.?\d{2}$', v):
            raise ValueError('NCM deve estar no formato 9999.99.99')

        return v

    @validator('cest')
    def validate_cest(cls, v):
        """Valida o formato do CEST."""
        if v is None:
            return v

        # Formato básico do CEST: 7 dígitos (podem ter pontos)
        if not re.match(r'^\d{2}\.?\d{3}\.?\d{2}$', v):
            raise ValueError('CEST deve estar no formato 99.999.99')

        return v


class ProductCreate(ProductBase):
    """Modelo para criação de produto."""
    confidence: Optional[float] = Field(
        None,
        description="Nível de confiança da identificação pela IA (0-1)",
        ge=0,
        le=1,
        example=0.85
    )
    image_hash: Optional[str] = Field(
        None,
        description="Hash da imagem usada para identificação"
    )

# Em backend/app/models.py

# ... (cole este código depois da classe ProductCreate)

class ClothingAttributes(BaseModel):
    """Modelo para os atributos específicos de vestuário."""
    size: Optional[str] = Field(None, description="Tamanho da peça (P, M, G, 42, etc.)")
    color: Optional[str] = Field(None, description="Cor principal da peça")
    fabric: Optional[str] = Field(None, description="Material/tecido da peça")
    gender: Optional[str] = Field(None, description="Gênero (Masculino, Feminino, Unissex)")


class ProductCreateClothing(ProductCreate):
    """Modelo para criar um produto de vestuário, combinando dados base e atributos específicos."""
    attributes: ClothingAttributes


class ProductCreateSupermarket(ProductCreate):
    """Modelo para criar um produto de supermercado (sem atributos extras)."""
    pass # Herda todos os campos de ProductCreate
class ProductUpdate(ProductBase):
    """Modelo para atualização de produto."""
    pass


class ProductInDB(ProductBase):
    """Modelo para produto no banco de dados."""
    id: int = Field(..., description="ID único do produto")
    confidence: Optional[float] = Field(
        None,
        description="Nível de confiança da identificação pela IA"
    )
    image_hash: Optional[str] = Field(
        None,
        description="Hash da imagem usada para identificação"
    )
    created_at: datetime = Field(...,
                                 description="Data de criação do registro")
    updated_at: datetime = Field(...,
                                 description="Data da última atualización")

    class Config:
        from_attributes = True


class ProductOut(ProductInDB):
    """Modelo para resposta de produto."""
    pass


class IdentifiedProduct(BaseModel):
    """Modelo para produto identificado (sem campos de banco de dados)."""
    gtin: Optional[str] = Field(
        None,
        description="Código GTIN/EAN do produto (8, 12, 13 ou 14 dígitos)",
        example="7891234567890"
    )
    title: str = Field(
        ...,
        description="Nome do produto",
        max_length=200,
        example="Arroz Integral Tipo 1"
    )
    brand: Optional[str] = Field(
        None,
        description="Marca do produto",
        max_length=100,
        example="Tio João"
    )
    category: Optional[str] = Field(  # Alterado de ProductCategory para str
        None,
        description="Categoria do produto"
    )
    price: Optional[float] = Field(
        None,
        description="Preço do produto em Reais",
        ge=0,
        example=12.90
    )
    ncm: Optional[str] = Field(
        None,
        description="Código NCM (Nomenclatura Comum do Mercosul)",
        example="1006.30.90"
    )
    cest: Optional[str] = Field(
        None,
        description="Código CEST (Código Especificador da Substituição Tributária)",
        example="13.001.00"
    )
    confidence: Optional[float] = Field(
        None,
        description="Nível de confiança da identificação pela IA (0-1)",
        ge=0,
        le=1,
        example=0.85
    )

    # Validações ajustadas para campos opcionais
    @validator('gtin')
    def validate_gtin(cls, v):
        """Valida o formato do GTIN apenas se presente."""
        if v is None or v == "":
            return None

        # Remove qualquer caractere não numérico
        v = re.sub(r'[^\d]', '', v)

        # Verifica se tem comprimento válido
        if len(v) not in [8, 12, 13, 14]:
            raise ValueError('GTIN deve ter 8, 12, 13 ou 14 dígitos')

        return v

    @validator('ncm')
    def validate_ncm(cls, v):
        """Valida o formato do NCM apenas se presente."""
        if v is None or v == "":
            return None

        # Formato básico do NCM: 8 dígitos (podem ter pontos)
        if not re.match(r'^\d{4}\.?\d{2}\.?\d{2}$', v):
            raise ValueError('NCM deve estar no formato 9999.99.99')

        return v

    @validator('cest')
    def validate_cest(cls, v):
        """Valida o formato do CEST apenas se presente."""
        if v is None or v == "":
            return None

        # Formato básico do CEST: 7 dígitos (podem ter pontos)
        if not re.match(r'^\d{2}\.?\d{3}\.?\d{2}$', v):
            raise ValueError('CEST deve estar no formato 99.999.99')

    @validator('category', pre=True)
    def validate_category(cls, v):
        """Valida e normaliza a categoria."""
        if v is None or v == "":
            return None

        # Converte para o formato padrão (primeira letra maiúscula)
        v = v.strip().title()

        # Mapeia variações comuns para as categorias padrão
        category_mapping = {
            'Alimento': 'Alimentos',
            'Comida': 'Alimentos',
            'Bebida': 'Bebidas',
            'Limpeza': 'Limpeza',
            'Higiene': 'Higiene',
            'Eletronico': 'Eletrônicos',
            'Eletrônica': 'Eletrônicos',
            'Roupa': 'Vestuário',
            'Vestuario': 'Vestuário',
            'Automotivo': 'Automotivo',
            'Carro': 'Automotivo',
            'Construcao': 'Construção',
            'Construção': 'Construção',
            'Outro': 'Outros'
        }

        return category_mapping.get(v, v)


class IdentificationRequest(BaseModel):
    """Modelo para requisição de identificação."""
    image_data: Optional[str] = Field(
        None,
        description="Dados da imagem em base64 (alternativa ao image_url)"
    )
    image_url: Optional[HttpUrl] = Field(
        None,
        description="URL da imagem a ser identificada (alternativa ao image_data)"
    )

    @validator('image_data', pre=True, always=True)
    def validate_image_input(cls, v, values):
        """Valida que pelo menos uma forma de imagem foi fornecida."""
        if v is None and values.get('image_url') is None:
            raise ValueError('É necessário fornecer image_data ou image_url')
        return v


class IdentificationResult(BaseModel):
    """Modelo para resultado de identificação."""
    success: bool = Field(...,
                          description="Indica se a identificação foi bem-sucedida")
    status: str = Field(
        "newly_identified",
        description="Status: 'newly_identified', 'duplicate_found', ou 'failed'"
    )
    product: Optional[IdentifiedProduct] = Field(
        None, description="Produto identificado")
    image_hash: Optional[str] = Field(
        None, description="Hash da imagem processada")
    raw_text: Optional[str] = Field(
        None, description="Texto cru extraído da imagem")
    detected_logos: List[str] = Field(
        default_factory=list, description="Logos detectadas")
    confidence: float = Field(
        0, description="Confiança geral da identificação", ge=0, le=1)
    processing_time: Optional[float] = Field(
        None, description="Tempo de processamento em segundos")
    error_message: Optional[str] = Field(
        None, description="Mensagem de erro em caso de falha")


class ProcessingLog(BaseModel):
    """Modelo para log de processamento."""
    id: int
    image_hash: str
    processing_time: float
    success: bool
    confidence: Optional[float]
    error_message: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class ProcessingStats(BaseModel):
    """Modelo para estatísticas de processamento."""
    total_processments: int = Field(..., description="Total de processamentos")
    successful_processments: int = Field(...,
                                         description="Processamentos bem-sucedidos")
    success_rate: float = Field(..., description="Taxa de sucesso (0-1)")
    average_processing_time: float = Field(
        ..., description="Tempo médio de processamento em segundos")
    by_category: Dict[str, int] = Field(
        default_factory=dict, description="Contagem por categoria")
    by_brand: Dict[str, int] = Field(
        default_factory=dict, description="Contagem por marca")


class PaginatedResponse(BaseModel):
    """Modelo para respostas paginadas."""
    items: List[Any] = Field(..., description="Itens da página atual")
    total: int = Field(..., description="Total de itens disponíveis")
    page: int = Field(..., description="Página atual")
    pages: int = Field(..., description="Total de páginas")
    size: int = Field(..., description="Tamanho da página")


class APIResponse(BaseModel):
    """Modelo padrão para respostas da API."""
    success: bool = Field(...,
                          description="Indica se a requisição foi bem-sucedida")
    message: Optional[str] = Field(None, description="Mensagem descritiva")
    data: Optional[Any] = Field(None, description="Dados da resposta")
    error_code: Optional[str] = Field(
        None, description="Código do erro em caso de falha")

    @classmethod
    def success_response(cls, data: Any = None, message: str = "Operação realizada com sucesso"):
        return cls(success=True, message=message, data=data)

    @classmethod
    def error_response(cls, message: str, error_code: str = None):
        return cls(success=False, message=message, error_code=error_code)

# Em backend/app/models.py

class ProductCreateSupermarket(ProductCreate):
    """Modelo para criar um produto de supermercado (sem atributos extras)."""
    pass # Herda todos os campos de ProductCreate