"""
Testes da camada 4 (vetorial/RRF) do pipeline de busca (ADR-006).

Cobrem:
  - _rrf_merge: reorder híbrido deterministic, itens exclusivos vetoriais
    descartados (camada 4 apenas refina o conjunto textual).
  - unified_search: degradação graciosa quando a camada vetorial falha
    (várias rotas de erro → meta.degraded contém 'vector', sem 5xx).
  - unified_search: provider offline → degraded (sem exceção).
"""
import pytest

from api import search


def _item(codigo, tipo="insumo"):
    return {"codigo": codigo, "tipo": tipo, "descricao": f"item {codigo}", "valor": 1.0}


class TestRRFMerge:
    def test_empty_vector_keeps_trigram_order(self):
        items = [_item(1), _item(2)]
        assert search._rrf_merge(items, []) == items

    def test_no_trigram_items_stays_empty(self):
        assert search._rrf_merge([], [{"codigo": 9, "tipo_item": "insumo"}]) == []

    def test_shared_items_reranked_above_exclusive(self):
        items = [_item(1), _item(2), _item(3)]
        hits = [
            {"codigo": 3, "tipo_item": "insumo"},
            {"codigo": 1, "tipo_item": "insumo"},
        ]
        merged = search._rrf_merge(items, hits)
        # 3 e 1 aparecem nas duas listas → sobem; 2 (só trigrama) fica por último.
        # RRF determinístico: 1 soma 1/61+1/62, 3 soma 1/63+1/61 → 1 > 3.
        assert [it["codigo"] for it in merged] == [1, 3, 2]

    def test_discards_items_only_in_vector(self):
        items = [_item(1)]
        hits = [
            {"codigo": 1, "tipo_item": "insumo"},
            {"codigo": 999, "tipo_item": "insumo"},
        ]
        merged = search._rrf_merge(items, hits)
        codes = [it["codigo"] for it in merged]
        assert 999 not in codes
        assert 1 in codes

    def test_tipo_key_matches_properly(self):
        items = [_item(1, "insumo"), _item(2, "composicao")]
        hits = [{"codigo": 2, "tipo_item": "composicao"}]
        merged = search._rrf_merge(items, hits)
        assert merged[0]["codigo"] == 2


class TestVectorProviderDegradationBudget:
    """STORY-SIN-095/§3.3 — orçamento de tempo da camada vetorial.

    Auditoria (2026-09-29): `sinapi_search(vector=on)` estourava o timeout de
    30s do MCP (×3 retries ≈ 92s) e virava ERRO — o primary pendurava em
    EMBEDDING_TIMEOUT=120s (nó Tailscale morto) antes de alcançar o fallback.
    SPEC-RULE-search-pipeline-graceful-degradation: lentidão também é falha →
    responder rápido com `meta.degraded=['vector']`, nunca travar a request.
    """

    def test_slow_embedding_responds_within_budget(self, monkeypatch):
        import time as _time

        from api import crud
        from api.config import settings
        import api.vector_store as vs

        monkeypatch.setattr(crud, "_trigram_enabled", lambda db: True)
        monkeypatch.setattr(crud, "search_unified",
                            lambda *a, **k: {"items": [_item(1)], "total": 1})
        monkeypatch.setattr(crud, "get_usado_em_summary",
                            lambda db, codigo, top=5: {})

        seen: dict = {}

        class SlowEmbed:
            def embed(self, texts):
                _time.sleep(1.2)          # simula o primary pendurado
                return [[0.1] * 8]

        def _mk_provider(*a, **k):
            seen.update(k)
            return SlowEmbed()

        monkeypatch.setattr(vs, "EmbeddingProvider", _mk_provider)
        monkeypatch.setattr(settings, "SEARCH_VECTOR_TIMEOUT", 0.3,
                            raising=False)

        t0 = _time.monotonic()
        result = search.unified_search(None, "areia", "SP", "2026-07",
                                       "NAO_DESONERADO", vector="on")
        elapsed = _time.monotonic() - t0

        assert "vector" in result["meta"]["degraded"]
        # o provider precisa receber o orçamento curto (backstop de socket)
        assert seen.get("timeout") is not None and seen["timeout"] <= 0.3, seen
        # e a request inteira responde dentro do orçamento
        assert elapsed <= 1.0, f"orçamento estourado: {elapsed:.2f}s"


class TestUnifiedSearchVectorDegradation:
    def test_vector_off_not_in_providers(self):
        # Sem chamadas a banco: proíbe qualquer degradação fake.
        from api import crud
        crud._trigram_enabled = lambda db: True
        crud.search_unified = lambda *a, **k: {"items": [_item(1)], "total": 1}
        crud.get_usado_em_summary = lambda db, codigo, top=5: {}
        result = search.unified_search(None, "areia", "SP", "2026-07", "NAO_DESONERADO",
                                       vector="off")
        assert "vector" not in result["meta"]["providers"]
        assert "vector" not in result["meta"]["degraded"]

    def test_vector_provider_degradation_appends_vector(self, monkeypatch):
        from api import crud
        crud._trigram_enabled = lambda db: True
        crud.search_unified = lambda *a, **k: {"items": [_item(1)], "total": 1}
        crud.get_usado_em_summary = lambda db, codigo, top=5: {}
        import api.vector_store as vs

        class BoomEmbed:
            def embed(self, texts):
                raise RuntimeError("offline")

        monkeypatch.setattr(vs, "EmbeddingProvider", lambda *a, **k: BoomEmbed())
        result = search.unified_search(None, "areia", "SP", "2026-07", "NAO_DESONERADO",
                                       vector="on")
        assert "vector" not in result["meta"]["providers"]
        assert "vector" in result["meta"]["degraded"]
        assert len(result["items"]) == 1  # base trigrama intacta