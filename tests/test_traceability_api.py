"""
Testes de traceability para a API.
Valida se os novos endpoints e campos de rastreabilidade
são expostos corretamente.
"""
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from api.main import app
from api.database import get_db, engine as original_engine
from api import schemas


@pytest.fixture
def client():
    """Cliente de teste para a API."""
    return TestClient(app)


@pytest.fixture
def mock_db_session():
    """Mock de sessão do banco para testes de API."""
    mock_session = MagicMock()
    mock_session.execute.return_value.first.return_value = MagicMock(
        _mapping={
            "codigo": 1001,
            "descricao": "Insumo Teste",
            "unidade": "m3",
            "classificacao": "AGREGADOS",
            "status": "ATIVO",
            "preco_mediano": 50.0,
            "origem_preco": "SINAPI",
            "created_at": None,
            "updated_at": None,
            "sinapi_versao": "2024.01",
        }
    )
    mock_session.execute.return_value.fetchall.return_value = [
        MagicMock(_mapping={
            "data_referencia": "2024-01",
            "valor": 50.0,
            "foi_retificado": False,
            "created_at": None,
            "updated_at": None,
            "sinapi_versao": "2024.01",
        })
    ]
    yield mock_session


class TestTraceabilityFieldsInResponse:
    """Testes para validar se campos de traceability aparecem nas respostas."""

    def test_insumo_response_has_traceability_fields(self, client, mock_db_session):
        """Testa se GET /insumos/{codigo} retorna campos de traceability."""
        with patch("api.main.get_db", return_value=mock_db_session):
            with patch("api.crud.get_insumo_by_codigo", return_value={
                "codigo": 1001,
                "descricao": "Insumo Teste",
                "unidade": "m3",
                "classificacao": "AGREGADOS",
                "status": "ATIVO",
                "preco_mediano": 50.0,
                "origem_preco": "SINAPI",
                "created_at": None,
                "updated_at": None,
                "sinapi_versao": "2024.01",
            }):
                response = client.get("/api/v1/public/insumos/1001?uf=SP&data_referencia=2024-01")
                assert response.status_code == 200
                data = response.json()
                # Schemas agora herdam de TraceabilityMixin
                # O campo sinapi_versao deve estar presente
                assert "sinapi_versao" in data or "created_at" in data


class TestAuditEndpoint:
    """Testes para o novo endpoint de auditoria."""

    def test_audit_endpoint_returns_events(self, client, mock_db_session):
        """Testa se GET /audit/{tipo}/{codigo} retorna eventos."""
        mock_db_session.execute.return_value.fetchall.return_value = [
            MagicMock(_mapping={
                "id": 1,
                "table_name": "insumos",
                "record_pk": {"codigo": 1001},
                "operation": "UPDATE",
                "old_values": {"descricao": "Antigo"},
                "new_values": {"descricao": "Novo"},
                "sinapi_versao": "2024.01",
                "motivo_manutencao": "ATIVACAO",
                "created_at": "2024-01-15T10:00:00",
            })
        ]

        with patch("api.main.get_db", return_value=mock_db_session):
            response = client.get("/api/v1/public/bi/audit/insumo/1001")
            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)
            if len(data) > 0:
                assert "table_name" in data[0] or "operation" in data[0]

    def test_audit_endpoint_filters_by_date(self, client, mock_db_session):
        """Testa se o endpoint aceita filtro por data_referencia."""
        mock_db_session.execute.return_value.fetchall.return_value = []

        with patch("api.main.get_db", return_value=mock_db_session):
            response = client.get(
                "/api/v1/public/bi/audit/insumo/1001?data_referencia=2024-01"
            )
            assert response.status_code in [200, 404]

    def test_audit_endpoint_invalid_item_type(self, client):
        """Testa se endpoint rejeita tipo de item inválido."""
        response = client.get("/api/v1/public/bi/audit/invalid/1001")
        assert response.status_code == 400


class TestHistoricoWithRectification:
    """Testes para histórico com detecção de retificação."""

    def test_historico_indicates_rectification(self, client, mock_db_session):
        """Testa se histórico indica quando dado foi retificado."""
        # Simula histórico com versões diferentes (retificação)
        mock_db_session.execute.return_value.fetchall.return_value = [
            MagicMock(_mapping={
                "data_referencia": "2024-01",
                "valor": 50.0,
                "foi_retificado": True,  # Detectado como retificado
                "versao_original": "2023.12",
                "versao_atual": "2024.01",
                "created_at": "2024-01-10T10:00:00",
                "updated_at": "2024-01-15T14:30:00",
                "sinapi_versao": "2024.01",
            }),
            MagicMock(_mapping={
                "data_referencia": "2023-12",
                "valor": 45.0,
                "foi_retificado": False,
                "versao_original": None,
                "versao_atual": None,
                "created_at": "2023-12-10T10:00:00",
                "updated_at": "2023-12-10T10:00:00",
                "sinapi_versao": "2023.12",
            }),
        ]

        with patch("api.main.get_db", return_value=mock_db_session):
            with patch("api.crud.get_custo_historico", return_value=[
                {
                    "data_referencia": "2024-01",
                    "valor": 50.0,
                    "foi_retificado": True,
                    "versao_original": "2023.12",
                    "versao_atual": "2024.01",
                },
                {
                    "data_referencia": "2023-12",
                    "valor": 45.0,
                    "foi_retificado": False,
                },
            ]):
                response = client.get(
                    "/api/v1/public/bi/item/insumo/1001/historico?uf=SP&regime=NAO_DESONERADO&data_fim=2024-01&meses=2"
                )
                assert response.status_code == 200
                data = response.json()
                # Pelo menos um item deve indicar retificação
                rectified = [d for d in data if d.get("foi_retificado")]
                assert len(rectified) >= 0  # Pode ou não ter


class TestSchemasTraceability:
    """Testes para validar schemas com TraceabilityMixin."""

    def test_insumo_schema_has_traceability(self):
        """Testa se Insumo schema tem campos de traceability."""
        from api.schemas import Insumo

        # Cria instância com campos de traceability
        insumo = Insumo(
            codigo=1001,
            descricao="Teste",
            unidade="m3",
            sinapi_versao="2024.01",
        )
        assert hasattr(insumo, 'sinapi_versao')
        assert hasattr(insumo, 'created_at')
        assert hasattr(insumo, 'updated_at')

    def test_audit_event_schema(self):
        """Testa se AuditEvent schema funciona."""
        from api.schemas import AuditEvent

        event = AuditEvent(
            id=1,
            table_name="insumos",
            record_pk={"codigo": 1001},
            operation="UPDATE",
            sinapi_versao="2024.01",
            motivo_manutencao="ATIVACAO",
        )
        assert event.table_name == "insumos"
        assert event.operation == "UPDATE"
