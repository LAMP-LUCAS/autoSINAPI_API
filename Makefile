
.PHONY: up down populate-db logs-api logs-kong status

up:
	@echo "Iniciando os containers Docker em modo detached..."
	docker-compose up --build -d

down:
	@echo "Parando e removendo os containers, redes e volumes..."
	docker-compose down -v

populate-db:
	@echo "Disparando a tarefa de ETL para popular o banco de dados..."
	docker-compose exec api python -c "from tasks import populate_database; populate_database.delay()"

logs-api:
	@echo "Exibindo logs do container da API..."
	docker-compose logs -f api

logs-kong:
	@echo "Exibindo logs do container do Kong..."
	docker-compose logs -f kong

status:
	@echo "Verificando o status dos containers..."
	docker-compose ps
