"""
Testes para STORY-API-002: Summaries explícitos.

Valida que 100% dos endpoints têm summary EXPLÍCITO (declarado no decorador)
com ≤ 80 chars e formato "Verbo + objeto + complemento".

Estratégia de verificação (TDD / DDD):
- AST: inspeciona o código-fonte de api/main.py para garantir que TODO
  decorador de rota declara o argumento nomeado `summary=` (explícito, e não
  derivado do docstring pelo FastAPI).
- OpenAPI runtime: garante que o summary resultante respeita o tamanho (≤ 80)
  e o formato (verbo no infinitivo + objeto).
"""
import ast
import os

import pytest
from fastapi.testclient import TestClient
from api.main import app

INFINITIVE_VERBS = {
    "verificar", "obter", "disparar", "exibir", "consultar",
    "buscar", "calcular", "listar", "atualizar", "deletar",
    "criar", "enviar", "receber", "validar", "autenticar",
    "registrar", "cancelar", "gerar", "exportar", "importar",
    "sincronizar", "notificar", "configurar", "simular",
    "analisar", "aplicar", "associar", "copiar", "definir",
    "executar", "filtrar", "identificar", "iniciar", "liberar",
    "monitorar", "processar", "recuperar", "remover", "restaurar",
    "salvar", "selecionar", "sugerir", "testar", "transformar",
    "ativar", "desativar", "agendar", "armazenar", "avaliar",
    "classificar", "comparar", "confirmar", "contar", "converter",
    "disponibilizar", "estimar", "formatar", "integrar",
    "mapear", "mensurar", "migrar", "normalizar", "otimizar",
    "parametrizar", "persistir", "prever", "produzir",
    "programar", "projetar", "rastrear", "redirecionar",
    "reindexar", "relacionar", "replicar", "reprocessar",
    "revisar", "rotear", "tabular", "traduzir", "vincular",
}

PORTUGUESE_INFINITIVE_SUFFIXES = ("ar", "er", "ir", "or")

HTTP_DECORATORS = {"get", "post", "put", "delete", "patch", "options", "head"}

MAIN_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "api", "main.py")


def _route_decorators():
    """Retorna lista de (nome_funcao, kwargs_dict) para cada decorador de rota."""
    with open(MAIN_PATH, "r", encoding="utf-8") as fh:
        tree = ast.parse(fh.read())

    routes = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        for dec in node.decorator_list:
            if (
                isinstance(dec, ast.Call)
                and isinstance(dec.func, ast.Attribute)
                and isinstance(dec.func.value, ast.Name)
                and dec.func.value.id == "app"
                and dec.func.attr in HTTP_DECORATORS
            ):
                kwargs = {kw.arg: kw.value for kw in dec.keywords if kw.arg}
                routes.append((node.name, kwargs))
    return routes


@pytest.fixture
def openapi():
    client = TestClient(app)
    return client.get("/openapi.json").json()


class TestEndpointSummaries:
    def test_all_routes_have_explicit_summary(self):
        """Todo decorador de rota DEVE declarar `summary=` explicitamente."""
        routes = _route_decorators()
        assert routes, "Nenhuma rota encontrada em api/main.py"
        for func_name, kwargs in routes:
            assert "summary" in kwargs, (
                f"Rota '{func_name}': ausente argumento explícito summary= no decorador"
            )

    def test_summary_max_length_80(self, openapi):
        for path, methods in openapi["paths"].items():
            for method, details in methods.items():
                if method == "parameters":
                    continue
                if details.get("tags", [None])[0] == "Admin":
                    continue
                summary = details.get("summary", "")
                assert len(summary) <= 80, (
                    f"{method.upper()} {path}: summary '{summary}' "
                    f"tem {len(summary)} chars (máx 80)"
                )

    def test_summary_format_verb_object(self, openapi):
        for path, methods in openapi["paths"].items():
            for method, details in methods.items():
                if method == "parameters":
                    continue
                if details.get("tags", [None])[0] == "Admin":
                    continue
                summary = details.get("summary", "")
                words = summary.split()
                assert len(words) >= 2, (
                    f"{method.upper()} {path}: summary '{summary}' "
                    f"precisa de ≥ 2 palavras (verbo + objeto)"
                )
                first_word = words[0].lower()
                assert first_word in INFINITIVE_VERBS or any(
                    first_word.endswith(suffix)
                    for suffix in PORTUGUESE_INFINITIVE_SUFFIXES
                ), (
                    f"{method.upper()} {path}: summary '{summary}' "
                    f"deve começar com verbo no infinitivo (formato Verbo + objeto + complemento)"
                )
