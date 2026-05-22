"""
Testes de traceability para o módulo Database.
Valida UPSERT, propagação de sinapi_versao/etl_run_id, e audit log.
"""
from unittest.mock import MagicMock, patch, call
import pandas as pd
import pytest
from sqlalchemy.exc import SQLAlchemyError

from autosinapi.config import Config
from autosinapi.core.database import Database
from autosinapi.exceptions import DatabaseError


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
    return {"state": "SP", "month": "01", "year": "2023", "type": "REFERENCIA"}


@pytest.fixture
def database(db_config, sinapi_config):
    """Fixture que cria uma instância do Database com engine mockada."""
    with patch("autosinapi.core.database.create_engine") as mock_create_engine:
        mock_engine = MagicMock()
        mock_create_engine.return_value = mock_engine
        config = Config(db_config, sinapi_config, mode="server")
        db = Database(config)
        db._engine = mock_engine
        yield db, mock_engine


@pytest.fixture
def sample_df_with_traceability():
    """DataFrame com colunas de traceability."""
    return pd.DataFrame({
        "codigo": [1001, 1002],
        "descricao": ["Insumo A", "Insumo B"],
        "unidade": ["m3", "kg"],
        "sinapi_versao": [None, None],
        "etl_run_id": [None, None],
        "created_at": [None, None],
        "updated_at": [None, None],
    })


class TestSaveDataTraceability:
    """Testes para propagação de sinapi_versao e etl_run_id."""

    def test_save_data_propagates_sinapi_versao(self, database, sample_df_with_traceability):
        """Testa se sinapi_versao é propagado para o DataFrame."""
        db, mock_engine = database
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__.return_value = mock_conn

        df = sample_df_with_traceability.copy()
        db.save_data(
            df, "insumos", policy="upsert",
            pk_columns=["codigo"],
            sinapi_versao="2024.01",
            etl_run_id="test-run-123"
        )

        # Verifica se sinapi_versao foi propagado
        assert df["sinapi_versao"].iloc[0] == "2024.01"
        assert df["etl_run_id"].iloc[0] == "test-run-123"

    def test_save_data_adds_missing_traceability_columns(self, database):
        """Testa se colunas de traceability são adicionadas se faltarem."""
        db, mock_engine = database
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__.return_value = mock_conn

        # DataFrame sem colunas de traceability
        df = pd.DataFrame({
            "codigo": [1001],
            "descricao": ["Insumo A"],
        })

        db.save_data(
            df, "insumos", policy="upsert",
            pk_columns=["codigo"],
            sinapi_versao="2024.01",
            etl_run_id="test-run-123"
        )

        # Verifica se as colunas foram adicionadas
        assert "sinapi_versao" in df.columns
        assert "etl_run_id" in df.columns
        assert "created_at" in df.columns
        assert "updated_at" in df.columns


class TestAppendDataUpsert:
    """Testes para validar que _append_data agora faz UPSERT."""

    def test_append_data_does_upsert_not_ignore(self, database):
        """Testa se _append_data faz UPDATE em conflito (não ignora)."""
        db, mock_engine = database
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__.return_value = mock_conn

        # Mock para simular que a tabela tem pk (codigo)
        mock_conn.execute.return_value.fetchall.return_value = [("codigo",)]

        df = pd.DataFrame({
            "codigo": [1001],
            "descricao": ["Insumo Atualizado"],
            "unidade": ["m3"],
            "sinapi_versao": ["2024.01"],
            "etl_run_id": ["test-run"],
            "created_at": [None],
            "updated_at": [None],
        })

        db._append_data(df, "insumos")

        # Verifica se a query tem DO UPDATE SET (UPSERT)
        call_args = mock_conn.execute.call_args_list
        upsert_called = False
        for call in call_args:
            if call and "DO UPDATE SET" in str(call):
                upsert_called = True
                break
        assert upsert_called, "UPSERT (DO UPDATE SET) não foi chamado"

    def test_append_data_updates_updated_at(self, database):
        """Testa se updated_at é atualizado no UPSERT."""
        db, mock_engine = database
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__.return_value = mock_conn

        mock_conn.execute.return_value.fetchall.return_value = [("codigo",)]

        df = pd.DataFrame({
            "codigo": [1001],
            "descricao": ["Insumo A"],
            "sinapi_versao": ["2024.01"],
            "etl_run_id": ["test-run"],
            "created_at": [None],
            "updated_at": [None],
        })

        db._append_data(df, "insumos")

        # Verifica se updated_at = NOW() está na query
        call_args = mock_conn.execute.call_args_list
        now_updated = False
        for call in call_args:
            if call and "updated_at" in str(call) and "NOW()" in str(call):
                now_updated = True
                break
        assert now_updated, "updated_at = NOW() não encontrado na query"


class TestAuditLog:
    """Testes para o método _log_audit_event."""

    def test_log_audit_event_inserts_correctly(self, database):
        """Testa se _log_audit_event insere corretamente."""
        db, mock_engine = database
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__.return_value = mock_conn

        db._log_audit_event(
            table_name="insumos",
            record_pk={"codigo": 1001},
            operation="UPDATE",
            old_values={"descricao": "Insumo A"},
            new_values={"descricao": "Insumo A Atualizado"},
            sinapi_versao="2024.01",
            etl_run_id="test-run-123",
            motivo_manutencao="ATIVACAO"
        )

        # Verifica se INSERT foi chamado
        mock_conn.execute.assert_called()
        call_args = mock_conn.execute.call_args
        assert "sinapi_audit_log" in str(call_args)
        assert "INSERT INTO" in str(call_args)

    def test_log_audit_event_handles_errors_gracefully(self, database):
        """Testa se erros no audit log não quebram o pipeline."""
        db, mock_engine = database
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__.return_value = mock_conn
        mock_conn.execute.side_effect = SQLAlchemyError("Connection lost")

        # Não deve levantar exceção
        db._log_audit_event(
            table_name="insumos",
            record_pk={"codigo": 1001},
            operation="UPDATE"
        )
        # Se chegou aqui, passou (não levantou exceção)
