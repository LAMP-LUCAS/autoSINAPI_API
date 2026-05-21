# api/config.py
"""
Módulo de Configuração da AutoSINAPI API.

Este módulo define a classe `Settings`, baseada em Pydantic, responsável por
centralizar, validar e gerenciar todas as configurações necessárias para a
execução da API.

As configurações são carregadas a partir de variáveis de ambiente, com
valores padrão definidos para facilitar o desenvolvimento e a implantação.
O arquivo `.env` é lido automaticamente.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict

from .sandbox_utils import get_sandbox_table_name

class Settings(BaseSettings):
    """
    Gerencia as configurações da aplicação, lendo de variáveis de ambiente.
    """
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Configurações do Banco de Dados ---
    # A URL de conexão completa, lida diretamente do .env
    DATABASE_URL: str

    # --- Nomes de Tabelas e Views (centralizando "magic strings") ---
    # Permite alterar nomes de tabelas em um único lugar, se necessário.
    @property
    def TABLE_INSUMOS(self) -> str:
        return get_sandbox_table_name("insumos")

    @property
    def TABLE_COMPOSICOES(self) -> str:
        return get_sandbox_table_name("composicoes")

    @property
    def TABLE_PRECOS_INSUMOS(self) -> str:
        return get_sandbox_table_name("precos_insumos_mensal")

    @property
    def TABLE_CUSTOS_COMPOSICOES(self) -> str:
        return get_sandbox_table_name("custos_composicoes_mensal")

    @property
    def VIEW_COMPOSICAO_ITENS(self) -> str:
        return get_sandbox_table_name("vw_composicao_itens_unificados")

    # --- Configurações de Cache ---
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    CACHE_DEFAULT_TTL: int = 86400  # 24 horas

    # --- Constantes de Negócio ---
    # Centraliza valores padrão usados nas queries.
    DEFAULT_ITEM_STATUS: str = "ATIVO"

# Cria uma instância única das configurações que será importada pelo resto da aplicação.
# Isso garante que as configurações sejam lidas e validadas uma única vez.
settings = Settings()