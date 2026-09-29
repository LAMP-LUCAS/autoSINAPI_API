"""Contrato do texto SSOT de autenticação/rate-limit exibido no Swagger.

`_AUTH_DOCS` é o que o usuário lê no Swagger e o que é espelhado nos
artefatos openapi (fallback do portal e `stacks/autosinapi/docs/openapi.yaml`).
As figuras vêm do Kong (`kong/plans.yaml` — guard cruzado na raiz do monorepo,
`automation/scripts/test_openapi_rate_limit_guard.py`); aqui se fixa a
COERÊNCIA INTERNA entre as seções e a orientação de cliente:

  - defeito 2026-09-29: `_MCP_SECTION` dizia "60 req/mês" enquanto
    `_AUTH_SECTION` dizia "60 req/min, 1.000 req/mês" — o Swagger se
    contradizia na própria página (não existe plano de 60 req/mês);
  - a integração MCP não tem OAuth (o gateway aceita só `X-API-KEY`) e o
    mesmo `/sse` atende os dois transportes (comportamento verificado por
    `SistemaServerLight/automation/scripts/verify_mcp_docs_facts.py`);
  - o Developer Portal é a SSOT dos snippets de cliente (`/dev/api#mcp-agents`).
"""
from api.main import _AUTH_DOCS, _AUTH_SECTION, _MCP_SECTION

DEMO_FIGURE = "60 req/min, 1.000 req/mês"


def test_auth_section_cites_demo_figure_correctly():
    assert DEMO_FIGURE in _AUTH_SECTION


def test_mcp_section_cites_same_demo_figure():
    """As duas seções precisam citar a MESMA figura — sem contradição."""
    assert DEMO_FIGURE in _MCP_SECTION


def test_no_monthly_only_demo_figure():
    """`60 req/mês` isolado (sem `req/min` no contexto) é contradição.

    Não existe plano de 60 por mês: o free é 60 req/min E 1.000 req/mês.
    """
    assert "60 req/mês" not in _AUTH_DOCS


def test_plan_figures_documented_in_auth_section():
    assert "**Starter**: 600 req/min" in _AUTH_SECTION
    assert "**Pro**: 3.000 req/min" in _AUTH_SECTION
    assert "**Business**: 10.000 req/min" in _AUTH_SECTION


def test_mcp_section_documents_oauth_unsupported():
    """OAuth não existe no gateway — aviso explícito contra `opencode mcp auth`."""
    assert "OAuth" in _MCP_SECTION
    assert "opencode mcp auth" in _MCP_SECTION


def test_mcp_section_points_to_portal_snippets():
    """Portal é a SSOT dos snippets — o Swagger não duplica config de cliente."""
    assert "/dev/api#mcp-agents" in _MCP_SECTION


def test_mcp_section_keeps_both_transports():
    """Comportamento medido: `/sse` atende streamable-http (POST) e SSE
    legado (GET); `POST /mcp` → `308 /sse` — o título precisa refletir os dois.
    """
    assert "Streamable HTTP / SSE" in _MCP_SECTION


def test_auth_docs_consists_of_the_four_sections():
    from api.main import _ERROR_SECTION, _TIER_SECTION

    assert _AUTH_DOCS == _AUTH_SECTION + _ERROR_SECTION + _TIER_SECTION + _MCP_SECTION
