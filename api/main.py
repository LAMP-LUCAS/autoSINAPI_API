# api/main.py (versão refatorada e com endpoints de BI)
"""
Ponto de entrada principal da AutoSINAPI API.

Este módulo define todos os endpoints da API utilizando FastAPI,
orquestrando as chamadas para as funções do módulo `crud` e utilizando os
`schemas` para validação e serialização de dados.
"""

import os
from typing import List
from fastapi import FastAPI, Depends, HTTPException, Query, Body, Path
from sqlalchemy.orm import Session
from datetime import date, datetime
from dateutil.relativedelta import relativedelta

from . import crud, schemas, config
from .database import get_db
from .tasks import populate_sinapi_task

# Carrega as configurações uma vez
settings = config.settings

app = FastAPI(
    title="AutoSINAPI API",
    description="API para consulta de preços, custos, estruturas e análises da base de dados SINAPI.",
    version="1.0.0",
)

# --- Endpoints de Administração ---

@app.post("/admin/populate-database", status_code=202, tags=["Admin"])
def trigger_database_population(year: int = Body(..., example=2025), month: int = Body(..., example=9)):
    """
    Dispara a tarefa de download e população da base SINAPI para um mês/ano.
    A tarefa roda em segundo plano (assíncrona).
    """
    db_config = {
        "host": os.getenv("POSTGRES_HOST", "db"),
        "port": os.getenv("POSTGRES_PORT", 5432),
        "database": os.getenv("POSTGRES_DB"),
        "user": os.getenv("POSTGRES_USER"),
        "password": os.getenv("POSTGRES_PASSWORD"),
    }
    sinapi_config = { "year": year, "month": month }

    task = populate_sinapi_task.delay(db_config, sinapi_config)
    return {"message": "Tarefa de população da base de dados iniciada com sucesso.", "task_id": task.id}


@app.get("/", tags=["Root"])
def read_root():
    return {"message": "Bem-vindo à API AutoSINAPI. Acesse /docs para a documentação interativa."}


# --- Endpoints de Insumos ---

@app.get("/insumos/{codigo}", response_model=schemas.Insumo, tags=["Insumos"])
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

@app.get("/insumos/", response_model=List[schemas.Insumo], tags=["Insumos"])
def search_insumos(
    q: str = Query(..., min_length=3, description="Termo para buscar na descrição do insumo."),
    uf: str = Query(..., description="Unidade Federativa (UF). Ex: SP", min_length=2, max_length=2),
    data_referencia: str = Query(..., description="Data de referência no formato AAAA-MM. Ex: 2025-09"),
    regime: str = Query("NAO_DESONERADO", description="Regime de preço."),
    skip: int = 0, limit: int = 100, db: Session = Depends(get_db)
):
    """
    Busca insumos pela descrição e retorna seus preços para um determinado contexto.
    """
    insumos = crud.search_insumos_by_descricao(db, q=q, uf=uf, data_referencia=data_referencia, regime=regime, skip=skip, limit=limit)
    return insumos


# --- Endpoints de Composições ---

@app.get("/composicoes/{codigo}", response_model=schemas.Composicao, tags=["Composições"])
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

@app.get("/composicoes/", response_model=List[schemas.Composicao], tags=["Composições"])
def search_composicoes(
    q: str = Query(..., min_length=3, description="Termo para buscar na descrição da composição."),
    uf: str = Query(..., description="Unidade Federativa (UF). Ex: SP", min_length=2, max_length=2),
    data_referencia: str = Query(..., description="Data de referência no formato AAAA-MM. Ex: 2025-09"),
    regime: str = Query("NAO_DESONERADO", description="Regime de custo."),
    skip: int = 0, limit: int = 100, db: Session = Depends(get_db)
):
    """
    Busca composições pela descrição e retorna seus custos para um determinado contexto.
    """
    composicoes = crud.search_composicoes_by_descricao(db, q=q, uf=uf, data_referencia=data_referencia, regime=regime, skip=skip, limit=limit)
    return composicoes


# --- Endpoints de Business Intelligence (BI) ---

@app.get("/bi/composicao/{codigo}/bom", response_model=List[schemas.ComposicaoBOMItem], tags=["Business Intelligence"])
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

@app.get("/bi/composicao/{codigo}/hora-homem", response_model=schemas.ComposicaoManHours, tags=["Business Intelligence"])
def get_composition_man_hours(codigo: int, db: Session = Depends(get_db)):
    """
    Calcula o total de Hora/Homem para uma composição, somando os coeficientes
    de todos os insumos de mão de obra (unidade 'H') em todos os níveis.
    """
    result = crud.get_composicao_man_hours(db, codigo=codigo)
    if result is None or result.total_hora_homem is None:
        return schemas.ComposicaoManHours(total_hora_homem=0.0)
    return result

@app.post("/bi/curva-abc", response_model=List[schemas.CurvaABCItem], tags=["Business Intelligence"])
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

@app.get("/bi/composicao/{codigo}/otimizar", response_model=List[schemas.ComposicaoBOMItem], tags=["Business Intelligence"])
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

@app.get("/bi/item/{tipo_item}/{codigo}/historico", response_model=List[schemas.HistoricoCusto], tags=["Business Intelligence"])
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