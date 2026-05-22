# Makefile para gerenciar o ambiente Docker do AutoSINAPI
# Fornece atalhos para os comandos mais comuns do docker-compose.

.PHONY: help build build-no-cache up run run-local down app-down db-down adminer-down app-start db-start adminer-start clean clean-app clean-db clean-adminer shell logs logs-app logs-db logs-adminer

# Garante que as variaveis do .env sejam carregadas
include .env

# Define o nome do projeto para evitar ambiguidades
COMPOSE_PROJECT_NAME=autosinapi

help:
	@echo "Comandos disponiveis:"
	@echo "  make build          - (Re)constroi a imagem da aplicacao usando o cache."
	@echo "  make build-no-cache - Forca a reconstrucao da imagem do zero (use apos adicionar dependencias)."
	@echo "  make up             - Sobe todos os servicos (db, app, adminer) em background."
	@echo "  make run            - Executa o pipeline de ETL (com download) dentro do container 'app'."
	@echo "  make run-local      - Executa o pipeline de ETL (sem download) usando arquivos locais."
	@echo "  make down           - Para e remove os conteineres."
	@echo "  make app-down       - Para o container app"
	@echo "  make db-down        - Para o container db"
	@echo "  make adminer-down   - Para o container adminer"
	@echo "  make app-start      - Inicia o container app"
	@echo "  make db-start       - Inicia o container db"
	@echo "  make adminer-start  - Inicia o container adminer"
	@echo "  make clean          - Para tudo e apaga os volumes (DADOS DO DB SERAO PERDIDOS)."
	@echo "  make clean-app      - Para o container app e remove os volumes."
	@echo "  make clean-db       - Para o container db e remove os volumes."
	@echo "  make clean-adminer  - Para o container adminer e remove os volumes."
	@echo "  make shell          - Abre um terminal interativo dentro do conteiner 'app' que ja esta rodando."
	@echo " "
	@echo "Comandos de Log:"
	@echo "  make logs           - Exibe os logs de TODOS os servicos em tempo real."
	@echo "  make logs-app       - Exibe os logs apenas da aplicacao."
	@echo "  make logs-db        - Exibe os logs apenas do banco de dados."
	@echo "  make logs-adminer   - Exibe os logs apenas do adminer."
	@echo " "
	@echo "Utilitarios:"
	@echo "  Adminer (DB GUI): http://localhost:8080"

# Constroi ou reconstroi a imagem da aplicacao se houver mudancas
build:
	@echo "=> Construindo as imagens Docker..."
	docker-compose build

# Forca a reconstrucao da imagem sem usar o cache
build-no-cache:
	@echo "=> Construindo as imagens Docker sem usar o cache..."
	docker-compose build --no-cache

# Sobe todos os servicos (db, app, adminer) em background
up:
	@echo "=> Iniciando todos os servicos em background..."
	docker-compose up -d

# =============================================================================
#                             COMANDOS DE EXECUÇÃO
# =============================================================================

# Executa o pipeline com download
run:
	@echo "=> Executando o pipeline do AutoSINAPI (com download) via 'exec'..."
	docker-compose exec -e AUTOSINAPI_SKIP_DOWNLOAD=False app python -c "from autosinapi import run_etl; run_etl(mode='server', log_level='INFO')"

# Executa o pipeline sem download, usando arquivos locais
run-local:
	@echo "=> Executando o pipeline em MODO LOCAL (sem download) via 'exec'..."
	docker-compose exec -e AUTOSINAPI_SKIP_DOWNLOAD=True app python -c "from autosinapi import run_etl; run_etl(mode='server', log_level='INFO')"

# =============================================================================

# Para e remove os conteineres de todos os serviços
down:
	@echo "=> Parando e removendo os conteineres..."
	docker-compose down

# Para containers individuais
app-down:
	@echo "=> Parando o container 'app'..."
	docker-compose stop app

db-down:
	@echo "=> Parando o container 'db'..."
	docker-compose stop db

adminer-down:
	@echo "=> Parando o container 'adminer'..."
	docker-compose stop adminer

# Inicia containers individuais que já existem mas estão parados
app-start:
	@echo "=> Iniciando o container 'app'..."
	docker-compose start app

db-start:
	@echo "=> Iniciando o container 'db'..."
	docker-compose start db

adminer-start:
	@echo "=> Iniciando o container 'adminer'..."
	docker-compose start adminer

# Limpa tudo: containers e volumes (cuidado!)
clean: 
	@echo "=> ATENCAO: Este comando ira apagar TUDO, incluindo o banco de dados."
	@echo "=> Parando conteineres e removendo volumes..."
	docker-compose down --volumes

# Limpa containers e volumes individuais
clean-app:
	@echo "=> ATENCAO: Parando e removendo o container 'app' e seus volumes..."
	docker-compose rm -s -v app

clean-db:
	@echo "=> ATENCAO: Parando e removendo o container 'db' e seus volumes (DADOS SERAO PERDIDOS)..."
	docker-compose rm -s -v db

clean-adminer:
	@echo "=> ATENCAO: Parando e removendo o container 'adminer' e seus volumes..."
	docker-compose rm -s -v adminer

# Comandos de Log
logs:
	@echo "=> Exibindo logs de todos os servicos (Pressione Ctrl+C para sair)..."
	docker-compose logs -f

logs-app:
	@echo "=> Exibindo logs da aplicacao (Pressione Ctrl+C para sair)..."
	docker-compose logs -f app

logs-db:
	@echo "=> Exibindo logs do banco de dados (Pressione Ctrl+C para sair)..."
	docker-compose logs -f db

logs-adminer:
	@echo "=> Exibindo logs do Adminer (Pressione Ctrl+C para sair)..."
	docker-compose logs -f adminer

# Abre um shell interativo no conteiner da aplicacao
shell:
	@echo "=> Abrindo shell interativo no conteiner 'app'..."
	docker-compose exec app bash
