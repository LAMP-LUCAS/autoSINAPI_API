# api/main.py
import os
from typing import List
from fastapi import FastAPI, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from . import crud, schemas
from .database import get_db
from .tasks import populate_sinapi_task

app = FastAPI(
    title="AutoSINAPI API",
    description="API para consulta de preços de insumos e composições da base SINAPI.",
    version="1.0.0",
)

# --- Endpoints de Administração ---

@app.post("/admin/populate-database", status_code=202, tags=["Admin"])
def trigger_database_population(year: int, month: int):
    """
    Dispara a tarefa de download e população da base SINAPI para um mês específico.
    A tarefa roda em segundo plano. Retorna imediatamente com o ID da tarefa.
    """
    # Monta os dicionários de configuração a partir do .env (lido pela API)
    # Esta é a "fonte única da verdade"
    db_config = {
        "user": os.getenv("POSTGRES_USER"),
        "password": os.getenv("POSTGRES_PASSWORD"),
        "host": os.getenv("DB_HOST"), # O worker se conecta ao 'db' hostname da rede docker
        "port": os.getenv("DB_PORT"),
        "dbname": os.getenv("POSTGRES_DB")
    }
    sinapi_config = {
        "year": year,
        "month": month,
        "workbook_type": os.getenv("SINAPI_WORKBOOK_TYPE", "REFERENCIA"),
        "duplicate_policy": os.getenv("SINAPI_DUPLICATE_POLICY", "substituir")
    }

    # Envia a tarefa para a fila do Celery
    task = populate_sinapi_task.delay(db_config, sinapi_config)

    return {"message": "Tarefa de população iniciada.", "task_id": task.id}


@app.get("/", tags=["Root"])
def read_root():
    return {"message": "Bem-vindo à API SINAPI. Acesse /docs para a documentação."}

# --- Endpoints de Insumos ---

@app.get("/insumos/search/", response_model=List[schemas.Insumo], tags=["Insumos"])
def search_insumos(
    q: str = Query(..., min_length=3, description="Termo para buscar na descrição do insumo"),
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """
    Busca insumos pela descrição.
    """
    insumos = crud.search_insumos_by_descricao(db, q=q, skip=skip, limit=limit)
    return insumos

@app.get("/insumos/{codigo}", response_model=schemas.Insumo, tags=["Insumos"])
def read_insumo_by_codigo(codigo: str, db: Session = Depends(get_db)):
    """
    Obtém um insumo específico pelo seu código.
    """
    db_insumo = crud.get_insumo_by_codigo(db, codigo=codigo)
    if db_insumo is None:
        raise HTTPException(status_code=404, detail="Insumo não encontrado")
    return db_insumo

# --- Endpoints de Composições ---

@app.get("/composicoes/search/", response_model=List[schemas.Composicao], tags=["Composições"])
def search_composicoes(
    q: str = Query(..., min_length=3, description="Termo para buscar na descrição da composição"),
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """
    Busca composições pela descrição.
    """
    composicoes = crud.search_composicoes_by_descricao(db, q=q, skip=skip, limit=limit)
    return composicoes

@app.get("/composicoes/{codigo}", response_model=schemas.Composicao, tags=["Composições"])
def read_composicao_by_codigo(codigo: str, db: Session = Depends(get_db)):
    """
    Obtém uma composição específica pelo seu código.
    """
    db_composicao = crud.get_composicao_by_codigo(db, codigo=codigo)
    if db_composicao is None:
        raise HTTPException(status_code=404, detail="Composição não encontrada")
    return db_composicao
