# Dockerfile

# Estágio 1: Imagem base
FROM python:3.10-slim

# Variáveis de ambiente
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Estágio 2: Instalação de dependências
WORKDIR /app
COPY requirements.txt .
# Copy AutoSINAPI toolkit before pip install for local install
COPY ./AutoSINAPI /app/AutoSINAPI
RUN apt-get update && \
    apt-get install -y git --no-install-recommends && \
    pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    SETUPTOOLS_SCM_PRETEND_VERSION_FOR_AUTOSINAPI=0.1.0 pip install --no-cache-dir ./AutoSINAPI && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Estágio 3: Cópia do código da aplicação
COPY ./api /app/api

# Estágio 4: Segurança e Execução
RUN apt-get update && apt-get install -y wget procps --no-install-recommends && \
    rm -rf /var/lib/apt/lists/* && \
    useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app
USER appuser

# Expõe a porta que o Uvicorn usará
EXPOSE 8000
# Inicia o servidor Uvicorn
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
