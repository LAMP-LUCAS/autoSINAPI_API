# 🚨 URGENTE: AutoSINAPI - Sobrecarga do Servidor

**Data:** 2026-05-18
**Severidade:** Alta
**Status:** Documentado — aguardando correção

---

## Problema Identificado

A API AutoSINAPI estava sobrecarregando o servidor. Após análise do código, foram identificados **3 problemas críticos** na gestão de filas Celery que podem causar consumo excessivo de CPU/RAM.

---

## Causas Raiz

### 1. Falta de Rate Limiting no Celery Worker

**Arquivo:** `api/celery_config.py`

O Celery está configurado sem nenhum limite de concorrência ou rate limiting:

```python
broker_url = 'redis://redis:6379/0'
result_backend = 'redis://redis:6379/0'
# SEM worker_concurrency, SEM task_acks_late, SEM rate limits
```

**Problema:** Se múltiplas tarefas `populate_sinapi_task` forem enfileiradas (ex: usuário clicando várias vezes no endpoint `/admin/populate-database`), o worker vai tentar executar todas simultaneamente. Cada tarefa de ETL do SINAPI consome ~1-2GB de RAM e CPU intensiva para download + processamento de arquivos ZIP + carga no PostgreSQL.

**Impacto:** 3-4 tarefas concorrentes = 4-8GB RAM + 100% CPU → servidor engasga.

### 2. Falta de Idempotência / Deduplicação de Tarefas

**Arquivo:** `api/main.py`, linha 32-48

O endpoint `/admin/populate-database` não verifica se já existe uma tarefa rodando para o mesmo mês/ano:

```python
@app.post("/admin/populate-database", status_code=202, tags=["Admin"])
def trigger_database_population(year: int = Body(...), month: int = Body(...)):
    # SEM VERIFICAÇÃO: já existe tarefa rodando para este month/year?
    task = populate_sinapi_task.delay(db_config, sinapi_config)
    return {"message": "...", "task_id": task.id}
```

**Problema:** Se o usuário chamar o endpoint 5 vezes para o mesmo mês/ano, 5 tarefas idênticas serão enfileiradas e executadas, desperdiçando recursos e podendo causar race conditions no banco.

### 3. Falta de Timeout e Retry Policy

**Arquivo:** `api/tasks.py`

A tarefa `populate_sinapi_task` não tem:
- `time_limit` (timeout hard)
- `soft_time_limit` (timeout soft com exception)
- `max_retries` / `retry_backoff` (política de retry)

**Problema:** Se a ETL travar (ex: download lento, timeout de rede, DB lock), o worker fica preso indefinidamente consumindo memória sem nunca liberar.

---

## Correções Recomendadas

### Correção 1: `api/celery_config.py`

```python
# api/celery_config.py
broker_url = 'redis://redis:6379/0'
result_backend = 'redis://redis:6379/0'

# LIMITAR CONCURRENCIA: Máximo 1 tarefa ETL por vez (ETL é pesada)
worker_concurrency = 1

# Rate limit na tarefa de ETL: máx 1 execução a cada 10 minutos
task_default_rate_limit = '1/m'

# Acknowledge apenas após conclusão (evita perda em crash)
task_acks_late = True

# Rejeitar tarefas se o worker estiver sobrecarregado
worker_max_tasks_per_child = 10  # Recicla worker a cada 10 tarefas

# Timeout global de tarefas (em segundos) — ETL do SINAPI pode demorar, mas não horas
task_soft_time_limit = 1800   # 30 min: worker lança SoftTimeLimitExceeded
task_time_limit = 2400        # 40 min: hard kill do processo

# Policy de retry
task_reject_on_worker_lost = True
```

### Correção 2: `api/tasks.py` — Adicionar limites na tarefa

```python
@celery_app.task(
    bind=True,
    max_retries=2,
    default_retry_delay=60,
    rate_limit='1/10m',  # Máx 1 execução a cada 10 minutos
    soft_time_limit=1800,
    time_limit=2400,
)
def populate_sinapi_task(self, db_config: dict, sinapi_config: dict):
    """
    A tarefa que o Celery Worker irá executar para popular a base de dados.
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
    except autosinapi.ETLTimeoutError as e:
        # Timeout específico do toolkit — retry com backoff
        print(f"Timeout na ETL: {e}. Retry em {self.default_retry_delay}s...")
        raise self.retry(exc=e, countdown=self.default_retry_delay)
    except Exception as e:
        print(f"Erro ao executar a tarefa de população: {e}")
        raise
```

### Correção 3: `api/main.py` — Deduplicação no endpoint

```python
# Adicionar no topo:
from celery.result import AsyncResult
import json

# Cache simples para rastrear tarefas ativas por (year, month)
# Em produção, usar Redis para persistência entre restarts
_active_tasks = {}

@app.post("/admin/populate-database", status_code=202, tags=["Admin"])
def trigger_database_population(year: int = Body(...), month: int = Body(...)):
    """
    Dispara a tarefa de download e população da base SINAPI para um mês/ano.
    Evita duplicação: se já existe uma tarefa rodando para o mesmo período,
    retorna o task_id existente.
    """
    task_key = f"{year}-{month:02d}"
    
    # Verificar se já existe tarefa ativa para este período
    if task_key in _active_tasks:
        task_id = _active_tasks[task_key]
        result = AsyncResult(task_id, app=populate_sinapi_task.app)
        if result.status in ('PENDING', 'STARTED', 'RETRY'):
            return {
                "message": f"Tarefa já em execução para {task_key}.",
                "task_id": task_id,
                "status": result.status
            }
        else:
            # Tarefa anterior já terminou, remover do cache
            del _active_tasks[task_key]
    
    db_config = {
        "host": os.getenv("POSTGRES_HOST", "db"),
        "port": os.getenv("POSTGRES_PORT", 5432),
        "database": os.getenv("POSTGRES_DB"),
        "user": os.getenv("POSTGRES_USER"),
        "password": os.getenv("POSTGRES_PASSWORD"),
    }
    sinapi_config = { "year": year, "month": month }

    task = populate_sinapi_task.delay(db_config, sinapi_config)
    _active_tasks[task_key] = task.id
    
    return {
        "message": "Tarefa de população da base de dados iniciada com sucesso.",
        "task_id": task.id
    }

# Adicionar endpoint para verificar status de tarefas
@app.get("/admin/tasks/{task_id}", tags=["Admin"])
def get_task_status(task_id: str):
    """Verifica o status de uma tarefa Celery."""
    result = AsyncResult(task_id, app=populate_sinapi_task.app)
    return {
        "task_id": task_id,
        "status": result.status,
        "result": str(result.result) if result.ready() else None
    }
```

### Correção 4: `compose.yaml` — Limitar recursos do worker

O `compose.yaml` já limita o worker a 1 CPU e 2GB RAM, o que é bom. Mas adicionar:

```yaml
  celery_worker:
    # ... existente ...
    environment:
      - C_FORCE_ROOT=true  # Necessário para rodar como root no container
      - CELERY_WORKER_CONCURRENCY=1  # Override via env
      - CELERY_WORKER_MAX_TASKS_PER_CHILD=10
    # ... existente ...
```

---

## Resumo das Mudanças

| Arquivo | Mudança | Impacto |
|---|---|---|
| `api/celery_config.py` | Concurrency=1, rate limits, timeouts | Impede sobrecarga por concorrência |
| `api/tasks.py` | Task decorators com retry, timeout | Worker não fica preso em tarefas travadas |
| `api/main.py` | Deduplicação de tarefas por período | Evita execuções duplicadas |
| `compose.yaml` | Env vars de controle do worker | Defesa em profundidade |

---

## Próximos Passos

1. Aplicar as correções acima no repo `repos/autosinapi_api/`
2. Testar localmente com carga simulada (múltiplas chamadas ao `/admin/populate-database`)
3. Redeploy via `bash automation/scripts/manage_stacks.sh up autosinapi`
4. Monitorar via Netdata/Sentinela nas primeiras execuções
