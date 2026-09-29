"""
Testes de integração REAL da busca (STORY-SRC-002 fix / bug UndefinedColumn).

Executam SQL contra o Postgres da stack via SQLAlchemy (sem TestClient, que
depende de httpx2 não instalado no container). Skip automático se o banco
não estiver acessível (mesmo padrão de test_legal).

Cobertura:
  - search_unified: tipo=all / insumo / composicao não lançam UndefinedColumn.
  - busca por código numérico exato retorna resultados.
  - did_you_mean retorna sugestão para termo sem resultado.
  - search_suggest cross-type funciona de ponta a ponta.
  - get_related_composicoes (Jaccard) estrutural.
"""
import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from api import crud

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="DATABASE_URL ausente — testes de integração requerem o banco da stack",
)


@pytest.fixture(scope="module")
def db():
    try:
        eng = create_engine(os.environ["DATABASE_URL"])
        with eng.connect() as c:
            c.execute(text("SELECT 1"))
        session = Session(eng)
    except Exception as exc:  # pragma: no cover - ambiente
        pytest.skip(f"banco de integração indisponível: {exc}")
    yield session
    session.close()
    eng.dispose() if "eng" in dir() else None


class TestSearchUnifiedIntegration:
    def test_all_types_runs(self, db):
        result = crud.search_unified(db, "areia", "SP", "2026-07", "NAO_DESONERADO",
                                     tipo="all", sort="relevance", skip=0, limit=5)
        assert result["total"] > 0
        tipos = {it["tipo"] for it in result["items"]}
        assert tipos.intersection({"insumo", "composicao"})

    def test_insumo_type_returns_only_insumos(self, db):
        result = crud.search_unified(db, "areia", "SP", "2026-07", "NAO_DESONERADO",
                                     tipo="insumo", sort="relevance", skip=0, limit=5)
        assert result["total"] > 0
        assert all(it["tipo"] == "insumo" for it in result["items"])

    def test_composicao_type_returns_only_composicoes(self, db):
        result = crud.search_unified(db, "alvenaria", "SP", "2026-07", "NAO_DESONERADO",
                                     tipo="composicao", sort="relevance", skip=0, limit=5)
        assert result["total"] > 0
        assert all(it["tipo"] == "composicao" for it in result["items"])

    def test_numeric_code_exact_included(self, db):
        result = crud.search_unified(db, "366", "SP", "2026-07", "NAO_DESONERADO",
                                     tipo="all", sort="relevance", skip=0, limit=5)
        codes = [it["codigo"] for it in result["items"]]
        assert 366 in codes

    def test_multiword_returns_and_results(self, db):
        result = crud.search_unified(db, "alvenaria cimento", "SP", "2026-07",
                                     "NAO_DESONERADO", tipo="all", sort="relevance",
                                     skip=0, limit=10)
        assert result["total"] > 0
        assert all("alvenaria" in it["descricao"].lower() and "cimento" in it["descricao"].lower()
                   for it in result["items"])

    def test_multiword_insumos_endpoint(self, db):
        result = crud.search_insumos_by_descricao(
            db, "perfil aco", "SP", "2026-07", "NAO_DESONERADO", skip=0, limit=10,
        )
        assert result["total"] > 0
        assert all("perfil" in it["descricao"].lower() and "aco" in it["descricao"].lower()
                   for it in result["items"])

    def test_multiword_or_fallback_returns_partial(self, db):
        result = crud.search_unified(db, "alvenaria cimento inexistente_zz", "SP", "2026-07",
                                     "NAO_DESONERADO", tipo="all", sort="relevance",
                                     skip=0, limit=10)
        assert result["total"] > 0
        assert result.get("relaxed") is True

    def test_did_you_mean_returns_suggestion(self, db):
        if not crud._trigram_enabled(db):
            pytest.skip("pg_trgm indisponível")
        dym = crud.did_you_mean(db, "projetto")
        assert dym  # sugere termo mais próximo (ex: GESSO PROJETADO)


class TestSuggestIntegration:
    def test_prefix_cross_type(self, db):
        out = crud.search_suggest(db, "cim", limit=5)
        assert out
        assert any(it.get("tipo") in ("insumo", "composicao") for it in out)


class TestRelatedIntegration:
    def test_jaccard_returns_related(self, db):
        out = crud.get_related_composicoes(db, 88307, limit=3)
        if not out:
            pytest.skip("composição 88307 sem relacionadas")
        assert out[0].get("jaccard", 0) >= 0


class TestRelevanceRankingIntegration:
    """STORY-SIN-095/§3.2 — a busca precisa rankear de fato (auditoria MCP §3.2).

    Estado auditado (2026-09-29): score constante 1.1 para qualquer item que
    contém o termo (word_similarity satura em 1.0 quando a palavra está no
    texto; `GREATEST(similarity, word_similarity * 1.1)` empatava tudo e o
    desempate alfabético colocava ARGAMASSA à frente de CIMENTO PORTLAND).
    Score também violava o intervalo 0..1 da SPEC-RULE-search-pipeline.
    """

    def test_cimento_ranks_prefix_first_and_scores_discriminate(self, db):
        if not crud._trigram_enabled(db):
            pytest.skip("pg_trgm indisponível")
        result = crud.search_unified(
            db, "cimento", "SP", "2026-07", "NAO_DESONERADO",
            tipo="insumo", sort="relevance", skip=0, limit=10,
        )
        items = result["items"]
        assert items, "busca 'cimento' sem resultados"
        # (a) o item que *começa* com o token vem primeiro (não o alfabético)
        assert items[0]["descricao"].upper().startswith("CIMENTO"), \
            items[0]["descricao"]
        # (b) score discrimina relevância (não constante)
        scores = [it.get("score") for it in items]
        assert len({s for s in scores if s is not None}) > 1, \
            f"score constante: {scores}"

    def test_multiword_scores_normalized_0_to_1(self, db):
        if not crud._trigram_enabled(db):
            pytest.skip("pg_trgm indisponível")
        result = crud.search_insumos_by_descricao(
            db, "perfil aco", "SP", "2026-07", "NAO_DESONERADO", skip=0, limit=10,
        )
        scores = [it.get("score") for it in result["items"]
                  if it.get("score") is not None]
        assert scores, "busca multi-tokeno sem score"
        assert all(0.0 <= s <= 1.0 for s in scores), \
            f"score fora de [0,1]: {scores}"


class TestVectorFailureIsolationIntegration:
    """STORY-SIN-095/§3.3 — falha SQL da camada 4 não envenena a request.

    Reproduzido ao vivo (2026-09-29): cosine_search falhava e deixava a
    transação da request abortada → o enriquecimento seguinte (usado_em)
    estourava InFailedSqlTransaction = 5xx, quando o contrato exigia
    meta.degraded=['vector'] com resposta íntegra.
    """

    def test_vector_sql_failure_keeps_request_intact(self, db, monkeypatch):
        from sqlalchemy import text as sql_text
        from api import search
        import api.vector_store as vs

        def _boom(vdb, *a, **k):
            vdb.execute(sql_text("SELECT * FROM tabela_inexistente_xyz"))
            return []

        class _Embed:
            def embed(self, texts):
                return [[0.0] * 8]

        monkeypatch.setattr(vs, "cosine_search", _boom)
        monkeypatch.setattr(vs, "EmbeddingProvider", lambda *a, **k: _Embed())
        result = search.unified_search(
            db, "cimento", "SP", "2026-07", "NAO_DESONERADO",
            tipo="insumo", vector="on", limit=5,
        )
        assert result["items"], "base trigrama deveria continuar íntegra"
        assert "vector" in result["meta"]["degraded"]
        # sessão da request saudável: segunda chamada segue respondendo
        assert crud._trigram_enabled(db) is True