# api/schemas.py
from pydantic import BaseModel

# Schema base para um Insumo, usado na resposta da API
class Insumo(BaseModel):
    codigo: str
    descricao: str
    unidade: str
    preco_mediano: float

    class Config:
        orm_mode = True # Permite que o Pydantic leia dados de objetos do ORM (SQLAlchemy)

# Schema base para uma Composicao, usado na resposta da API
class Composicao(BaseModel):
    codigo: str
    descricao: str
    unidade: str
    custo_total: float # O nome do campo de preço/custo pode ser diferente

    class Config:
        orm_mode = True
