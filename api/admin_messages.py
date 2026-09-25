# api/admin_messages.py
"""MessageDispatcher (ODC) management API — the gateway's communication hub.

Exposes the MD topics/destinations/DLQ/metrics plus a send endpoint so the
CMS/CRM panel can manage and observe all gateway communications (email,
WhatsApp, webhook) in one place. Requires admin Bearer token.
"""

import logging
import os
import time
import hmac
import hashlib
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from .admin_auth import verify_admin_token
from .database import get_saas_db
from .message_dispatcher import MessageDispatcher, MessageDispatcherError, get_client

logger = logging.getLogger("autosinapi.admin")
router = APIRouter(tags=["Admin"], dependencies=[Depends(verify_admin_token)])


def _client():
    return get_client()


def _call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except MessageDispatcherError as e:
        raise HTTPException(status_code=502, detail=str(e))


# ── Schemas ───────────────────────────────────────────────────────────────────

class TopicCreate(BaseModel):
    name: str = Field(..., min_length=2)
    description: Optional[str] = ""
    destinations: Optional[list] = None


class DestinationAdd(BaseModel):
    channel: str = Field(..., description="email | whatsapp | webhook")
    target: str
    channel_account: Optional[str] = None


class ContactCreate(BaseModel):
    channel: str
    identifier: str
    name: Optional[str] = None
    metadata: Optional[dict] = None


class MessageSend(BaseModel):
    topic: str
    message: str
    title: Optional[str] = None
    sender: Optional[str] = None
    metadata: Optional[dict] = None


# ── Health / metrics ──────────────────────────────────────────────────────────

@router.get("/api/v1/admin/messages/health", summary="Saúde do MessageDispatcher")
def md_health():
    c = _client()
    return {"enabled": c.enabled, "base_url": c.base_url, "healthy": c.health()}


@router.get("/api/v1/admin/messages/metrics", summary="Métricas do MD")
def md_metrics():
    return _call(_client().metrics)


@router.get("/api/v1/admin/messages/usage", summary="Uso/quota do MD")
def md_usage():
    return _call(_client().usage)


# ── Topics ────────────────────────────────────────────────────────────────────

@router.get("/api/v1/admin/messages/topics", summary="Listar tópicos")
def md_list_topics():
    return {"items": _call(_client().list_topics)}


@router.post("/api/v1/admin/messages/topics", summary="Criar tópico")
def md_create_topic(req: TopicCreate):
    return _call(_client().create_topic, req.name, req.description or "", req.destinations)


@router.delete("/api/v1/admin/messages/topics/{topic_id}", summary="Remover tópico")
def md_delete_topic(topic_id: str):
    return _call(_client().delete_topic, topic_id)


@router.post("/api/v1/admin/messages/topics/{topic_id}/destinations", summary="Adicionar destino")
def md_add_destination(topic_id: str, req: DestinationAdd):
    return _call(_client().add_destination, topic_id, req.channel, req.target, req.channel_account)


@router.delete("/api/v1/admin/messages/topics/{topic_id}/destinations", summary="Remover destino")
def md_remove_destination(topic_id: str, channel: str = Query(...), target: str = Query(...)):
    return _call(_client().remove_destination, topic_id, channel, target)


# ── Send ──────────────────────────────────────────────────────────────────────

@router.post("/api/v1/admin/messages/send", summary="Enviar mensagem via MD")
def md_send(req: MessageSend):
    return _call(_client().send, req.topic, req.message, req.title, req.sender, req.metadata)


# ── Contacts ──────────────────────────────────────────────────────────────────

@router.get("/api/v1/admin/messages/contacts", summary="Listar contatos do MD")
def md_list_contacts():
    return {"items": _call(_client().list_contacts)}


# ── Orders (envios reais por destinatário) ────────────────────────────────────

@router.get("/api/v1/admin/messages/orders", summary="Envios recentes (destinatários reais)")
def md_orders(limit: int = Query(100, ge=1, le=500)):
    """OS recentes do MD: destinatários REAIS (usuários/leads/visitantes).

    Diferente de /messages/topics (que expõe os destinos ESTÁTICOS dos tópicos —
    notificações internas da equipe), esta lista mostra quem de fato recebeu.
    """
    return {"items": _call(_client().list_orders, limit)}


@router.post("/api/v1/admin/messages/contacts", summary="Criar contato no MD")
def md_create_contact(req: ContactCreate):
    return _call(_client().create_contact, req.channel, req.identifier, req.name, req.metadata)


# ── Dead letters / audit ──────────────────────────────────────────────────────

@router.get("/api/v1/admin/messages/dead-letters", summary="Fila de falhas (DLQ)")
def md_dead_letters():
    return {"items": _call(_client().list_dead_letters)}


@router.post("/api/v1/admin/messages/dead-letters/{dlq_id}/redispatch", summary="Reenviar da DLQ")
def md_redispatch(dlq_id: str):
    return _call(_client().redispatch, dlq_id)


@router.get("/api/v1/admin/messages/audit", summary="Auditoria de mensagens")
def md_audit(limit: int = Query(50, ge=1, le=500)):
    return {"items": _call(_client().list_audit_logs, limit)}


# ── SSO handoff (federated access to the native MD UI) ────────────────────────

@router.get("/api/v1/admin/messages/sso/{client_id}",
            summary="Gera handoff SSO assinado para a UI nativa do MD (Business)")
def md_sso_handoff(client_id: str, response: Response, db: Session = Depends(get_saas_db)):
    """Emite uma asserção SSO curta, sem recuperar a API key em plaintext.

    O MessageDispatcher deve trocar a asserção por uma sessão própria. A chave
    da API nunca é lida de ``key_value`` nem devolvida neste handoff.
    """
    secret = os.getenv("MD_AUTOSINAPI_SSO_SECRET", "")
    if not secret:
        raise HTTPException(status_code=500, detail="MD_AUTOSINAPI_SSO_SECRET não configurado")

    row = db.execute(text("""
        SELECT c.email AS email, c.id AS client_id,
               s.id AS subscription_id, k.id AS key_id,
               k.key_prefix AS key_prefix, p.slug AS plan_slug
        FROM saas.clients c
        JOIN saas.subscriptions s ON s.client_id = c.id AND s.status = 'active'
        JOIN saas.plans p ON p.id = s.plan_id
        JOIN saas.api_keys k ON k.subscription_id = s.id AND k.status = 'active'
        WHERE c.id = :cid
          AND p.slug LIKE 'business%'
          AND s.current_period_end > NOW()
          AND s.deleted_at IS NULL
          AND k.deleted_at IS NULL
          AND (k.expires_at IS NULL OR k.expires_at > NOW())
        ORDER BY s.current_period_end DESC
        LIMIT 1
    """), {"cid": client_id}).mappings().first()

    if not row:
        raise HTTPException(
            status_code=403,
            detail="Cliente sem assinatura Business ativa ou chave elegível")

    ts = int(time.time())
    payload = "|".join(str(row[name]) for name in (
        "email", "client_id", "subscription_id", "key_id", "key_prefix", "timestamp"
    ) if name != "timestamp") + f"|{ts}"
    signature = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    assertion = f"{payload}|{signature}"

    response.headers["Cache-Control"] = "no-store"
    base = os.getenv("MD_PUBLIC_URL", "https://mensagem.mundoaec.com").rstrip("/")
    return {
        "action": f"{base}/admin/sso/autosinapi",
        "method": "POST",
        "fields": {
            "email": row["email"],
            "sso_assertion": assertion,
            "timestamp": str(ts),
            "signature": signature,
        },
        "plan_slug": row["plan_slug"],
    }
