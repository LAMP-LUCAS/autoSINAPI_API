"""
Testes para STORY-INFRA-004: Geração automatizada da OpenAPI spec.

Valida, em nível de unidade (in-process, sem Docker), que o schema OpenAPI
produzido por `app.openapi()` satisfaz as SPEC-RULE de documentação que a
spec versionada (SSOT em stacks/autosinapi/docs/openapi.yaml) deve respeitar
antes de ser consolidada no CI (STORY-INFRA-003 / Regra 6.1).

Este teste é o portão TDD rápido: garante que qualquer spec gerada pelo
`scripts/generate_openapi.sh` será conforme, quebrando o build antes mesmo de
subir o container de staging.

Regras cobertas (SPEC-RULE-audit.md):
  - 1.1: primeira tag do endpoint = tier_1/tier_2/tier_3
  - 2.1: summary obrigatório e <= 80 chars
  - 2.2: params de domínio finito usam `examples` (plural), nunca `example` (singular)
  - 2.4: securityScheme ApiKeyAuth (X-API-KEY) documentado
  - 2.5: códigos 401/402/429 documentados nas respostas
  - 2.6: spec versionada (openapi 3.1.0) com info.title e paths não-vazios
  - Hygiene: operationId presente em toda operação (rastreabilidade)
"""
import re

import pytest
from fastapi.testclient import TestClient
from api.main import app


TIER_RE = re.compile(r"^tier_[123]$")


@pytest.fixture
def openapi():
    client = TestClient(app)
    return client.get("/openapi.json").json()


def _iter_operations(openapi):
    """Yield (path, method, details) for every HTTP operation."""
    for path, methods in openapi.get("paths", {}).items():
        for method, details in methods.items():
            if method == "parameters":
                continue
            if not isinstance(details, dict):
                continue
            yield path, method, details


# --- Regra 2.6: estrutura da spec versionada (SSOT) ---


class TestSpecStructure:
    def test_openapi_version(self, openapi):
        assert openapi.get("openapi", "").startswith("3.")

    def test_info_title_present(self, openapi):
        assert openapi.get("info", {}).get("title") == "AutoSINAPI API"

    def test_has_paths(self, openapi):
        assert len(openapi.get("paths", {})) > 0

    def test_components_present(self, openapi):
        # custom_openapi() injeta components.securitySchemes; a spec gerada
        # deve preservá-los para o botão "Authorize" do Swagger.
        assert "components" in openapi


# --- Regra 1.1: primeira tag = tier ---


class TestTierTags:
    def test_first_tag_is_tier_or_admin(self, openapi):
        for path, method, details in _iter_operations(openapi):
            tags = details.get("tags", [])
            assert len(tags) >= 1, f"{method.upper()} {path}: sem tags"
            # Admin/CRM operations are not public catalog tiers; they retain
            # their own explicit tag instead of being mislabeled as tier_1.
            if tags[0] == "Admin":
                continue
            assert TIER_RE.match(tags[0]), (
                f"{method.upper()} {path}: primeira tag '{tags[0]}' "
                f"deve casar ^tier_[123]$ (SPEC-RULE 1.1)"
            )

    def test_all_operations_have_operation_id(self, openapi):
        for path, method, details in _iter_operations(openapi):
            assert details.get("operationId"), (
                f"{method.upper()} {path}: operationId ausente (rastreabilidade)"
            )


# --- Regra 2.1: summary obrigatório e <= 80 chars ---


class TestSummary:
    def test_summary_present_and_bounded(self, openapi):
        for path, method, details in _iter_operations(openapi):
            summary = details.get("summary")
            assert summary, f"{method.upper()} {path}: summary ausente (SPEC-RULE 2.1)"
            assert len(summary) <= 80, (
                f"{method.upper()} {path}: summary com {len(summary)} chars "
                f"(> 80, SPEC-RULE 2.1)"
            )


# --- Regra 2.2: examples (plural), nunca example (singular) ---


class TestParameterExamples:
    FINITE_DOMAIN = {"uf", "regime", "data_referencia", "data_fim"}

    def test_finite_domain_params_use_examples_plural(self, openapi):
        for path, method, details in _iter_operations(openapi):
            params = details.get("parameters", [])
            # Parâmetros de caminho também podem vir do nível do path.
            params += openapi["paths"][path].get("parameters", [])
            for p in params:
                if p.get("name") in self.FINITE_DOMAIN:
                    # Não pode usar a forma singlar depreciada.
                    assert "example" not in p, (
                        f"{method.upper()} {path}: param '{p['name']}' usa "
                        f"`example=` singular (depreciado, SPEC-RULE 2.2)"
                    )
                    # Deve expor a forma plural (media type Example válido).
                    examples = p.get("examples") or (
                        p.get("schema", {}).get("examples")
                    )
                    assert examples, (
                        f"{method.upper()} {path}: param '{p['name']}' sem "
                        f"`examples` plural (SPEC-RULE 2.2)"
                    )


# --- Regra 2.4: securityScheme ApiKeyAuth (X-API-KEY) ---


class TestAuthScheme:
    def test_apikey_auth_scheme_documented(self, openapi):
        schemes = openapi.get("components", {}).get("securitySchemes", {})
        assert "ApiKeyAuth" in schemes, "securityScheme ApiKeyAuth ausente (SPEC-RULE 2.4)"
        scheme = schemes["ApiKeyAuth"]
        assert scheme.get("type") == "apiKey"
        assert scheme.get("in") == "header"
        assert scheme.get("name") == "X-API-KEY"


# --- Regra 2.5: códigos 401/402/429 documentados ---


class TestErrorResponses:
    # Endpoints admin/root documentam 401/402/429; públicos documentam 429.
    def test_auth_errors_documented_somewhere(self, openapi):
        documented = set()
        for _path, _method, details in _iter_operations(openapi):
            documented.update(int(code) for code in details.get("responses", {}))
        # Pelo menos os códigos de erro do Kong devem aparecer na spec.
        assert 429 in documented, "429 (rate limit) não documentado (SPEC-RULE 2.5)"
        assert 401 in documented, "401 (api key) não documentado (SPEC-RULE 2.5)"
        assert 402 in documented, "402 (subscription) não documentado (SPEC-RULE 2.5)"
