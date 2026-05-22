"""
Testes unitários para o módulo de configuração.
"""

import pytest

from autosinapi.config import Config
from autosinapi.exceptions import ConfigurationError


# Fixtures
@pytest.fixture
def valid_db_config():
    return {
        "host": "localhost",
        "port": 5432,
        "database": "test_db",
        "user": "test_user",
        "password": "test_pass",
    }


@pytest.fixture
def valid_sinapi_config():
    return {"state": "SP", "month": "01", "year": "2023", "type": "insumos"}


# Testes
def test_valid_config(valid_db_config, valid_sinapi_config):
    """Deve criar configuração válida com sucesso."""
    config = Config(valid_db_config, valid_sinapi_config, "server")
    assert config.mode == "server"
    assert config.db_config == valid_db_config
    assert config.sinapi_config == valid_sinapi_config


def test_invalid_mode(valid_db_config, valid_sinapi_config):
    """Deve levantar erro para modo inválido."""
    with pytest.raises(ConfigurationError) as exc_info:
        Config(valid_db_config, valid_sinapi_config, "invalid")
    assert "Modo inválido" in str(exc_info.value)


def test_missing_db_config(valid_sinapi_config):
    """Deve levantar erro para config de DB incompleta."""
    with pytest.raises(ConfigurationError) as exc_info:
        Config({"host": "localhost"}, valid_sinapi_config, "server")
    assert "Configurações de banco ausentes" in str(exc_info.value)


def test_missing_sinapi_config(valid_db_config):
    """Deve levantar erro para config do SINAPI incompleta."""
    with pytest.raises(ConfigurationError) as exc_info:
        Config(valid_db_config, {"state": "SP"}, "server")
    assert "Configurações do SINAPI ausentes" in str(exc_info.value)


def test_mode_properties(valid_db_config, valid_sinapi_config):
    """Deve retornar corretamente o modo de operação."""
    config = Config(valid_db_config, valid_sinapi_config, "server")
    assert config.is_server_mode is True
    assert config.is_local_mode is False
