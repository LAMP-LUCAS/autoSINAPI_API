"""
Testes unitários para o módulo processor.py
"""

import logging

import pandas as pd
import pytest

from autosinapi.config import Config
from autosinapi.core.processor import Processor


@pytest.fixture
def db_config():
    """Fixture com configuração de teste do banco de dados."""
    return {
        "host": "localhost",
        "port": 5432,
        "database": "test_db",
        "user": "test_user",
        "password": "test_pass",
    }


@pytest.fixture
def sinapi_config():
    """Fixture com configuração SINAPI mínima para testes."""
    return {"state": "SP", "month": 8, "year": 2025, "type": "REFERENCIA"}


@pytest.fixture
def processor(db_config, sinapi_config):
    """Fixture que cria um processador com configurações completas."""
    config = Config(db_config, sinapi_config, mode="server")
    p = Processor(config)
    p.logger.setLevel(logging.DEBUG)
    return p


@pytest.fixture
def sample_insumos_df():
    """Fixture que cria um DataFrame de exemplo para insumos."""
    return pd.DataFrame(
        {
            "CODIGO": ["1234", "5678", "9012"],
            "DESCRICAO": ["AREIA MEDIA", "CIMENTO PORTLAND", "TIJOLO CERAMICO"],
            "UNIDADE": ["M3", "KG", "UN"],
            "PRECO_MEDIANO": [120.50, 0.89, 1.25],
        }
    )


@pytest.fixture
def sample_composicoes_df():
    """Fixture que cria um DataFrame de exemplo para composições."""
    return pd.DataFrame(
        {
            "CODIGO_COMPOSICAO": ["87453", "87522", "87890"],
            "DESCRICAO_COMPOSICAO": [
                "ALVENARIA DE VEDACAO",
                "REVESTIMENTO CERAMICO",
                "CONTRAPISO",
            ],
            "UNIDADE": ["M2", "M2", "M2"],
            "CUSTO_TOTAL": [89.90, 45.75, 32.80],
        }
    )


def test_normalize_cols(processor):
    """Testa a normalização dos nomes das colunas."""
    df = pd.DataFrame(
        {
            "Código do Item": [1, 2, 3],
            "Descrição": ["a", "b", "c"],
            "Preço Unitário": [10, 20, 30],
        }
    )
    result = processor._normalize_cols(df)
    assert "CODIGO_DO_ITEM" in result.columns
    assert "DESCRICAO" in result.columns
    assert "PRECO_UNITARIO" in result.columns


def test_process_composicao_itens(processor, tmp_path):
    """Testa o processamento da estrutura das composições."""
    # Cria um arquivo XLSX de teste
    test_file = tmp_path / "test_sinapi.xlsx"
    df = pd.DataFrame(
        {
            "CODIGO_DA_COMPOSICAO": ["87453", "87453"],
            "TIPO_ITEM": ["INSUMO", "COMPOSICAO"],
            "CODIGO_DO_ITEM": ["1234", "5678"],
            "COEFICIENTE": ["1,0", "2,5"],
            "DESCRICAO": ["INSUMO A", "COMPOSICAO B"],
            "UNIDADE": ["UN", "M2"],
        }
    )
    # Adiciona linha de cabeçalho e outras linhas para simular o arquivo real
    writer = pd.ExcelWriter(test_file, engine="xlsxwriter")
    df.to_excel(writer, index=False, header=True, sheet_name="Analítico", startrow=9)
    writer.close()

    result = processor.process_composicao_itens(str(test_file))

    assert "composicao_insumos" in result
    assert "composicao_subcomposicoes" in result
    assert len(result["composicao_insumos"]) == 1
    assert len(result["composicao_subcomposicoes"]) == 1
    assert result["composicao_insumos"].iloc[0]["insumo_filho_codigo"] == 1234