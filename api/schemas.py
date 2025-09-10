# api/schemas.py (versão refatorada e expandida)
"""
Módulo de Schemas Pydantic para a API.

Este módulo define a estrutura, os tipos de dados e a validação para os
objetos que são recebidos e, principalmente, retornados pela API.

O uso de `from_attributes = True` permite que os modelos sejam criados
diretamente a partir de objetos do SQLAlchemy, facilitando a conversão dos
resultados do banco de dados em JSON.
"""
from pydantic import BaseModel
from typing import List, Optional

# --- Schemas Base (CRUD) ---

class Insumo(BaseModel):
    """Schema para um insumo com seu preço contextual."""
    codigo: int
    descricao: str
    unidade: str
    preco_mediano: Optional[float] = None

    class Config:
        from_attributes = True

class Composicao(BaseModel):
    """Schema para uma composição com seu custo contextual."""
    codigo: int
    descricao: str
    unidade: str
    custo_total: Optional[float] = None

    class Config:
        from_attributes = True

# --- Schemas de Business Intelligence (BI) ---

class ComposicaoBOMItem(BaseModel):
    """Schema para um item dentro do Bill of Materials de uma composição."""
    item_codigo: int
    tipo_item: str
    descricao: str
    unidade: str
    coeficiente_total: float
    custo_unitario: Optional[float] = None
    custo_impacto_total: Optional[float] = None

    class Config:
        from_attributes = True

class ComposicaoManHours(BaseModel):
    """Schema para o resultado do cálculo de Hora/Homem."""
    total_hora_homem: Optional[float] = 0.0

class CurvaABCItem(BaseModel):
    """Schema para um item na análise da Curva ABC."""
    codigo: int
    descricao: str
    unidade: str
    custo_total_agregado: float
    percentual_individual: float
    percentual_acumulado: float
    classe_abc: str

    class Config:
        from_attributes = True

class HistoricoCusto(BaseModel):
    """Schema para um ponto de dado no histórico de custo de um item."""
    data_referencia: str
    valor: float

    class Config:
        from_attributes = True