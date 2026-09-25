# api/database.py
"""
Módulo de Conexão com o Banco de Dados.

Este módulo é responsável por estabelecer e gerenciar a conexão com o banco de
dados PostgreSQL. Ele utiliza SQLAlchemy para criar um 'engine' de conexão e
gerencia as sessões que serão utilizadas pela aplicação.

Principais Funções:
- Carrega a URL de conexão a partir da variável de ambiente `DATABASE_URL`,
  que é definida no arquivo .env[cite: 4].
- Cria um 'engine' do SQLAlchemy, que gerencia um pool de conexões com o banco.
- Fornece a função `get_db`, que atua como uma dependência do FastAPI. A cada
  requisição a um endpoint, o `get_db` cria uma nova sessão, a disponibiliza
  para a lógica de negócio (CRUD), e garante que a sessão seja sempre fechada
  ao final da requisição, mesmo que ocorram erros. Este padrão garante o uso
  eficiente dos recursos do banco de dados.
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

# Carrega as variáveis de ambiente do arquivo .env [cite: 4]
load_dotenv()

# Lê a URL de conexão do ambiente [cite: 4]
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL")

if not SQLALCHEMY_DATABASE_URL:
    raise ValueError("Variável de ambiente DATABASE_URL não definida!")

engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# ── SaaS database (billing/subscriptions/coupons) ─────────────────────────────
# The public API gateway (Kong + ssl-mp-adapter) owns the SaaS domain and reads
# from its own PostgreSQL (`api-gateway-db`, database `saas`). The SINAPI data
# DB (DATABASE_URL) is a separate concern. Never silently use the data DB in a
# production process; local/test environments may opt into the legacy fallback.
SQLALCHEMY_SAAS_DATABASE_URL = os.getenv("SAAS_DATABASE_URL")
_RUNTIME_ENVIRONMENT = os.getenv("MP_ENVIRONMENT", os.getenv("ENVIRONMENT", "development")).lower()
if not SQLALCHEMY_SAAS_DATABASE_URL and _RUNTIME_ENVIRONMENT in {"prod", "production"}:
    raise RuntimeError("SAAS_DATABASE_URL must be configured in production")
SQLALCHEMY_SAAS_DATABASE_URL = SQLALCHEMY_SAAS_DATABASE_URL or SQLALCHEMY_DATABASE_URL

saas_engine = create_engine(SQLALCHEMY_SAAS_DATABASE_URL)
SaasSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=saas_engine)

def get_db():
    """
    Dependência do FastAPI que fornece uma sessão de banco de dados por requisição.

    Esta função cria uma nova sessão (`SessionLocal()`) para cada requisição,
    a injeta no endpoint através do `yield`, e garante que `db.close()` seja
    chamado ao final, liberando a conexão de volta para o pool.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_saas_db():
    """Sessão do banco SaaS (billing/assinaturas/cupons).

    Usada pelos endpoints de administração e pelo worker de ciclo de vida, que
    devem operar sobre o mesmo banco lido pelo gateway (api-gateway-db.saas).
    """
    db = SaasSessionLocal()
    try:
        yield db
    finally:
        db.close()