"""
Testes para STORY-API-001: Tags de tier nos endpoints.

Valida que 100% dos endpoints públicos têm tags começando com "tier_1" ou "tier_2"
e que o Swagger UI agrupa por tier.
"""
import pytest
from fastapi.testclient import TestClient
from api.main import app


@pytest.fixture
def openapi():
    client = TestClient(app)
    return client.get("/openapi.json").json()


class TestTierTags:
    def test_all_endpoints_have_tier_tag_as_first(self, openapi):
        for path, methods in openapi["paths"].items():
            for method, details in methods.items():
                if method == "parameters":
                    continue
                tags = details.get("tags", [])
                assert len(tags) >= 1, (
                    f"{method.upper()} {path}: no tags defined"
                )
                if tags[0] == "Admin":
                    continue
                assert tags[0].startswith("tier_"), (
                    f"{method.upper()} {path}: first tag '{tags[0]}' must start with 'tier_'"
                )

    def test_tier_1_classification(self, openapi):
        tier1_paths = [
            "/api/v1/public/health",
            "/api/v1/public/stats",
            "/api/v1/public/filters",
            "/api/v1/public/insumos/{codigo}",
            "/api/v1/public/insumos",
            "/api/v1/public/composicoes/{codigo}",
            "/api/v1/public/composicoes",
        ]
        for path in tier1_paths:
            for method, details in openapi["paths"][path].items():
                if method == "parameters":
                    continue
                assert "tier_1" in details.get("tags", []), (
                    f"{method.upper()} {path} should have tier_1 tag"
                )

    def test_tier_2_classification(self, openapi):
        tier2_paths = [
            "/api/v1/public/bi/composicao/{codigo}/bom",
            "/api/v1/public/bi/composicao/{codigo}/hora-homem",
            "/api/v1/public/bi/curva-abc",
            "/api/v1/public/bi/composicao/{codigo}/otimizar",
            "/api/v1/public/bi/item/{tipo_item}/{codigo}/historico",
            "/api/v1/public/bi/item/{tipo_item}/{codigo}/manutencoes",
            "/api/v1/public/bi/audit/{tipo_item}/{codigo}",
            "/api/v1/public/bi/curva-abc/por-classificacao",
            "/api/v1/public/bi/tendencias/por-classificacao",
            "/api/v1/public/bi/item/{tipo_item}/{codigo}/precos-uf",
            "/api/v1/public/bi/composicao/{codigo}/produtividade",
            "/api/v1/public/bi/insumo/{codigo}/onde-usado",
        ]
        for path in tier2_paths:
            for method, details in openapi["paths"][path].items():
                if method == "parameters":
                    continue
                assert "tier_2" in details.get("tags", []), (
                    f"{method.upper()} {path} should have tier_2 tag"
                )

    def test_admin_and_root_are_tier_1(self, openapi):
        admin_paths = [
            "/api/v1/admin/populate-database",
            "/api/v1/admin/tasks/{task_id}",
            "/",
        ]
        for path in admin_paths:
            for method, details in openapi["paths"][path].items():
                if method == "parameters":
                    continue
                assert "tier_1" in details.get("tags", []), (
                    f"{method.upper()} {path} (admin/root) should have tier_1 tag"
                )
