"""
Testes unitários para o módulo de download.
"""

from io import BytesIO
from unittest.mock import Mock, patch

import pytest
import requests

from autosinapi.config import Config
from autosinapi.core.downloader import Downloader
from autosinapi.exceptions import DownloadError


# Fixtures
@pytest.fixture
def valid_db_config():
    """Fixture com configuração de banco de dados válida."""
    return {
        "host": "localhost",
        "port": 5432,
        "database": "test_db",
        "user": "test_user",
        "password": "test_pass",
    }


@pytest.fixture
def sinapi_config():
    """Fixture com configuração SINAPI básica."""
    return {"state": "SP", "month": "01", "year": "2023", "type": "REFERENCIA"}


@pytest.fixture
def mock_response():
    """Fixture para mock de resposta HTTP."""
    response = Mock()
    response.content = b"test content"
    response.raise_for_status = Mock()
    return response


@pytest.fixture
def downloader(valid_db_config, sinapi_config):
    """Fixture que cria uma instância do Downloader com config mockada."""
    config = Config(db_config=valid_db_config, sinapi_config=sinapi_config, mode="server")
    return Downloader(config)


# Testes de URL Building
def test_build_url_referencia(downloader):
    """Testa construção de URL para planilha referencial."""
    url = downloader._build_url()
    assert "SINAPI_REFERENCIA_01_2023.zip" in url
    assert url.startswith("https://www.caixa.gov.br/Downloads/sinapi-a-vista-composicoes")


def test_build_url_desonerado(valid_db_config):
    """Testa construção de URL para planilha desonerada."""
    sinapi_cfg = {"state": "SP", "month": "12", "year": "2023", "type": "DESONERADO"}
    config = Config(db_config=valid_db_config, sinapi_config=sinapi_cfg, mode="server")
    downloader = Downloader(config)
    url = downloader._build_url()
    assert "SINAPI_DESONERADO_12_2023.zip" in url


def test_build_url_invalid_type(valid_db_config):
    """Testa erro ao construir URL com tipo inválido."""
    sinapi_cfg = {"state": "SP", "month": "01", "year": "2023", "type": "INVALIDO"}
    config = Config(db_config=valid_db_config, sinapi_config=sinapi_cfg, mode="server")
    downloader = Downloader(config)
    with pytest.raises(ValueError, match="Tipo de planilha inválido"):
        downloader._build_url()


def test_build_url_zero_padding(valid_db_config):
    """Testa padding com zeros nos números."""
    sinapi_cfg = {"state": "SP", "month": 1, "year": 2023, "type": "REFERENCIA"}
    config = Config(db_config=valid_db_config, sinapi_config=sinapi_cfg, mode="server")
    downloader = Downloader(config)
    url = downloader._build_url()
    assert "SINAPI_REFERENCIA_01_2023.zip" in url


# Testes de Funcionalidade
@patch("autosinapi.core.downloader.requests.Session")
def test_successful_download(mock_session, valid_db_config, sinapi_config, mock_response):
    """Deve realizar download com sucesso."""
    session = Mock()
    session.get.return_value = mock_response
    mock_session.return_value = session

    config = Config(db_config=valid_db_config, sinapi_config=sinapi_config, mode="server")
    downloader = Downloader(config)

    result = downloader.get_sinapi_data()
    assert isinstance(result, BytesIO)
    assert result.getvalue() == b"test content"
    session.get.assert_called_once()


@patch("autosinapi.core.downloader.requests.Session")
def test_download_network_error(mock_session, valid_db_config, sinapi_config):
    """Deve tratar erro de rede corretamente."""
    session = Mock()
    session.get.side_effect = requests.ConnectionError("Network error")
    mock_session.return_value = session

    config = Config(db_config=valid_db_config, sinapi_config=sinapi_config, mode="server")
    downloader = Downloader(config)

    with pytest.raises(DownloadError, match="Erro no download: Network error"):
        downloader.get_sinapi_data()


@patch("autosinapi.core.downloader.requests.Session")
def test_local_mode_save(mock_session, valid_db_config, sinapi_config, mock_response, tmp_path):
    """Deve salvar arquivo localmente em modo local."""
    session = Mock()
    session.get.return_value = mock_response
    mock_session.return_value = session

    save_path = tmp_path / "test.xlsx"
    
    # Cria config para modo local
    config = Config(db_config=valid_db_config, sinapi_config=sinapi_config, mode="local")
    downloader = Downloader(config)
    
    result = downloader.get_sinapi_data(save_path=save_path)
    
    assert save_path.exists()
    assert save_path.read_bytes() == b"test content"
    assert isinstance(result, BytesIO)
    assert result.getvalue() == b"test content"


def test_context_manager(downloader):
    """Deve funcionar corretamente como context manager."""
    with downloader as d:
        assert isinstance(d, Downloader)