# api/schemas.py (versão refatorada e expandida)
"""
Módulo de Schemas Pydantic para a API.

Este módulo define a estrutura, os tipos de dados e a validação para os
objetos que são recebidos e, principalmente, retornados pela API.

O uso de `from_attributes = True` permite que os modelos sejam criados
diretamente a partir de objetos do SQLAlchemy, facilitando a conversão dos
resultados do banco de dados em JSON.
"""
from pydantic import BaseModel, Field
from pydantic_settings import SettingsConfigDict
from typing import List, Optional
from datetime import datetime

# --- SSOT: HTTP response contracts (auth / rate-limit) ---
# Centralizado aqui para evitar import circular entre main.py e portal.py.
_AUTH_RESPONSES = {
    401: {"description": "API key ausente ou inválida (header X-API-KEY)."},
    402: {"description": "Assinatura inativa ou expirada. Renove em https://autosinapi.mundoaec.com/checkout."},
    429: {"description": "Limite de requisições excedido (rate limit do plano ou demo)."},
}
# Apenas o erro de rate limit se aplica aos endpoints públicos (demo 60/min).
_RATE_LIMIT_RESPONSE = {
    429: {"description": "Limite de requisições excedido (demonstração: 60 req/min, 1.000 req/mês)."},
}
# Erros levantados pelo próprio FastAPI (HTTPException) — SSOT reutilizada nos
# endpoints que de fato os produzem (coesão/DRY, STORY-API-006).
_NOT_FOUND_404 = {"description": "Recurso não encontrado para os filtros informados."}
_BAD_REQUEST_400 = {"description": "Parâmetro inválido (tipo_item ou data_fim)."}
_CONFLICT_409 = {"description": "Já existe tarefa em andamento para o período/UF (lock)."}
_SERVER_ERROR_500 = {"description": "Erro interno ao enfileirar a tarefa de ETL."}
_SERVICE_UNAVAILABLE_503 = {
    "description": "Serviço degradado: banco de dados ou Redis indisponível.",
}

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
    score: Optional[float] = None

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
    score: Optional[float] = None

    class Config:
        from_attributes = True

# --- Schemas de Busca Paginada (SPEC-RULE-SEARCH) ---

class InsumoSearchResult(BaseModel):
    """Envelope paginado da busca de insumos (modo `meta=true`)."""
    items: List["Insumo"]
    total: int

class ComposicaoSearchResult(BaseModel):
    """Envelope paginado da busca de composições (modo `meta=true`)."""
    items: List["Composicao"]
    total: int

# --- Schemas da Busca Unificada (STORY-SRC-002 / endpoint /search) ---

class SearchMeta(BaseModel):
    """Metadados de enriquecimento e degradação (SPEC-RULE-search-pipeline)."""
    providers: List[str]
    degraded: List[str] = []
    did_you_mean: Optional[str] = None
    page: Optional[int] = None
    page_size: Optional[int] = None
    total: Optional[int] = None
    relaxed: bool = False

class UsadoEmItem(BaseModel):
    composicao_codigo: int
    composicao_descricao: Optional[str] = None
    nivel: Optional[int] = None

class UsadoEm(BaseModel):
    total: int
    items: List[UsadoEmItem] = []

class UnifiedSearchItem(BaseModel):
    """Item unificado da busca (insumo ou composição)."""
    codigo: int
    descricao: str
    unidade: str
    tipo: str
    valor: Optional[float] = None
    classificacao: Optional[str] = None
    grupo: Optional[str] = None
    score: Optional[float] = None
    usado_em: Optional[UsadoEm] = None

class UnifiedSearchResult(BaseModel):
    """Envelope da busca unificada (paginação + meta de camadas)."""
    items: List[UnifiedSearchItem]
    total: int
    meta: SearchMeta

class SearchSuggestItem(BaseModel):
    """Sugestão de autocomplete cross-type."""
    codigo: int
    descricao: str
    unidade: str
    tipo: str
    score: Optional[float] = 0.0

class SearchSuggestResult(BaseModel):
    items: List[SearchSuggestItem]

class RelatedComposicao(BaseModel):
    """Composição relacionada por similaridade Jaccard do BOM."""
    codigo: int
    descricao: str
    unidade: Optional[str] = None
    sobreposicao: Optional[int] = 0
    alvo_itens: Optional[int] = 0
    jaccard: Optional[float] = None

class SearchRelatedResult(BaseModel):
    items: List[RelatedComposicao]

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
    variacao_mensal: Optional[float] = None
    variacao_pct: Optional[float] = None
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
    variacao_mensal: Optional[float] = None
    variacao_pct: Optional[float] = None
    media_movel: Optional[float] = None

    class Config:
        from_attributes = True

class PrecoPorUF(BaseModel):
    """Schema para o preço de um item em uma UF específica."""
    uf: str
    valor: float

    class Config:
        from_attributes = True

class RegionalStats(BaseModel):
    """Schema com estatísticas regionais de preços entre UFs."""
    media: float = 0.0
    mediana: float = 0.0
    min: float = 0.0
    max: float = 0.0
    desvio_padrao: float = 0.0
    amplitude: float = 0.0
    uf_mais_barato: Optional[str] = None
    uf_mais_cara: Optional[str] = None

class CenarioComposicao(BaseModel):
    """Schema para uma composição dentro de um cenário consolidado."""
    codigo: int
    descricao: str
    custo_total: float

class CenarioTendencia(BaseModel):
    """Schema para um ponto de tendência mensal do custo total do cenário."""
    data_referencia: str
    valor: float
    variacao_mensal: Optional[float] = None
    variacao_pct: Optional[float] = None

class CenarioResponse(BaseModel):
    """Schema para resposta consolidada de cenário BI ('PowerBI do SINAPI')."""
    uf: str
    data_referencia: str
    regime: str
    composicoes: List[CenarioComposicao]
    total_bom: float
    abc: List[CurvaABCItem]
    spread_regional: RegionalStats
    tendencias: List[CenarioTendencia]

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


# --- Schemas de Requisição (POST) ---
# DTOs de entrada: usam model_config (Pydantic v2) com json_schema_extra para
# expor exemplos visíveis no Swagger (SPEC-RULE Regra 2.3 / GUIDE 2.1.2).
# Mantidos separados dos schemas de leitura (DDD: camada de aplicação vs domínio).

class CurvaABCRequest(BaseModel):
    """Corpo de requisição para cálculo de Curva ABC a partir de composições."""
    model_config = SettingsConfigDict(
        json_schema_extra={"example": {"codigos": [92711, 88307]}}
    )
    codigos: List[int]


class PopulateDatabaseRequest(BaseModel):
    """Corpo de requisição para disparar a população assíncrona da base SINAPI."""
    model_config = SettingsConfigDict(
        json_schema_extra={"example": {"year": 2025, "month": 9, "state": "SP"}}
    )
    year: int
    month: int
    state: str = Field(default="SP", min_length=2, max_length=2)


class PlanInfo(BaseModel):
    slug: str
    name: str
    price_cents: int


class QuotaInfo(BaseModel):
    used: int
    limit: int
    percentage: float


class PortalLinks(BaseModel):
    upgrade: dict
    downgrade: Optional[str] = None
    renew: str


class PortalResponse(BaseModel):
    client_id: str
    plan: PlanInfo
    subscription: dict
    quota: QuotaInfo
    features: dict
    links: PortalLinks