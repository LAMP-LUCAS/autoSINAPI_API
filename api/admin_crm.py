# api/admin_crm.py
"""CMS/CRM management API for the SaaS layer.

Read/manage the SaaS entities that live in the gateway's authoritative database
(`api-gateway-db.saas`): clients, leads, subscriptions, api_keys, plans, usage
metrics and audit trails. All routes require the admin Bearer token.

Coupons/grants/expiring live in `admin_portal.py`; messaging in `admin_messages.py`.
"""

import json
import logging
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from .database import get_saas_db
from .admin_auth import verify_admin_token

logger = logging.getLogger("autosinapi.admin")
router = APIRouter(tags=["Admin"], dependencies=[Depends(verify_admin_token)])


def _row(r):
    out = {}
    for k, v in dict(r).items():
        if isinstance(v, datetime):
            out[k] = v.isoformat()
        elif hasattr(v, "hex"):  # UUID
            out[k] = str(v)
        else:
            out[k] = v
    return out


# ── Dashboard ─────────────────────────────────────────────────────────────────

@router.get("/api/v1/admin/dashboard", summary="KPIs do painel CMS/CRM")
def dashboard(db: Session = Depends(get_saas_db)):
    kpis = db.execute(text("""
        SELECT
          (SELECT COUNT(*) FROM saas.clients WHERE deleted_at IS NULL)                   AS clients_total,
          (SELECT COUNT(*) FROM saas.clients WHERE deleted_at IS NULL AND is_test)       AS clients_test,
          (SELECT COUNT(*) FROM saas.subscriptions WHERE status = 'active' AND deleted_at IS NULL) AS subs_active,
          (SELECT COUNT(*) FROM saas.subscriptions WHERE status = 'pending' AND deleted_at IS NULL) AS subs_pending,
          (SELECT COUNT(*) FROM saas.subscriptions WHERE status = 'expired' AND deleted_at IS NULL) AS subs_expired,
          (SELECT COUNT(*) FROM saas.subscriptions WHERE status = 'cancelled' AND deleted_at IS NULL) AS subs_cancelled,
          (SELECT COUNT(*) FROM saas.api_keys WHERE status = 'active' AND deleted_at IS NULL) AS keys_active,
          (SELECT COUNT(*) FROM saas.api_keys WHERE status = 'revoked' AND deleted_at IS NULL) AS keys_revoked,
          (SELECT COUNT(*) FROM saas.leads WHERE deleted_at IS NULL)                      AS leads_total,
          (SELECT COUNT(*) FROM saas.leads WHERE deleted_at IS NULL AND is_test)          AS leads_test,
          (SELECT COUNT(*) FROM saas.leads WHERE status = 'new' AND deleted_at IS NULL)   AS leads_new,
          (SELECT COUNT(*) FROM saas.coupons WHERE active = TRUE)                        AS coupons_active,
          (SELECT COUNT(*) FROM saas.usage_logs WHERE requested_at >= NOW() - INTERVAL '24 hours') AS usage_24h,
          (SELECT COUNT(*) FROM saas.usage_logs WHERE requested_at >= NOW() - INTERVAL '30 days') AS usage_30d
    """)).mappings().first()

    by_plan = db.execute(text("""
        SELECT p.slug, p.name, COUNT(s.id) AS total
        FROM saas.plans p
        LEFT JOIN saas.subscriptions s ON s.plan_id = p.id AND s.status = 'active'
        GROUP BY p.slug, p.name
        ORDER BY total DESC
    """)).mappings().all()

    return {
        "kpis": _row(kpis),
        "subscriptions_by_plan": [_row(r) for r in by_plan],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


# ── Clients (CRM) ─────────────────────────────────────────────────────────────

@router.get("/api/v1/admin/clients", summary="Listar clientes")
def list_clients(
    q: Optional[str] = Query(None, description="Busca por nome/email/empresa"),
    status: Optional[str] = Query(None),
    include_deleted: bool = Query(False, description="Incluir clientes soft-deleted"),
    is_test: Optional[bool] = Query(None, description="Filtrar por flag de teste"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_saas_db),
):
    where, params = ["1=1"], {"limit": limit, "offset": offset}
    if not include_deleted:
        where.append("c.deleted_at IS NULL")
    if is_test is not None:
        where.append("c.is_test = :is_test")
        params["is_test"] = is_test
    if q:
        where.append("(c.name ILIKE :q OR c.email ILIKE :q OR COALESCE(c.company,'') ILIKE :q)")
        params["q"] = f"%{q}%"
    if status:
        where.append("c.status = :status")
        params["status"] = status
    clause = " AND ".join(where)

    rows = db.execute(text(f"""
        SELECT c.id, c.name, c.email, c.company, c.status, c.is_test, c.deleted_at, c.mp_customer_id, c.created_at,
               (SELECT COUNT(*) FROM saas.subscriptions s WHERE s.client_id = c.id AND s.status='active') AS active_subs,
               (SELECT COUNT(*) FROM saas.api_keys k WHERE k.client_id = c.id AND k.status='active') AS active_keys,
               (SELECT MAX(ul.requested_at) FROM saas.usage_logs ul WHERE ul.client_id = c.id) AS last_usage,
               (SELECT COUNT(*) FROM saas.usage_logs ul WHERE ul.client_id = c.id) AS total_usage,
               (SELECT COALESCE(p.slug, '(none)') FROM saas.subscriptions s
                  JOIN saas.plans p ON p.id = s.plan_id
                  WHERE s.client_id = c.id AND s.status='active'
                  ORDER BY s.current_period_end DESC LIMIT 1) AS current_plan
        FROM saas.clients c
        WHERE {clause}
        ORDER BY c.created_at DESC
        LIMIT :limit OFFSET :offset
    """), params).mappings().all()

    total = db.execute(text(f"SELECT COUNT(*) FROM saas.clients c WHERE {clause}"),
                       {k: v for k, v in params.items() if k not in ("limit", "offset")}).scalar_one()
    return {"total": total, "items": [_row(r) for r in rows]}


@router.get("/api/v1/admin/clients/{client_id}", summary="Detalhe do cliente (CRM)")
def client_detail(client_id: str, db: Session = Depends(get_saas_db)):
    client = db.execute(text("SELECT * FROM saas.clients WHERE id = :id"),
                        {"id": client_id}).mappings().first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    subs = db.execute(text("""
        SELECT s.id, s.status, s.source, s.granted_by, s.current_period_start,
               s.current_period_end, s.created_at,
               p.slug AS plan_slug, p.name AS plan_name, p.price_cents, p.max_requests
        FROM saas.subscriptions s JOIN saas.plans p ON p.id = s.plan_id
        WHERE s.client_id = :id ORDER BY s.created_at DESC
    """), {"id": client_id}).mappings().all()

    keys = db.execute(text("""
        SELECT id, key_prefix, status, subscription_id, created_at, last_used_at, expires_at
        FROM saas.api_keys WHERE client_id = :id ORDER BY created_at DESC
    """), {"id": client_id}).mappings().all()

    events = db.execute(text("""
        SELECT id, event_type, actor, details, occurred_at
        FROM saas.client_events WHERE client_id = :id ORDER BY occurred_at DESC LIMIT 50
    """), {"id": client_id}).mappings().all()

    leads = db.execute(text("""
        SELECT id, name, email, source, status, lead_score, tags, created_at, converted_at
        FROM saas.leads WHERE email = :email ORDER BY created_at DESC
    """), {"email": client["email"]}).mappings().all()

    usage = db.execute(text("""
        SELECT COUNT(*) AS total,
               COUNT(*) FILTER (WHERE cache_status='HIT') AS hits,
               ROUND(AVG(latency_ms),2) AS avg_latency
        FROM saas.usage_logs WHERE client_id = :id
    """), {"id": client_id}).mappings().first()

    top_endpoints = db.execute(text("""
        SELECT endpoint, COUNT(*) AS total
        FROM saas.usage_logs WHERE client_id = :id
        GROUP BY endpoint ORDER BY total DESC LIMIT 10
    """), {"id": client_id}).mappings().all()

    return {
        "client": _row(client),
        "subscriptions": [_row(r) for r in subs],
        "api_keys": [_row(r) for r in keys],
        "events": [_row(r) for r in events],
        "leads": [_row(r) for r in leads],
        "usage": _row(usage) if usage else {},
        "top_endpoints": [_row(r) for r in top_endpoints],
    }


# ── Leads ─────────────────────────────────────────────────────────────────────

class LeadUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    source: Optional[str] = None
    status: Optional[str] = None
    plan_slug: Optional[str] = None
    lead_score: Optional[int] = None
    tags: Optional[list] = None
    phone: Optional[str] = None
    company: Optional[str] = None
    persona: Optional[str] = None
    metadata: Optional[dict] = None
    is_test: Optional[bool] = None


@router.get("/api/v1/admin/leads", summary="Listar leads")
def list_leads(
    q: Optional[str] = None,
    status: Optional[str] = None,
    source: Optional[str] = None,
    include_deleted: bool = Query(False, description="Incluir leads soft-deleted"),
    is_test: Optional[bool] = Query(None, description="Filtrar por flag de teste"),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_saas_db),
):
    where, params = ["1=1"], {"limit": limit, "offset": offset}
    if not include_deleted:
        where.append("l.deleted_at IS NULL")
    if is_test is not None:
        where.append("l.is_test = :is_test"); params["is_test"] = is_test
    if q:
        where.append("(l.name ILIKE :q OR l.email ILIKE :q OR COALESCE(l.company,'') ILIKE :q)")
        params["q"] = f"%{q}%"
    if status:
        where.append("l.status = :status"); params["status"] = status
    if source:
        where.append("l.source = :source"); params["source"] = source
    clause = " AND ".join(where)

    rows = db.execute(text(f"""
        SELECT l.*, (c.id IS NOT NULL) AS has_client
        FROM saas.leads l
        LEFT JOIN saas.clients c ON c.email = l.email AND c.deleted_at IS NULL
        WHERE {clause}
        ORDER BY l.created_at DESC LIMIT :limit OFFSET :offset
    """), params).mappings().all()
    total = db.execute(text(f"SELECT COUNT(*) FROM saas.leads l WHERE {clause}"),
                       {k: v for k, v in params.items() if k not in ("limit", "offset")}).scalar_one()

    by_source = db.execute(text("""
        SELECT source, COUNT(*) AS total FROM saas.leads
        WHERE deleted_at IS NULL GROUP BY source ORDER BY total DESC
    """)).mappings().all()

    return {"total": total, "items": [_row(r) for r in rows],
            "by_source": [_row(r) for r in by_source]}


@router.patch("/api/v1/admin/leads/{lead_id}", summary="Atualizar lead (funil)")
def update_lead(lead_id: str, req: LeadUpdate, db: Session = Depends(get_saas_db)):
    fields, params = [], {"id": lead_id}
    for col in ("name", "email", "source", "status", "plan_slug", "lead_score",
                "phone", "company", "persona", "is_test"):
        val = getattr(req, col)
        if val is not None:
            fields.append(f"{col} = :{col}")
            params[col] = val.strip().lower() if col == "email" else val
    if req.tags is not None:
        fields.append("tags = :tags"); params["tags"] = req.tags
    if req.metadata is not None:
        fields.append("metadata = COALESCE(metadata, '{}'::jsonb) || CAST(:metadata AS jsonb)")
        params["metadata"] = json.dumps(req.metadata)
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")
    fields.append("last_activity_at = NOW()")

    res = db.execute(text(f"UPDATE saas.leads SET {', '.join(fields)} WHERE id = :id RETURNING id"),
                     params).scalar_one_or_none()
    if not res:
        db.rollback()
        raise HTTPException(status_code=404, detail="Lead not found")
    db.commit()
    return {"status": "updated", "id": lead_id}


# ── Subscriptions ─────────────────────────────────────────────────────────────

@router.get("/api/v1/admin/subscriptions", summary="Listar assinaturas")
def list_subscriptions(
    q: Optional[str] = None,
    status: Optional[str] = None,
    source: Optional[str] = None,
    include_deleted: bool = Query(False, description="Incluir assinaturas soft-deleted"),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_saas_db),
):
    where, params = ["1=1"], {"limit": limit, "offset": offset}
    if not include_deleted:
        where.append("s.deleted_at IS NULL")
    if q:
        where.append("(c.name ILIKE :q OR c.email ILIKE :q)")
        params["q"] = f"%{q}%"
    if status:
        where.append("s.status = :status"); params["status"] = status
    if source:
        where.append("s.source = :source"); params["source"] = source
    clause = " AND ".join(where)

    rows = db.execute(text(f"""
        SELECT s.id, s.status, s.source, s.granted_by, s.current_period_start,
               s.current_period_end, s.created_at,
               p.slug AS plan_slug, p.name AS plan_name, p.price_cents,
               c.id AS client_id, c.name AS client_name, c.email AS client_email,
               (SELECT COUNT(*) FROM saas.api_keys k WHERE k.subscription_id = s.id AND k.status='active') AS active_keys,
               (SELECT COUNT(*) FROM saas.usage_logs ul
                  JOIN saas.api_keys k2 ON k2.id = ul.api_key_id
                  WHERE k2.subscription_id = s.id) AS total_usage
        FROM saas.subscriptions s
        JOIN saas.plans p ON p.id = s.plan_id
        LEFT JOIN saas.clients c ON c.id = s.client_id
        WHERE {clause}
        ORDER BY s.current_period_end DESC NULLS LAST
        LIMIT :limit OFFSET :offset
    """), params).mappings().all()
    total = db.execute(text(f"""
        SELECT COUNT(*) FROM saas.subscriptions s LEFT JOIN saas.clients c ON c.id = s.client_id
        WHERE {clause}
    """), {k: v for k, v in params.items() if k not in ("limit", "offset")}).scalar_one()
    return {"total": total, "items": [_row(r) for r in rows]}


@router.get("/api/v1/admin/subscriptions/{sub_id}", summary="Detalhe da assinatura")
def subscription_detail(sub_id: str, db: Session = Depends(get_saas_db)):
    sub = db.execute(text("""
        SELECT s.*, p.slug AS plan_slug, p.name AS plan_name, p.max_requests,
               p.duration_days, p.price_cents,
               c.name AS client_name, c.email AS client_email
        FROM saas.subscriptions s
        JOIN saas.plans p ON p.id = s.plan_id
        LEFT JOIN saas.clients c ON c.id = s.client_id
        WHERE s.id = :id
    """), {"id": sub_id}).mappings().first()
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")

    keys = db.execute(text("""
        SELECT id, key_prefix, status, created_at, last_used_at
        FROM saas.api_keys WHERE subscription_id = :id ORDER BY created_at DESC
    """), {"id": sub_id}).mappings().all()
    usage = db.execute(text("""
        SELECT COUNT(*) AS total, COUNT(*) FILTER (WHERE cache_status='HIT') AS hits,
               ROUND(AVG(latency_ms),2) AS avg_latency, MAX(requested_at) AS last_request
        FROM saas.usage_logs ul JOIN saas.api_keys k ON k.id = ul.api_key_id
        WHERE k.subscription_id = :id
    """), {"id": sub_id}).mappings().first()
    return {"subscription": _row(sub), "api_keys": [_row(r) for r in keys],
            "usage": _row(usage) if usage else {}}


# ── API keys ──────────────────────────────────────────────────────────────────

@router.get("/api/v1/admin/api-keys", summary="Listar chaves de API")
def list_api_keys(
    status: Optional[str] = None,
    q: Optional[str] = None,
    include_deleted: bool = Query(False, description="Incluir chaves soft-deleted"),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_saas_db),
):
    where, params = ["1=1"], {"limit": limit, "offset": offset}
    if not include_deleted:
        where.append("k.deleted_at IS NULL")
    if status:
        where.append("k.status = :status"); params["status"] = status
    if q:
        where.append("(k.key_prefix ILIKE :q OR c.email ILIKE :q OR c.name ILIKE :q)")
        params["q"] = f"%{q}%"
    clause = " AND ".join(where)
    rows = db.execute(text(f"""
        SELECT k.id, k.key_prefix, k.status, k.created_at, k.last_used_at,
               s.id AS subscription_id, s.status AS sub_status, s.source,
               p.slug AS plan_slug,
               c.id AS client_id, c.name AS client_name, c.email AS client_email
        FROM saas.api_keys k
        JOIN saas.subscriptions s ON s.id = k.subscription_id
        JOIN saas.plans p ON p.id = s.plan_id
        LEFT JOIN saas.clients c ON c.id = k.client_id
        WHERE {clause}
        ORDER BY k.created_at DESC LIMIT :limit OFFSET :offset
    """), params).mappings().all()
    return {"items": [_row(r) for r in rows]}


# ── Plans ─────────────────────────────────────────────────────────────────────

@router.get("/api/v1/admin/plans", summary="Listar planos (SSOT)")
def list_plans(db: Session = Depends(get_saas_db)):
    rows = db.execute(text("""
        SELECT id, slug, name, price_cents, currency, duration_days, max_requests,
               rate_limit_per_minute, monthly_quota, active, features,
               (SELECT COUNT(*) FROM saas.subscriptions s WHERE s.plan_id = p.id AND s.status='active') AS active_subs
        FROM saas.plans p ORDER BY price_cents
    """)).mappings().all()
    return {"items": [_row(r) for r in rows]}


# ── Produtos (catálogo + entitlements) — ADR-016 ─────────────────────────────

@router.get("/api/v1/admin/products", summary="Catálogo de produtos e entitlements")
def list_products(db: Session = Depends(get_saas_db)):
    rows = db.execute(text("""
        SELECT pr.id, pr.slug, pr.name, pr.kind, pr.domain, pr.canonical_prefix,
               pr.status, pr.metadata,
               (SELECT COUNT(*) FROM saas.plan_products pp WHERE pp.product_id = pr.id AND pp.active) AS planos,
               (SELECT COUNT(*) FROM saas.subscriptions s
                  JOIN saas.plan_products pp ON pp.plan_id = s.plan_id
                 WHERE pp.product_id = pr.id AND s.status = 'active') AS assinaturas_ativas
        FROM saas.products pr
        ORDER BY pr.kind, pr.slug
    """)).mappings().all()

    entitlements = db.execute(text("""
        SELECT pr.slug AS product_slug, p.slug AS plan_slug, pp.active, pp.features
        FROM saas.plan_products pp
        JOIN saas.products pr ON pr.id = pp.product_id
        JOIN saas.plans p ON p.id = pp.plan_id
        ORDER BY pr.slug, p.slug
    """)).mappings().all()

    return {"items": [_row(r) for r in rows],
            "entitlements": [_row(r) for r in entitlements]}


@router.get("/api/v1/admin/products/usage", summary="Uso por produto (metrificação)")
def products_usage(days: int = Query(30, ge=1, le=365), db: Session = Depends(get_saas_db)):
    rows = db.execute(text("""
        SELECT CASE
            WHEN endpoint LIKE '/v1/cub%' OR endpoint LIKE '/cub/%'
              OR endpoint LIKE '/v1/padroes%' OR endpoint LIKE '/v1/sinduscons%'
              OR endpoint LIKE '/api/v1/cub%' THEN 'cub'
            WHEN endpoint LIKE '/api/v1/incc%' OR endpoint LIKE '/incc/%' THEN 'incc'
            WHEN endpoint LIKE '/api/v1/sinapi%' OR endpoint LIKE '/api/v1/public%' THEN 'sinapi'
            ELSE '(plataforma)'
        END AS product,
        COUNT(*) AS requests,
        COUNT(DISTINCT client_id) AS clientes
        FROM saas.usage_logs
        WHERE requested_at >= NOW() - make_interval(days => :days)
        GROUP BY 1 ORDER BY requests DESC
    """), {"days": days}).mappings().all()
    return {"items": [_row(r) for r in rows]}


# ── Usage / metrics ───────────────────────────────────────────────────────────

@router.get("/api/v1/admin/usage/summary", summary="Resumo de uso da API")
def usage_summary(days: int = Query(30, ge=1, le=365), db: Session = Depends(get_saas_db)):
    params = {"days": days}
    totals = db.execute(text("""
        SELECT COUNT(*) AS requests,
               COUNT(*) FILTER (WHERE cache_status='HIT') AS cache_hits,
               COUNT(DISTINCT client_id) AS clients,
               COUNT(DISTINCT api_key_id) AS keys_used,
               ROUND(AVG(latency_ms),2) AS avg_latency,
               ROUND(100.0 * COUNT(*) FILTER (WHERE cache_status='HIT') / GREATEST(COUNT(*),1), 1) AS cache_hit_pct
        FROM saas.usage_logs WHERE requested_at >= NOW() - make_interval(days => :days)
    """), params).mappings().first()

    by_plan = db.execute(text("""
        SELECT COALESCE(plan_slug,'(anon)') AS plan_slug, COUNT(*) AS requests
        FROM saas.usage_logs WHERE requested_at >= NOW() - make_interval(days => :days)
        GROUP BY 1 ORDER BY requests DESC
    """), params).mappings().all()

    by_status = db.execute(text("""
        SELECT status_code, COUNT(*) AS total
        FROM saas.usage_logs WHERE requested_at >= NOW() - make_interval(days => :days)
        GROUP BY 1 ORDER BY total DESC
    """), params).mappings().all()

    top_endpoints = db.execute(text("""
        SELECT endpoint, COUNT(*) AS requests, ROUND(AVG(latency_ms),2) AS avg_latency
        FROM saas.usage_logs WHERE requested_at >= NOW() - make_interval(days => :days)
        GROUP BY endpoint ORDER BY requests DESC LIMIT 20
    """), params).mappings().all()

    by_day = db.execute(text("""
        SELECT date_trunc('day', requested_at) AS day, COUNT(*) AS requests
        FROM saas.usage_logs WHERE requested_at >= NOW() - make_interval(days => :days)
        GROUP BY 1 ORDER BY 1
    """), params).mappings().all()

    return {
        "totals": _row(totals),
        "by_plan": [_row(r) for r in by_plan],
        "by_status": [_row(r) for r in by_status],
        "top_endpoints": [_row(r) for r in top_endpoints],
        "by_day": [_row(r) for r in by_day],
    }


@router.get("/api/v1/admin/usage/hourly", summary="Consumo agregado por hora")
def usage_hourly(hours: int = Query(72, ge=1, le=720), db: Session = Depends(get_saas_db)):
    rows = db.execute(text("""
        SELECT hour_start, endpoint, tier, plan_slug, total_requests,
               cache_hits, cache_misses, avg_latency_ms, p95_latency_ms, max_latency_ms, estimated_cost
        FROM saas.consumption_hourly
        WHERE hour_start >= NOW() - make_interval(hours => :hours)
        ORDER BY hour_start DESC LIMIT 500
    """), {"hours": hours}).mappings().all()
    return {"items": [_row(r) for r in rows]}


# ── Audit ─────────────────────────────────────────────────────────────────────

@router.get("/api/v1/admin/audit/subscriptions", summary="Auditoria de assinaturas")
def audit_subscriptions(limit: int = Query(100, ge=1, le=1000), db: Session = Depends(get_saas_db)):
    rows = db.execute(text("""
        SELECT a.id, a.subscription_id, a.client_id, a.action, a.old_status, a.new_status,
               a.changed_at, p.slug AS plan_slug, c.name AS client_name, c.email AS client_email
        FROM saas.subscription_audit a
        LEFT JOIN saas.plans p ON p.id = a.plan_id
        LEFT JOIN saas.clients c ON c.id = a.client_id
        ORDER BY a.changed_at DESC LIMIT :limit
    """), {"limit": limit}).mappings().all()
    return {"items": [_row(r) for r in rows]}


@router.get("/api/v1/admin/audit/events", summary="Eventos de cliente")
def audit_events(limit: int = Query(100, ge=1, le=1000), db: Session = Depends(get_saas_db)):
    rows = db.execute(text("""
        SELECT e.id, e.client_id, e.event_type, e.actor, e.details, e.occurred_at,
               c.name AS client_name, c.email AS client_email
        FROM saas.client_events e
        LEFT JOIN saas.clients c ON c.id = e.client_id
        ORDER BY e.occurred_at DESC LIMIT :limit
    """), {"limit": limit}).mappings().all()
    return {"items": [_row(r) for r in rows]}


@router.get("/api/v1/admin/audit/webhooks", summary="Eventos de webhook")
def audit_webhooks(limit: int = Query(100, ge=1, le=1000), db: Session = Depends(get_saas_db)):
    rows = db.execute(text("""
        SELECT id, external_id, topic, source, status, error_message,
               processed_at, created_at
        FROM saas.webhook_events ORDER BY created_at DESC LIMIT :limit
    """), {"limit": limit}).mappings().all()
    return {"items": [_row(r) for r in rows]}


# ══════════════════════════════════════════════════════════════════════════════
# CRUD total (CMS/CRM) — criar / editar / soft-delete / restaurar + assessoria
# ══════════════════════════════════════════════════════════════════════════════

CLIENT_STATUSES = {"active", "suspended", "cancelled"}
SUB_STATUSES = {"active", "pending", "expired", "cancelled", "suspended"}
KEY_STATUSES = {"active", "revoked"}


def _fail(msg: str, code: int = 400):
    raise HTTPException(status_code=code, detail=msg)


def _audit_sub(db, sub_id, client_id, action, plan_id, old_status, new_status):
    db.execute(text("""
        INSERT INTO saas.subscription_audit
            (subscription_id, client_id, action, plan_id, old_status, new_status, changed_at)
        VALUES (:sid, :cid, :action, :pid, :old, :new, NOW())
    """), {"sid": sub_id, "cid": client_id, "action": action,
           "pid": plan_id, "old": old_status, "new": new_status})


def _client_event(db, client_id, event_type, details=None, actor="admin"):
    db.execute(text("""
        INSERT INTO saas.client_events (client_id, event_type, actor, details, occurred_at)
        VALUES (:cid, :et, :actor, CAST(:details AS jsonb), NOW())
    """), {"cid": client_id, "et": event_type, "actor": actor,
           "details": json.dumps(details or {})})


# ── Clients ───────────────────────────────────────────────────────────────────

class ClientCreate(BaseModel):
    name: str = Field(..., min_length=1)
    email: str = Field(..., min_length=3)
    company: Optional[str] = None
    status: str = "active"
    metadata: Optional[dict] = None
    is_test: bool = False


class ClientUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    company: Optional[str] = None
    status: Optional[str] = None
    metadata: Optional[dict] = None
    is_test: Optional[bool] = None


@router.post("/api/v1/admin/clients", status_code=201, summary="Criar cliente")
def create_client(req: ClientCreate, db: Session = Depends(get_saas_db)):
    if req.status not in CLIENT_STATUSES:
        _fail(f"status inválido (use {sorted(CLIENT_STATUSES)})")
    email = req.email.strip().lower()
    dup = db.execute(text("SELECT id FROM saas.clients WHERE lower(email) = :e"),
                     {"e": email}).scalar_one_or_none()
    if dup:
        db.rollback()
        _fail("Já existe cliente com esse e-mail", 409)
    cid = db.execute(text("""
        INSERT INTO saas.clients (name, email, company, status, metadata, is_test)
        VALUES (:name, :email, :company, :status, CAST(:metadata AS jsonb), :is_test)
        RETURNING id
    """), {"name": req.name.strip(), "email": email, "company": req.company,
           "status": req.status, "metadata": json.dumps(req.metadata or {}),
           "is_test": req.is_test}).scalar_one()
    _client_event(db, cid, "client_created", {"source": "admin"})
    db.commit()
    return {"status": "created", "id": str(cid)}


@router.patch("/api/v1/admin/clients/{client_id}", summary="Atualizar cliente")
def update_client(client_id: str, req: ClientUpdate, db: Session = Depends(get_saas_db)):
    fields, params = [], {"id": client_id}
    for col in ("name", "email", "company", "status", "is_test"):
        val = getattr(req, col)
        if val is not None:
            if col == "status" and val not in CLIENT_STATUSES:
                _fail(f"status inválido (use {sorted(CLIENT_STATUSES)})")
            fields.append(f"{col} = :{col}")
            params[col] = val.strip().lower() if col == "email" else val
    if req.metadata is not None:
        fields.append("metadata = COALESCE(metadata, '{}'::jsonb) || CAST(:metadata AS jsonb)")
        params["metadata"] = json.dumps(req.metadata)
    if not fields:
        _fail("Nada para atualizar")
    fields.append("updated_at = NOW()")
    res = db.execute(text(f"UPDATE saas.clients SET {', '.join(fields)} WHERE id = :id RETURNING id"),
                     params).scalar_one_or_none()
    if not res:
        db.rollback()
        _fail("Cliente não encontrado", 404)
    db.commit()
    return {"status": "updated", "id": client_id}


@router.delete("/api/v1/admin/clients/{client_id}", summary="Soft-delete cliente (reversível)")
def delete_client(
    client_id: str,
    revoke_keys: bool = Query(True),
    cancel_subs: bool = Query(True),
    db: Session = Depends(get_saas_db),
):
    res = db.execute(text("""
        UPDATE saas.clients SET deleted_at = NOW(), status = 'cancelled', updated_at = NOW()
        WHERE id = :id AND deleted_at IS NULL RETURNING id
    """), {"id": client_id}).scalar_one_or_none()
    if not res:
        db.rollback()
        _fail("Cliente não encontrado ou já excluído", 404)
    if cancel_subs:
        db.execute(text("""
            UPDATE saas.subscriptions SET status = 'cancelled',
                   deleted_at = COALESCE(deleted_at, NOW()), updated_at = NOW()
            WHERE client_id = :id AND status IN ('active', 'pending')
        """), {"id": client_id})
    if revoke_keys:
        db.execute(text("""
            UPDATE saas.api_keys SET status = 'revoked'
            WHERE client_id = :id AND status = 'active'
        """), {"id": client_id})
    _client_event(db, client_id, "client_soft_deleted",
                  {"revoke_keys": revoke_keys, "cancel_subs": cancel_subs})
    db.commit()
    return {"status": "deleted", "id": client_id}


@router.post("/api/v1/admin/clients/{client_id}/restore", summary="Restaurar cliente")
def restore_client(client_id: str, db: Session = Depends(get_saas_db)):
    res = db.execute(text("""
        UPDATE saas.clients SET deleted_at = NULL, status = 'active', updated_at = NOW()
        WHERE id = :id AND deleted_at IS NOT NULL RETURNING id
    """), {"id": client_id}).scalar_one_or_none()
    if not res:
        db.rollback()
        _fail("Cliente não encontrado ou não está excluído", 404)
    _client_event(db, client_id, "client_restored")
    db.commit()
    return {"status": "restored", "id": client_id}


class NoteCreate(BaseModel):
    text: str = Field(..., min_length=1)
    actor: str = "admin"
    kind: str = "admin_note"


@router.post("/api/v1/admin/clients/{client_id}/notes", status_code=201,
             summary="Adicionar anotação/atendimento ao cliente")
def add_client_note(client_id: str, req: NoteCreate, db: Session = Depends(get_saas_db)):
    exists = db.execute(text("SELECT id FROM saas.clients WHERE id = :id"),
                        {"id": client_id}).scalar_one_or_none()
    if not exists:
        _fail("Cliente não encontrado", 404)
    _client_event(db, client_id, req.kind or "admin_note", {"text": req.text},
                  actor=req.actor or "admin")
    db.commit()
    return {"status": "created"}


# ── Leads ─────────────────────────────────────────────────────────────────────

@router.get("/api/v1/admin/leads/{lead_id}", summary="Detalhe do lead")
def lead_detail(lead_id: str, db: Session = Depends(get_saas_db)):
    row = db.execute(text("SELECT * FROM saas.leads WHERE id = :id"),
                     {"id": lead_id}).mappings().first()
    if not row:
        _fail("Lead não encontrado", 404)
    return {"lead": _row(row)}


class LeadCreate(BaseModel):
    email: str = Field(..., min_length=3)
    name: str = ""
    source: str = "manual"
    status: str = "new"
    plan_slug: Optional[str] = None
    lead_score: int = 0
    phone: Optional[str] = None
    company: Optional[str] = None
    persona: Optional[str] = None
    tags: Optional[list] = None
    metadata: Optional[dict] = None
    is_test: bool = False


@router.post("/api/v1/admin/leads", status_code=201, summary="Criar lead")
def create_lead(req: LeadCreate, db: Session = Depends(get_saas_db)):
    email = req.email.strip().lower()
    dup = db.execute(text("""
        SELECT id FROM saas.leads WHERE lower(email) = :e AND deleted_at IS NULL LIMIT 1
    """), {"e": email}).scalar_one_or_none()
    if dup:
        db.rollback()
        _fail(f"Já existe lead ativo com esse e-mail (id={dup})", 409)
    lid = db.execute(text("""
        INSERT INTO saas.leads
            (email, name, source, status, plan_slug, lead_score, phone, company,
             persona, tags, metadata, is_test, last_activity_at)
        VALUES
            (:email, :name, :source, :status, :plan_slug, :lead_score, :phone, :company,
             :persona, :tags, CAST(:metadata AS jsonb), :is_test, NOW())
        RETURNING id
    """), {"email": email, "name": req.name or "", "source": req.source or "manual",
           "status": req.status or "new", "plan_slug": req.plan_slug,
           "lead_score": req.lead_score, "phone": req.phone, "company": req.company,
           "persona": req.persona, "tags": req.tags or [],
           "metadata": json.dumps(req.metadata or {}), "is_test": req.is_test}).scalar_one()
    db.commit()
    return {"status": "created", "id": str(lid)}


@router.delete("/api/v1/admin/leads/{lead_id}", summary="Soft-delete lead (reversível)")
def delete_lead(lead_id: str, db: Session = Depends(get_saas_db)):
    res = db.execute(text("""
        UPDATE saas.leads SET deleted_at = NOW(), last_activity_at = NOW()
        WHERE id = :id AND deleted_at IS NULL RETURNING id
    """), {"id": lead_id}).scalar_one_or_none()
    if not res:
        db.rollback()
        _fail("Lead não encontrado ou já excluído", 404)
    db.commit()
    return {"status": "deleted", "id": lead_id}


@router.post("/api/v1/admin/leads/{lead_id}/restore", summary="Restaurar lead")
def restore_lead(lead_id: str, db: Session = Depends(get_saas_db)):
    res = db.execute(text("""
        UPDATE saas.leads SET deleted_at = NULL, last_activity_at = NOW()
        WHERE id = :id AND deleted_at IS NOT NULL RETURNING id
    """), {"id": lead_id}).scalar_one_or_none()
    if not res:
        db.rollback()
        _fail("Lead não encontrado ou não está excluído", 404)
    db.commit()
    return {"status": "restored", "id": lead_id}


@router.post("/api/v1/admin/leads/{lead_id}/notes", status_code=201,
             summary="Anotar/registrar contato no lead")
def add_lead_note(lead_id: str, req: NoteCreate, db: Session = Depends(get_saas_db)):
    row = db.execute(text("SELECT id, COALESCE(metadata,'{}'::jsonb) AS metadata "
                          "FROM saas.leads WHERE id = :id"), {"id": lead_id}).mappings().first()
    if not row:
        _fail("Lead não encontrado", 404)
    meta = dict(row["metadata"] or {})
    notes = list(meta.get("notes") or [])
    notes.append({"at": datetime.now(timezone.utc).isoformat(),
                  "actor": req.actor or "admin", "kind": req.kind or "admin_note",
                  "text": req.text})
    meta["notes"] = notes
    db.execute(text("UPDATE saas.leads SET metadata = CAST(:m AS jsonb), "
                    "last_activity_at = NOW() WHERE id = :id"),
               {"m": json.dumps(meta), "id": lead_id})
    db.commit()
    return {"status": "created", "notes": len(notes)}


@router.post("/api/v1/admin/leads/{lead_id}/convert", summary="Converter lead em cliente")
def convert_lead(
    lead_id: str,
    name: Optional[str] = None,
    company: Optional[str] = None,
    db: Session = Depends(get_saas_db),
):
    lead = db.execute(text("SELECT * FROM saas.leads WHERE id = :id"),
                      {"id": lead_id}).mappings().first()
    if not lead:
        _fail("Lead não encontrado", 404)
    email = (lead["email"] or "").strip().lower()
    client = db.execute(text("SELECT id FROM saas.clients WHERE lower(email) = :e"),
                        {"e": email}).mappings().first()
    if client:
        client_id = client["id"]
    else:
        client_id = db.execute(text("""
            INSERT INTO saas.clients (name, email, company, status, metadata)
            VALUES (:name, :email, :company, 'active', CAST(:m AS jsonb)) RETURNING id
        """), {"name": name or lead["name"] or email, "email": email,
               "company": company or lead["company"],
               "m": json.dumps({"converted_from_lead": str(lead_id)})}).scalar_one()
        _client_event(db, client_id, "client_created", {"from_lead": str(lead_id)})
    db.execute(text("""
        UPDATE saas.leads SET status = 'converted', converted_at = NOW(),
               converted_to_user_id = :cid, last_activity_at = NOW()
        WHERE id = :id
    """), {"cid": client_id, "id": lead_id})
    db.commit()
    return {"status": "converted", "lead_id": lead_id, "client_id": str(client_id)}


# ── Subscriptions ─────────────────────────────────────────────────────────────

class SubscriptionUpdate(BaseModel):
    status: Optional[str] = None
    plan_slug: Optional[str] = None
    source: Optional[str] = None
    granted_by: Optional[str] = None
    current_period_end: Optional[str] = None
    extend_days: Optional[int] = None


@router.patch("/api/v1/admin/subscriptions/{sub_id}", summary="Atualizar assinatura")
def update_subscription(sub_id: str, req: SubscriptionUpdate, db: Session = Depends(get_saas_db)):
    sub = db.execute(text("SELECT * FROM saas.subscriptions WHERE id = :id"),
                     {"id": sub_id}).mappings().first()
    if not sub:
        _fail("Assinatura não encontrada", 404)
    fields, params = [], {"id": sub_id}
    if req.status is not None:
        if req.status not in SUB_STATUSES:
            _fail(f"status inválido (use {sorted(SUB_STATUSES)})")
        fields.append("status = :status"); params["status"] = req.status
    if req.plan_slug is not None:
        plan = db.execute(text("SELECT id FROM saas.plans WHERE slug = :s"),
                          {"s": req.plan_slug}).scalar_one_or_none()
        if not plan:
            _fail("Plano não encontrado", 404)
        fields.append("plan_id = :plan_id"); params["plan_id"] = plan
    if req.source is not None:
        fields.append("source = :source"); params["source"] = req.source
    if req.granted_by is not None:
        fields.append("granted_by = :granted_by"); params["granted_by"] = req.granted_by
    if req.current_period_end is not None:
        try:
            end = datetime.fromisoformat(req.current_period_end.replace("Z", "+00:00"))
        except ValueError:
            _fail("current_period_end inválido (use ISO-8601)")
        fields.append("current_period_end = :end"); params["end"] = end
    if req.extend_days:
        fields.append("current_period_end = GREATEST(current_period_end, NOW()) "
                      "+ make_interval(days => :extend)")
        params["extend"] = req.extend_days
    if not fields:
        _fail("Nada para atualizar")
    fields.append("updated_at = NOW()")
    db.execute(text(f"UPDATE saas.subscriptions SET {', '.join(fields)} WHERE id = :id"), params)
    _audit_sub(db, sub_id, sub["client_id"], "admin_update", sub["plan_id"],
               sub["status"], req.status or sub["status"])
    db.commit()
    return {"status": "updated", "id": sub_id}


@router.delete("/api/v1/admin/subscriptions/{sub_id}",
               summary="Soft-delete assinatura + revogar chaves")
def delete_subscription(sub_id: str, revoke_keys: bool = Query(True),
                        db: Session = Depends(get_saas_db)):
    sub = db.execute(text("SELECT id, client_id, plan_id, status FROM saas.subscriptions "
                          "WHERE id = :id AND deleted_at IS NULL"),
                     {"id": sub_id}).mappings().first()
    if not sub:
        _fail("Assinatura não encontrada ou já excluída", 404)
    db.execute(text("""
        UPDATE saas.subscriptions SET deleted_at = NOW(), status = 'cancelled', updated_at = NOW()
        WHERE id = :id
    """), {"id": sub_id})
    if revoke_keys:
        db.execute(text("""
            UPDATE saas.api_keys SET status = 'revoked'
            WHERE subscription_id = :id AND status = 'active'
        """), {"id": sub_id})
    _audit_sub(db, sub_id, sub["client_id"], "admin_soft_deleted",
               sub["plan_id"], sub["status"], "cancelled")
    db.commit()
    return {"status": "deleted", "id": sub_id}


@router.post("/api/v1/admin/subscriptions/{sub_id}/restore", summary="Restaurar assinatura")
def restore_subscription(sub_id: str, db: Session = Depends(get_saas_db)):
    res = db.execute(text("""
        UPDATE saas.subscriptions SET deleted_at = NULL, status = 'active', updated_at = NOW()
        WHERE id = :id AND deleted_at IS NOT NULL RETURNING id
    """), {"id": sub_id}).scalar_one_or_none()
    if not res:
        db.rollback()
        _fail("Assinatura não encontrada ou não está excluída", 404)
    db.commit()
    return {"status": "restored", "id": sub_id}


# ── API keys ──────────────────────────────────────────────────────────────────

class ApiKeyCreate(BaseModel):
    subscription_id: str
    status: str = "active"


class ApiKeyUpdate(BaseModel):
    status: Optional[str] = None


@router.post("/api/v1/admin/api-keys", status_code=201, summary="Emitir nova chave de API")
def create_api_key(req: ApiKeyCreate, response: Response, db: Session = Depends(get_saas_db)):
    if req.status not in KEY_STATUSES:
        _fail(f"status inválido (use {sorted(KEY_STATUSES)})")
    sub = db.execute(text("SELECT id, client_id FROM saas.subscriptions WHERE id = :id"),
                     {"id": req.subscription_id}).mappings().first()
    if not sub:
        _fail("Assinatura não encontrada", 404)
    key_value = f"autosinapi_{secrets.token_hex(16)}"
    key_prefix = key_value[11:19]
    kid = db.execute(text("""
        INSERT INTO saas.api_keys (client_id, subscription_id, key_prefix, key_hash, status)
        VALUES (:cid, :sid, :prefix, crypt(:kv, gen_salt('bf')), :status)
        RETURNING id
    """), {"cid": sub["client_id"], "sid": sub["id"], "kv": key_value,
           "prefix": key_prefix, "status": req.status}).scalar_one()
    _client_event(db, sub["client_id"], "api_key_created",
                  {"subscription_id": str(sub["id"])})
    db.commit()
    response.headers["Cache-Control"] = "no-store"
    return {"status": "created", "id": str(kid), "api_key": key_value, "key_prefix": key_prefix}


@router.patch("/api/v1/admin/api-keys/{key_id}", summary="Ativar/revogar chave de API")
def update_api_key(key_id: str, req: ApiKeyUpdate, db: Session = Depends(get_saas_db)):
    if req.status not in KEY_STATUSES:
        _fail(f"status inválido (use {sorted(KEY_STATUSES)})")
    res = db.execute(text("UPDATE saas.api_keys SET status = :s WHERE id = :id RETURNING id"),
                     {"s": req.status, "id": key_id}).scalar_one_or_none()
    if not res:
        db.rollback()
        _fail("Chave não encontrada", 404)
    db.commit()
    return {"status": "updated", "id": key_id}


@router.delete("/api/v1/admin/api-keys/{key_id}", summary="Soft-delete + revogar chave")
def delete_api_key(key_id: str, db: Session = Depends(get_saas_db)):
    res = db.execute(text("""
        UPDATE saas.api_keys SET status = 'revoked', deleted_at = NOW()
        WHERE id = :id AND deleted_at IS NULL RETURNING id
    """), {"id": key_id}).scalar_one_or_none()
    if not res:
        db.rollback()
        _fail("Chave não encontrada ou já excluída", 404)
    db.commit()
    return {"status": "deleted", "id": key_id}


# ── Plans (SSOT) ──────────────────────────────────────────────────────────────

class PlanUpdate(BaseModel):
    name: Optional[str] = None
    price_cents: Optional[int] = None
    duration_days: Optional[int] = None
    max_requests: Optional[int] = None
    rate_limit_per_minute: Optional[int] = None
    monthly_quota: Optional[int] = None
    active: Optional[bool] = None
    features: Optional[dict] = None


@router.patch("/api/v1/admin/plans/{plan_id}", summary="Atualizar plano (SSOT)")
def update_plan(plan_id: str, req: PlanUpdate, db: Session = Depends(get_saas_db)):
    fields, params = [], {"id": plan_id}
    for col in ("name", "price_cents", "duration_days", "max_requests",
                "rate_limit_per_minute", "monthly_quota", "active"):
        val = getattr(req, col)
        if val is not None:
            fields.append(f"{col} = :{col}"); params[col] = val
    if req.features is not None:
        fields.append("features = CAST(:features AS jsonb)")
        params["features"] = json.dumps(req.features)
    if not fields:
        _fail("Nada para atualizar")
    fields.append("updated_at = NOW()")
    res = db.execute(text(f"UPDATE saas.plans SET {', '.join(fields)} WHERE id = :id RETURNING id"),
                     params).scalar_one_or_none()
    if not res:
        db.rollback()
        _fail("Plano não encontrado", 404)
    db.commit()
    return {"status": "updated", "id": plan_id}
