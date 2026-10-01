"""
Testes do self-service de chave do portal (BYOK — STORY-MCP-008).

Cobre GET/POST /api/v1/public/portal/me/api-key:
1. Documentação OpenAPI (path, tag tier_1, header X-API-KEY, summary)
2. 401 sem X-API-KEY nos dois verbos
3. GET introspecta a chave (prefixo/status) SEM expor plaintext e SEM escrita
4. POST rotaciona: revoga a anterior, emite nova (retorno único), registra
   evento de auditoria e responde com Cache-Control: no-store
5. Chave revogada: GET mostra o status; POST recusa rotação (401)

O banco é simulado (_FakeDB) capturando as statements — mesmo padrão de
tests/test_portal.py — para validar o contrato SQL sem exigir Postgres.
"""
import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.database import get_saas_db


class _FakeResult:
    def __init__(self, rows=None, scalar=None):
        self._rows = rows or []
        self._scalar = scalar

    def mappings(self):
        return self

    def first(self):
        return self._rows[0] if self._rows else None

    def scalar_one(self):
        return self._scalar


class _FakeDB:
    """Fila de resultados por statement + captura para asserções."""

    def __init__(self, queue=None):
        self.queue = list(queue or [])
        self.statements = []
        self.committed = False

    def execute(self, stmt, params=None):
        self.statements.append((str(stmt), dict(params or {})))
        if not self.queue:
            return _FakeResult()
        item = self.queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def rollback(self):
        pass

    def commit(self):
        self.committed = True

    def sqls(self):
        return " || ".join(s for s, _ in self.statements)


def _key_row(status="active"):
    return {
        "key_id": "11111111-2222-3333-4444-555555555555",
        "client_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "subscription_id": "99999999-8888-7777-6666-555555555555",
        "key_prefix": "deadbeef",
        "key_status": status,
    }


def _use(db):
    app.dependency_overrides[get_saas_db] = lambda: db


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.pop(get_saas_db, None)


# ── 1. Documentação OpenAPI ──────────────────────────────────────────────────

class TestPortalApiKeyOpenAPI:
    @pytest.fixture
    def openapi(self):
        return TestClient(app).get("/openapi.json").json()

    def test_path_documented(self, openapi):
        assert "/api/v1/public/portal/me/api-key" in openapi["paths"], (
            "path /api/v1/public/portal/me/api-key ausente no OpenAPI"
        )

    def test_get_and_post_documented(self, openapi):
        methods = openapi["paths"]["/api/v1/public/portal/me/api-key"]
        assert "get" in methods, "GET self-service ausente"
        assert "post" in methods, "POST (rotação) ausente"

    def test_first_tag_is_tier_1(self, openapi):
        for method in ("get", "post"):
            tags = openapi["paths"]["/api/v1/public/portal/me/api-key"][method].get("tags", [])
            assert tags and tags[0] == "tier_1", f"{method.upper()}: primeira tag deve ser tier_1"

    def test_summary_present_and_short(self, openapi):
        for method in ("get", "post"):
            summary = openapi["paths"]["/api/v1/public/portal/me/api-key"][method].get("summary", "")
            assert 0 < len(summary) <= 80, f"{method.upper()}: summary deve ter 1..80 chars"

    def test_x_api_key_header_documented(self, openapi):
        for method in ("get", "post"):
            params = openapi["paths"]["/api/v1/public/portal/me/api-key"][method].get("parameters", [])
            names = [p["name"] for p in params if p.get("in") == "header"]
            assert "X-API-KEY" in names, f"{method.upper()}: header X-API-KEY não documentado"

    def test_response_schema_exported(self, openapi):
        assert "PortalApiKeyResponse" in openapi.get("components", {}).get("schemas", {}), (
            "schema PortalApiKeyResponse ausente no OpenAPI"
        )


# ── 2. Autenticação ─────────────────────────────────────────────────────────

class TestPortalApiKeyAuth:
    def test_get_sem_header_401(self):
        _use(_FakeDB())
        r = TestClient(app).get("/api/v1/public/portal/me/api-key")
        assert r.status_code == 401

    def test_post_sem_header_401(self):
        _use(_FakeDB())
        r = TestClient(app).post("/api/v1/public/portal/me/api-key")
        assert r.status_code == 401

    def test_get_key_invalida_401_sem_escrita(self):
        db = _FakeDB(queue=[])  # lookup não encontra linha
        _use(db)
        r = TestClient(app).get("/api/v1/public/portal/me/api-key", headers={"X-API-KEY": "autosinapi_x"})
        assert r.status_code == 401
        assert not db.committed
        assert "INSERT" not in db.sqls() and "UPDATE" not in db.sqls()

    def test_post_key_invalida_401_sem_escrita(self):
        db = _FakeDB(queue=[])
        _use(db)
        r = TestClient(app).post("/api/v1/public/portal/me/api-key", headers={"X-API-KEY": "autosinapi_x"})
        assert r.status_code == 401
        assert not db.committed
        assert "INSERT" not in db.sqls() and "UPDATE" not in db.sqls()


# ── 3. GET: introspecção sem plaintext ───────────────────────────────────────

class TestPortalApiKeyGet:
    def test_retorna_prefixo_e_status_sem_plaintext(self):
        db = _FakeDB(queue=[_FakeResult(rows=[_key_row()])])
        _use(db)
        r = TestClient(app).get("/api/v1/public/portal/me/api-key", headers={"X-API-KEY": "autosinapi_abcd1234"})
        assert r.status_code == 200
        body = r.json()
        assert body["key_prefix"] == "deadbeef"
        assert body["status"] == "active"
        assert not body.get("api_key"), "GET jamais pode expor a chave em plaintext"

    def test_lookup_valida_contra_hash(self):
        db = _FakeDB(queue=[_FakeResult(rows=[_key_row()])])
        _use(db)
        TestClient(app).get("/api/v1/public/portal/me/api-key", headers={"X-API-KEY": "autosinapi_abcd1234"})
        lookup = db.statements[0][0]
        assert "k.key_hash = crypt(:x_api_key, k.key_hash)" in lookup, (
            "lookup deve validar o hash via crypt(), nunca comparar plaintext"
        )
        assert db.statements[0][1] == {"x_api_key": "autosinapi_abcd1234"}

    def test_get_nao_cria_nem_revoga_chaves(self):
        db = _FakeDB(queue=[_FakeResult(rows=[_key_row()])])
        _use(db)
        TestClient(app).get("/api/v1/public/portal/me/api-key", headers={"X-API-KEY": "autosinapi_abcd1234"})
        sqls = db.sqls()
        assert "INSERT INTO saas.api_keys" not in sqls, "GET não pode emitir chave"
        assert "revoked" not in sqls, "GET não pode revogar chave"
        assert not db.committed

    def test_chave_revogada_e_visivel_no_get(self):
        db = _FakeDB(queue=[_FakeResult(rows=[_key_row(status="revoked")])])
        _use(db)
        r = TestClient(app).get("/api/v1/public/portal/me/api-key", headers={"X-API-KEY": "autosinapi_abcd1234"})
        assert r.status_code == 200
        assert r.json()["status"] == "revoked"


# ── 4. POST: rotação (retorno único) ────────────────────────────────────────

class TestPortalApiKeyRotate:
    def _post(self, db):
        return TestClient(app).post(
            "/api/v1/public/portal/me/api-key", headers={"X-API-KEY": "autosinapi_oldkey1"}
        )

    def _rotate_db(self):
        return _FakeDB(queue=[
            _FakeResult(rows=[_key_row()]),   # lookup da key atual
            _FakeResult(scalar=1),            # UPDATE revoga
            _FakeResult(scalar="22222222-3333-4444-5555-666666666666"),  # INSERT RETURNING id
            _FakeResult(),                    # INSERT client_events
        ])

    def test_rotacao_retorna_nova_chave_uma_vez(self):
        db = self._rotate_db()
        _use(db)
        r = self._post(db)
        assert r.status_code == 200
        body = r.json()
        assert body["api_key"].startswith("autosinapi_"), "rotação deve devolver a nova chave"
        assert len(body["api_key"]) == 11 + 32, "formato esperado: autosinapi_ + 32 hex"
        assert body["rotated"] is True
        assert body["key_prefix"] == body["api_key"][11:19]
        assert body["status"] == "active"

    def test_rotacao_cabecalho_no_store(self):
        db = self._rotate_db()
        _use(db)
        r = self._post(db)
        assert r.headers.get("Cache-Control") == "no-store"

    def test_rotacao_revoga_anterior_emite_nova_e_registra_evento(self):
        db = self._rotate_db()
        _use(db)
        r = self._post(db)
        sqls = db.sqls()
        assert "UPDATE saas.api_keys" in sqls and "revoked" in sqls, "deve revogar a key anterior"
        assert "INSERT INTO saas.api_keys" in sqls, "deve emitir a key nova"
        assert "INSERT INTO saas.client_events" in sqls, "deve registrar evento de auditoria"
        assert db.committed, "transação deve ser commitada"

        insert_sql, insert_params = next(
            (s, p) for s, p in db.statements if "INSERT INTO saas.api_keys" in s
        )
        assert "crypt(:kv, gen_salt('bf'))" in insert_sql, "hash bcrypt obrigatório (REGRA 1)"
        new_value = insert_params["kv"]
        assert insert_params["prefix"] == new_value[11:19]
        assert new_value != "autosinapi_oldkey1", "a chave nova deve ser diferente da antiga"

        event_sql, event_params = next(
            (s, p) for s, p in db.statements if "INSERT INTO saas.client_events" in s
        )
        assert event_params["et"] == "api_key_rotated"
        assert event_params["actor"] == "portal"

    def test_rotacao_nao_devolve_plaintext_antiga(self):
        db = self._rotate_db()
        _use(db)
        r = self._post(db)
        assert "autosinapi_oldkey1" not in r.text

    def test_chave_revogada_nao_rotaciona(self):
        db = _FakeDB(queue=[_FakeResult(rows=[_key_row(status="revoked")])])
        _use(db)
        r = self._post(db)
        assert r.status_code == 401
        assert not db.committed
        assert "INSERT" not in db.sqls() and "revoked" not in db.sqls()
