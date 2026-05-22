"""
AutoSINAPI: Um toolkit para automação de dados do SINAPI.

Este arquivo é o ponto de entrada do pacote `autosinapi`. Ele define a interface
pública da biblioteca, expondo as principais classes e exceções para serem
utilizadas por outras aplicações.

O `__all__` define explicitamente quais nomes são exportados quando um cliente
usa `from autosinapi import *`.
"""

__version__ = "0.1.0"  # A ser gerenciado pelo setuptools-scm

from autosinapi.config import Config
from autosinapi.core.database import Database
from autosinapi.core.downloader import Downloader
from autosinapi.core.processor import Processor
from autosinapi.exceptions import (AutoSinapiError, ConfigurationError,
                                   DatabaseError, DownloadError,
                                   ProcessingError)

__all__ = [
    "Config",
    "Database",
    "Downloader",
    "Processor",
    "AutoSinapiError",
    "ConfigurationError",
    "DownloadError",
    "ProcessingError",
    "DatabaseError",
    "run_etl"
]

import os
import logging
import uuid # Added for run_id generation
from contextlib import contextmanager
from typing import Dict, Any

from .etl_pipeline import PipelineETL, setup_logging


# Configure a logger for this module
logger = logging.getLogger(__name__)

@contextmanager
def set_env_vars(env_vars: Dict[str, str]):
    """Temporarily sets environment variables."""
    original_env = {key: os.getenv(key) for key in env_vars}
    for key, value in env_vars.items():
        os.environ[key] = str(value) # Ensure value is string for env vars
    try:
        yield
    finally:
        for key, value in original_env.items():
            if value is None:
                del os.environ[key]
            else:
                os.environ[key] = value

def run_etl(db_config: Dict[str, Any] = None, sinapi_config: Dict[str, Any] = None, mode: str = 'local', log_level: str = 'INFO'):
    # Generate a unique run_id for this execution
    run_id = str(uuid.uuid4())[:8]

    # Read skip_download from environment variable
    skip_download_env = os.getenv('AUTOSINAPI_SKIP_DOWNLOAD', 'False').lower()
    skip_download = (skip_download_env == 'true' or skip_download_env == '1')

    # If configs are not provided, try to load from environment variables
    if db_config is None:
        try:
            db_config = {
                'host': os.getenv('POSTGRES_HOST', 'db'),
                'port': int(os.getenv('POSTGRES_PORT', 5432)),
                'database': os.getenv('POSTGRES_DB'),
                'user': os.getenv('POSTGRES_USER'),
                'password': os.getenv('POSTGRES_PASSWORD')
            }
            # Basic validation for required DB vars
            if not all(db_config.get(k) for k in ['database', 'user', 'password']):
                raise ValueError("Variáveis de ambiente do banco de dados incompletas.")
        except (ValueError, TypeError) as e:
            logger.error(f"Erro ao carregar db_config de variáveis de ambiente: {e}", exc_info=True)
            return {
                "status": "failed",
                "message": f"Erro de configuração do banco de dados: {e}. Verifique as variáveis de ambiente POSTGRES_.",
                "tables_updated": [],
                "records_inserted": 0
            }

    if sinapi_config is None:
        try:
            sinapi_config = {
                'year': int(os.getenv('AUTOSINAPI_YEAR')),
                'month': int(os.getenv('AUTOSINAPI_MONTH')),
                'type': os.getenv('AUTOSINAPI_TYPE', 'REFERENCIA'),
                'duplicate_policy': os.getenv('AUTOSINAPI_POLICY', 'substituir')
            }
            # Basic validation for required SINAPI vars
            if not all(sinapi_config.get(k) for k in ['year', 'month']):
                raise ValueError("Variáveis de ambiente SINAPI incompletas.")
        except (ValueError, TypeError) as e:
            logger.error(f"Erro ao carregar sinapi_config de variáveis de ambiente: {e}", exc_info=True)
            return {
                "status": "failed",
                "message": f"Erro de configuração SINAPI: {e}. Verifique as variáveis de ambiente AUTOSINAPI_.",
                "tables_updated": [],
                "records_inserted": 0
            }

    # Validate inputs (after potentially loading from env vars)
    if not isinstance(db_config, dict) or not db_config:
        return {
            "status": "failed",
            "message": "Erro de validação: db_config inválido ou vazio.",
            "tables_updated": [],
            "records_inserted": 0
        }
    if not isinstance(sinapi_config, dict) or not sinapi_config:
        return {
            "status": "failed",
            "message": "Erro de validação: sinapi_config inválido ou vazio.",
            "tables_updated": [],
            "records_inserted": 0
        }
    if mode not in ['local', 'server']:
        return {
            "status": "failed",
            "message": "Erro de validação: mode deve ser 'local' ou 'server'.",
            "tables_updated": [],
            "records_inserted": 0
        }
    if log_level.upper() not in ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']:
        return {
            "status": "failed",
            "message": f"Erro de validação: log_level inválido: {log_level}. Use 'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'.",
            "tables_updated": [],
            "records_inserted": 0
        }

    # Prepare environment variables
    env_vars_to_set = {
        'DOCKER_ENV': 'true', # Assuming API runs in a docker-like environment
        'POSTGRES_HOST': db_config.get('host'),
        'POSTGRES_PORT': db_config.get('port'),
        'POSTGRES_DB': db_config.get('database'),
        'POSTGRES_USER': db_config.get('user'),
        'POSTGRES_PASSWORD': db_config.get('password'),
        'AUTOSINAPI_YEAR': sinapi_config.get('year'),
        'AUTOSINAPI_MONTH': sinapi_config.get('month'),
        'AUTOSINAPI_TYPE': sinapi_config.get('type', 'REFERENCIA'),
        'AUTOSINAPI_POLICY': sinapi_config.get('duplicate_policy', 'substituir'),
        'AUTOSINAPI_MODE': mode # Pass the mode
    }

    # Filter out None values
    env_vars_to_set = {k: v for k, v in env_vars_to_set.items() if v is not None}

    # Set up logging for the pipeline run
    # The setup_logging function in autosinapi_pipeline.py takes debug_mode.
    # We need to map log_level to debug_mode.
    debug_mode = (log_level.upper() == 'DEBUG')
    setup_logging(run_id=run_id, debug_mode=debug_mode)

    try:
        with set_env_vars(env_vars_to_set):
            logger.info(f"Iniciando execução do pipeline com modo: {mode}"
                        f"e nível de log: {log_level}")
            pipeline = PipelineETL(debug_mode=debug_mode, run_id=run_id) # Pass run_id to PipelineETL
            result = pipeline.run()
            logger.info("Pipeline executado com sucesso.")
            return result
    except Exception as e:
        logger.error(f"Erro ao executar o pipeline: {e}", exc_info=True)
        # Re-raise the exception to indicate task failure, or return a structured error
        # based on the user's request for run_etl to return a dictionary on failure.
        # Since pipeline.run() already returns a dictionary on failure,
        # this outer exception block should only catch errors *before* pipeline.run() is called
        # or unexpected errors not caught by pipeline.run().
        # For consistency, we'll return a structured error here too.
        return {
            "status": "failed",
            "message": f"Erro inesperado antes ou durante a inicialização do pipeline: {e}",
            "tables_updated": [],
            "records_inserted": 0
        }

