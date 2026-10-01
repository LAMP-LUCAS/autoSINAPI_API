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

    @property
    def TABLE_MANUTENCOES_HISTORICO(self) -> str:
        return get_sandbox_table_name("manutencoes_historico")

    # --- Configurações de Cache ---
    # SSOT: nome único da stack (evita colisão do alias genérico "redis"
    # no server_mesh, que round-robina para server_redis de outra stack).
    REDIS_HOST: str = "autosinapi_redis"
    REDIS_PORT: int = 6379
    CACHE_DEFAULT_TTL: int = 86400  # 24 horas

    # --- Constantes de Negócio ---
    # Centraliza valores padrão usados nas queries.
    DEFAULT_ITEM_STATUS: str = "ATIVO"

    # --- Observabilidade ---
    SENTRY_DSN: str | None = None
    SENTRY_ENV: str = "production"

    # --- Segurança Administrativa ---
    ADMIN_API_TOKEN: str | None = None

    # --- ETL Automatizado (STORY-GOLIVE-03) ---
    ETL_LOOKBACK_MONTHS: int = 1
    ETL_STATES: str = "SP"

    # --- Evento de conclusão de ETL (adapter neutro de saída, OPT-IN) ---
    # Ausente/vazia → nenhum evento é publicado (comportamento padrão do
    # repositório open source permanece inalterado). Quando configurada, a API
    # faz POST JSON do evento `etl.completed` ao final de cada execução — o
    # consumidor é definido exclusivamente por configuração de deploy, nunca
    # por código (ver api/etl_events.py).
    ETL_EVENT_WEBHOOK_URL: str | None = None
    # Timeout curto: um consumidor lento nunca pode segurar a task de ETL.
    ETL_EVENT_TIMEOUT: float = 5.0
    # Tentativas de publicação (1 = sem retry, comportamento histórico).
    # 3 cobre a janela comum de indisponibilidade do consumidor (restart,
    # deploy) sem transformar o ETL em cliente pesado: backoff 1s/4s.
    ETL_EVENT_TENTATIVAS: int = 3
    ETL_EVENT_BACKOFF: float = 1.0

    # --- Configurações de Segurança ---
    ALLOWED_ORIGINS: str = "*"  # Lista separada por vírgula. Ex: "https://demo.lamp.local,http://localhost:8080"

    # URL pública do servidor MCP, injetada pelo ambiente de deploy.
    # Mantida opcional para desenvolvimento; nunca usar hostname legado no código.
    MCP_PUBLIC_URL: str | None = None

    # --- Embeddings vetoriais (ADR-006 / STORY-SRC-004, Fase 4) ---
    # Provider primário: bge-m3 no Ollama do notebook (lampbook, via Tailscale).
    # Fallback: nomic-embed-text no Ollama local (server_ollama).
    EMBEDDING_PRIMARY_URL: str = "http://100.69.111.112:11434"
    EMBEDDING_PRIMARY_MODEL: str = "bge-m3"
    EMBEDDING_FALLBACK_URL: str = "http://server-ollama:11434"
    EMBEDDING_FALLBACK_MODEL: str = "nomic-embed-text"
    # Slug padrão no registry embedding_models → tabela `vec_1024_bge_m3`.
    SEARCH_VECTOR_MODEL: str = "bge_m3"
    # Tamanho do lote de geração de embeddings (warm-up ~21s no notebook).
    EMBEDDING_BATCH_SIZE: int = 16
    # Timeout de inferência: 1ª chamada no notebook inclui warm-up (~21s+).
    EMBEDDING_TIMEOUT: float = 120.0
    # Orçamento da camada vetorial POR REQUEST de busca (STORY-SIN-095/§3.3):
    # o passo inteiro (embedding + cosine) responde ou degrada dentro dele —
    # o primary pendurado não pode estourar o timeout do cliente (MCP 30s).
    # O provider recebe timeout/2 por endpoint (primary + fallback somam o orçamento).
    SEARCH_VECTOR_TIMEOUT: float = 8.0

# Cria uma instância única das configurações que será importada pelo resto da aplicação.
# Isso garante que as configurações sejam lidas e validadas uma única vez.
settings = Settings()