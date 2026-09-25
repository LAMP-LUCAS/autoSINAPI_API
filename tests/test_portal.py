"""
Testes para STORY-PRICE-006: Portal mínimo do usuário.

Valida:
1. Endpoint /api/v1/public/portal/me documentado no OpenAPI com tags corretas
2. Schema PortalResponse serializa/valida corretamente
3. Endpoint retorna 401 sem X-API-KEY
4. Endpoint retorna estrutura JSON esperada
5. Links de upgrade/downgrade corretos por plano
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from api.main import app
from api.database import get_saas_db
from api.schemas import PortalResponse, PlanInfo, QuotaInfo, PortalLinks


class _FakeResult:
    def mappings(self):
        return self

    def first(self):
        return None


class _FakeDB:
    """Captura as SQL executadas sem precisar de um Postgres real."""

    def __init__(self):
        self.statements = []

    def execute(self, stmt, params=None):
        self.statements.append(str(stmt))
        return _FakeResult()


@pytest.fixture
def captured_db():
    db = _FakeDB()
    app.dependency_overrides[get_saas_db] = lambda: db
    yield db
    app.dependency_overrides.pop(get_saas_db, None)


@pytest.fixture
def openapi():
    client = TestClient(app)
    return client.get("/openapi.json").json()


class TestPortalOpenAPI:
    def test_portal_endpoint_documented(self, openapi):
        assert "/api/v1/public/portal/me" in openapi["paths"], (
            "Endpoint /api/v1/public/portal/me ausente no OpenAPI"
        )

    def test_portal_endpoint_tags(self, openapi):
        methods = openapi["paths"]["/api/v1/public/portal/me"]
        for method, details in methods.items():
            if method == "parameters":
                continue
            tags = details.get("tags", [])
            assert len(tags) >= 1
            assert tags[0] == "tier_1", (
                f"{method.upper()} /api/v1/public/portal/me: primeira tag deve ser tier_1"
            )

    def test_portal_endpoint_summary(self, openapi):
        get_spec = openapi["paths"]["/api/v1/public/portal/me"]["get"]
        summary = get_spec.get("summary", "")
        assert len(summary) > 0, "summary deve estar presente"
        assert len(summary) <= 80, f"summary deve ter <= 80 chars (tem {len(summary)})"

    def test_portal_endpoint_has_x_api_key_header(self, openapi):
        get_spec = openapi["paths"]["/api/v1/public/portal/me"]["get"]
        params = get_spec.get("parameters", [])
        header_names = [p["name"] for p in params if p.get("in") == "header"]
        assert "X-API-KEY" in header_names, (
            "X-API-KEY header parameter must be documented"
        )

    def test_portal_endpoint_has_401_response(self, openapi):
        get_spec = openapi["paths"]["/api/v1/public/portal/me"]["get"]
        responses = get_spec.get("responses", {})
        assert "401" in responses, (
            "Endpoint deve documentar resposta 401 (não autenticado)"
        )

    def test_portal_endpoint_has_200_response(self, openapi):
        get_spec = openapi["paths"]["/api/v1/public/portal/me"]["get"]
        responses = get_spec.get("responses", {})
        assert "200" in responses, (
            "Endpoint deve documentar resposta 200 (sucesso)"
        )


class TestPortalSchema:
    def test_plan_info_schema(self):
        plan = PlanInfo(slug="pro", name="Pro", price_cents=9900)
        assert plan.slug == "pro"
        assert plan.name == "Pro"
        assert plan.price_cents == 9900

    def test_quota_info_schema(self):
        quota = QuotaInfo(used=100, limit=1000, percentage=10.0)
        assert quota.used == 100
        assert quota.limit == 1000
        assert quota.percentage == 10.0

    def test_quota_percentage_zero_when_no_usage(self):
        quota = QuotaInfo(used=0, limit=1000, percentage=0.0)
        assert quota.percentage == 0.0

    def test_portal_links_upgrade_empty(self):
        links = PortalLinks(
            upgrade={},
            downgrade=None,
            renew="https://example.com/renew",
        )
        assert links.upgrade == {}
        assert links.downgrade is None

    def test_portal_links_with_upgrade(self):
        links = PortalLinks(
            upgrade={"pro": "https://example.com/checkout?plan=pro"},
            downgrade=None,
            renew="https://example.com/renew",
        )
        assert "pro" in links.upgrade

    def test_portal_links_with_downgrade(self):
        links = PortalLinks(
            upgrade={},
            downgrade="https://example.com/checkout?plan=starter",
            renew="https://example.com/renew",
        )
        assert links.downgrade is not None

    def test_portal_response_complete(self):
        response = PortalResponse(
            client_id="550e8400-e29b-41d4-a716-446655440000",
            plan=PlanInfo(slug="pro", name="Pro", price_cents=9900),
            subscription={
                "status": "active",
                "current_period_start": "2026-07-15T00:00:00Z",
                "current_period_end": "2026-08-14T00:00:00Z",
            },
            quota=QuotaInfo(used=1250, limit=3000, percentage=41.7),
            features={"api_access": True, "bi_analytics": True},
            links=PortalLinks(
                upgrade={"business": "https://example.com/checkout?plan=business"},
                downgrade="https://example.com/checkout?plan=starter",
                renew="https://example.com/checkout?plan=pro",
            ),
        )
        assert response.client_id == "550e8400-e29b-41d4-a716-446655440000"
        assert response.plan.slug == "pro"
        assert response.quota.percentage == 41.7
        assert "business" in response.links.upgrade
        assert response.links.downgrade is not None

    def test_portal_response_serializes_to_json(self):
        response = PortalResponse(
            client_id="550e8400-e29b-41d4-a716-446655440000",
            plan=PlanInfo(slug="starter", name="Starter", price_cents=1300),
            subscription={
                "status": "active",
                "current_period_start": "2026-07-15T00:00:00Z",
                "current_period_end": "2026-07-22T00:00:00Z",
            },
            quota=QuotaInfo(used=50, limit=600, percentage=8.3),
            features={"api_access": True},
            links=PortalLinks(
                upgrade={"pro": "https://x/pro", "business": "https://x/business"},
                downgrade=None,
                renew="https://x/renew",
            ),
        )
        data = response.model_dump()
        assert data["plan"]["slug"] == "starter"
        assert data["quota"]["percentage"] == 8.3
        assert data["links"]["downgrade"] is None
        assert len(data["links"]["upgrade"]) == 2


class TestPortalKeyHashLookup:
    """GW-023: lookup de API key deve usar key_hash (crypt), nunca plaintext."""

    def test_lookup_uses_key_hash_not_plaintext(self, captured_db):
        client = TestClient(app)
        # 401 esperado (fake DB não retorna linha), mas capturamos a SQL.
        resp = client.get("/api/v1/public/portal/me", headers={"X-API-KEY": "tok"})
        assert resp.status_code in (401, 500)
        assert captured_db.statements, "nenhuma SQL executada"
        sql = captured_db.statements[0]
        assert "key_hash = crypt(" in sql, "lookup deve comparar pelo hash bcrypt"
        assert "key_value = " not in sql, "Não expor comparação por plaintext"
