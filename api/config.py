# api/config.py
"""
Módulo de Configuração da AutoSINAPI API.

Este módulo utiliza a biblioteca pydantic-settings para carregar e validar
configurações a partir de variáveis de ambiente (e de um arquivo .env).

Ele centraliza todos os valores que podem variar entre ambientes (desenvolvimento,
produção) ou que são importantes para a lógica de negócio (como nomes de tabelas),
seguindo o princípio de "Clean Code" de evitar "magic strings" e "hardcoded values".
"""

from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    """
    Gerencia as configurações da aplicação, lendo de variáveis de ambiente.
    """
    DATABASE_URL: str
    TABLE_INSUMOS: str = "insumos"
    TABLE_COMPOSICOES: str = "composicoes"
    TABLE_PRECOS_INSUMOS: str = "precos_insumos_mensal"
    TABLE_CUSTOS_COMPOSICOES: str = "custos_composicoes_mensal"
    VIEW_COMPOSICAO_ITENS: str = "vw_composicao_itens_unificados"
    DEFAULT_ITEM_STATUS: str = "ATIVO"

    class Config:
        env_file = ".env"

settings = Settings()
