# api/tasks.py
from celery import Celery
# Supondo que o AutoSINAPI será instalado como uma biblioteca
import autosinapi 

# Instancia o app Celery
celery_app = Celery('tasks', broker='redis://redis:6379/0', backend='redis://redis:6379/0')
celery_app.config_from_object('api.celery_config')

@celery_app.task
def populate_sinapi_task(db_config: dict, sinapi_config: dict):
    """
    A tarefa que o Celery Worker irá executar.
    Ela chama a função principal do nosso toolkit AutoSINAPI.
    """
    try:
        # Chama a interface pública que definimos para o toolkit
        result = autosinapi.run_etl(
            db_config=db_config,
            sinapi_config=sinapi_config,
            mode='server' # Modo de alta performance
        )
        return result
    except Exception as e:
        # Logar o erro e relançar para que a tarefa seja marcada como falha
        print(f"Erro ao executar a tarefa de população: {e}")
        raise
