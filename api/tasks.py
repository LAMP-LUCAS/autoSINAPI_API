# api/tasks.py (versão corrigida e documentada)
"""
Módulo de Definição de Tarefas Assíncronas (Celery).

Este módulo define as tarefas que podem ser executadas em background pelo Celery Worker.
A principal tarefa é a `populate_sinapi_task`, que encapsula a chamada ao
pacote `autosinapi` para realizar o processo de ETL (Extração, Transformação e Carga).
"""
from celery import Celery
import autosinapi

celery_app = Celery('tasks')
celery_app.config_from_object('api.celery_config')

@celery_app.task
def populate_sinapi_task(db_config: dict, sinapi_config: dict):
    """
    A tarefa que o Celery Worker irá executar para popular a base de dados.

    Recebe as configurações do banco de dados e do SINAPI, e dispara o processo
    de ETL da biblioteca `autosinapi`.
    """
    try:
        print(f"Iniciando tarefa de ETL para {sinapi_config.get('month')}/{sinapi_config.get('year')}...")
        result = autosinapi.run_etl(
            db_config=db_config,
            sinapi_config=sinapi_config,
            mode='server'
        )
        print("Tarefa de ETL concluída com sucesso.")
        return result
    except Exception as e:
        print(f"Erro ao executar a tarefa de população: {e}")
        raise
