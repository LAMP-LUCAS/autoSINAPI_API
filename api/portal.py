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

# Ordem fixa das claims do handoff SSO. Manter como constante evita que um
# campo entre na asserção sem cobertura de teste — foi assim que um `jti` local
# virou `row["jti"]` e derrubou o endpoint com 500 em 2026-09-25.
SSO_CLAIM_FIELDS = ("email", "client_id", "subscription_id", "key_id", "key_prefix")

# Sinal de login do app — o marcador **canônico** de atividade do funil.
#
# O app é o que é pago; "entrou no produto" é o que distingue lead ativo de
# lead frio. Antes não existia escritor de login: `leads.last_activity_at` só
# era tocado pelo envio do formulário de captura e por ação manual no admin,
# o que fazia `SQL_CONSUMO_APP` ser cópia byte-a-byte de `SQL_CONSUMO_PORTAL`
# e a cascata de sinais um no-op (medido: 0 divergências em 32 leads).
#
# **Vai para `client_events`, não para `leads`.** `last_activity_at` é a
# mesma coluna que o portal escreve pela ponte de formulário; gravar login
# lá fundiria os dois sinais e a cascata voltaria a ser no-op com outros
# nomes. Login é evento, e `client_events` (`client_id`, `event_type`,
# `occurred_at`) existe para isso.
EVENTO_LOGIN_APP = "portal_login"

# Janela de auto-limitação, em horas. `portal/me` é chamado a **cada abertura
# de tela**: sem isto, 200 aberturas = 200 INSERTs. Com, no máximo um evento
# por pessoa por janela — frequência suficiente, já que o winback só olha de
# 30 em 30 dias. Precisa ser bem menor que 30 dias: acima disso, ninguém
# marcaria atividade a tempo de evitar a recuperação.
MARGEM_REATIVACAO_HORAS = 12


def _registrar_login_app(db: Session, client_id: Optional[str]) -> None:
    """Registra que `client_id` abriu o produto agora.

    Chamado por dentro do `portal/me`, **depois** da chave ser validada — só
    uma requisição autenticada gera evento.

    Três decisões que não são óbvias:

    * **auto-limitado na própria SQL** (`WHERE NOT EXISTS`), e não com um
      SELECT antes: uma instrução só, sem corrida entre requisições
      simultâneas do mesmo cliente;
    * **INSERT direto, sem `leads`** — quem consome API sem ser lead
      continua sem lead;
    * **best-effort**: o `try/except` fica **aqui**, não no call-site, para
      que a função seja segura em qualquer ponto de chamada. Um sinal de
      marketing não pode derrubar a tela principal do produto.
    """
    alvo = (client_id or "").strip()
    if not alvo:
        return
    try:
        db.execute(
            text("""
                INSERT INTO saas.client_events
                    (client_id, event_type, actor, details, occurred_at)
                SELECT :client_id, :evento, 'system', '{}'::jsonb, now()
                 WHERE NOT EXISTS (
                       SELECT 1 FROM saas.client_events
                        WHERE client_id = :client_id
                          AND event_type = :evento
                          AND occurred_at > now()
                              - make_interval(hours => :margem))
            """),
            {"client_id": alvo, "evento": EVENTO_LOGIN_APP,
             "margem": MARGEM_REATIVACAO_HORAS},
        )
        # O commit é **obrigatório e mora aqui**. `get_saas_db` só faz
        # `close()` — sem commit, a escrita é revertida no fim da requisição e
        # o evento some silenciosamente. Foi exatamente o que aconteceu na
        # primeira verificação: o endpoint devolvia 200, o `except` engolia o
        # sintoma, e o sinal simplesmente não existia. Um helper de telemetria
        # que depende de o chamador lembrar do commit não é best-effort, é
        # sorte.
        db.commit()
    except Exception:                            # noqa: BLE001 — sinal é acessório
        try:
            db.rollback()
        except Exception:                        # noqa: BLE001
            pass


def _build_sso_claims(row, jti: str, issued_at: int, expires_at: int) -> str:
    """Serializa as claims do handoff: metadados + jti + validade.

    Só entram os campos listados em SSO_CLAIM_FIELDS — nunca a raw key.
    `key_prefix` nulo (linha legada) vira string vazia em vez de explodir.
    """
    parts = [
        "" if row[name] is None else str(row[name])
        for name in SSO_CLAIM_FIELDS
    ]
    parts.extend([str(jti), str(issued_at), str(expires_at)])
    return "|".join(parts)


def _sign_sso_claims(claims: str, secret: str) -> str:
    return hmac.new(secret.encode(), claims.encode(), hashlib.sha256).hexdigest()


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
                   p.price_cents, p.features::text as features,
                   c.email as email
            FROM saas.api_keys k
            JOIN saas.subscriptions s ON s.id = k.subscription_id
            JOIN saas.plans p ON p.id = s.plan_id
            JOIN saas.clients c ON c.id = k.client_id
            WHERE k.key_hash = crypt(:x_api_key, k.key_hash)
        """),
        {"x_api_key": x_api_key},
    ).mappings().first()

    if not key_row:
        raise HTTPException(status_code=401, detail="API key inválida ou não encontrada")

    # Sinal de login: esta é a chamada que o app faz ao abrir, com chave já
    # validada — logo, é o marcador canônico de atividade do funil. Só depois
    # do 401: chave inválida não ativa ninguém. Best-effort por construção.
    _registrar_login_app(db, key_row.get("client_id"))

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


def _lookup_own_key(x_api_key: str, db: Session):
    """Resolve a chave apresentada contra o hash (bcrypt via crypt()).

    Retorna a linha (key_id/client_id/subscription_id/key_prefix/key_status)
    ou None — a comparação é SEMPRE por hash, nunca por plaintext (REGRA 1).
    """
    return db.execute(
        text("""
            SELECT k.id as key_id, k.client_id::text as client_id, k.subscription_id,
                   k.status as key_status, k.key_prefix
            FROM saas.api_keys k
            WHERE k.key_hash = crypt(:x_api_key, k.key_hash)
        """),
        {"x_api_key": x_api_key},
    ).mappings().first()


@router.get(
    "/api/v1/public/portal/me/api-key",
    summary="Consultar a chave de API do próprio assinante",
    response_description="Prefixo e status da chave apresentada (sem plaintext)",
    response_model=schemas.PortalApiKeyResponse,
    responses={**_AUTH_RESPONSES, **_RATE_LIMIT_RESPONSE},
)
def portal_api_key(
    x_api_key: Optional[str] = Header(None, alias="X-API-KEY"),
    db: Session = Depends(get_saas_db),
):
    """Introspecção BYOK (STORY-MCP-008): identifica qual chave está em uso.

    Nunca devolve a chave em claro; apenas o prefixo (para conferência no
    painel/OpenWebUI) e o status. Sem efeitos colaterais — não escreve.
    """
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Header X-API-KEY obrigatório")
    key_row = _lookup_own_key(x_api_key, db)
    if not key_row:
        raise HTTPException(status_code=401, detail="API key inválida ou não encontrada")
    return schemas.PortalApiKeyResponse(
        key_prefix=key_row["key_prefix"] or "",
        status=key_row["key_status"],
        rotated=False,
        api_key=None,
    )


@router.post(
    "/api/v1/public/portal/me/api-key",
    summary="Rotacionar a chave de API do próprio assinante",
    response_description="Nova chave em claro (retorno único) + prefixo da nova",
    response_model=schemas.PortalApiKeyResponse,
    responses={**_AUTH_RESPONSES, **_RATE_LIMIT_RESPONSE},
)
def rotate_api_key(
    response: Response,
    x_api_key: Optional[str] = Header(None, alias="X-API-KEY"),
    db: Session = Depends(get_saas_db),
):
    """Rotação self-service (STORY-MCP-008).

    Prova de posse = autenticação com a chave atual. Na mesma transação:
    revoga a anterior, emite a nova (bcrypt) na MESMA assinatura, registra
    `client_events.api_key_rotated` e devolve o plaintext UMA única vez.
    Chave revogada não rotaciona (401) — recuperação é via admin/CRM.
    """
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Header X-API-KEY obrigatório")
    key_row = _lookup_own_key(x_api_key, db)
    if not key_row:
        raise HTTPException(status_code=401, detail="API key inválida ou não encontrada")
    if key_row["key_status"] != "active":
        raise HTTPException(status_code=401, detail="API key não está ativa")

    import json

    key_value = f"autosinapi_{secrets.token_hex(16)}"
    key_prefix = key_value[11:19]

    db.execute(
        text("""
            UPDATE saas.api_keys SET status = 'revoked', deleted_at = NOW()
            WHERE id = :kid AND status = 'active'
        """),
        {"kid": key_row["key_id"]},
    )
    new_id = db.execute(
        text("""
            INSERT INTO saas.api_keys (client_id, subscription_id, key_prefix, key_hash, status)
            VALUES (:cid, :sid, :prefix, crypt(:kv, gen_salt('bf')), 'active')
            RETURNING id
        """),
        {"cid": key_row["client_id"], "sid": key_row["subscription_id"],
         "prefix": key_prefix, "kv": key_value},
    ).scalar_one()
    db.execute(
        text("""
            INSERT INTO saas.client_events (client_id, event_type, actor, details, occurred_at)
            VALUES (:cid, :et, :actor, CAST(:details AS jsonb), NOW())
        """),
        {"cid": key_row["client_id"], "et": "api_key_rotated", "actor": "portal",
         "details": json.dumps({"subscription_id": str(key_row["subscription_id"]),
                                "key_prefix": key_prefix, "key_id": str(new_id)})},
    )
    db.commit()

    response.headers["Cache-Control"] = "no-store"
    return schemas.PortalApiKeyResponse(
        key_prefix=key_prefix,
        status="active",
        rotated=True,
        api_key=key_value,
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
    claims = _build_sso_claims(row, jti=jti, issued_at=ts, expires_at=expires_at)
    signature = _sign_sso_claims(claims, secret)

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
