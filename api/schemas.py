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
from datetime import datetime

# --- Traceability Mixin ---
class TraceabilityMixin(BaseModel):
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    sinapi_versao: Optional[str] = None

# --- Schemas Base (CRUD) ---

class Insumo(TraceabilityMixin):
    """Schema para um insumo com seu preço contextual."""
    codigo: int
    descricao: str
    unidade: str
    preco_mediano: Optional[float] = None
    classificacao: Optional[str] = None
    origem_preco: Optional[str] = None
    status: Optional[str] = None

    class Config:
        from_attributes = True

class Composicao(TraceabilityMixin):
    """Schema para uma composição com seu custo contextual."""
    codigo: int
    descricao: str
    unidade: str
    custo_total: Optional[float] = None
    grupo: Optional[str] = None
    percentual_mo: Optional[float] = None
    status: Optional[str] = None

    class Config:
        from_attributes = True

# --- Schemas de Business Intelligence (BI) ---

class ComposicaoBOMItem(BaseModel):
    """Schema para um item dentro do Bill of Materials de uma composição."""
    item_codigo: int
    tipo_item: str
    nivel: int
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

class HistoricoCusto(TraceabilityMixin):
    """Schema para um ponto de dado no histórico de custo de um item."""
    data_referencia: str
    valor: float
    foi_retificado: Optional[bool] = False
    versao_original: Optional[str] = None
    versao_atual: Optional[str] = None

    class Config:
        from_attributes = True

class HistoricoManutencao(TraceabilityMixin):
    """Schema para um registro de manutenção (ativação/desativação) de item."""
    item_codigo: int
    tipo_item: str
    data_referencia: str
    tipo_manutencao: str
    descricao_item: Optional[str] = None

    class Config:
        from_attributes = True

class AuditEvent(BaseModel):
    """Schema para um evento de auditoria no sinapi_audit_log."""
    id: int
    table_name: str
    record_pk: dict
    operation: str
    old_values: Optional[dict] = None
    new_values: Optional[dict] = None
    sinapi_versao: Optional[str] = None
    motivo_manutencao: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class AbcPorClassificacao(BaseModel):
    """Schema para análise ABC agrupada por classificação de insumo."""
    classificacao: str
    custo_total: float
    percentual: float
    total_insumos: int

    class Config:
        from_attributes = True

class TendenciaClassificacao(BaseModel):
    """Schema para um ponto de tendência de preço por classificação."""
    classificacao: str
    mes: str
    preco_medio: float
    qtd_insumos: int

    class Config:
        from_attributes = True

class PrecoPorUF(BaseModel):
    """Schema para o preço de um item em uma UF específica."""
    uf: str
    valor: float

    class Config:
        from_attributes = True

class ComposicaoProdutividade(BaseModel):
    """Schema para análise de produtividade de uma composição."""
    total_custo: float
    mao_de_obra: float
    material: float
    equipamento: float
    total_hh: float
    custo_por_hh: Optional[float] = None

class InsumoOndeUsado(BaseModel):
    """Schema para um item na lista 'onde é usado'."""
    composicao_codigo: int
    composicao_descricao: str
    tipo_item: str
    coeficiente: float
    nivel: int