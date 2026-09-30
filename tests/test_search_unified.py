"""
Testes da Fase 2 da busca (STORY-SRC-002): `/search` unificado (insumo+composição)
com `did_you_mean`, `usado_em`, degradação `vector`; `/search/suggest`; `/search/related`.

Cobertura:
  - `crud.search_suggest`: UNION cross-type, prefixo primeiro, fallback ILIKE.
  - `crud.search_unified`: merge insumo+composição, campo `tipo`, sort server-side,
    fallback trigram, filtros grupo/classificacao.
  - `crud.did_you_mean`: termo mais próximo com limiar de similaridade.
  - `crud.get_related_composicoes`: Jaccard BOM, exclui a própria composição.
  - `crud.get_usado_em_summary`: reusa get_onde_usado (top 5 + total).
  - `search.unified_search`: monta `meta.providers`/`meta.degraded`/`did_you_mean`,
    enriquece `usado_em`; `vector` degrada sem quebrar.
  - Endpoints `/search`, `/search/suggest`, `/search/related`: envelope + tier tags +
    schemas documentados no OpenAPI.
"""
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

from api import crud
from api.main import app
from api import search as search_pkg


def _fake_rows(mappings):
    out = []
    for m in mappings:
        row = Mock()
        row._mapping = m
        out.append(row)
    return out


def _db_mock(rows=None):
    db = Mock()
    rows = rows or []
    db.execute.return_value.fetchall.return_value = _fake_rows(rows)
    db.execute.return_value.first.return_value = _fake_rows(rows[:1])[0] if rows else None
    return db


class TestSearchSuggest:
    def _db(self, rows=None):
        return _db_mock(rows)

    def test_union_cross_type_with_prefix_boost(self):
        db = self._db()
        with patch.object(crud, "_trigram_enabled", return_value=True):
            crud.search_suggest(db, "cim", limit=8)
            sql = str(db.execute.call_args[0][0])
            params = db.execute.call_args[0][1]
        assert "UNION ALL" in sql
        assert "word_similarity" in sql
        assert "'insumo'" in sql and "'composicao'" in sql
        assert params.get("limit") == 8

    def test_fallback_ilike_without_trigram(self):
        db = self._db()
        with patch.object(crud, "_trigram_enabled", return_value=False):
            crud.search_suggest(db, "cim", limit=8)
            sql = str(db.execute.call_args[0][0])
        assert "ILIKE" in sql
        assert "similarity" not in sql
        assert "UNION ALL" in sql

    def test_items_expose_tipo(self):
        db = self._db([{"codigo": 1, "descricao": "Cimento", "unidade": "KG",
                        "tipo": "insumo", "score": 0.9}])
        result = crud.search_suggest(db, "cim")
        assert result[0]["tipo"] == "insumo"
        assert result[0]["codigo"] == 1


class TestSearchUnified:
    def _db(self, rows=None):
        return _db_mock(rows)

    def test_unified_sql_merges_types_with_total(self):
        db = self._db()
        with patch.object(crud, "_trigram_enabled", return_value=True):
            crud.search_unified(db, "bloco", "SP", "2025-09", "NAO_DESONERADO",
                                tipo="all", sort="relevance", skip=0, limit=10)
            sql = str(db.execute.call_args[0][0])
        assert "UNION ALL" in sql
        assert "AS tipo" in sql
        assert "total_count" in sql
        assert "ORDER BY score DESC" in sql
        assert "f_unaccent" in sql

    def test_sort_price_asc(self):
        db = self._db()
        with patch.object(crud, "_trigram_enabled", return_value=True):
            crud.search_unified(db, "bloco", "SP", "2025-09", "NAO_DESONERADO",
                                tipo="all", sort="price_asc", skip=0, limit=10)
            sql = str(db.execute.call_args[0][0])
        assert "ORDER BY valor ASC" in sql

    def test_tipo_insumo_skips_union(self):
        db = self._db()
        with patch.object(crud, "_trigram_enabled", return_value=True):
            crud.search_unified(db, "bloco", "SP", "2025-09", "NAO_DESONERADO",
                                tipo="insumo", sort="relevance", skip=0, limit=10)
            sql = str(db.execute.call_args[0][0])
        assert "UNION ALL" not in sql

    def test_fallback_ilike(self):
        db = self._db()
        with patch.object(crud, "_trigram_enabled", return_value=False):
            crud.search_unified(db, "bloco", "SP", "2025-09", "NAO_DESONERADO",
                                tipo="all", sort="relevance", skip=0, limit=10)
            sql = str(db.execute.call_args[0][0])
        assert "ILIKE" in sql
        assert "similarity" not in sql

    def test_wrappers_return_envelope(self):
        db = self._db([{"codigo": 1, "tipo": "insumo", "total_count": 5}])
        result = crud.search_unified(db, "bloco", "SP", "2025-09", "NAO_DESONERADO",
                                     tipo="all", sort="relevance", skip=0, limit=10)
        assert "items" in result and "total" in result
        assert result["total"] == 5

    def test_insumo_branch_does_not_reference_grupo_column(self):
        db = self._db()
        with patch.object(crud, "_trigram_enabled", return_value=True):
            crud.search_unified(db, "bloco", "SP", "2025-09", "NAO_DESONERADO",
                                tipo="insumo", sort="relevance", skip=0, limit=10)
            sql = str(db.execute.call_args[0][0])
        # t.grupo NÃO existe em insumos (UndefinedColumn em produção, STORY-SRC-002 fix)
        assert "t.classificacao AS classificacao" in sql
        assert "null::text AS grupo" in sql.replace("NULL", "null")
        assert "t.grupo" not in sql

    def test_insumo_branch_null_emits_null_grupo_in_union_all(self):
        db = self._db()
        with patch.object(crud, "_trigram_enabled", return_value=True):
            crud.search_unified(db, "bloco", "SP", "2025-09", "NAO_DESONERADO",
                                tipo="all", sort="relevance", skip=0, limit=10)
            sql = str(db.execute.call_args[0][0])
        # branch composição ainda referencia t.grupo (legítimo); insumo usa NULL.
        assert "UNION ALL" in sql
        assert "null::text AS grupo" in sql.replace("NULL", "null")

    def test_composicao_branch_does_not_reference_classificacao_column(self):
        db = self._db()
        with patch.object(crud, "_trigram_enabled", return_value=True):
            crud.search_unified(db, "alvenaria", "SP", "2025-09", "NAO_DESONERADO",
                                tipo="composicao", sort="relevance", skip=0, limit=10)
            sql = str(db.execute.call_args[0][0])
        # t.classificacao NÃO existe em composicoes — a faceta paralela é
        # t.grupo, usada também para popular `classificacao` (§3.10).
        assert "t.grupo AS grupo" in sql
        assert "t.grupo AS classificacao" in sql
        assert "t.classificacao" not in sql
        assert "t.grupo" in sql

    def test_composicao_branch_popula_classificacao_a_partir_do_grupo(self):
        """§3.10: `classificacao` não pode sair `null` no caminho de composição.

        A casa trata classificacao (insumos) e grupo (composições) como
        facetas paralelas — ver endpoint BI `agrupar_por` ("classificacao"
        (Insumos), "grupo" (Composições)) e `sinapi_filters`, que cataloga
        `classificacoes` e `grupos`. O item unificado deve espelhar o grupo
        na faceta `classificacao` em vez de emitir literal NULL.
        """
        db = self._db()
        with patch.object(crud, "_trigram_enabled", return_value=True):
            crud.search_unified(db, "alvenaria", "SP", "2025-09", "NAO_DESONERADO",
                                tipo="composicao", sort="relevance", skip=0, limit=10)
            sql = str(db.execute.call_args[0][0])
        assert "t.grupo AS classificacao" in sql
        assert "null::text AS classificacao" not in sql.replace("NULL", "null")
        assert "t.classificacao" not in sql  # coluna não existe na tabela


class TestDidYouMean:
    def _db(self, rows=None):
        return _db_mock(rows)

    def test_returns_closest_term_above_threshold(self):
        db = self._db([{"descricao": "cimento portland", "sim": 0.85}])
        with patch.object(crud, "_trigram_enabled", return_value=True):
            result = crud.did_you_mean(db, "cimneto")
        assert result == "cimento portland"
        sql = str(db.execute.call_args[0][0])
        assert "%" in sql  # operador trigram -> usa índice GIN

    def test_returns_none_when_no_candidate(self):
        db = self._db([])
        assert crud.did_you_mean(db, "zzzqqq") is None


class TestRelatedComposicoes:
    def _db(self, rows=None):
        return _db_mock(rows)

    def test_jaccard_query_excludes_self(self):
        db = self._db()
        crud.get_related_composicoes(db, codigo=88247, limit=5)
        sql = str(db.execute.call_args[0][0])
        params = db.execute.call_args[0][1]
        assert "jaccard" in sql
        assert "composicao_pai_codigo <> :codigo" in sql
        assert params.get("codigo") == 88247
        assert params.get("limit") == 5


class TestUsadoEmSummary:
    def test_reuses_onde_usado_with_top5(self):
        db = Mock()
        onde_usado = [
            {"composicao_codigo": 1, "composicao_descricao": "C1", "nivel": 1},
            {"composicao_codigo": 2, "composicao_descricao": "C2", "nivel": 2},
            {"composicao_codigo": 3, "composicao_descricao": "C3", "nivel": 3},
            {"composicao_codigo": 4, "composicao_descricao": "C4", "nivel": 4},
            {"composicao_codigo": 5, "composicao_descricao": "C5", "nivel": 5},
            {"composicao_codigo": 6, "composicao_descricao": "C6", "nivel": 6},
        ]
        with patch.object(crud, "get_onde_usado", return_value=onde_usado):
            result = crud.get_usado_em_summary(db, codigo=92711, top=5)
        assert result["total"] == 6
        assert len(result["items"]) == 5


class TestSearchPackage:
    def test_unified_search_builds_meta_and_enriches_usado_em(self):
        db = Mock()
        items = [
            {"codigo": 92711, "tipo": "insumo", "valor": 150.5, "score": 0.9},
            {"codigo": 88247, "tipo": "composicao", "valor": 500.0, "score": 0.8},
        ]
        with patch.object(crud, "_trigram_enabled", return_value=True), \
             patch.object(crud, "search_unified",
                          return_value={"items": items, "total": 2}), \
             patch.object(crud, "get_usado_em_summary",
                          return_value={"total": 3, "items": [{"composicao_codigo": 1}]}) as usado, \
             patch.object(crud, "did_you_mean", return_value=None) as dym:
            result = search_pkg.unified_search(
                db, "cimento", "SP", "2025-09", "NAO_DESONERADO",
                tipo="all", sort="relevance", vector="auto", skip=0, limit=10)
        assert result["total"] == 2
        assert result["meta"]["providers"] == ["trigram"]
        assert "vector" in result["meta"]["degraded"]
        assert result["items"][0]["usado_em"]["total"] == 3
        usado.assert_called()
        dym.assert_not_called()

    def test_vector_off_avoids_degraded(self):
        db = Mock()
        with patch.object(crud, "_trigram_enabled", return_value=True), \
             patch.object(crud, "search_unified", return_value={"items": [], "total": 0}), \
             patch.object(crud, "get_usado_em_summary"), \
             patch.object(crud, "did_you_mean", return_value=None):
            result = search_pkg.unified_search(
                db, "cimento", "SP", "2025-09", "NAO_DESONERADO",
                tipo="all", sort="relevance", vector="off", skip=0, limit=10)
        assert "vector" not in result["meta"]["degraded"]

    def test_did_you_mean_computed_when_no_results(self):
        db = Mock()
        with patch.object(crud, "_trigram_enabled", return_value=True), \
             patch.object(crud, "search_unified", return_value={"items": [], "total": 0}), \
             patch.object(crud, "get_usado_em_summary"), \
             patch.object(crud, "did_you_mean", return_value="cimento portland") as dym:
            result = search_pkg.unified_search(
                db, "cimneto", "SP", "2025-09", "NAO_DESONERADO",
                tipo="all", sort="relevance", vector="off", skip=0, limit=10)
        dym.assert_called_once()
        assert result["meta"]["did_you_mean"] == "cimento portland"

    def test_relaxed_propagates_to_meta_when_or_fallback(self):
        db = Mock()
        items = [
            {"codigo": 87327, "tipo": "composicao", "valor": 100.0, "score": 1.1},
        ]
        with patch.object(crud, "_trigram_enabled", return_value=True), \
             patch.object(crud, "search_unified",
                          return_value={"items": items, "total": 1, "relaxed": True}), \
             patch.object(crud, "get_usado_em_summary"), \
             patch.object(crud, "did_you_mean", return_value=None):
            result = search_pkg.unified_search(
                db, "alvenaria cimento portland", "SP", "2025-09", "NAO_DESONERADO",
                tipo="all", sort="relevance", vector="off", skip=0, limit=10)
        assert result["meta"]["relaxed"] is True


class TestSearchEndpoints:
    @pytest.fixture
    def client(self):
        yield TestClient(app)

    def test_search_endpoint_envelope(self, client):
        with patch.object(search_pkg, "unified_search", return_value={
            "items": [{"codigo": 92711, "descricao": "Cimento", "unidade": "KG",
                       "tipo": "insumo", "valor": 150.5, "score": 0.9}],
            "total": 1,
            "meta": {"providers": ["trigram"], "degraded": [], "did_you_mean": None,
                     "page": 1, "page_size": 20, "total": 1},
        }):
            r = client.get("/api/v1/public/search", params={
                "q": "cimento", "uf": "SP", "data_referencia": "2025-09"})
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 1
        assert body["meta"]["providers"] == ["trigram"]
        assert body["items"][0]["tipo"] == "insumo"

    def test_suggest_endpoint(self, client):
        with patch.object(crud, "search_suggest", return_value=[
            {"codigo": 1, "descricao": "Cimento", "unidade": "KG", "tipo": "insumo", "score": 0.9},
        ]):
            r = client.get("/api/v1/public/search/suggest", params={"q": "cim"})
        assert r.status_code == 200
        assert r.json()["items"][0]["descricao"] == "Cimento"

    def test_related_endpoint(self, client):
        with patch.object(crud, "get_related_composicoes", return_value=[
            {"codigo": 2, "descricao": "Outra", "unidade": "M2", "jaccard": 0.5, "shared": 3},
        ]):
            r = client.get("/api/v1/public/search/related", params={
                "codigo": 88247, "uf": "SP", "data_referencia": "2025-09"})
        assert r.status_code == 200
        assert r.json()["items"][0]["jaccard"] == 0.5

    def test_openapi_documents_search_schemas(self, client):
        spec = client.get("/openapi.json").json()
        schemas = spec["components"]["schemas"]
        assert "UnifiedSearchResult" in schemas
        assert "SearchSuggestResult" in schemas
        assert "SearchRelatedResult" in schemas
        assert "SearchMeta" in schemas
        search_op = spec["paths"]["/api/v1/public/search"]["get"]
        assert search_op["tags"][0] == "tier_1"
        related_op = spec["paths"]["/api/v1/public/search/related"]["get"]
        assert related_op["tags"][0] == "tier_2"
