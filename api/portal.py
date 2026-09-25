import os
import time
import hmac
import hashlib
import secrets
from typing import Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from . import schemas
from .database import get_db, get_saas_db
from .schemas import _RATE_LIMIT_RESPONSE, _AUTH_RESPONSES

router = APIRouter(tags=["tier_1", "Portal"])


@router.get(
    "/api/v1/public/portal/me",
    summary="Obter dados do portal do assinante",
    response_description="Plano, validade, quota usada/limite, features e links de upgrade/downgrade",
    response_model=schemas.PortalResponse,
    responses={**_AUTH_RESPONSES, **_RATE_LIMIT_RESPONSE},
)
def portal_me(
    x_api_key: str = Header(..., alias="X-API-KEY"),
    db: Session = Depends(get_saas_db),
):
    key_row = db.execute(
        text("""
            SELECT k.id as key_id, k.client_id::text as client_id, k.subscription_id,
                   k.status as key_status,
                   s.status as sub_status,
                   s.current_period_start, s.current_period_end,
                   p.slug as plan_slug, p.name as plan_name,
                   p.max_requests, p.duration_days,
                   p.price_cents, p.features::text as features
            FROM saas.api_keys k
            JOIN saas.subscriptions s ON s.id = k.subscription_id
            JOIN saas.plans p ON p.id = s.plan_id
            WHERE k.key_hash = crypt(:x_api_key, k.key_hash)
        """),
        {"x_api_key": x_api_key},
    ).mappings().first()

    if not key_row:
        raise HTTPException(status_code=401, detail="API key inválida ou não encontrada")

    import json
    features = key_row["features"]
    if isinstance(features, str):
        features = json.loads(features)

    usage_row = db.execute(
        text("""
            SELECT COUNT(*) as total
            FROM saas.usage_logs
            WHERE api_key_id = :key_id
              AND requested_at >= :period_start
              AND requested_at <= :period_end
        """),
        {
            "key_id": key_row["key_id"],
            "period_start": key_row["current_period_start"],
            "period_end": key_row["current_period_end"],
        },
    ).mappings().first()

    total_used = usage_row["total"] if usage_row else 0
    limit = key_row["max_requests"]
    pct = round((total_used / limit) * 100, 1) if limit > 0 else 0.0

    frontend_base = os.getenv("FRONTEND_BASE_URL", "https://autosinapi.mundoaec.com")

    plan_slug = key_row["plan_slug"]
    upgrade_links = {}
    if plan_slug == "free":
        upgrade_links = {
            "starter": f"{frontend_base}/checkout?plan=starter",
            "pro": f"{frontend_base}/checkout?plan=pro",
            "Business": f"{frontend_base}/checkout?plan=Business",
        }
    elif plan_slug == "starter":
        upgrade_links = {
            "pro": f"{frontend_base}/checkout?plan=pro",
            "Business": f"{frontend_base}/checkout?plan=Business",
        }
    elif plan_slug == "pro":
        upgrade_links = {
            "Business": f"{frontend_base}/checkout?plan=Business",
        }

    def _fmt_ts(ts):
        return ts.isoformat() if ts else None

    return schemas.PortalResponse(
        client_id=key_row["client_id"],
        plan=schemas.PlanInfo(
            slug=plan_slug,
            name=key_row["plan_name"],
            price_cents=key_row["price_cents"],
        ),
        subscription={
            "status": key_row["sub_status"],
            "current_period_start": _fmt_ts(key_row["current_period_start"]),
            "current_period_end": _fmt_ts(key_row["current_period_end"]),
        },
        quota=schemas.QuotaInfo(
            used=total_used,
            limit=limit,
            percentage=pct,
        ),
        features=features,
        links=schemas.PortalLinks(
            upgrade=upgrade_links,
            downgrade=None
            if plan_slug in ("free", "starter")
            else f"{frontend_base}/checkout?plan=starter",
            renew=f"{frontend_base}/checkout?plan={plan_slug}",
        ),
    )


@router.post(
    "/api/v1/public/portal/message-dispatcher-sso",
    summary="Gerar handoff SSO para o MessageDispatcher (assinante Business)",
    response_description="Parâmetros assinados para POST no login federado do MD",
    responses={**_AUTH_RESPONSES, **_RATE_LIMIT_RESPONSE},
)
def message_dispatcher_sso(
    response: Response,
    x_api_key: Optional[str] = Header(None, alias="X-API-KEY"),
    db: Session = Depends(get_saas_db),
):
    """Autentica a key e entrega uma asserção SSO curta sem plaintext.

    Restrito a assinaturas **Business** ativas (regra do MD). A key é validada
    por ``key_hash``; ela não é recuperada nem incluída no handoff.
    """
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Header X-API-KEY obrigatório")

    secret = os.getenv("MD_AUTOSINAPI_SSO_SECRET", "")
    if not secret:
        raise HTTPException(status_code=503, detail="SSO do MessageDispatcher não configurado")

    row = db.execute(text("""
        SELECT c.email AS email, c.id AS client_id,
               s.id AS subscription_id, k.id AS key_id,
               k.key_prefix AS key_prefix, p.slug AS plan_slug
        FROM saas.api_keys k
        JOIN saas.subscriptions s ON s.id = k.subscription_id
        JOIN saas.plans p ON p.id = s.plan_id
        JOIN saas.clients c ON c.id = k.client_id
        WHERE k.key_hash = crypt(:key, k.key_hash)
          AND k.status = 'active'
          AND k.deleted_at IS NULL
          AND s.status = 'active'
          AND s.deleted_at IS NULL
          AND s.current_period_end > NOW()
          AND (k.expires_at IS NULL OR k.expires_at > NOW())
          AND p.slug LIKE 'business%'
        ORDER BY s.current_period_end DESC
        LIMIT 1
    """), {"key": x_api_key}).mappings().first()

    if not row:
        raise HTTPException(
            status_code=403,
            detail="Acesso ao MessageDispatcher requer assinatura Business ativa")

    ts = int(time.time())
    expires_at = ts + 300
    jti = secrets.token_urlsafe(16)
    claims = "|".join(str(row[name]) for name in (
        "email", "client_id", "subscription_id", "key_id", "key_prefix", "jti"
    )) + f"|{ts}|{expires_at}"
    signature = hmac.new(secret.encode(), claims.encode(), hashlib.sha256).hexdigest()

    if response is not None:
        response.headers["Cache-Control"] = "no-store"
    base = os.getenv("MD_PUBLIC_URL", "https://mensagem.mundoaec.com").rstrip("/")
    return {
        "action": f"{base}/admin/sso/autosinapi",
        "method": "POST",
        "fields": {
            "email": row["email"],
            "sso_assertion": f"{claims}|{signature}",
            "timestamp": str(ts),
            "expires_at": str(expires_at),
            "jti": jti,
            "signature": signature,
        },
        "plan_slug": row["plan_slug"],
    }
