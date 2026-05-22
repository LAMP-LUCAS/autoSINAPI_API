# Use uma imagem base oficial do Python
FROM python:3.9-slim

# Instala o Git
RUN apt-get update && apt-get install -y git

# Define o diretorio de trabalho dentro do container
WORKDIR /app

# Copia os arquivos de configuração do projeto para o diretorio de trabalho
COPY pyproject.toml /app/
COPY setup.py /app/
COPY autosinapi/ /app/autosinapi/

# Copia o restante do contexto do projeto
COPY . /app

# Desinstala o pacote autosinapi se existir, para garantir uma instalação limpa
RUN pip uninstall -y autosinapi || true

# Atualiza o pip e instala o driver do postgres explicitamente
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir psycopg2-binary

# Instala as dependencias do projeto
RUN pip install --no-cache-dir --force-reinstall .

# Define o comando padrao para executar o pipeline
CMD ["python", "-m", "autosinapi.etl_pipeline"]