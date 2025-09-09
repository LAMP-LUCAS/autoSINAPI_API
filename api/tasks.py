# api/tasks.py
"""
Módulo de Definição de Tarefas Assíncronas (Celery).

Este módulo define as tarefas que serão executadas em segundo plano pelos
workers do Celery. A principal vantagem é desacoplar processos demorados
da API principal, garantindo que a API permaneça rápida e responsiva.

- `celery_app`: Instancia a aplicação Celery e carrega sua configuração
  a partir do módulo `api.celery_config`.

- `populate_sinapi_task`: É a tarefa principal, que atua como uma ponte entre
  a API e o toolkit `autosinapi`. Ela recebe os dicionários de configuração
  do endpoint da API e os repassa para a função `autosinapi.run_etl`.
  Todo o processo de download, processamento e carga de dados acontece
  aqui, de forma isolada do processo da API.
"""

from celery import Celery
# O toolkit AutoSINAPI é importado como uma biblioteca instalada no ambiente.
import autosinapi

# Instancia o app Celery, sem configurar URLs diretamente aqui.
celery_app = Celery('tasks')
# Carrega a configuração a partir do arquivo celery_config.py
celery_app.config_from_object('api.celery_config')

@celery_app.task
def populate_sinapi_task(db_config: dict, sinapi_config: dict):
    """
    A tarefa que o Celery Worker irá executar para popular a base de dados.

    Recebe as configurações do banco de dados e do SINAPI, e dispara o processo
    de ETL da biblioteca `autosinapi`.
    """
    try:
        # Chama a interface pública do toolkit para executar o ETL
        print(f"Iniciando tarefa de ETL para {sinapi_config.get('month')}/{sinapi_config.get('year')}...")
        result = autosinapi.run_etl(
            db_config=db_config,
            sinapi_config=sinapi_config,
            mode='server' # Modo 'server' é ideal para workers, pois não salva arquivos intermediários
        )
        print("Tarefa de ETL concluída com sucesso.")
        return result
    except Exception as e:
        # Loga o erro e relança para que a tarefa seja marcada como FALHA no Celery
        print(f"Erro ao executar a tarefa de população: {e}")
        raise
