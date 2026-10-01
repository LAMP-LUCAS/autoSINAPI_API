"""Os relatórios de uso/devolutiva de custo não podem contar tráfego E2E.

A migration 018 criou `saas.clients.is_test` exatamente para isolar clientes
de teste/integração (E2E do validador, provisionamentos de smoke) do funil
real, e a listagem de assinaturas já expõe o sinal — mas os endpoints de
USO (`/admin/usage/summary`, `/admin/products/usage`) somavam tudo, então
as contagens de requisições/clientes ficavam infladas por tráfego de teste
(ex.: 181 keys revogadas do e2e-validacao).

Estes testes fixam que toda agregação sobre `saas.usage_logs` exclui linhas
cujo cliente está marcado `is_test` (cliente ausente/anon continua contando).
"""
from api import admin_crm


class _Result:
    def __init__(self, rows=None):
        self._rows = rows or []

    def mappings(self):
        return self

    def first(self):
        return self._rows[0] if self._rows else {}

    def all(self):
        return self._rows

    def scalar_one(self):
        return 0


class _DB:
    def __init__(self):
        self.queries = []

    def execute(self, stmt, params=None):
        q = str(stmt)
        self.queries.append(q)
        return _Result([{}])


def _assert_excludes_test(queries):
    usage_queries = [q for q in queries if "FROM saas.usage_logs" in q]
    assert usage_queries, "nenhuma query sobre saas.usage_logs capturada"
    for q in usage_queries:
        assert "saas.clients" in q and "is_test" in q, (
            "agregação de uso sem exclusão de clientes is_test: relatório "
            "contamina tráfego E2E — ex.: " + q[:120]
        )
        assert "NOT COALESCE" in q, (
            "a exclusão precisa ser NOT COALESCE(...): cliente sem vínculo "
            "(anon) NÃO pode ser descartado por acidente"
        )


def test_usage_summary_todas_as_agregacoes_excluem_is_test():
    db = _DB()
    admin_crm.usage_summary(days=30, db=db)
    assert len(db.queries) >= 5, "usage_summary deve executar 5 agregações"
    _assert_excludes_test(db.queries)


def test_products_usage_exclui_is_test():
    db = _DB()
    admin_crm.products_usage(days=30, db=db)
    _assert_excludes_test(db.queries)


def test_dashboard_kpis_de_uso_excluem_is_test():
    """usage_24h/usage_30d do dashboard são relatório — não podem contar E2E.

    (clients_test/leads_test são stats de consciência e continuam visíveis.)
    """
    db = _DB()
    admin_crm.dashboard(db=db)
    usage_subqueries = [q for q in db.queries
                        if "usage_24h" in q or "usage_30d" in q]
    assert usage_subqueries, "KPIs de uso do dashboard ausentes"
    for q in usage_subqueries:
        assert q.count("is_test") >= 2, (
            "usage_24h/usage_30d devem excluir clientes is_test (2 ocorrências)"
        )
        assert "NOT COALESCE" in q


def test_clausula_e_ancorada_na_subquery_correlata():
    """A cláusula é NOT COALESCE(subquery, false) — só remove `is_test=true`.

    - cliente real (is_test=false)  → subquery false → NOT false = true → conta
    - cliente teste (is_test=true)  → subquery true  → NOT true  = false → fora
    - sem client_id (anon)          → subquery NULL  → COALESCE  → false → conta
    """
    frag = admin_crm._EXCLUDE_TEST_USAGE
    assert "NOT COALESCE" in frag, "sem NOT COALESCE, anon (NULL) seria descartado"
    assert "is_test" in frag and "saas.clients" in frag
    assert "saas.usage_logs.client_id" in frag, "subquery deve correlacionar por client_id"
    assert "false)" in frag, "COALESCE precisa ter default false para manter anon"
