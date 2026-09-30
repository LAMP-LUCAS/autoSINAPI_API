"""P1 da auditoria MCP de custo (2026-09-29) — sinalização de indisponibilidade
e enriquecimento da composição. Critérios GREEN iguais aos do gate da casa
`automation/scripts/verify_mcp_audit_claims.py`:

§3.4: composição sem preço (custo_total=0) sinaliza `preco_disponivel` —
      nunca `0.0` silencioso com `status='ATIVO'`
      (gate: `zero_sem_sinal = custo==0 and sinal is None` → FAIL).
§3.5: insumo HORISTA (unidade 'H') responde `total_hora_homem == 1.0` —
      hoje a query recursiva só enxerga composições e devolve 0.0.
§3.6: `percentual_mo` preenchido (0 < x < 100) em composição ativa —
      a coluna existe desde a migration 005 mas é NULL em 100% das linhas
      (o ETL nunca gravou); fallback calcula %MO a partir do BOM
      (mesmo split de `get_composicao_produtividade`).

Rede: host sem Redis (cache_result é fail-open) e sem Postgres — os testes
usam sessão mockada no padrão de `test_bi_enrichment.py`.
"""
from __future__ import annotations

from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

from api import crud
from api.main import app


def _db_with_row(mapping):
    """Sessão mockada cujo `.first()` devolve a linha mapeada."""
    db = Mock()
    row = Mock()
    row._mapping = mapping
    db.execute.return_value.first.return_value = row
    db.execute.return_value.fetchall.return_value = [row]
    return db


def _composicao_row(custo_total, percentual_mo=None):
    return {
        "codigo": 99235,
        "descricao": "COMP2 ESQUADRIA (SOLO QUALITY GRAU MÉDIO)",
        "unidade": "m2",
        "grupo": "INSTALACOES",
        "status": "ATIVO",
        "custo_total": custo_total,
        "percentual_mo": percentual_mo,
        "created_at": None,
        "updated_at": None,
        "sinapi_versao": None,
    }


# ── §3.4 — preco_disponivel ─────────────────────────────────────────

class TestPrecoDisponivel34:
    def test_composicao_sem_preco_sinaliza_indisponivel(self):
        # Evidência: 105539/SP 2026-07 → custo_total=0, status ATIVO, sem sinal.
        db = _db_with_row(_composicao_row(custo_total=0))
        with patch.object(crud, "get_composicao_produtividade",
                          return_value={"mao_de_obra": 0.0, "total_custo": 0.0}):
            out = crud.get_composicao_by_codigo(
                db, codigo=105539, uf="SP",
                data_referencia="2026-07", regime="NAO_DESONERADO",
            )
        assert out is not None
        # STORY-MCP-007/S-02: o §3.4 exigia um SINAL; o S-02 exige que o 0.0
        # SAIA (vira null) para não ser somado como R$ 0,00 num orçamento. O
        # sinal `preco_disponivel` continua sendo o contrato do §3.4.
        assert out.get("custo_total") is None, (
            "custo zerado não pode sair como 0.0 — vira null + motivo (S-02)"
        )
        assert out.get("preco_disponivel") is False, (
            "custo_total=0 sem sinal de indisponibilidade (§3.4)"
        )
        assert out.get("motivo_indisponivel") == "SEM_COTACAO_NA_UF"

    def test_composicao_com_preco_sinaliza_disponivel(self):
        db = _db_with_row(_composicao_row(custo_total=646.80))
        with patch.object(crud, "get_composicao_produtividade",
                          return_value={"mao_de_obra": 194.04, "total_custo": 646.80}):
            out = crud.get_composicao_by_codigo(
                db, codigo=99235, uf="SP",
                data_referencia="2026-07", regime="NAO_DESONERADO",
            )
        assert out.get("preco_disponivel") is True

    def test_openapi_expoe_preco_disponivel(self):
        client = TestClient(app)
        props = (client.get("/openapi.json").json()
                 ["components"]["schemas"]["Composicao"]["properties"])
        assert "preco_disponivel" in props, (
            "schema Composicao deve expor preco_disponivel (§3.4)"
        )


# ── §3.5 — hora-homem do insumo horista ─────────────────────────────

class TestHoraHomem35:
    def test_insumo_horista_retorna_1_hh(self):
        # Evidência: código 1213 = "CARPINTEIRO DE FORMAS… (HORISTA)", unidade H.
        db = Mock()
        consulta_composicao = Mock()
        consulta_composicao.first.return_value = None  # não é composição
        consulta_insumo = Mock()
        consulta_insumo.scalar.return_value = "H"
        db.execute.side_effect = [consulta_composicao, consulta_insumo]

        out = crud.get_composicao_man_hours(db, codigo=1213)
        assert out["total_hora_homem"] == pytest.approx(1.0), (
            "insumo horista (unidade H) deve responder 1.0 HH (§3.5)"
        )

    def test_insumo_nao_horista_continua_zero(self):
        db = Mock()
        consulta_composicao = Mock()
        consulta_composicao.first.return_value = None
        consulta_insumo = Mock()
        consulta_insumo.scalar.return_value = "kg"
        db.execute.side_effect = [consulta_composicao, consulta_insumo]

        out = crud.get_composicao_man_hours(db, codigo=1234)
        assert out["total_hora_homem"] == 0.0

    def test_composicao_conserva_somatorio_existente(self):
        db = Mock()
        row = Mock()
        row._mapping = {"total_hora_homem": 3.5}
        row.total_hora_homem = 3.5
        db.execute.return_value.first.return_value = row

        out = crud.get_composicao_man_hours(db, codigo=5627)
        assert out["total_hora_homem"] == pytest.approx(3.5)


# ── §3.6 — percentual_mo ────────────────────────────────────────────

class TestPercentualMo36:
    def test_percentual_mo_calculado_quando_coluna_null(self):
        # Evidência: 99235/SP 2026-07 → custo_total=646.80, percentual_mo NULL
        # (a coluna é NULL em 100% das 13,7 M linhas — ETL nunca gravou).
        db = _db_with_row(_composicao_row(custo_total=646.80, percentual_mo=None))
        with patch.object(crud, "get_composicao_produtividade",
                          return_value={"mao_de_obra": 194.04, "total_custo": 646.80}):
            out = crud.get_composicao_by_codigo(
                db, codigo=99235, uf="SP",
                data_referencia="2026-07", regime="NAO_DESONERADO",
            )
        pmo = out.get("percentual_mo")
        assert isinstance(pmo, (int, float)) and 0 < float(pmo) < 100, (
            f"percentual_mo deve ser calculado do BOM, não {pmo!r} (§3.6)"
        )
        assert float(pmo) == pytest.approx(30.0, abs=0.01)

    def test_percentual_mo_armazenado_tem_prioridade(self):
        db = _db_with_row(_composicao_row(custo_total=646.80, percentual_mo=42.5))
        with patch.object(crud, "get_composicao_produtividade") as prod:
            out = crud.get_composicao_by_codigo(
                db, codigo=99235, uf="SP",
                data_referencia="2026-07", regime="NAO_DESONERADO",
            )
            prod.assert_not_called()  # valor armazenado vence — sem BOM extra
        assert out.get("percentual_mo") == pytest.approx(42.5)

    def test_percentual_mo_sem_preco_continua_null(self):
        db = _db_with_row(_composicao_row(custo_total=0, percentual_mo=None))
        with patch.object(crud, "get_composicao_produtividade",
                          return_value={"mao_de_obra": 0.0, "total_custo": 0.0}):
            out = crud.get_composicao_by_codigo(
                db, codigo=105539, uf="SP",
                data_referencia="2026-07", regime="NAO_DESONERADO",
            )
        assert out.get("percentual_mo") is None
        assert out.get("preco_disponivel") is False
