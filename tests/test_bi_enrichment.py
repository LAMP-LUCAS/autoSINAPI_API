"""
Testes da Fase 3 do BI enriquecido (STORY-SRC-003): "PowerBI do SINAPI".

Cobertura:
  - `crud._compute_variacao`: variacao_mensal + variacao_pct na série histórica.
  - `HistoricoCusto` expõe os novos campos no OpenAPI.
  - `crud._regional_stats` + envelope `?meta=1` em `/precos-uf`.
  - `crud.get_tendencias` enriquecida: variacao_periodo, media_movel, inflacao_acumulada.
  - `crud.get_cenario` compõe composicoes + total_bom + abc + spread_regional + tendencias.
  - Endpoint `/bi/cenario` (tier_2) documentado no OpenAPI.
"""
from __future__ import annotations

from typing import Optional
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

from api import crud, schemas
from api.main import app


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


# ── Variação mês a mês ─────────────────────────────────────────────

class TestVariacaoMensal:
    def test_first_point_has_null_variacao(self):
        from datetime import date
        serie = [{"data_referencia": "2025-01", "valor": 100.0}]
        out = crud._compute_variacao(serie)
        assert out[0]["variacao_mensal"] is None
        assert out[0]["variacao_pct"] is None

    def test_second_point_computes_abs_and_pct(self):
        serie = [
            {"data_referencia": "2025-01", "valor": 100.0},
            {"data_referencia": "2025-02", "valor": 105.0},
        ]
        out = crud._compute_variacao(serie)
        assert out[1]["variacao_mensal"] == 5.0
        assert abs(out[1]["variacao_pct"] - 5.0) < 1e-6

    def test_previous_zero_guards_division(self):
        serie = [
            {"data_referencia": "2025-01", "valor": 0.0},
            {"data_referencia": "2025-02", "valor": 10.0},
        ]
        out = crud._compute_variacao(serie)
        assert out[1]["variacao_mensal"] == 10.0
        assert out[1]["variacao_pct"] is None

    def test_three_points_chain(self):
        serie = [
            {"data_referencia": "2025-01", "valor": 100.0},
            {"data_referencia": "2025-02", "valor": 110.0},
            {"data_referencia": "2025-03", "valor": 121.0},
        ]
        out = crud._compute_variacao(serie)
        assert out[2]["variacao_mensal"] == 11.0
        assert abs(out[2]["variacao_pct"] - 10.0) < 1e-6


class TestHistoricoSchema:
    def test_historico_custo_exposes_variacao_fields(self):
        fields = schemas.HistoricoCusto.model_fields
        assert "variacao_mensal" in fields
        assert "variacao_pct" in fields
        assert fields["variacao_mensal"].annotation == Optional[float]
        assert fields["variacao_pct"].annotation == Optional[float]


def _round(x, n=6):
    return round(float(x), n)


# ── Estatísticas regionais ─────────────────────────────────────────

class TestRegionalStats:
    def test_stats_compute_basic(self):
        points = [
            {"uf": "SP", "valor": 100.0},
            {"uf": "RJ", "valor": 110.0},
            {"uf": "MG", "valor": 90.0},
            {"uf": "BA", "valor": 100.0},
        ]
        st = crud._regional_stats(points)
        assert st["media"] == 100.0
        assert st["mediana"] == 100.0
        assert st["min"] == 90.0
        assert st["max"] == 110.0
        assert st["amplitude"] == 20.0
        assert st["uf_mais_barato"] == "MG"
        assert st["uf_mais_cara"] == "RJ"
        assert round(st["desvio_padrao"], 4) == round(
            __import__("statistics").pstdev([100, 110, 90, 100]), 4
        )

    def test_stats_single_uf(self):
        st = crud._regional_stats([{"uf": "SP", "valor": 42.0}])
        assert st["min"] == st["max"] == st["mediana"] == st["media"] == 42.0
        assert st["uf_mais_barato"] == st["uf_mais_cara"] == "SP"

    def test_stats_empty(self):
        st = crud._regional_stats([])
        assert st["media"] == 0.0


# ── Tendências enriquecidas ────────────────────────────────────────

class TestTendenciasEnrichment:
    def test_tendencias_rows_carry_aggregates(self):
        db = _db_mock([
            {"classificacao": "CONCRETO", "mes": "2025-01", "preco_medio": 100.0, "qtd_insumos": 3},
            {"classificacao": "CONCRETO", "mes": "2025-02", "preco_medio": 110.0, "qtd_insumos": 3},
            {"classificacao": "CONCRETO", "mes": "2025-03", "preco_medio": 121.0, "qtd_insumos": 3},
            {"classificacao": "ACO", "mes": "2025-01", "preco_medio": 10.0, "qtd_insumos": 2},
            {"classificacao": "ACO", "mes": "2025-02", "preco_medio": 10.5, "qtd_insumos": 2},
        ])
        result = crud.get_tendencias(db, uf="SP", regime="NAO_DESONERADO",
                                     data_referencia="2025-03", agrupar_por="classificacao")
        assert len(result) >= 5
        concreto = [r for r in result if r["classificacao"] == "CONCRETO"]
        assert abs(concreto[2]["variacao_periodo"] - 21.0) < 1e-6
        assert abs(concreto[2]["inflacao_acumulada"] - 21.0) < 1e-6
        assert abs(concreto[1]["media_movel"] - 105.0) < 1e-6


# ── §3.7 da auditoria MCP de custo (STORY-SIN-095) ────────────────
# Sintoma auditado (2026-09-29): `get_tendencias` devolvia
# variacao_mensal=0.0 em TODOS os pontos e variacao_pct=null, mesmo com o
# preço se movendo (520,26 → 511,06 → 558,69 → 570,51). Causa: as linhas do
# BI trazem `preco_medio`, mas `_compute_variacao` lia `valor` → 0.0 silencioso.

class TestVariacaoTendencias:
    def test_compute_variacao_explicit_preco_medio_key(self):
        serie = [
            {"mes": "2025-07", "preco_medio": 520.26},
            {"mes": "2025-09", "preco_medio": 511.06},
        ]
        out = crud._compute_variacao(serie, value_key="preco_medio")
        assert out[1]["variacao_mensal"] == pytest.approx(-9.2, abs=0.01)
        assert out[1]["variacao_pct"] == pytest.approx(-1.7683, abs=0.01)

    def test_compute_variacao_rejects_series_without_value(self):
        # Nunca assumir 0 silencioso quando a chave de valor não existe —
        # era exatamente o defeito que zerava as tendências.
        with pytest.raises(ValueError):
            crud._compute_variacao([{"mes": "2025-01"}])

    def test_tendencias_variacao_reflects_price_movement(self):
        db = _db_mock([
            {"classificacao": "34872 - CONCRETO", "mes": "2025-07",
             "preco_medio": 520.26, "qtd_insumos": 1},
            {"classificacao": "34872 - CONCRETO", "mes": "2025-08",
             "preco_medio": 520.26, "qtd_insumos": 1},
            {"classificacao": "34872 - CONCRETO", "mes": "2025-09",
             "preco_medio": 511.06, "qtd_insumos": 1},
            {"classificacao": "34872 - CONCRETO", "mes": "2026-04",
             "preco_medio": 558.69, "qtd_insumos": 1},
        ])
        result = crud.get_tendencias(db, uf="SP", regime="NAO_DESONERADO",
                                     data_referencia="2026-07",
                                     agrupar_por="item", codigos=[34872])
        rows = [r for r in result if r["classificacao"].startswith("34872")]
        assert len(rows) == 4
        assert rows[0]["variacao_mensal"] is None      # 1º ponto: null
        assert rows[1]["variacao_mensal"] == 0.0        # preço igual → 0 legítimo
        assert rows[2]["variacao_mensal"] == pytest.approx(-9.2, abs=0.01)
        assert rows[2]["variacao_pct"] is not None      # RED: null (prev=0)
        assert rows[3]["variacao_mensal"] == pytest.approx(47.63, abs=0.01)
        assert rows[3]["variacao_pct"] == pytest.approx(9.3195, abs=0.01)


# ── Cenário orçamentário ───────────────────────────────────────────

class TestCenario:
    def test_cenario_composes_all_blocks(self):
        db = _db_mock()
        with patch.object(crud, "get_composicao_by_codigo", return_value={
            "codigo": 1, "descricao": "Alvenaria de bloco", "custo_total": 10.0, "unidade": "m2"
        }):
            with patch.object(crud, "get_composicao_bom", return_value=[
                {"item_codigo": 99, "custo_impacto_total": 40.0},
                {"item_codigo": 98, "custo_impacto_total": 60.0},
            ]):
                with patch.object(crud, "get_abc_curve_for_composicoes", return_value=[
                    {"codigo": 99, "descricao": "Argamassa", "unidade": "kg",
                     "custo_total_agregado": 40.0, "percentual_individual": 40.0,
                     "percentual_acumulado": 40.0, "classe_abc": "A"},
                    {"codigo": 98, "descricao": "Bloco", "unidade": "un",
                     "custo_total_agregado": 60.0, "percentual_individual": 60.0,
                     "percentual_acumulado": 100.0, "classe_abc": "A"},
                ]):
                    with patch.object(crud, "get_cenario_spread", return_value={
                        "media": 105.0, "mediana": 105.0, "min": 100.0, "max": 110.0,
                        "desvio_padrao": 5.0, "amplitude": 10.0,
                        "uf_mais_barato": "MG", "uf_mais_cara": "RJ",
                    }):
                        with patch.object(crud, "get_cenario_tendencias", return_value=[{
                            "data_referencia": "2025-03", "valor": 121.0,
                            "variacao_mensal": 11.0, "variacao_pct": 10.0,
                        }]):
                            result = crud.get_cenario(db, codigos=[1], uf="SP",
                                                      data_referencia="2025-03",
                                                      regime="NAO_DESONERADO")
        assert result["total_bom"] == 100.0
        assert result["composicoes"][0]["custo_total"] == 100.0
        assert result["composicoes"][0]["descricao"] == "Alvenaria de bloco"
        assert len(result["abc"]) == 2
        assert result["spread_regional"]["uf_mais_cara"] == "RJ"
        assert result["tendencias"][0]["variacao_pct"] == 10.0

    def test_tier_2_and_schema_documented(self):
        client = TestClient(app)
        openapi = client.get("/openapi.json").json()
        path = "/api/v1/public/bi/cenario"
        assert path in openapi["paths"]
        get_op = openapi["paths"][path]["get"]
        assert "tier_2" in get_op.get("tags", [])
        ref = get_op.get("responses", {}).get("200", {})
        assert "CenarioResponse" in str(ref)