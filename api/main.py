# api/main.py (versão refatorada e com endpoints de BI)
"""
Ponto de entrada principal da AutoSINAPI API.

Este módulo define todos os endpoints da API utilizando FastAPI,
orquestrando as chamadas para as funções do módulo `crud` e utilizando os
`schemas` para validação e serialização de dados.
"""

import os
import json
import time
import logging
import redis
from celery.result import AsyncResult
from .sandbox_utils import is_sandbox_mode
from typing import List
from fastapi import FastAPI, Depends, HTTPException, Query, Body, Path, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.orm import Session
from datetime import date, datetime
from dateutil.relativedelta import relativedelta

from . import crud, schemas, config
from .database import get_db
from .tasks import populate_sinapi_task
from .cache_utils import redis_client as cache_redis

# Carrega as configurações uma vez
settings = config.settings

# Structured Logging
class JSONLogFormatter(logging.Formatter):
    def format(self, record):
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "endpoint"):
            log_entry["endpoint"] = record.endpoint
        if hasattr(record, "duration"):
            log_entry["duration_ms"] = round(record.duration * 1000, 2)
        if record.exc_info and record.exc_info[0]:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry, ensure_ascii=False)

# Configure root logger with JSON format
json_handler = logging.StreamHandler()
json_handler.setFormatter(JSONLogFormatter())
root_logger = logging.getLogger()
root_logger.handlers = [json_handler]
root_logger.setLevel(logging.INFO)

logger = logging.getLogger("autosinapi.api")

app = FastAPI(
    title="AutoSINAPI API",
    description="API para consulta de preços, custos, estruturas e análises da base de dados SINAPI.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS.split(",") if settings.ALLOWED_ORIGINS != "*" else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static GeoJSON data
import os
_data_dir = os.path.join(os.path.dirname(__file__), "..", "demo", "data")
if os.path.isdir(_data_dir):
    app.mount("/api/v1/public/data/geo", StaticFiles(directory=_data_dir), name="data")

# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration = time.time() - start
    extra = {"endpoint": request.url.path, "duration": duration}
    logger.info(f"{request.method} {request.url.path} {response.status_code}", extra=extra)
    return response

@app.get("/api/v1/public/health", tags=["Health"])
def health_check(db: Session = Depends(get_db)):
    """
    Health check endpoint. Retorna status do banco, Redis e versão da API.
    """
    checks = {"status": "healthy", "version": "1.0.0", "timestamp": datetime.utcnow().isoformat() + "Z"}

    try:
        db.execute(text("SELECT 1"))
        checks["database"] = "connected"
    except Exception as e:
        checks["database"] = f"error: {str(e)}"
        checks["status"] = "degraded"

    try:
        cache_redis.ping()
        checks["redis"] = "connected"
    except Exception as e:
        checks["redis"] = f"error: {str(e)}"
        checks["status"] = "degraded"

    status_code = 200 if checks["status"] == "healthy" else 503
    return JSONResponse(content=checks, status_code=status_code)

# Conexão direta com Redis para lock de tarefas (idempotência)
redis_client = redis.Redis(host=os.getenv("REDIS_HOST", "redis"), port=6379, db=0)

@app.get("/api/v1/public/stats", tags=["Public"])
def get_database_stats(db: Session = Depends(get_db)):
    """
    Retorna estatísticas de volumetria do banco de dados.
    """
    return crud.get_global_stats(db)

@app.get("/api/v1/public/filters", tags=["Public"])
def get_filters(
    tipo: str = Query(None, description="Filtrar por tipo: 'insumo' (retorna classificacoes) ou 'composicao' (retorna grupos)."),
    db: Session = Depends(get_db)
):
    """
    Retorna os filtros dinâmicos disponíveis no banco.
    Opcionalmente filtra por tipo para retornar classificações ou grupos.
    """
    result = crud.get_available_filters(db)
    if tipo == 'insumo':
        result.pop('grupos', None)
    elif tipo == 'composicao':
        result.pop('classificacoes', None)
    return result

# --- Endpoints de Administração ---

@app.post("/api/v1/admin/populate-database", status_code=202, tags=["Admin"])
def trigger_database_population(
    year: int = Body(..., example=2025), 
    month: int = Body(..., example=9),
    state: str = Body("SP", example="SP", min_length=2, max_length=2)
):
    """
    Dispara a tarefa de download e população da base SINAPI para um mês/ano/UF.
    A tarefa roda em segundo plano. Implementa trava (lock) para evitar duplicações.
    """
    sandbox = is_sandbox_mode()
    lock_key = f"lock:autosinapi:populate:{year}:{month:02d}:{state.upper()}:{'sandbox' if sandbox else 'prod'}"

    if not redis_client.set(lock_key, "active", nx=True, ex=3600):
        raise HTTPException(
            status_code=409,
            detail=f"Já existe uma tarefa em andamento para {state.upper()} {month:02d}/{year}."
        )

    db_config = {
        "host": os.getenv("POSTGRES_NAME", "autosinapi_db"),
        "port": 5432,
        "database": os.getenv("POSTGRES_DB", "sinapi"),
        "user": os.getenv("POSTGRES_USER", "admin"),
        "password": os.getenv("POSTGRES_PASSWORD", "admin"),
    }
    sinapi_config = { 
        "year": year, 
        "month": month, 
        "state": state.upper(),
        "type": "REFERENCIA"
    }

    try:
        task = populate_sinapi_task.delay(db_config, sinapi_config)
        redis_client.set(f"task:{lock_key}", task.id, ex=86400)
        return {
            "message": "Tarefa de população da base de dados iniciada com sucesso.",
            "task_id": task.id,
            "sandbox": sandbox
        }
    except Exception as e:
        redis_client.delete(lock_key)
        raise HTTPException(status_code=500, detail=f"Falha ao enfileirar tarefa: {str(e)}")

@app.get("/api/v1/admin/tasks/{task_id}", tags=["Admin"])
def get_task_status(task_id: str):
    """Verifica o status e resultado de uma tarefa Celery."""
    result = AsyncResult(task_id, app=populate_sinapi_task.app)
    return {
        "task_id": task_id,
        "status": result.status,
        "ready": result.ready(),
        "result": str(result.result) if result.ready() else None
    }



@app.get("/", tags=["Root"])
def read_root():
    return {"message": "Bem-vindo à API AutoSINAPI. Acesse /docs para a documentação interativa."}


# --- Endpoints de Insumos ---

@app.get("/api/v1/public/insumos/{codigo}", response_model=schemas.Insumo, tags=["Insumos"])
def read_insumo_by_codigo(
    codigo: int,
    uf: str = Query(..., description="Unidade Federativa (UF). Ex: SP", min_length=2, max_length=2),
    data_referencia: str = Query(..., description="Data de referência no formato AAAA-MM. Ex: 2025-09"),
    regime: str = Query("NAO_DESONERADO", description="Regime de preço."),
    db: Session = Depends(get_db)
):
    """
    Obtém um insumo específico e seu preço para um determinado contexto.
    """
    db_insumo = crud.get_insumo_by_codigo(db, codigo=codigo, uf=uf, data_referencia=data_referencia, regime=regime)
    if db_insumo is None:
        raise HTTPException(status_code=404, detail="Insumo não encontrado para os filtros especificados.")
    return db_insumo

@app.get("/api/v1/public/insumos", response_model=List[schemas.Insumo], tags=["Insumos"])
def search_insumos(
    q: str = Query(..., min_length=3, description="Termo para buscar na descrição do insumo."),
    uf: str = Query(..., description="Unidade Federativa (UF). Ex: SP", min_length=2, max_length=2),
    data_referencia: str = Query(..., description="Data de referência no formato AAAA-MM. Ex: 2025-09"),
    regime: str = Query("NAO_DESONERADO", description="Regime de preço."),
    classificacao: str = Query(None, description="Filtrar por classificação do insumo. Ex: AGREGADOS, ACO, CONCRETO"),
    skip: int = 0, limit: int = 100, db: Session = Depends(get_db)
):
    """
    Busca insumos pela descrição e retorna seus preços para um determinado contexto.
    Opcionalmente filtra por classificação.
    """
    insumos = crud.search_insumos_by_descricao(db, q=q, uf=uf, data_referencia=data_referencia, regime=regime, skip=skip, limit=limit, classificacao=classificacao)
    return insumos


# --- Endpoints de Composições ---

@app.get("/api/v1/public/composicoes/{codigo}", response_model=schemas.Composicao, tags=["Composições"])
def read_composicao_by_codigo(
    codigo: int,
    uf: str = Query(..., description="Unidade Federativa (UF). Ex: SP", min_length=2, max_length=2),
    data_referencia: str = Query(..., description="Data de referência no formato AAAA-MM. Ex: 2025-09"),
    regime: str = Query("NAO_DESONERADO", description="Regime de custo."),
    db: Session = Depends(get_db)
):
    """
    Obtém uma composição específica e seu custo para um determinado contexto.
    """
    db_composicao = crud.get_composicao_by_codigo(db, codigo=codigo, uf=uf, data_referencia=data_referencia, regime=regime)
    if db_composicao is None:
        raise HTTPException(status_code=404, detail="Composição não encontrada para os filtros especificados.")
    return db_composicao

@app.get("/api/v1/public/composicoes", response_model=List[schemas.Composicao], tags=["Composições"])
def search_composicoes(
    q: str = Query(..., min_length=3, description="Termo para buscar na descrição da composição."),
    uf: str = Query(..., description="Unidade Federativa (UF). Ex: SP", min_length=2, max_length=2),
    data_referencia: str = Query(..., description="Data de referência no formato AAAA-MM. Ex: 2025-09"),
    regime: str = Query("NAO_DESONERADO", description="Regime de custo."),
    grupo: str = Query(None, description="Filtrar por grupo da composição. Ex: SERVICOS, ESTRUTURA, INSTALACOES"),
    skip: int = 0, limit: int = 100, db: Session = Depends(get_db)
):
    """
    Busca composições pela descrição e retorna seus custos para um determinado contexto.
    Opcionalmente filtra por grupo.
    """
    composicoes = crud.search_composicoes_by_descricao(db, q=q, uf=uf, data_referencia=data_referencia, regime=regime, skip=skip, limit=limit, grupo=grupo)
    return composicoes


# --- Endpoints de Business Intelligence (BI) ---

@app.get("/api/v1/public/bi/composicao/{codigo}/bom", response_model=List[schemas.ComposicaoBOMItem], tags=["Business Intelligence"])
def get_composition_bom(
    codigo: int,
    uf: str = Query(..., description="Unidade Federativa (UF). Ex: SP", min_length=2, max_length=2),
    data_referencia: str = Query(..., description="Data de referência no formato AAAA-MM. Ex: 2025-09"),
    regime: str = Query("NAO_DESONERADO", description="Regime de custo/preço."),
    db: Session = Depends(get_db)
):
    """
    Retorna o Bill of Materials (BOM) completo de uma composição,
    explodindo todos os níveis e calculando o impacto de custo de cada item.
    """
    bom_items = crud.get_composicao_bom(db, codigo=codigo, uf=uf, data_referencia=data_referencia, regime=regime)
    if not bom_items:
        raise HTTPException(status_code=404, detail="Composição não encontrada ou sem estrutura para os filtros especificados.")
    return bom_items

@app.get("/api/v1/public/bi/composicao/{codigo}/hora-homem", response_model=schemas.ComposicaoManHours, tags=["Business Intelligence"])
def get_composition_man_hours(codigo: int, db: Session = Depends(get_db)):
    """
    Calcula o total de Hora/Homem para uma composição, somando os coeficientes
    de todos os insumos de mão de obra (unidade 'H') em todos os níveis.
    """
    result = crud.get_composicao_man_hours(db, codigo=codigo)
    total_hh = 0.0
    if result is not None:
        if isinstance(result, dict):
            total_hh = result.get('total_hora_homem') or 0.0
        else:
            total_hh = getattr(result, 'total_hora_homem', None) or 0.0
    return schemas.ComposicaoManHours(total_hora_homem=total_hh)

@app.post("/api/v1/public/bi/curva-abc", response_model=List[schemas.CurvaABCItem], tags=["Business Intelligence"])
def get_abc_curve(
    codigos: List[int] = Body(..., description="Lista de códigos de composições a serem analisadas.", example=[92711, 88307]),
    uf: str = Query(..., description="Unidade Federativa (UF). Ex: SP", min_length=2, max_length=2),
    data_referencia: str = Query(..., description="Data de referência no formato AAAA-MM. Ex: 2025-09"),
    regime: str = Query("NAO_DESONERADO", description="Regime de preço."),
    db: Session = Depends(get_db)
):
    """
    Calcula a Curva ABC de insumos para um grupo de composições,
    identificando os itens de maior impacto financeiro.
    """
    abc_curve = crud.get_abc_curve_for_composicoes(db, codigos=codigos, uf=uf, data_referencia=data_referencia, regime=regime)
    if not abc_curve:
        raise HTTPException(status_code=404, detail="Nenhum insumo encontrado para as composições e filtros especificados.")
    return abc_curve

@app.get("/api/v1/public/bi/composicao/{codigo}/otimizar", response_model=List[schemas.ComposicaoBOMItem], tags=["Business Intelligence"])
def get_optimization_candidates(
    codigo: int,
    uf: str = Query(..., description="Unidade Federativa (UF). Ex: SP", min_length=2, max_length=2),
    data_referencia: str = Query(..., description="Data de referência no formato AAAA-MM. Ex: 2025-09"),
    regime: str = Query("NAO_DESONERADO", description="Regime de custo/preço."),
    top_n: int = Query(5, description="Número de principais insumos a serem retornados."),
    db: Session = Depends(get_db)
):
    """
    Retorna os N insumos de maior impacto financeiro em uma composição (Curva ABC - Foco).
    """
    candidates = crud.get_candidatos_otimizacao(db, codigo=codigo, uf=uf, data_referencia=data_referencia, regime=regime, top_n=top_n)
    if not candidates:
        raise HTTPException(status_code=404, detail="Não foi possível calcular os candidatos para otimização.")
    return candidates

@app.get("/api/v1/public/bi/item/{tipo_item}/{codigo}/historico", response_model=List[schemas.HistoricoCusto], tags=["Business Intelligence"])
def get_item_cost_history(
    tipo_item: str = Path(..., description="Tipo do item: 'insumo' ou 'composicao'"),
    codigo: int = Path(..., description="Código do item."),
    uf: str = Query(..., description="Unidade Federativa (UF). Ex: SP", min_length=2, max_length=2),
    regime: str = Query("NAO_DESONERADO", description="Regime de custo/preço."),
    data_fim: str = Query(f"{date.today():%Y-%m}", description="Data final (AAAA-MM) da análise."),
    meses: int = Query(12, description="Número de meses a serem analisados para trás."),
    db: Session = Depends(get_db)
):
    """
    Retorna o histórico de custo/preço de um item para um período.
    """
    try:
        end_date = datetime.strptime(data_fim, "%Y-%m")
    except ValueError:
        raise HTTPException(status_code=400, detail="Formato de data_fim inválido. Use AAAA-MM.")

    start_date = end_date - relativedelta(months=meses - 1)
    data_inicio_str = start_date.strftime("%Y-%m")

    if tipo_item not in ['insumo', 'composicao']:
        raise HTTPException(status_code=400, detail="Tipo de item inválido. Use 'insumo' ou 'composicao'.")

    history = crud.get_custo_historico(
        db, tipo_item=tipo_item, codigo=codigo, uf=uf, regime=regime,
        data_inicio=data_inicio_str, data_fim=data_fim
    )
    if not history:
        raise HTTPException(status_code=404, detail="Não foram encontrados dados históricos para o item e filtros especificados.")
    return history

@app.get("/api/v1/public/bi/item/{tipo_item}/{codigo}/manutencoes", response_model=List[schemas.HistoricoManutencao], tags=["Business Intelligence"])
def get_item_maintenance_history(
    tipo_item: str = Path(..., description="Tipo do item: 'insumo' ou 'composicao'"),
    codigo: int = Path(..., description="Código do item."),
    db: Session = Depends(get_db)
):
    """
    Retorna o histórico de manutenção (ativações/desativações) de um item.
    """
    if tipo_item not in ['insumo', 'composicao']:
        raise HTTPException(status_code=400, detail="Tipo de item inválido. Use 'insumo' ou 'composicao'.")
    manutencoes = crud.get_manutencoes_historico(db, codigo=codigo, tipo_item=tipo_item)
    if not manutencoes:
        raise HTTPException(status_code=404, detail="Nenhum histórico de manutenção encontrado para este item.")
    return manutencoes

@app.post("/api/v1/public/bi/curva-abc/por-classificacao", response_model=List[schemas.AbcPorClassificacao], tags=["Business Intelligence"])
def get_abc_by_classificacao(
    codigos: List[int] = Body(..., description="Lista de códigos de composições a serem analisadas.", example=[92711, 88307]),
    uf: str = Query(..., description="Unidade Federativa (UF). Ex: SP", min_length=2, max_length=2),
    data_referencia: str = Query(..., description="Data de referência no formato AAAA-MM. Ex: 2025-09"),
    regime: str = Query("NAO_DESONERADO", description="Regime de preço."),
    db: Session = Depends(get_db)
):
    """
    Calcula a Curva ABC agrupada por classificação de insumo,
    agregando todos os insumos de mesma categoria para mostrar
    quais classes de materiais dominam o custo.
    """
    result = crud.get_abc_by_classificacao(db, codigos=codigos, uf=uf, data_referencia=data_referencia, regime=regime)
    if not result:
        raise HTTPException(status_code=404, detail="Nenhuma classificação encontrada para as composições e filtros especificados.")
    return result

@app.get("/api/v1/public/bi/tendencias/por-classificacao", response_model=List[schemas.TendenciaClassificacao], tags=["Business Intelligence"])
def get_tendencias_classificacao(
    uf: str = Query(..., description="Unidade Federativa (UF). Ex: SP", min_length=2, max_length=2),
    data_referencia: str = Query(..., description="Data de referência final no formato AAAA-MM. Ex: 2025-09"),
    regime: str = Query("NAO_DESONERADO", description="Regime de preço."),
    meses: int = Query(12, description="Número de meses a serem analisados para trás."),
    db: Session = Depends(get_db)
):
    """
    Retorna a evolução mensal do preço médio por classificação de insumo
    para análise de tendências e volatilidade de categorias de materiais.
    """
    result = crud.get_tendencias_by_classificacao(db, uf=uf, regime=regime, data_referencia=data_referencia, meses=meses)
    if not result:
        raise HTTPException(status_code=404, detail="Nenhum dado de tendência encontrado para os filtros especificados.")
    return result

@app.get("/api/v1/public/bi/item/{tipo_item}/{codigo}/precos-uf", response_model=List[schemas.PrecoPorUF], tags=["Business Intelligence"])
def get_item_prices_all_ufs(
    tipo_item: str = Path(..., description="Tipo do item: 'insumo' ou 'composicao'"),
    codigo: int = Path(..., description="Código do item."),
    data_referencia: str = Query(..., description="Data de referência no formato AAAA-MM. Ex: 2025-09"),
    regime: str = Query("NAO_DESONERADO", description="Regime de custo/preço."),
    db: Session = Depends(get_db)
):
    """
    Retorna o preço de um item em TODAS as UFs disponíveis para
    comparação regional completa e mapa de calor.
    """
    if tipo_item not in ['insumo', 'composicao']:
        raise HTTPException(status_code=400, detail="Tipo de item inválido. Use 'insumo' ou 'composicao'.")
    precos = crud.get_precos_all_ufs(db, tipo_item=tipo_item, codigo=codigo, data_referencia=data_referencia, regime=regime)
    if not precos:
        raise HTTPException(status_code=404, detail="Nenhum dado encontrado para o item e filtros especificados.")
    return precos

@app.get("/api/v1/public/bi/composicao/{codigo}/produtividade", response_model=schemas.ComposicaoProdutividade, tags=["Business Intelligence"])
def get_composition_productivity(
    codigo: int,
    uf: str = Query(..., description="Unidade Federativa (UF). Ex: SP", min_length=2, max_length=2),
    data_referencia: str = Query(..., description="Data de referência no formato AAAA-MM. Ex: 2025-09"),
    regime: str = Query("NAO_DESONERADO", description="Regime de custo/preço."),
    db: Session = Depends(get_db)
):
    """
    Classifica os itens do BOM de uma composição em Mão de Obra, Material e Equipamento,
    retornando o total de Horas-Homem e o custo por HH como métrica de produtividade.
    """
    result = crud.get_composicao_produtividade(db, codigo=codigo, uf=uf, data_referencia=data_referencia, regime=regime)
    if not result:
        raise HTTPException(status_code=404, detail="Não foi possível calcular a produtividade para esta composição.")
    return result

@app.get("/api/v1/public/bi/insumo/{codigo}/onde-usado", response_model=List[schemas.InsumoOndeUsado], tags=["Business Intelligence"])
def get_insumo_where_used(
    codigo: int,
    tipo_item: str = Query("insumo", description="Tipo do item: 'insumo' ou 'composicao'"),
    db: Session = Depends(get_db)
):
    """
    Query reversa: encontra todas as composições (em qualquer nível) que utilizam
    um determinado insumo ou subcomposição. Útil para análise de impacto.
    """
    if tipo_item not in ['insumo', 'composicao']:
        raise HTTPException(status_code=400, detail="Tipo de item inválido. Use 'insumo' ou 'composicao'.")
    result = crud.get_onde_usado(db, codigo=codigo, tipo_item=tipo_item)
    if not result:
        raise HTTPException(status_code=404, detail="Nenhuma composição encontrada que utilize este item.")
    return result
