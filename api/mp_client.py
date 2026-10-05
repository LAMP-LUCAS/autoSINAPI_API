"""Cliente **somente leitura** do Mercado Pago.

POR QUE UM MÓDULO PRÓPRIO
-------------------------
Até 05/10/2026 o único acesso ao MP no lado Python era... nenhum: o token vivia
só na config do plugin Kong. A operação de pagamento dependia inteiramente do
webhook — e o webhook já falhou (`MP API error 404` em 06/09, porque o código
usava `GET /preapproval/{id}` quando a doc manda `GET /preapproval/search`).

Este cliente existe para dar um SEGUNDO CAMINHO de leitura. Ele é deliberadamente
read-only: reconciliação que escreve no MP a partir do painel é uma decisão
outra (e mais perigosa) — estorno e cancelamento ficam fora do escopo.

ENDPOINTS (todos da doc oficial "Webhooks > Ações necessárias após receber uma
notificação"):

| evento                          | endpoint                                    |
|---------------------------------|---------------------------------------------|
| `payment`                       | `GET /v1/payments/{id}`                     |
| `subscription_preapproval`      | `GET /preapproval/search?preapproval_id=`    |
| `subscription_authorized_payment` | `GET /authorized_payments/{id}`            |
| `subscription_preapproval_plan` | `GET /preapproval_plan/search`              |

ESCOPO v1: LER. Nada aqui cria, cancela ou estorna.

CONFIG
------
O token vem de `MP_ACCESS_TOKEN` (ou `MP_ACCESS_TOKEN_TEST`, que já existia no
`secrets.env`). É o MESMO token do plugin Kong (decisão de 06/10/2026): um
segundo token seria uma segunda credencial rodando em outro lugar — mais um
segredo para rotacionar, sem ganho de segurança. O risco é mitigado pelo fato de
este módulo não escrever.

TRANSPORTE
----------
`urllib.request` da biblioteca padrão, como o resto do backend
(`message_dispatcher`). Não `httpx`/`requests`: nenhum dos dois está no
`requirements.txt`, e adicionar uma dependência de produção para ler quatro
endpoints seria desproporcional.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import urllib.error
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)

BASE_URL = "https://api.mercadopago.com"
TIMEOUT_S = 15.0

# Um `search` do MP devolve 10 itens por página. 50 é o teto aceito e cobre
# uma janela de dias mesmo num volume baixo — que é o nosso caso.
PAGE_LIMIT = 50


class MPUnavailable(RuntimeError):
    """Rede/5xx do MP. Distinto de "recurso não existe" (404), que é resposta
    válida e não deve abortar a sincronização inteira."""


@dataclass
class MPResource:
    """Um recurso do MP já normalizado.

    A normalização acontece AQUI, e não no consumidor, porque os quatro
    endpoints têm formatos diferentes e o resto do sistema não deveria saber
    qual endpoint originou cada linha.
    """

    resource_type: str
    resource_id: str
    status: str | None = None
    status_detail: str | None = None
    amount_cents: int | None = None
    currency_id: str | None = None
    payer_email: str | None = None
    payer_id: str | None = None
    payer_name: str | None = None
    external_reference: str | None = None
    reason: str | None = None
    preapproval_plan_id: str | None = None
    preapproval_id: str | None = None
    mp_created_at: datetime | None = None
    mp_updated_at: datetime | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    def to_row(self) -> dict[str, Any]:
        return {
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "status": self.status,
            "status_detail": self.status_detail,
            "amount_cents": self.amount_cents,
            "currency_id": self.currency_id,
            "payer_email": self.payer_email,
            "payer_id": self.payer_id,
            "payer_name": self.payer_name,
            "external_reference": self.external_reference,
            "reason": self.reason,
            "preapproval_plan_id": self.preapproval_plan_id,
            "preapproval_id": self.preapproval_id,
            "mp_created_at": self.mp_created_at,
            "mp_updated_at": self.mp_updated_at,
            "raw": self.raw,
        }


def _ts(value: Any) -> datetime | None:
    """Converte timestamp do MP ("2026-10-05T16:34:51.000-04:00") em aware UTC.

    Sem `tzinfo` a comparação com `NOW()` do Postgres erra por horas e a janela
    de sincronização passa a pegar (ou perder) recursos na borda.
    """
    if not value or not isinstance(value, str):
        return None
    text = value.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _cents(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(round(float(value) * 100))
    except (TypeError, ValueError):
        return None


def _payer(raw: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    """(email, id, nome) do pagador.

    O nome vem do MP quando existe. `clients.name` é NOT NULL, então o
    reconciliador precisa de um — e o local-part do e-mail é um last resort,
    não a primeira escolha.
    """
    payer = raw.get("payer") or {}
    if not isinstance(payer, dict):
        return None, None, None
    email = payer.get("email")
    pid = payer.get("id")
    nome = payer.get("first_name") or payer.get("last_name") or None
    return (str(email) if email else None,
            str(pid) if pid else None,
            str(nome).strip() if nome else None)


class MPClient:
    """Leitor do Mercado Pago. Stateless; instanciar por uso."""

    def __init__(self, token: str | None = None, base_url: str | None = None,
                 transport: Any = None) -> None:
        # O `secrets.env` do stack já traz `MP_ACCESS_TOKEN_TEST` e
        # `MP_ACCESS_TOKEN_PROD` separados (decisão de 06/10: o MESMO token do
        # plugin Kong, sem criar uma credencial nova para rotacionar). Aceitar os
        # dois nomes evita inventar um terceiro segredo; o genérico tem
        # precedência para que um override explícito funcione.
        #
        # O default é TEST porque ler em produção por engano materializaria
        # assinatura de uma venda de teste — e o erro é invisível justamente
        # porque a assinatura "faria sentido".
        self._token = (token
                       or os.getenv("MP_ACCESS_TOKEN", "")
                       or os.getenv("MP_ACCESS_TOKEN_TEST", "")
                       or os.getenv("MP_ACCESS_TOKEN_PROD", ""))
        self._base = (base_url or os.getenv("MP_API_BASE") or BASE_URL).rstrip("/")
        # `transport` é injetável para teste; por padrão usa urllib.
        self._transport = transport

    def close(self) -> None:
        return None

    def __enter__(self) -> "MPClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    @property
    def configured(self) -> bool:
        return bool(self._token)

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        if not self._token:
            raise MPUnavailable("MP_ACCESS_TOKEN ausente")
        url = f"{self._base}{path}"
        if params:
            url = f"{url}?{urllib.parse.urlencode(params, doseq=True)}"
        headers = {"Authorization": f"Bearer {self._token}",
                   "Accept": "application/json"}

        if self._transport is not None:      # injetado (teste)
            status, text = self._transport(url, headers)
        else:
            req = urllib.request.Request(url, headers=headers, method="GET")
            try:
                with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
                    status, text = resp.status, resp.read().decode("utf-8", "replace")
            except urllib.error.HTTPError as exc:
                status, text = exc.code, (exc.read().decode("utf-8", "replace") if exc.fp else "")
            except (urllib.error.URLError, OSError) as exc:
                raise MPUnavailable(f"rede: {exc}") from exc

        if status >= 500:
            raise MPUnavailable(f"MP {status}")
        if status == 404:
            return None
        if status >= 400:
            # 4xx de requisição é erro NOSSO (token, filtro). Não é "recurso
            # ausente": mascarar os dois levaria a concluir que não houve venda.
            raise MPUnavailable(f"MP {status}: {text[:180]}")
        try:
            return json.loads(text)
        except ValueError as exc:
            raise MPUnavailable("resposta não-JSON") from exc

    # ── leituras por recurso ──────────────────────────────────────────────────

    def get_payment(self, payment_id: str) -> MPResource | None:
        raw = self._get(f"/v1/payments/{payment_id}")
        if not raw:
            return None
        email, pid, nome = _payer(raw)
        detail = (raw.get("status_details") or {}).get("code")
        return MPResource(
            resource_type="payment",
            resource_id=str(raw.get("id") or payment_id),
            status=raw.get("status"),
            status_detail=detail,
            amount_cents=_cents(raw.get("transaction_amount")),
            currency_id=raw.get("currency_id"),
            payer_email=email,
            payer_id=pid,
            payer_name=nome,
            external_reference=raw.get("external_reference"),
            reason=(raw.get("reason") or raw.get("description") or None),
            preapproval_id=str(raw.get("preapproval_id")) if raw.get("preapproval_id") else None,
            mp_created_at=_ts(raw.get("date_created")),
            mp_updated_at=_ts(raw.get("date_last_updated")),
            raw=raw,
        )

    def get_preapproval(self, preapproval_id: str) -> MPResource | None:
        """`subscription_preapproval` — o endpoint DOCUMENTADO é `search`.

        `GET /preapproval/{id}` respondia 404 no sandbox (medido em 05/10/2026)
        e era o que o plugin usava. Busca por `preapproval_id` devolve o
        envelope `{results: [...]}`.

        ⚠ O filtro `preapproval_id` do MP **não é confiável**: medido em
        05/10/2026, `search?preapproval_id=X&limit=1` devolveu o PRIMEIRO item
        da lista 19 vezes seguidas, sempre outro. Sem conferir o id, o
        reconciliador gravava 19 linhas com o MESMO resource_id — e o
        `PRIMARY KEY (resource_type, resource_id)` colapsava tudo em uma só,
        produzindo um espelho que parecia ter 1 assinatura quando o MP
       =listava 19. Dado errado e silencioso é pior que erro: aqui, materializar
        a assinatura errada entrega acesso ao cliente errado.
        Por isso o match é conferido item a item.
        """
        data = self._get("/preapproval/search",
                         {"preapproval_id": preapproval_id, "limit": 20})
        results = (data or {}).get("results") or []
        raw = next((r for r in results
                    if str(r.get("id")) == str(preapproval_id)), None)
        if raw is None:
            return None
        email, pid, nome = _payer(raw)
        return MPResource(
            resource_type="preapproval",
            resource_id=str(raw.get("id") or preapproval_id),
            status=raw.get("status"),
            status_detail=raw.get("status_detail"),
            amount_cents=_cents(raw.get("transaction_amount")),
            currency_id=raw.get("currency_id"),
            payer_email=email,
            payer_id=pid,
            payer_name=nome,
            external_reference=raw.get("external_reference"),
            reason=raw.get("reason"),
            preapproval_plan_id=str(raw.get("preapproval_plan_id")) if raw.get("preapproval_plan_id") else None,
            preapproval_id=str(raw.get("id")),
            mp_created_at=_ts(raw.get("date_created")),
            mp_updated_at=_ts(raw.get("last_modified")),
            raw=raw,
        )

    def get_authorized_payment(self, authorized_payment_id: str) -> MPResource | None:
        """`subscription_authorized_payment` — a COBRANÇA recorrente.

        Este é o recurso que responde "o cliente pagou o mês passado?", e é o
        que dá churn real (assinatura sem cobrança aprovada no mês).
        """
        raw = self._get(f"/authorized_payments/{authorized_payment_id}")
        if not raw:
            return None
        email, pid, nome = _payer(raw)
        return MPResource(
            resource_type="authorized_payment",
            resource_id=str(raw.get("id") or authorized_payment_id),
            status=raw.get("status"),
            status_detail=raw.get("status_detail"),
            amount_cents=_cents(raw.get("transaction_amount")),
            currency_id=raw.get("currency_id"),
            payer_email=email,
            payer_id=pid,
            payer_name=nome,
            external_reference=raw.get("external_reference"),
            reason=raw.get("reason"),
            preapproval_id=str(raw.get("preapproval_id")) if raw.get("preapproval_id") else None,
            mp_created_at=_ts(raw.get("date_created")),
            mp_updated_at=_ts(raw.get("date_last_updated")),
            raw=raw,
        )

    def search_payments(self, since: datetime, until: datetime | None = None,
                        limit: int = PAGE_LIMIT) -> list[MPResource]:
        data = self._get("/v1/payments/search", {
            "begin_date": since.strftime("%Y-%m-%dT%H:%M:%S.000-03:00"),
            "end_date": (until or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%S.000-03:00"),
            "limit": min(int(limit), PAGE_LIMIT),
        })
        return [self.get_payment(str(p["id"])) for p in (data or {}).get("results", [])]

    def search_preapprovals(self, since: datetime, limit: int = PAGE_LIMIT) -> list[MPResource]:
        data = self._get("/preapproval/search", {
            "begin_date": since.strftime("%Y-%m-%dT%H:%M:%S.000-03:00"),
            "limit": min(int(limit), PAGE_LIMIT),
        })
        out: list[MPResource] = []
        for item in (data or {}).get("results", []):
            res = self.get_preapproval(str(item.get("id")))
            if res:
                out.append(res)
        return out

    def health(self) -> dict[str, Any]:
        """Prova de vida do token, sem efeitos colaterais.

        Usado no painel: um token expirado produz a MESMA aparência de "não
        houve venda", e essa confusão é exatamente o que este trabalho existe
        para eliminar.
        """
        if not self._token:
            return {"configured": False, "reachable": False,
                    "detail": "MP_ACCESS_TOKEN ausente"}
        try:
            me = self._get("/users/me")
        except MPUnavailable as exc:
            return {"configured": True, "reachable": False, "detail": str(exc)}
        return {
            "configured": True,
            "reachable": True,
            "detail": (me or {}).get("nickname") or "autenticado",
            "site_id": (me or {}).get("site_id"),
        }


def window(days: int) -> timedelta:
    return timedelta(days=max(int(days), 1))