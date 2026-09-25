"""
Testes para STORY-API-005: Documentação consolidada de autenticação e erros.

Valida os 3 critérios de aceitação via OpenAPI runtime (/openapi.json) e inspeção
das constantes de contrato de erro do gateway:

1. Botão "Authorize" com `X-API-KEY` no Swagger
   → `components.securitySchemes.ApiKeyAuth` (type=apiKey, in=header, name=X-API-KEY).
2. Rate limits 600 / 3.000 / 10.000 req/min visíveis
   → presentes em `info.description` (por plano Starter/Pro/Business).
3. Erros 401 / 402 / 429 documentados
   → presentes em `info.description` e refletidos em `responses` dos endpoints.

Estratégia (TDD / DDD):
- OpenAPI runtime: garante que o contrato entregue ao cliente (Swagger) expõe
  auth, rate limits e erros de forma consolidada.
- Inspeção das constantes `_AUTH_RESPONSES` / `_RATE_LIMIT_RESPONSE`: garante que o
  contrato de erro do gateway Kong é a SSOT reutilizada (coesão/DRY) e não duplicada
  inline por endpoint.
"""
import pytest
from fastapi.testclient import TestClient
from api.main import app, _AUTH_RESPONSES, _RATE_LIMIT_RESPONSE, _normalize_mcp_public_url

# SSOT canônico dos rate limits por plano (espelha stacks/autosinapi/kong/plans.yaml).
# Mantido aqui apenas para validação de documentação; a API NÃO importa de `stacks/`.
EXPECTED_RATE_LIMITS = {
    "Starter": "600",
    "Pro": "3.000",
    "Business": "10.000",
}

AUTH_ENDPOINTS = [
    "/api/v1/admin/populate-database",
    "/api/v1/admin/tasks/{task_id}",
    "/",
]


@pytest.fixture
def openapi():
    client = TestClient(app)
    return client.get("/openapi.json").json()


class TestAuthErrorsDocs:
    # ── Critério 1: Botão Authorize (X-API-KEY) ──
    def test_authorize_button_x_api_key(self, openapi):
        schemes = openapi.get("components", {}).get("securitySchemes", {})
        assert "ApiKeyAuth" in schemes, (
            "SecurityScheme 'ApiKeyAuth' ausente → botão Authorize não aparece no Swagger"
        )
        scheme = schemes["ApiKeyAuth"]
        assert scheme.get("type") == "apiKey", (
            f"ApiKeyAuth.type deve ser 'apiKey' (recebido: {scheme.get('type')})"
        )
        assert scheme.get("in") == "header", (
            f"ApiKeyAuth.in deve ser 'header' (recebido: {scheme.get('in')})"
        )
        assert scheme.get("name") == "X-API-KEY", (
            f"ApiKeyAuth.name deve ser 'X-API-KEY' (recebido: {scheme.get('name')})"
        )

    # ── Critério 2: Rate limits 600/3000/10000 visíveis ──
    def test_rate_limits_visible_per_plan(self, openapi):
        desc = openapi.get("info", {}).get("description", "")
        assert desc, "info.description vazio — documentação de auth não encontrada"
        for plan, limit in EXPECTED_RATE_LIMITS.items():
            assert plan in desc, (
                f"Plano '{plan}' não documentado em info.description"
            )
            assert limit in desc, (
                f"Rate limit '{limit}' do plano '{plan}' não visível em info.description"
            )

    def test_mcp_url_normalizer_accepts_base_or_sse_endpoint(self):
        assert _normalize_mcp_public_url("https://mcp.example.test/") == "https://mcp.example.test"
        assert _normalize_mcp_public_url("https://mcp.example.test/sse/") == "https://mcp.example.test"
        assert _normalize_mcp_public_url("https://mcp.example.test/sse") == "https://mcp.example.test"

    def test_public_contract_is_current_and_environment_driven(self, openapi):
        desc = openapi.get("info", {}).get("description", "")
        assert "60 req/min" in desc
        assert "1.000 req/mês" in desc
        assert "mcp.autosinapi.mundoaec.com" not in desc
        assert "sinapi_search" in desc
        assert "transporte MCP exige `X-API-KEY`" in desc
        assert "modo anônimo" in desc
        assert "PUBLIC_MCP_AUTOSINAPI_URL" in desc

    # ── Critério 3: Erros 401/402/429 documentados ──
    def test_error_codes_documented_in_description(self, openapi):
        desc = openapi.get("info", {}).get("description", "").lower()
        assert "401" in desc and "api key" in desc, (
            "Código 401 (API key ausente/inválida) não documentado em info.description"
        )
        assert "402" in desc and ("assinatura" in desc or "subscription" in desc), (
            "Código 402 (assinatura inativa/expirada) não documentado em info.description"
        )
        assert "429" in desc and "rate limit" in desc, (
            "Código 429 (rate limit excedido) não documentado em info.description"
        )

    # ── Contrato de erro do gateway (SSOT reutilizada, não duplicada) ──
    def test_auth_responses_contract(self):
        assert set(_AUTH_RESPONSES.keys()) >= {401, 402, 429}, (
            f"_AUTH_RESPONSES deve documentar 401/402/429 "
            f"(recebido: {sorted(_AUTH_RESPONSES.keys())})"
        )
        assert set(_RATE_LIMIT_RESPONSE.keys()) == {429}, (
            f"_RATE_LIMIT_RESPONSE deve documentar apenas 429 "
            f"(recebido: {sorted(_RATE_LIMIT_RESPONSE.keys())})"
        )

    # ── Endpoints admin/root expõem 401/402/429 (operação nível) ──
    def test_admin_endpoints_surface_auth_responses(self, openapi):
        # No OpenAPI JSON os códigos de resposta são strings ("401"), não ints.
        for path in AUTH_ENDPOINTS:
            methods = openapi["paths"][path]
            for method, details in methods.items():
                if method == "parameters":
                    continue
                responses = details.get("responses", {})
                for code in ("401", "402", "429"):
                    assert code in responses, (
                        f"{method.upper()} {path}: resposta {code} ausente "
                        f"(esperado em endpoints protegidos pelo gateway)"
                    )

    # ── Endpoints públicos expõem 429 (rate limit de demonstração) ──
    def test_public_endpoints_surface_rate_limit(self, openapi):
        for path, methods in openapi["paths"].items():
            if not path.startswith("/api/v1/public/"):
                continue
            for method, details in methods.items():
                if method == "parameters":
                    continue
                assert "429" in details.get("responses", {}), (
                    f"{method.upper()} {path}: endpoint público deve documentar 429"
                )
