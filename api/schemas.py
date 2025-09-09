# api/schemas.py (versão refatorada e expandida)
"""
Módulo de Schemas Pydantic para a API.

Define a estrutura dos dados que serão recebidos e enviados pela API.
Esses modelos garantem a validação, serialização e documentação automática
dos dados, sendo um pilar fundamental do FastAPI.
"""
from pydantic import BaseModel
from typing import List, Optional

class Insumo(BaseModel):
    codigo: int
    descricao: str
    unidade: str
    preco_mediano: Optional[float] = None
    class Config: from_attributes = True

class Composicao(BaseModel):
    codigo: int
    descricao: str
    unidade: str
    custo_total: Optional[float] = None
    class Config: from_attributes = True

class ComposicaoBOMItem(BaseModel):
    item_codigo: int
    tipo_item: str
    descricao: str
    unidade: str
    coeficiente_total: float
    custo_unitario: Optional[float] = None
    custo_impacto_total: Optional[float] = None
    class Config: from_attributes = True

class ComposicaoManHours(BaseModel):
    total_hora_homem: Optional[float] = 0.0

class CurvaABCItem(BaseModel):
    codigo: int
    descricao: str
    unidade: str
    custo_total_agregado: float
    percentual_individual: float
    percentual_acumulado: float
    classe_abc: str
    class Config: from_attributes = True
