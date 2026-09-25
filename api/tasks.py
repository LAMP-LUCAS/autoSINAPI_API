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
import logging
from celery import Celery
from sqlalchemy import text
import autosinapi

logger = logging.getLogger("autosinapi.tasks")

# Instancia o app Celery
celery_app = Celery('tasks')
celery_app.config_from_object('api.celery_config')


def run_populate_task(db_config: dict, sinapi_config: dict, lock_token: str = None) -> dict:
    """Executa o ETL e libera o lock de posse ao final.

    Extraído do wrapper Celery para ser testável de forma isolada. A liberação
    do lock só ocorre se este processo for o dono (token confere), evitando
    corrida entre retentativas/workers distintos.
    """
    year = sinapi_config.get('year')
    month = sinapi_config.get('month')
    state = sinapi_config.get('state', 'SP')
    mode_suffix = 'sandbox' if os.getenv("AUTOSINAPI_SANDBOX") == "true" else 'prod'
    try:
        logger.info("Iniciando ETL para %s %s/%s (Modo: %s)...", state, month, year, mode_suffix)
        result = autosinapi.run_etl(
            db_config=db_config,
            sinapi_config=sinapi_config,
            mode='server'
        )
        if result.get("status") == "success":
            _invalidate_caches()
        return result
    finally:
        # Libera o lock SOMENTE se este worker for o dono (token confere).
        from .populate_utils import release_populate_lock
        release_populate_lock(year, month, state, lock_token, sandbox=(mode_suffix == "sandbox"))


def _invalidate_caches():
    """Invalida caches da API e do Kong após ETL bem-sucedido."""
    from .cache_utils import invalidate_cache
    n1 = invalidate_cache('cache:get_global_stats:*')
    n2 = invalidate_cache('cache:get_available_filters:*')
    n3 = invalidate_cache('respcache:*')
    logger.info(
        "Caches pós-ETL invalidados: API stats=%d filters=%d Kong=%d",
        n1, n2, n3
    )


@celery_app.task(bind=True, max_retries=3, default_retry_delay=300)
def populate_sinapi_task(self, db_config: dict, sinapi_config: dict, lock_token: str = None):
    """
    Ponte Celery para run_populate_task. Mantém a política de retentativa
    (específica do Celery) e delega a execução/liberação de lock.
    """
    result = run_populate_task(db_config, sinapi_config, lock_token=lock_token)

    if result.get("status") == "failure":
        msg = result.get("message", "")
        if "Too Many Requests" in msg or "429" in msg:
            raise self.retry(countdown=600)

    return result


@celery_app.task(acks_late=True, max_retries=1, default_retry_delay=3600)
def schedule_monthly_etl():
    """Periodic task (Celery beat): compute & dispatch ETL for each ETL_STATES."""
    from .config import settings
    from .populate_utils import compute_target_month, parse_etl_states, dispatch_populate

    try:
        year, month = compute_target_month(settings.ETL_LOOKBACK_MONTHS)
        states = parse_etl_states(settings.ETL_STATES)

        if not states:
            logger.warning("ETL_STATES is empty; no ETL dispatched")
            return {"dispatched": 0, "reason": "no states configured"}

        dispatched = 0
        for state in states:
            result = dispatch_populate(year, month, state)
            if result is not None:
                dispatched += 1
                logger.info("ETL dispatched: %s %02d/%d task=%s", state, month, year, result["task_id"])
            else:
                logger.info("ETL skipped (lock held): %s %02d/%d", state, month, year)

        logger.info("schedule_monthly_etl done: %d/%d dispatched", dispatched, len(states))
        return {"dispatched": dispatched, "total": len(states)}
    except Exception as exc:
        logger.error("schedule_monthly_etl failed: %s", exc, exc_info=True)
        try:
            import sentry_sdk
            sentry_sdk.capture_exception(exc)
        except ImportError:
            pass
        raise


@celery_app.task(acks_late=True, max_retries=2, default_retry_delay=300)
def rollup_consumption_hourly():
    """Rollup horário de consumo (saas.consumption_hourly).

    Plano de Gestão (D5): agrega saas.usage_logs por hora (endpoint, tier,
    plan_slug) com latência p50/p95/max, cache HIT/MISS e custo estimado, com
    upsert idempotente. Roda via Celery beat a cada 10 minutos cobrindo a
    última hora completa. Popula a tabela que hoje está vazia e alimenta o
    futuro módulo interno de observabilidade/gestão/BI.
    """
    from .config import settings
    from .database import SaasSessionLocal

    db = SaasSessionLocal()
    try:
        row = db.execute(text("""
            WITH agg AS (
                SELECT
                    date_trunc('hour', requested_at) AS hour_start,
                    endpoint,
                    CASE
                        WHEN plan_slug IS NULL OR plan_slug = '' THEN '__anon__'
                        ELSE plan_slug
                    END AS plan_slug,
                    CASE
                        WHEN endpoint ~ '/bi/|/bom|/curva-abc|/tendencias|/precos-uf'
                             THEN 'tier_2'
                        WHEN endpoint ~ '/insumos|/composicoes|/produtividade'
                             THEN 'tier_1'
                        ELSE 'tier_1'
                    END AS tier,
                    COUNT(*) AS total_requests,
                    COUNT(*) FILTER (WHERE cache_status = 'HIT') AS cache_hits,
                    COUNT(*) FILTER (WHERE cache_status = 'MISS') AS cache_misses,
                    COALESCE(SUM(latency_ms), 0) AS sum_latency_ms,
                    ROUND(AVG(latency_ms), 3) AS avg_latency_ms,
                    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms) AS p95_latency_ms,
                    MAX(latency_ms) AS max_latency_ms,
                    ROUND(COUNT(*) * 0.00000023, 8) AS estimated_cost
                FROM saas.usage_logs
                WHERE requested_at >= date_trunc('hour', now() - interval '2 hours')
                GROUP BY 1, 2, 3, 4
            )
            INSERT INTO saas.consumption_hourly
                (hour_start, endpoint, tier, plan_slug, total_requests,
                 cache_hits, cache_misses, sum_latency_ms, avg_latency_ms,
                 p95_latency_ms, max_latency_ms, estimated_cost)
            SELECT
                hour_start, endpoint, tier, plan_slug, total_requests,
                cache_hits, cache_misses, sum_latency_ms, avg_latency_ms,
                p95_latency_ms, max_latency_ms, estimated_cost
            FROM agg
            ON CONFLICT (hour_start, endpoint, plan_slug) DO UPDATE SET
                tier = EXCLUDED.tier,
                total_requests = EXCLUDED.total_requests,
                cache_hits = EXCLUDED.cache_hits,
                cache_misses = EXCLUDED.cache_misses,
                sum_latency_ms = EXCLUDED.sum_latency_ms,
                avg_latency_ms = EXCLUDED.avg_latency_ms,
                p95_latency_ms = EXCLUDED.p95_latency_ms,
                max_latency_ms = EXCLUDED.max_latency_ms,
                estimated_cost = EXCLUDED.estimated_cost
            RETURNING hour_start
        """))
        rows = row.fetchall()
        db.commit()
        logger.info("rollup_consumption_hourly: %d hora(s) atualizada(s)", len(rows))
        return {"status": "success", "hours": len(rows)}
    except Exception as exc:
        db.rollback()
        logger.error("rollup_consumption_hourly failed: %s", exc, exc_info=True)
        try:
            import sentry_sdk
            sentry_sdk.capture_exception(exc)
        except ImportError:
            pass
        raise
    finally:
        db.close()


@celery_app.task(acks_late=True, max_retries=2, default_retry_delay=300)
def expire_stale_subscriptions():
    """Expira assinaturas cujo período já venceu (SR-GW-8 / lifecycle).

    Varre saas.subscriptions com status='active' e current_period_end < now(),
    marca como 'expired', registra em saas.expiration_events (audit/notificação)
    e em saas.client_events. Idempotente: só afeta assinaturas ainda marcadas
    como 'active'. Planos de acesso perpétuo (current_period_end ~ 2099) são
    ignorados naturalmente pelo filtro temporal.

    Roda no banco SaaS (api-gateway-db.saas) — o mesmo lido pelo gateway.
    """
    from .database import SaasSessionLocal

    db = SaasSessionLocal()
    try:
        # Seleciona assinaturas a expirar (com dados para auditoria)
        rows = db.execute(text("""
            SELECT s.id, s.client_id, s.plan_id, s.current_period_end,
                   p.slug AS plan_slug
            FROM saas.subscriptions s
            JOIN saas.plans p ON p.id = s.plan_id
            WHERE s.status = 'active'
              AND s.deleted_at IS NULL
              AND s.current_period_end IS NOT NULL
              AND s.current_period_end < NOW()
        """)).mappings().all()

        if not rows:
            logger.info("expire_stale_subscriptions: nenhuma assinatura a expirar")
            return {"status": "success", "expired": 0}

        expired_count = 0
        for r in rows:
            claimed = db.execute(
                text("""
                    UPDATE saas.subscriptions
                    SET status = 'expired', updated_at = NOW()
                    WHERE id = :id AND status = 'active'
                    RETURNING id
                """),
                {"id": r["id"]},
            ).scalar_one_or_none()
            if claimed is None:
                # Another worker claimed the same subscription between the scan
                # and this update; do not duplicate audit/events.
                continue
            expired_count += 1
            db.execute(
                text("""
                    INSERT INTO saas.subscription_audit
                        (subscription_id, client_id, action, plan_id,
                         old_status, new_status, changed_at)
                    VALUES (:sid, :cid, 'expired', :pid, 'active', 'expired', NOW())
                """),
                {"sid": r["id"], "cid": r["client_id"], "pid": r["plan_id"]},
            )
            db.execute(
                text("""
                    INSERT INTO saas.expiration_events
                        (subscription_id, client_id, expired_at, details)
                    VALUES (:sid, :cid, NOW(), :det)
                """),
                {
                    "sid": r["id"],
                    "cid": r["client_id"],
                    "det": f'{{"plan": "{r["plan_slug"]}", "period_end": "{r["current_period_end"]}"}}',
                },
            )
            db.execute(
                text("""
                    INSERT INTO saas.client_events
                        (client_id, event_type, actor, details, occurred_at)
                    VALUES (:cid, 'subscription_expired', 'system', :det, NOW())
                """),
                {
                    "cid": r["client_id"],
                    "det": f'{{"plan": "{r["plan_slug"]}", "reason": "period_elapsed"}}',
                },
            )

        db.commit()
        logger.info("expire_stale_subscriptions: %d assinatura(s) expirada(s)", expired_count)
        return {"status": "success", "expired": expired_count}
    except Exception as exc:
        db.rollback()
        logger.error("expire_stale_subscriptions failed: %s", exc, exc_info=True)
        try:
            import sentry_sdk
            sentry_sdk.capture_exception(exc)
        except ImportError:
            pass
        raise
    finally:
        db.close()


@celery_app.task(acks_late=True, max_retries=2, default_retry_delay=300)
def sync_lead_conversions():
    """Reconcilia leads × clientes: marca lead como `converted` quando existe
    cliente com o mesmo e-mail e uma assinatura ativa (funil → conversão real).

    Fecha o ciclo lead→CRM de forma idempotente e independente da origem
    (checkout MP, provision Free, concessão manual). Cobre o gap em que o
    webhook `/webhook/lead-conversion` não tinha chamador: sem isto o funil
    (e o relatório noturno de KPIs) mostrava sempre 0 conversões.

    Escopo: apenas leads não deletados, não convertidos e não-teste.
    """
    from .database import SaasSessionLocal

    db = SaasSessionLocal()
    try:
        rows = db.execute(text("""
            UPDATE saas.leads l
               SET status = 'converted',
                   converted_at = NOW(),
                   converted_to_user_id = c.id
              FROM saas.clients c
             WHERE lower(l.email) = lower(c.email)
               AND l.status NOT IN ('converted', 'lost', 'rejected', 'cancelled', 'closed')
               AND l.deleted_at IS NULL
               AND COALESCE(l.is_test, FALSE) = FALSE
               AND c.deleted_at IS NULL
               AND COALESCE(c.is_test, FALSE) = FALSE
               AND EXISTS (
                   SELECT 1 FROM saas.subscriptions s
                    WHERE s.client_id = c.id
                      AND s.status = 'active'
                      AND s.deleted_at IS NULL
                      AND s.current_period_end > NOW()
               )
            RETURNING l.id
        """)).fetchall()
        db.commit()
        logger.info("sync_lead_conversions: %d lead(s) convertido(s)", len(rows))
        return {"status": "success", "converted": len(rows)}
    except Exception as exc:
        db.rollback()
        logger.error("sync_lead_conversions failed: %s", exc, exc_info=True)
        try:
            import sentry_sdk
            sentry_sdk.capture_exception(exc)
        except ImportError:
            pass
        raise
    finally:
        db.close()


@celery_app.task(acks_late=True, max_retries=3, default_retry_delay=120)
def generate_embeddings_task(model_slug: str = "bge_m3",
                             tipo_items: list = ("insumo", "composicao")):
    """Gera/popula embeddings vetoriais (ADR-006 / STORY-SRC-004, Fase 4).

    Lê os itens ATIVOS de cada tipo, gera embeddings em lotes via
    `EmbeddingProvider` (bge-m3 no notebook, fallback nomic local) e faz
    upsert na tabela `vec_<dims>_<slug>`. Degrada graciosamente quando a
    extensão vector não existe ou o provider está fora (sem 5xx/crash).
    """
    from .config import settings
    from .database import SessionLocal
    from .vector_store import (
        VECTOR_MODELS,
        EmbeddingProvider,
        ensure_vector_table,
        get_embedding_table,
        refresh_row_count,
        upsert_batch,
    )

    if model_slug not in VECTOR_MODELS:
        logger.warning("generate_embeddings_task: modelo desconhecido %s", model_slug)
        return {"status": "skipped", "reason": f"unknown model {model_slug}"}

    meta = VECTOR_MODELS[model_slug]
    db = SessionLocal()
    try:
        tname = ensure_vector_table(db, meta["dims"], model_slug)
        if tname is None:
            logger.warning("generate_embeddings_task: pgvector indisponível; pulando")
            return {"status": "skipped", "reason": "pgvector unavailable"}
        provider = EmbeddingProvider()
        batch_size = settings.EMBEDDING_BATCH_SIZE
        totals = {}
        for tipo in tipo_items:
            rows = db.execute(
                text(
                    f"""
                    SELECT codigo, descricao
                    FROM {get_embedding_table(tipo)}
                    WHERE status = 'ATIVO' AND descricao IS NOT NULL
                    ORDER BY codigo
                    """
                )
            ).fetchall()
            embedded = 0
            n = len(rows)
            for i in range(0, n, batch_size):
                chunk = rows[i:i + batch_size]
                texts = [r.descricao for r in chunk]
                vectors = provider.embed(texts)
                if not vectors or len(vectors) != len(chunk):
                    logger.warning("embed lote devolveu %d vecs p/ %d itens (tipo=%s)",
                                   len(vectors or []), len(chunk), tipo)
                    continue
                embedded += upsert_batch(
                    db, tname, tipo,
                    [(int(r.codigo), vec) for r, vec in zip(chunk, vectors)],
                )
            totals[tipo] = embedded
            logger.info("generate_embeddings_task %s: %d/%d embedded", tipo, embedded, n)
        refresh_row_count(db, meta["dims"], model_slug)
        return {"status": "success", "model": model_slug, "embedded": totals}
    finally:
        db.close()
