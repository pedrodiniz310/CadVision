# backend/app/models.py
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class SaveProductIn(BaseModel):
    gtin: Optional[str] = None
    title: str
    brand: Optional[str] = None
    category: Optional[str] = None
    price: Optional[float] = None
    ncm: Optional[str] = None
    cest: Optional[str] = None
    confidence: Optional[float] = None

class ProductOut(BaseModel):
    id: int
    gtin: Optional[str]
    title: str
    brand: Optional[str]
    # ... adicione os outros campos que você retorna na lista de produtos