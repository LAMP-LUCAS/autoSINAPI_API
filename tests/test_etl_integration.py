import pytest
from sqlalchemy import text
from api.database import SessionLocal, engine
from api.tasks import populate_sinapi_task
from api.crud import get_insumo_by_codigo
from unittest.mock import patch

@pytest.fixture
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()

@pytest.mark.skip(reason="Requer banco PostgreSQL real com sandbox configurado")
def test_etl_persistence_and_api_read_consistency(db_session):
    """
    Teste de Integração: Verifica se o ETL persiste dados em tabelas que a API consegue ler.
    Este teste deve falhar na arquitetura atual devido ao 'Data Mismatch'.
    """
    # 1. Configuração do Mock para evitar download real mas simular sucesso do Toolkit
    # Simulamos o que o toolkit ATUAL faz (salva em 'sinapi_sp' por exemplo)
    mock_db_config = {
        "host": "localhost",
        "port": 5432,
        "database": "sinapi",
        "user": "postgres",
        "password": "password",
    }
    sinapi_config = {"year": 2026, "month": 5, "state": "SP"}
    
    # Inserimos um dado via "ETL" (Simulado ou Real se o toolkit permitir)
    # Para este teste falhar rápido, vamos verificar as tabelas esperadas pela API
    
    codigo_teste = 999999
    uf_teste = "SP"
    referencia_teste = "2026-05"
    
    # Tenta ler um insumo que acabou de ser "povoado"
    # Na versão atual, o ETL salvaria em 'sinapi_sp' e o crud buscaria em 'insumos' + 'precos_insumos_mensal'
    insumo = get_insumo_by_codigo(
        db_session, 
        codigo=codigo_teste, 
        uf=uf_teste, 
        data_referencia=referencia_teste, 
        regime="NAO_DESONERADO"
    )
    
    # Se o insumo for None, significa que a API não encontrou o que o ETL deveria ter posto lá
    # (Ou que o ETL nem pôs no lugar certo)
    assert insumo is not None, "A API deveria encontrar o insumo persistido pelo ETL"
