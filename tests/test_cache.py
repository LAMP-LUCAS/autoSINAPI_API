import pytest
from unittest.mock import Mock, MagicMock, patch, PropertyMock
from api import crud
from api.config import settings

@pytest.fixture(autouse=True)
def mock_redis():
    """Mocka o Redis client para evitar dependência externa."""
    with patch("api.cache_utils.redis_client") as mock_redis:
        mock_redis.get.return_value = None
        mock_redis.set.return_value = True
        mock_redis.delete.return_value = 1
        mock_redis.scan.return_value = (0, [])
        yield mock_redis

@pytest.fixture
def mock_db():
    return MagicMock()

def test_cache_hit_prevents_db_call_bom(mock_db, mock_redis):
    """Cache hit para BOM evita execução SQL."""
    codigo = 123
    uf = "SP"
    referencia = "2025-10"
    regime = "DESONERADO"

    mock_db.execute.return_value.fetchall.return_value = [
        Mock(_mapping={"item_codigo": 1, "tipo_item": "INSUMO", "descricao": "Item 1", "coeficiente": 1.0})
    ]

    # Primeira chamada: cache miss, executa SQL
    crud.get_composicao_bom(mock_db, codigo, uf, referencia, regime)
    assert mock_db.execute.call_count == 1

    # Segunda chamada: cache hit (simulado por mock_redis.get retornando valor)
    mock_redis.get.return_value = '[{"item_codigo": 1}]'
    crud.get_composicao_bom(mock_db, codigo, uf, referencia, regime)
    assert mock_db.execute.call_count == 1

def test_cache_hit_prevents_db_call_abc(mock_db, mock_redis):
    """Cache hit para ABC evita execução SQL."""
    codigos = [100, 200]
    uf = "RJ"
    referencia = "2025-09"
    regime = "NAO_DESONERADO"

    mock_db.execute.return_value.fetchall.return_value = [
        Mock(_mapping={"codigo": 100, "descricao": "Insumo A", "unidade": "KG", "custo_impacto_total": 500.0, "percentual_individual": 100.0, "percentual_acumulado": 100.0, "classe_abc": "A"})
    ]

    crud.get_abc_curve_for_composicoes(mock_db, codigos, uf, referencia, regime)
    assert mock_db.execute.call_count == 1

    mock_redis.get.return_value = '[{"codigo": 100}]'
    crud.get_abc_curve_for_composicoes(mock_db, codigos, uf, referencia, regime)
    assert mock_db.execute.call_count == 1

def test_cache_miss_executes_sql(mock_db, mock_redis):
    """Cache miss (sem valor) executa SQL."""
    codigo = 456
    uf = "SP"
    referencia = "2025-11"
    regime = "NAO_DESONERADO"

    mock_db.execute.return_value.fetchall.return_value = [
        Mock(_mapping={"item_codigo": 2, "tipo_item": "COMPOSICAO", "descricao": "Item 2", "coeficiente": 2.0})
    ]

    mock_redis.get.return_value = None
    crud.get_composicao_bom(mock_db, codigo, uf, referencia, regime)
    assert mock_db.execute.call_count == 1

def test_invalidate_cache(mock_redis):
    """invalidate_cache deleta chaves por padrão."""
    from api.cache_utils import invalidate_cache

    mock_redis.scan.return_value = (0, ["cache:get_composicao_bom:test:key1", "cache:get_composicao_bom:test:key2"])

    deleted = invalidate_cache("cache:get_composicao_bom:*")
    assert deleted == 2
    mock_redis.delete.assert_called_once()