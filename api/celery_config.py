# api/celery_config.py
"""
Módulo de Configuração do Celery.

Este arquivo centraliza as configurações essenciais para a aplicação Celery,
que gerencia as tarefas em segundo plano.

- `broker_url`: Define o endereço do message broker (Redis), que é a fila
  onde a API publica as tarefas a serem executadas. O nome 'redis' funciona
  porque os contêineres estão na mesma rede Docker[cite: 7].

- `result_backend`: Define o endereço do backend de resultados (também Redis),
  onde o Celery armazena o estado e o resultado das tarefas executadas.
"""

import os

# Configurações para o Celery
# Utiliza REDIS_HOST do ambiente ou fallback para o nome único da stack
redis_host = os.getenv("REDIS_HOST", "autosinapi_redis")
broker_url = f'redis://{redis_host}:6379/0'
result_backend = f'redis://{redis_host}:6379/0'

# --- Limites de Concorrência e Sobrecarga ---
# Máximo 1 tarefa por worker (ETL do SINAPI é pesada e consome muita RAM)
worker_concurrency = 1

# Recicla o processo worker a cada 10 tarefas para evitar vazamentos de memória (comum com Pandas/Openpyxl)
worker_max_tasks_per_child = 10

# Pre-fetch de apenas 1 tarefa por vez
worker_prefetch_multiplier = 1

# --- Resiliência e Confirmação ---
# Acknowledge apenas após a conclusão da tarefa (evita perda se o container cair no meio)
task_acks_late = True

# Se o worker sumir (ex: OOM Kill), a tarefa é rejeitada e pode ser re-enfileirada
task_reject_on_worker_lost = True

# --- Timeouts (Defesa contra tarefas travadas) ---
# Hard kill após 90 minutos (Ingestão nacional de SP é pesada)
task_time_limit = 5400

# Soft timeout (lança exception SoftTimeLimitExceeded) após 60 minutos
task_soft_time_limit = 3600