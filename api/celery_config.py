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
from celery.schedules import crontab

# Configurações para o Celery
# Utiliza REDIS_HOST do ambiente ou fallback para o nome único da stack
redis_host = os.getenv("REDIS_HOST", "autosinapi_redis")
broker_url = f'redis://{redis_host}:6379/0'
result_backend = f'redis://{redis_host}:6379/0'

# --- Agendamento de Tarefas Periódicas (STORY-GOLIVE-03 / REGRA 7) ---
# Executa no dia 2 de cada mês às 03:00 UTC, para dar tempo de a SINAPI
# publicar a competência do mês anterior.
beat_schedule = {
    "monthly-etl": {
        "task": "api.tasks.schedule_monthly_etl",
        "schedule": crontab(day_of_month=2, hour=3, minute=0),
    },
    # --- Fase 4 (ADR-006): população de embeddings vetoriais ---
    # Diário às 04:00 UTC. Idempotente (upsert), degrada quando pgvector
    # ou o provider de embeddings estiver fora.
    "generate-embeddings": {
        "task": "api.tasks.generate_embeddings_task",
        "schedule": crontab(hour=4, minute=0),
    },
    # --- Plano de Gestão (D5): rollup horário de consumo ---
    # A cada 10 minutos, cobre a última hora completa de usage_logs
    # (idempotente por upsert; janela 2h para tolerância a atrasos).
    "rollup-consumption-hourly": {
        "task": "api.tasks.rollup_consumption_hourly",
        "schedule": crontab(minute="*/10"),
    },
    # --- Lifecycle: expiração de assinaturas (SR-GW-8) ---
    # De hora em hora, marca assinaturas vencidas como 'expired' e registra
    # auditoria/eventos. Idempotente.
    "expire-stale-subscriptions": {
        "task": "api.tasks.expire_stale_subscriptions",
        "schedule": crontab(minute=5),
    },
    # --- Funil CRM: reconciliação lead -> cliente convertido ---
    # A cada 10 minutos, marca o lead como 'converted' quando existe cliente
    # com o mesmo e-mail e assinatura ativa. Idempotente; alimenta o KPI de
    # conversão do funil (Funnel Metrics / dashboard).
    "sync-lead-conversions": {
        "task": "api.tasks.sync_lead_conversions",
        "schedule": crontab(minute="*/10"),
    },
}

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