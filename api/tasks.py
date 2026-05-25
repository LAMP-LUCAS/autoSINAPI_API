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

import os
import redis
from celery import Celery
import autosinapi

# Instancia o app Celery
celery_app = Celery('tasks')
celery_app.config_from_object('api.celery_config')

# Cliente Redis para gerenciar o lock
redis_client = redis.Redis(host=os.getenv("REDIS_HOST", "redis"), port=6379, db=0)

@celery_app.task(bind=True, max_retries=3, default_retry_delay=300)
def populate_sinapi_task(self, db_config: dict, sinapi_config: dict):
    """
    A tarefa que o Celery Worker irá executar para popular a base de dados.
    Implementa limpeza de lock ao final e política de retentativa.
    """
    year = sinapi_config.get('year')
    month = sinapi_config.get('month')
    state = sinapi_config.get('state', 'SP')
    mode_suffix = 'sandbox' if os.getenv("AUTOSINAPI_SANDBOX") == "true" else 'prod'
    lock_key = f"lock:autosinapi:populate:{year}:{month:02d}:{state.upper()}:{mode_suffix}"

    try:
        print(f"[{self.request.id}] Iniciando ETL para {state} {month}/{year} (Modo: {mode_suffix})...")
        
        result = autosinapi.run_etl(
            db_config=db_config,
            sinapi_config=sinapi_config,
            mode='server'
        )
        
        if result.get("status") == "failed":
            msg = result.get("message", "")
            print(f"[{self.request.id}] Erro no Toolkit: {msg}")
            if "Too Many Requests" in msg or "429" in msg:
                raise self.retry(countdown=600)
            return result

        print(f"[{self.request.id}] Tarefa de ETL concluída com sucesso.")
        return result
    except Exception as e:
        print(f"[{self.request.id}] Erro fatal ao executar a tarefa: {e}")
        raise
    finally:
        # Garante a remoção do lock para permitir novas tentativas
        if not self.request.called_directly:
            redis_client.delete(lock_key)
            print(f"[{self.request.id}] Lock {lock_key} liberado.")
