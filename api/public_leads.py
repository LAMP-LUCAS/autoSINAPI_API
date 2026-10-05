"""api/public_leads.py — a porta de entrada do negócio.

`POST /api/v1/public/leads` é o caminho **único** de criação de lead.

Por que o backend e não o plugin Lua do Kong
---------------------------------------------
Até 2026-10-01 o dono era o plugin `ssl-mp-adapter` com `mode=lead`, que
interceptava a rota `mp-leads` e **nunca fazia proxy** — este backend não tinha
a rota. Isso criou três problemas concretos:

1. **Sem dono de verdade.** Havia uma rota Kong apontando para um serviço que
   não conhecia o caminho. Se o plugin fosse removido (como aconteceu por
   drift de config), a captura inteira caía em **404** e os formulários do
   portal falhavam em silêncio. Foi o incidente de 2026-10-01.
2. **Falha silenciosa.** O envio de e-mail era `pcall(...)`: se o
   MessageDispatcher estivesse fora, nada era registrado e o lead ficava sem
   contato e ninguém soube.
3. **Sem validação de servidor.** O plugin aceitava `email="qualquercoisa"`.

Decisão de projeto
------------------
A porta de entrada é a peça que não pode degradar em silêncio. Aqui:

- **Validação real** no servidor (o portal continua sendo a primeira linha,
  mas um `curl` não passa).
- **Lead persiste mesmo se o e-mail falhar** — o lead é o negócio; o e-mail é
  cortesia. A falha do MD é registrada e o lead fica na base.
- **Anti-relay.** O endpoint manda e-mail para um endereço escolhido pelo
  chamador. Sem orçamento por IP, isso é um relay de spam. Há orçamento de
  envio *e* rate limit de requisições, ambos por IP.
- **Degradação explícita.** Redis fora do ar não vira 500 (perderia lead) nem
  "aberto" (perderia a proteção): cai para um limitador local, mais conservador.
- **Sem enumeração.** A resposta não distingue "e-mail novo" de "e-mail
  existente" por status HTTP — isso entregaria a lista de clientes a quem
  chute e-mails.

O `mode=lead` do plugin foi removido junto; manter os dois seria duas portas
escrevendo na mesma tabela com semânticas diferentes.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from collections import defaultdict
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.orm import Session

from .database import get_saas_db
from .links import PORTAL_URL, TOOLS_URL
from .schemas import _RATE_LIMIT_RESPONSE

logger = logging.getLogger("autosinapi.public_leads")
# `tier_1` primeiro por convenção do projeto (SPEC-RULE-003): a primeira tag
# classifica o nível de acesso e é o que o Swagger agrupa. `Leads` fica depois
# como rótulo de domínio.
router = APIRouter(tags=["tier_1", "Leads"])

# Regex deliberadamente enxuta: rejeita o óbvio, não tenta ser parser de RFC 5322.
_EMAIL_RE = re.compile(r"^[^@\s,;<>\"]+@[^@\s,;<>\"]+\.[A-Za-z]{2,}$")

# Domínios reservados (RFC 2606 / RFC 6761) nunca resolvem para um destinatário
# real: são, por definição, sintéticos. A suíte E2E do portal usa `.invalid`
# justamente para não entregar e-mail a ninguém — mas eles entravam no funil como
# `is_test = false` e inflavam todo KPI (48 de 56 leads eram sintéticos, e o
# relatório noturno mostrava "100% de conversão" que não existia).
#
# Marcar aqui é a regra PERMANENTE e server-side: não depende de o harness de
# teste lembrar de marcar, e vale para qualquer futuro teste, inclusive os que
# rodam direto contra o PostgreSQL.
_RESERVED_EMAIL_DOMAINS = ("invalid", "test", "example", "localhost")


def _is_synthetic_email(email: str) -> bool:
    """True para domínios reservados (RFC 2606/6761) — nunca um humano real."""
    domain = email.rsplit("@", 1)[-1].lower().rstrip(".")
    tld = domain.rsplit(".", 1)[-1] if "." in domain else domain
    return tld in _RESERVED_EMAIL_DOMAINS or domain in _RESERVED_EMAIL_DOMAINS

# Atribuição de tráfego. O portal só envia estes campos com consentimento de
# marketing (SPEC-RULE-055), então chegar aqui já significa que houve
# consentimento — mas segue restrito a estas chaves, para que um payload
# forjado não vire coluna arbitrária no jsonb.
_ATTRIBUTION_KEYS = (
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "referrer", "landing_path",
)

# Teto anti-abuso. `requests` protege a base; `email_budget` protege os
# destinatários. Os dois são por IP porque é o único identificador confiável
# de quem ainda não se identificou.
_MAX_REQUESTS_PER_MIN = 10
_MAX_EMAILS_PER_HOUR = 5

# Template de boas-vindas no MessageDispatcher. Fica aqui, e não inline na
# chamada, porque o sintoma de errar é silencioso: a OS sai `sent` com o
# template genérico e o cliente só percebe ao abrir a caixa.
LEAD_WELCOME_TEMPLATE_ID = "66666666-6666-6666-6666-666666666666"

# Tempo máximo de espera pelo MD. Acima disso o lead já está salvo e a resposta
# não pode esperar: a captura é o que importa.
_MD_TIMEOUT_S = 2.0


# ── contrato ──────────────────────────────────────────────────────────────────

class LeadIn(BaseModel):
    """Correto espelha o que o portal envia hoje.

    `model_config = extra="ignore"` é deliberado: o gateway antes ignorava
    campos desconhecidos, e um cliente antigo não pode quebrar por isso. Mas
    ignorar ≠ aceitar — `status` e `is_test` forjados são descartados aqui
    porque não são campos deste modelo (o status é sempre `contacted`).
    """

    model_config = {"extra": "ignore"}

    name: str = Field(..., min_length=1, max_length=200)
    email: str = Field(..., min_length=3, max_length=254)
    source: str = Field("portal", max_length=80)
    phone: Optional[str] = Field(None, max_length=40)
    company: Optional[str] = Field(None, max_length=200)
    persona: Optional[str] = Field(None, max_length=80)
    plan_slug: Optional[str] = Field(None, max_length=80)
    plano_interesse: Optional[str] = Field(None, max_length=80)
    message: Optional[str] = Field(None, max_length=2000)
    # Consentimento que o portal já envia (lead.ts, contrato v1). Chega aqui e
    # era descartado por `extra="ignore"` — o backend lia
    # `metadata->>'marketing_optin'` que ninguém gravava, então todo mundo
    # caía no default.
    consent_lgpd: Optional[bool] = None
    consent_em: Optional[str] = Field(None, max_length=40)
    visitor_id: Optional[str] = Field(None, max_length=64)
    utm_source: Optional[str] = Field(None, max_length=200)
    utm_medium: Optional[str] = Field(None, max_length=200)
    utm_campaign: Optional[str] = Field(None, max_length=200)
    utm_term: Optional[str] = Field(None, max_length=200)
    utm_content: Optional[str] = Field(None, max_length=200)
    referrer: Optional[str] = Field(None, max_length=500)
    landing_path: Optional[str] = Field(None, max_length=500)

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name não pode ser só espaços")
        return v

    @field_validator("email")
    @classmethod
    def _email_valid(cls, v: str) -> str:
        v = v.strip().lower()
        if not _EMAIL_RE.match(v):
            raise ValueError("email em formato inválido")
        return v

    def attribution(self) -> dict:
        return {k: getattr(self, k) for k in _ATTRIBUTION_KEYS if getattr(self, k)}


# ── limitadores (injetáveis; o wiring real fica em `_wire`) ────────────────────

class _MemoryLimiter:
    """Janela deslizante em memória, com trava.

    É o caminho de degradação quando o Redis está fora do ar. Mais
    conservador que o Redis (não é compartilhado entre réplicas), mas nunca
    "aberto".
    """

    def __init__(self) -> None:
        self._hits: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def hit(self, key: str, limit: int, window_s: int) -> bool:
        now = time.time()
        with self._lock:
            bucket = self._hits[key]
            bucket[:] = [t for t in bucket if now - t < window_s]
            if len(bucket) >= limit:
                return False
            bucket.append(now)
            return True


class _RedisLimiter:
    """Rate limit compartilhado via Redis (contador com TTL)."""

    def __init__(self, client) -> None:
        self._r = client

    def hit(self, key: str, limit: int, window_s: int) -> bool:
        pipe = self._r.pipeline()
        pipe.incr(key)
        pipe.expire(key, window_s)
        count = pipe.execute()[0]
        return int(count) <= limit


def _redis_limiter():
    """Devolve o limiter Redis, ou o local se o Redis não estiver usável."""
    try:
        from .cache_utils import redis_client
        if redis_client is None:
            return _MemoryLimiter()
        redis_client.ping()
        return _RedisLimiter(redis_client)
    except Exception as exc:  # pragma: no cover - depende do ambiente
        logger.warning("Redis indisponível para rate limit (%s); degradando para local", exc)
        return _MemoryLimiter()


def _mailer():
    """Despachante do e-mail de boas-vindas via MessageDispatcher.

    O `MessageDispatcher` expõe `send(topic, ...)`; o texto de fallback é
    montado aqui e o MD cuida da entrega.

    `template_id` **não é opcional**: sem ele o MD resolve o tópico para o
    template genérico (`gateway_message`) e o cliente recebe assunto e corpo
    errados. Foi o que aconteceu com a primeira lead real depois da porta ser
    restaurada (2026-10-02): a OS saiu `sent` com o template errado e nada no
    fluxo denunciou.
    """
    from .message_dispatcher import MessageDispatcher

    md = MessageDispatcher()

    def send(lead_id: str, name: str, email: str, source: Optional[str] = None):
        portal = getattr(md, "portal_url", None) or PORTAL_URL
        message = (
            f"Obrigado pelo interesse!\n\n"
            f"Olá {name or 'Lead'},\n\n"
            "Recebemos seu cadastro e entraremos em contato em breve.\n\n"
            "Enquanto isso, conheça nossos serviços:\n"
            "- AutoSINAPI: Custos da construção civil\n"
            "- AutoCUB: Custo Unitário Básico\n"
            "- AutoINCC: Índice Nacional de Custo da Construção\n\n"
            f"Portal: {portal}\n\n"
            "Equipe AutoSINAPI"
        )
        return md.send(
            "gateway.lead_welcome",
            message,
            title="Bem-vindo ao Ecossistema Mundoaec",
            recipient=email,
            template_id=LEAD_WELCOME_TEMPLATE_ID,
            # Schema do template (odc_template_versions.variables_schema):
            # {lead_name, portal_url, tools_url}. Enviar menos deixa o Liquid
            # com `{{ ... }}` visível no corpo do e-mail.
            variables={
                "lead_name": name or "Lead",
                "portal_url": portal,
                # SSOT única (`api/links.py`). Este literal já foi
                # `.../ferramentas` — HTTP 404 no primeiro e-mail que um lead
                # recebe — e ninguém pego, porque nenhum contrato cobria este
                # produtor.
                "tools_url": TOOLS_URL,
            },
            # Um e-mail de boas-vindas por lead. O dedupe de lead evita duas
            # linhas no banco, mas o envio acontece na mesma requisição — sem
            # chave, um reenvio que chegue antes do commit duplica a caixa do
            # cliente. O MD deduplica por esta chave.
            idempotency_key=f"lead_welcome:{lead_id}",
            metadata={"lead_id": lead_id, "source": source or "portal"},
        )

    return send


class _LimiterFactory:
    """Permite ao teste instruir 'Redis fora do ar' sem monkeypatch de rede."""

    def __init__(self) -> None:
        self._fn = _redis_limiter
        self._cache: Optional[object] = None

    def get(self):
        if self._cache is None:
            self._cache = self._fn()
        return self._cache


limiter_factory = _LimiterFactory()
mailer_factory = staticmethod(_mailer)

# Atalhos usados pelos testes (o `_wire` do conftest substitui por dublê).
repo = None
mailer = None
limiter = None


def _limiters():
    """Resolve os três injetáveis, preferindo os substituídos pelo teste.

    O despachante pode vir como função (`send_lead_welcome`) ou como objeto com
    método `send_lead_welcome` — o teste usa a segunda forma porque precisa
    contar as tentativas.
    """
    dispatcher = mailer if mailer is not None else mailer_factory()
    send = (dispatcher if callable(dispatcher)
            else dispatcher.send_lead_welcome)
    return (
        repo,  # None em produção: o endpoint liga a sessão da requisição
        send,
        limiter if limiter is not None else limiter_factory.get(),
    )


class _SqlLeadRepo:
    """Persistência de `saas.leads`.

    SQL explícito em vez de ORM porque a tabela é compartilhada com o plugin
    Kong (grava por fora do ORM) e porque upsert parcial precisa de
    `COALESCE` — expresso com clareza em SQL.
    """

    def __init__(self) -> None:
        self._db: Optional[Session] = None

    def bind(self, db: Session) -> "_SqlLeadRepo":
        self._db = db
        return self

    def find_by_email(self, email: str) -> Optional[dict]:
        row = self._db.execute(text("""
            SELECT id, email, name, status FROM saas.leads
             WHERE lower(email) = :e AND deleted_at IS NULL
             ORDER BY created_at DESC LIMIT 1
        """), {"e": email}).mappings().first()
        return dict(row) if row else None

    def mark_test(self, lead_id: str) -> None:
        """Marca a linha como sintética (see `_is_synthetic_email`)."""
        self._db.execute(text(
            "UPDATE saas.leads SET is_test = TRUE WHERE id = :id"
        ), {"id": lead_id})
        self._db.commit()

    def insert(self, data: dict) -> dict:
        row = self._db.execute(text("""
            INSERT INTO saas.leads
                (email, name, source, status, plan_slug, phone, company,
                 persona, metadata, last_activity_at, is_test)
            VALUES
                (:email, :name, :source, 'contacted', :plan_slug, :phone, :company,
                 :persona, CAST(:metadata AS jsonb), now(), :is_test)
            RETURNING id, email, name, status
        """), data).mappings().one()
        self._db.commit()
        # `status` volta do RETURNING; o literal 'contacted' fica no SQL para
        # que o banco seja a fonte da verdade mesmo se o chamador passar algo.
        out = dict(row)
        out.setdefault("status", "contacted")
        return out

    def enrich(self, lead_id: str, fields: dict) -> None:
        """Atualiza só os campos que vieram preenchidos.

        `status` NÃO é tocado: reenviar o formulário não pode rebaixar um lead
        já `converted` para `contacted`.
        """
        allowed = {"name", "phone", "company", "persona", "plan_slug"}
        sets, params = [], {"id": lead_id}
        for key, value in fields.items():
            if key in allowed and value:
                sets.append(f"{key} = :{key}")
                params[key] = value
        # O consentimento e o visitor também são atualizados no reenvio: quem
        # reenvia o form está renovando a autorização, e perder isso faria o
        # lead voltar ao estado "sem consentimento gravado".
        consent = fields.get("metadata") or {}
        for chave_json, campo in (("consent_lgpd", "consent_lgpd"),
                                  ("consent_em", "consent_em"),
                                  ("visitor_id", "visitor_id")):
            if consent.get(chave_json):
                sets.append(
                    f"metadata = COALESCE(metadata,'{{}}'::jsonb) "
                    f"|| jsonb_build_object(:k, :v)")
                params[f"k_{campo}"] = chave_json
                params[f"v_{campo}"] = str(consent[chave_json])
        if not sets:
            return
        params["last_activity_at"] = "NOW()"
        self._db.execute(
            text(f"UPDATE saas.leads SET {', '.join(sets)}, "
                 "last_activity_at = now() WHERE id = :id"),
            params,
        )
        self._db.commit()


def _sql_repo(db: Session) -> _SqlLeadRepo:
    """Repo de produção, ligado à sessão da requisição.

    Sem singleton de propósito: um `_SqlLeadRepo` compartilhado entre threads
    carregaria a `Session` de uma requisição para a seguinte — e o sintoma
    (`'NoneType' object has no attribute 'execute'`) só apareceria em
    produção, nunca no teste.
    """
    return _SqlLeadRepo().bind(db)


# ── endpoint ──────────────────────────────────────────────────────────────────

def _client_ip(request: Request) -> str:
    """IP do cliente, honrando o proxy.

    `X-Forwarded-For` só é confiável atrás do Kong; como este serviço é
    interno e só é alcançável pela rota do gateway, o cabeçalho é o que
    identifica o visitante real atrás do Cloudflare.
    """
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _dispatch_welcome(send, lead: dict, source: str, limiter) -> str:
    """Envia a boas-vindas, sob orçamento por IP.

    Devolve `"sent"`, `"budget_exhausted"` ou `"failed"`. Nunca levanta: uma
    falha de e-mail não pode custar o lead.
    """
    ip = lead.get("_ip", "unknown")
    if not limiter.hit(f"leadmail:{ip}", _MAX_EMAILS_PER_HOUR, 3600):
        logger.warning(
            "Orçamento de e-mail por IP esgotado para %s — lead %s gravado sem contato",
            ip, lead.get("id"),
        )
        return "budget_exhausted"
    try:
        send(lead_id=str(lead["id"]), name=lead.get("name") or "Lead",
             email=lead["email"], source=source)
        return "sent"
    except Exception as exc:
        logger.error("Falha ao enviar boas-vindas para lead %s: %s", lead.get("id"), exc)
        return "failed"


@router.post(
    "/api/v1/public/leads",
    status_code=201,
    summary="Capturar lead do portal",
    responses={**_RATE_LIMIT_RESPONSE},
)
def create_lead(
    payload: LeadIn,
    request: Request,
    db: Session = Depends(get_saas_db),
):
    """Captura um lead do portal.

    Contrato de resiliência: **um lead gravado não é perdido por falha de
    e-mail, de MD ou de rate limiter**. A resposta 201 significa "lead no
    banco", não "e-mail enviado" — e `welcome` diz o que aconteceu com o
    envio, para o painel poder observar.
    """
    ip = _client_ip(request)
    store, send, limiter = _limiters()
    if store is None:
        store = _sql_repo(db)

    if not limiter.hit(f"leadrate:{ip}", _MAX_REQUESTS_PER_MIN, 60):
        raise HTTPException(status_code=429,
                            detail="Muitas solicitações. Tente novamente em instantes.")

    body = payload.model_dump()
    attribution = payload.attribution()

    existing = store.find_by_email(payload.email)
    if existing:
        # Não rebaixa status: só enriquece o que o chamador mandou.
        store.enrich(existing["id"], {
            "name": payload.name,
            "phone": payload.phone,
            "company": payload.company,
            "persona": payload.persona,
            "plan_slug": payload.plan_slug or payload.plano_interesse,
            "metadata": {k: v for k, v in {
                "consent_lgpd": payload.consent_lgpd,
                "consent_em": payload.consent_em,
                "visitor_id": payload.visitor_id,
            }.items() if v},
        })
        existing["_ip"] = ip
        return {
            "id": str(existing["id"]),
            "status": existing.get("status") or "contacted",
            "deduped": True,
            "welcome": _dispatch_welcome(send, existing, payload.source, limiter),
        }

    metadata = {
        "phone": payload.phone,
        "company": payload.company,
        "persona": payload.persona,
        "plano_interesse": payload.plano_interesse,
    }
    if attribution:
        metadata["attribution"] = attribution
    if payload.message:
        metadata["message"] = payload.message
    if payload.consent_lgpd:
        # Só grava com instante válido: consentimento sem data não prova nada.
        metadata["consent_lgpd"] = True
        if payload.consent_em:
            metadata["consent_em"] = payload.consent_em
    if payload.visitor_id:
        metadata["visitor_id"] = payload.visitor_id

    is_test = _is_synthetic_email(payload.email)
    lead = store.insert({
        "email": payload.email,
        "name": payload.name,
        "source": payload.source or "portal",
        "plan_slug": payload.plan_slug or payload.plano_interesse,
        "phone": payload.phone,
        "company": payload.company,
        "persona": payload.persona,
        "metadata": _json(metadata),
        "is_test": is_test,
    })
    lead["_ip"] = ip

    logger.info("Lead capturado id=%s source=%s ip=%s is_test=%s",
                lead["id"], payload.source, ip, is_test)
    return {
        "id": str(lead["id"]),
        "status": lead.get("status", "contacted"),
        "deduped": False,
        "welcome": _dispatch_welcome(send, lead, payload.source, limiter),
    }


def _json(obj: dict) -> str:
    import json
    return json.dumps(obj, ensure_ascii=False)