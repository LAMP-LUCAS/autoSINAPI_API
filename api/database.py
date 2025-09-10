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