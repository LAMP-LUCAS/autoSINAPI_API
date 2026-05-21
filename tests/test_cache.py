import pytest
from unittest.mock import Mock, MagicMock
from api import crud
from api.config import settings

@pytest.fixture(autouse=True)
def clear_cache():
    """Limpa o Redis antes de cada teste para evitar interferência."""
    from api.cache_utils import redis_client
    redis_client.flushdb()

@pytest.fixture
def mock_db():
    return MagicMock()

def test_cache_hit_prevents_db_call_bom(mock_db):
    """Verifica cache para BOM."""
    codigo = 123
    uf = "SP"
    referencia = "2025-10"
    regime = "DESONERADO"
    
    mock_db.execute.return_value.fetchall.return_value = [
        {"item_codigo": 1, "tipo_item": "INSUMO", "descricao": "Item 1", "coeficiente": 1.0}
    ]

    crud.get_composicao_bom(mock_db, codigo, uf, referencia, regime)
    assert mock_db.execute.call_count == 1

    crud.get_composicao_bom(mock_db, codigo, uf, referencia, regime)
    assert mock_db.execute.call_count == 1

def test_abc_curve_cache(mock_db):
    """Verifica cache para Curva ABC."""
    codigos = [100, 200]
    uf = "RJ"
    referencia = "2025-09"
    regime = "NAO_DESONERADO"

    # Simula retorno do fetchall()
    mock_db.execute.return_value.fetchall.return_value = [
        {"codigo": 100, "descricao": "Insumo A", "unidade": "KG", "custo_total_agregado": 500.0}
    ]

    crud.get_abc_curve_for_composicoes(mock_db, codigos, uf, referencia, regime)
    assert mock_db.execute.call_count == 1

    crud.get_abc_curve_for_composicoes(mock_db, codigos, uf, referencia, regime)
    assert mock_db.execute.call_count == 1
