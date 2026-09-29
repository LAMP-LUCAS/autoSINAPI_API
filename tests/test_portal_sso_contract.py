"""Contrato HTTP do handoff SSO — lado emissor (STORY-GW-043).

O receptor (MessageDispatcher `spec/requests/sso_spec.rb`) foi escrito contra
o retorno REAL destes endpoints. Este arquivo fixa os NOMES dos campos, o
formato das claims e a verificabilidade da assinatura como contrato: se o
emissor mudar por conta própria, estes testes ficam vermelhos antes de
qualquer deploy.

O guard cruzado
(`SistemaServerLight/automation/scripts/test_sso_contract_guard.py`)
compara estes mesmos nomes com o que o receptor lê no POST — é ele que pega
mudança UNILATERAL de qualquer dos lados. A prova em produção é o e2e vivo
(`verify_sso_handoff.py`), que monta o POST do receptor a partir do retorno
do emissor, nunca de fixture escrita à mão.

Cobertos os DOIS emissores que postam no mesmo endpoint do MD:
  - POST /api/v1/public/portal/message-dispatcher-sso  (portal, 8 claims)
  - GET  /api/v1/admin/messages/sso/{client_id}        (admin,  6 claims)
"""
import hashlib
import hmac
import time

import pytest
from fastapi.testclient import TestClient

from api.admin_auth import verify_admin_token
from api.database import get_saas_db
from api.main import app

# ── contrato declarado (SSOT dos nomes compartilhados com o receptor) ─────────
PORTAL_FIELDS = ["email", "sso_assertion", "timestamp", "expires_at", "jti", "signature"]
ADMIN_FIELDS = ["email", "sso_assertion", "timestamp", "signature"]
CLAIMS_PORTAL_LEN = 8  # email|client_id|subscription_id|key_id|key_prefix|jti|issued_at|expires_at
CLAIMS_ADMIN_LEN = 6   # email|client_id|subscription_id|key_id|key_prefix|ts
SECRET = "contrato-sso-de-teste"

BUSINESS_ROW = {
    "email": "cliente@exemplo.test",
    "client_id": "11111111-1111-1111-1111-111111111111",
    "subscription_id": "22222222-2222-2222-2222-222222222222",
    "key_id": "33333333-3333-3333-3333-333333333333",
    "key_prefix": "ab12cd34",
    "plan_slug": "business",
}


class _FakeResult:
    def __init__(self, row):
        self._row = row

    def mappings(self):
        return self

    def first(self):
        return self._row


class _FakeDB:
    """Devolve a linha Business sem Postgres; captura as SQL executadas."""

    def __init__(self):
        self.statements = []

    def execute(self, stmt, params=None):
        self.statements.append(str(stmt))
        return _FakeResult(BUSINESS_ROW)


@pytest.fixture
def sso(monkeypatch):
    monkeypatch.setenv("MD_AUTOSINAPI_SSO_SECRET", SECRET)
    monkeypatch.setenv("MD_PUBLIC_URL", "https://mensagem.mundoaec.com")
    db = _FakeDB()
    app.dependency_overrides[get_saas_db] = lambda: db
    app.dependency_overrides[verify_admin_token] = lambda: None
    yield TestClient(app), db
    app.dependency_overrides.pop(get_saas_db, None)
    app.dependency_overrides.pop(verify_admin_token, None)


def _hmac(claims: str) -> str:
    return hmac.new(SECRET.encode(), claims.encode(), hashlib.sha256).hexdigest()


# ── emissor portal ───────────────────────────────────────────────────────────

def test_portal_handoff_envelope(sso):
    client, _ = sso
    resp = client.post(
        "/api/v1/public/portal/message-dispatcher-sso",
        headers={"X-API-KEY": "chave-de-teste-sem-valor-real"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"action", "method", "fields", "plan_slug"}
    assert body["method"] == "POST"
    assert body["action"] == "https://mensagem.mundoaec.com/admin/sso/autosinapi"
    assert body["plan_slug"] == "business"
    assert resp.headers.get("cache-control") == "no-store"


def test_portal_fields_names_are_the_contract(sso):
    """NOMES dos fields — o que o receptor lê no POST. Mudou aqui, vermelho."""
    client, _ = sso
    fields = client.post(
        "/api/v1/public/portal/message-dispatcher-sso",
        headers={"X-API-KEY": "chave-de-teste-sem-valor-real"},
    ).json()["fields"]
    assert list(fields) == PORTAL_FIELDS


def test_portal_assertion_is_claims_signature_and_verifies(sso):
    client, _ = sso
    body = client.post(
        "/api/v1/public/portal/message-dispatcher-sso",
        headers={"X-API-KEY": "chave-de-teste-sem-valor-real"},
    ).json()
    fields = body["fields"]

    claims, sep, embedded = fields["sso_assertion"].rpartition("|")
    assert sep, "sso_assertion precisa ser claims|signature"
    parts = claims.split("|")
    assert len(parts) == CLAIMS_PORTAL_LEN
    assert parts[0] == fields["email"]
    assert parts[5] == fields["jti"]
    assert parts[6] == fields["timestamp"]
    assert parts[7] == fields["expires_at"]

    # assinatura independente e verificável — é assim que o receptor valida.
    assert embedded == fields["signature"]
    assert hmac.compare_digest(embedded, _hmac(claims))

    issued_at = int(parts[6])
    assert abs(int(time.time()) - issued_at) <= 300
    assert int(parts[7]) == issued_at + 300


def test_portal_handoff_never_carries_a_raw_key(sso):
    """Invariante STORY-GW-043: nenhum plaintext de key no handoff."""
    raw = "chave-de-teste-sem-valor-real"
    client, _ = sso
    body = client.post(
        "/api/v1/public/portal/message-dispatcher-sso",
        headers={"X-API-KEY": raw},
    )
    assert raw not in body.text


def test_portal_sql_gates_business_and_never_reads_key_value(sso):
    client, db = sso
    client.post(
        "/api/v1/public/portal/message-dispatcher-sso",
        headers={"X-API-KEY": "chave-de-teste-sem-valor-real"},
    )
    sql = " ".join(db.statements)
    # plano Business é garantido NA EMISSÃO — é o gate que o receptor herda.
    assert "p.slug LIKE 'business%'" in sql
    assert "k.key_hash = crypt(" in sql
    assert "key_value" not in sql


# ── emissor admin ────────────────────────────────────────────────────────────

def test_admin_handoff_envelope_and_fields(sso):
    client, _ = sso
    resp = client.get("/api/v1/admin/messages/sso/11111111-1111-1111-1111-111111111111")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"action", "method", "fields", "plan_slug"}
    assert list(body["fields"]) == ADMIN_FIELDS
    assert resp.headers.get("cache-control") == "no-store"


def test_admin_assertion_claims_len_and_signature(sso):
    client, _ = sso
    fields = client.get(
        "/api/v1/admin/messages/sso/11111111-1111-1111-1111-111111111111"
    ).json()["fields"]
    claims, sep, embedded = fields["sso_assertion"].rpartition("|")
    assert sep
    parts = claims.split("|")
    assert len(parts) == CLAIMS_ADMIN_LEN
    assert parts[0] == fields["email"]
    assert parts[5] == fields["timestamp"]
    assert hmac.compare_digest(embedded, _hmac(claims))
    assert embedded == fields["signature"]
    assert abs(int(time.time()) - int(parts[5])) <= 300


def test_admin_sql_gates_business(sso):
    client, db = sso
    client.get("/api/v1/admin/messages/sso/11111111-1111-1111-1111-111111111111")
    sql = " ".join(db.statements)
    assert "p.slug LIKE 'business%'" in sql
