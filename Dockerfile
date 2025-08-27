# Dockerfile

# Estágio 1: Imagem base
FROM python:3.10-slim

# Variáveis de ambiente
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Estágio 2: Instalação de dependências
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Estágio 3: Cópia do código da aplicação
COPY ./api /app/api

# Estágio 4: Comando de execução
# Expõe a porta que o Uvicorn usará
EXPOSE 8000
# Inicia o servidor Uvicorn
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
