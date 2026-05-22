"""
Testes unitários para o módulo database.py
"""
from unittest.mock import MagicMock, patch
import pandas as pd
import pytest
from sqlalchemy.exc import SQLAlchemyError
from autosinapi.config import Config
from autosinapi.core.database import Database
from autosinapi.exceptions import DatabaseError

@pytest.fixture
def db_config():
    return {"host": "localhost", "port": 5432, "database": "test_db", "user": "test_user", "password": "test_pass"}

@pytest.fixture
def sinapi_config():
    return {"state": "SP", "month": "01", "year": "2023", "type": "REFERENCIA"}

@pytest.fixture
def database(db_config, sinapi_config):
    with patch("autosinapi.core.database.create_engine") as mock_ce:
        mock_engine = MagicMock()
        mock_ce.return_value = mock_engine
        config = Config(db_config, sinapi_config, mode="server")
        db = Database(config)
        db._engine = mock_engine
        yield db, mock_engine

@pytest.fixture
def sample_df():
    return pd.DataFrame({"CODIGO": ["1234", "5678"], "DESCRICAO": ["Produto A", "Produto B"], "PRECO": [100.0, 200.0]})

@pytest.fixture
def sample_df_with_trace():
    return pd.DataFrame({
        "codigo": [1001, 1002], "descricao": ["Insumo A", "Insumo B"],
        "unidade": ["m3", "kg"], "sinapi_versao": [None, None],
        "etl_run_id": [None, None], "created_at": [None, None], "updated_at": [None, None],
    })

def test_connect_success(db_config, sinapi_config):
    with patch("autosinapi.core.database.create_engine") as mock_ce:
        mock_engine = MagicMock()
        mock_ce.return_value = mock_engine
        config = Config(db_config, sinapi_config, mode="server")
        db = Database(config)
        assert db._engine is not None
        mock_ce.assert_called_once()

def test_connect_failure(db_config, sinapi_config):
    with patch("autosinapi.core.database.create_engine") as mock_ce:
        mock_ce.side_effect = SQLAlchemyError("Connection failed")
        with pytest.raises(DatabaseError, match="Erro ao conectar"):
            Config(db_config, sinapi_config, mode="server")
            Database(None)

def test_save_data_success(database, sample_df):
    db, mock_engine = database
    mock_conn = MagicMock()
    mock_engine.connect.return_value.__enter__.return_value = mock_conn
    db.save_data(sample_df, "test_table", policy="append")
    assert mock_conn.execute.call_count > 0

class TestUpsertBehavior:
    def test_append_data_does_upsert(self, database):
        db, mock_engine = database
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__.return_value = mock_conn
        mock_conn.execute.return_value.fetchall.return_value = [("codigo",)]

        df = pd.DataFrame({
            "codigo": [1001], "descricao": ["Insumo Atualizado"],
            "sinapi_versao": ["2024.01"], "etl_run_id": ["test-run"],
            "created_at": [None], "updated_at": [None],
        })

        db._append_data(df, "insumos")

        # Check UPSERT in TextClause content via call.args
        all_args = [str(a.args[0]) for a in mock_conn.execute.call_args_list]
        upsert_found = any("DO UPDATE SET" in arg for arg in all_args)
        assert upsert_found, "UPSERT (DO UPDATE SET) nao foi chamado"

    def test_append_data_updates_updated_at(self, database):
        db, mock_engine = database
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__.return_value = mock_conn
        mock_conn.execute.return_value.fetchall.return_value = [("codigo",)]

        df = pd.DataFrame({
            "codigo": [1001], "descricao": ["Insumo A"],
            "sinapi_versao": ["2024.01"], "etl_run_id": ["test-run"],
            "created_at": [None], "updated_at": [None],
        })

        db._append_data(df, "insumos")

        all_args = [str(a.args[0]) for a in mock_conn.execute.call_args_list]
        now_found = any("updated_at" in arg and "NOW()" in arg for arg in all_args)
        assert now_found, "updated_at = NOW() nao encontrado na query"

class TestTraceabilityPropagation:
    def test_save_data_propagates_sinapi_versao(self, database, sample_df_with_trace):
        db, mock_engine = database
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__.return_value = mock_conn

        df = sample_df_with_trace.copy()
        db.save_data(df, "insumos", policy="append", sinapi_versao="2024.01", etl_run_id="test-run-123")
        assert df["sinapi_versao"].iloc[0] == "2024.01"
        assert df["etl_run_id"].iloc[0] == "test-run-123"

    def test_save_data_adds_missing_traceability_columns(self, database):
        db, mock_engine = database
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__.return_value = mock_conn

        df = pd.DataFrame({"codigo": [1001], "descricao": ["Insumo A"]})
        db.save_data(df, "insumos", policy="append", sinapi_versao="2024.01", etl_run_id="test-run-123")
        assert "sinapi_versao" in df.columns
        assert df["sinapi_versao"].iloc[0] == "2024.01"

class TestAuditLog:
    def test_log_audit_event_inserts_correctly(self, database):
        db, mock_engine = database
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__.return_value = mock_conn

        db._log_audit_event(
            table_name="insumos", record_pk={"codigo": 1001}, operation="UPDATE",
            old_values={"descricao": "Insumo A"}, new_values={"descricao": "Insumo A Atualizado"},
            sinapi_versao="2024.01", etl_run_id="test-run-123", motivo_manutencao="ATIVACAO"
        )

        call_str = str(mock_conn.execute.call_args[0][0])
        assert "sinapi_audit_log" in call_str

    def test_log_audit_event_handles_errors_gracefully(self, database):
        db, mock_engine = database
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__.return_value = mock_conn
        mock_conn.execute.side_effect = SQLAlchemyError("Connection lost")
        db._log_audit_event(table_name="insumos", record_pk={"codigo": 1001}, operation="UPDATE")
