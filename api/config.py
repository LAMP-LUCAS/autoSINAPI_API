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

from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    """
    Gerencia as configurações da aplicação, lendo de variáveis de ambiente.
    """
    # --- Configurações do Banco de Dados ---
    # A URL de conexão completa, lida diretamente do .env
    DATABASE_URL: str

    # --- Nomes de Tabelas e Views (centralizando "magic strings") ---
    # Permite alterar nomes de tabelas em um único lugar, se necessário.
    TABLE_INSUMOS: str = "insumos"
    TABLE_COMPOSICOES: str = "composicoes"
    TABLE_PRECOS_INSUMOS: str = "precos_insumos_mensal"
    TABLE_CUSTOS_COMPOSICOES: str = "custos_composicoes_mensal"
    VIEW_COMPOSICAO_ITENS: str = "vw_composicao_itens_unificados"

    # --- Constantes de Negócio ---
    # Centraliza valores padrão usados nas queries.
    DEFAULT_ITEM_STATUS: str = "ATIVO"

    class Config:
        # Pede ao Pydantic para carregar as variáveis de um arquivo .env
        env_file = ".env"

# Cria uma instância única das configurações que será importada pelo resto da aplicação.
# Isso garante que as configurações sejam lidas e validadas uma única vez.
settings = Settings()