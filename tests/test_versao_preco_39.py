"""§3.9 da auditoria MCP de custo (2026-09-29) — versão do preço aplicado.

A resposta de composição/insumo emitia apenas `sinapi_versao` do CADASTRO
(ex.: 2025.09), enquanto o preço consultado era de outra versão (ex.: 2026-07)
— o agente que cita a composição em documento técnico não tem como declarar
qual versão contratual aplicou.

Critérios GREEN (espelham o gate `automation/scripts/verify_mcp_audit_claims.py`
— claim `claim_versao_preco`):

§3.9a: `versao_preco` presente em `schemas.Insumo` e `schemas.Composicao`;
§3.9b: a SQL de detalhe seleciona a versão da LINHA DE PREÇO
       (`p.sinapi_versao`) alias `versao_preco`;
§3.9c: fallback por `data_referencia` (coluna já existe — decisão do usuário
       2026-09-30): meses cujo ETL não carimbou a coluna (ex.: 2026-04,
       2026-03, 2025-10..12) derivam `AAAA.MM` da própria data consultada,
       porque a CAIXA publica a versão do sistema junto com o mês;
§3.9d: `sinapi_versao` (cadastro) segue exposto — é traceability, não é
       substituído.

Rede: host sem Redis (cache_result é fail-open) e sem Postgres — sessão
mockada no padrão de `tests/test_p1_sinalizacao_composicao.py`.
"""
from __future__ import annotations

from unittest.mock import Mock, patch

from api import crud, schemas


def _db_with_row(mapping):
    """Sessão mockada cujo `.first()` devolve a linha mapeada."""
    db = Mock()
    row = Mock()
    row._mapping = mapping
    db.execute.return_value.first.return_value = row
    db.execute.return_value.fetchall.return_value = [row]
    return db


def _captured_sql(db) -> str:
    return str(db.execute.call_args[0][0])


def _composicao_row():
    # Evidência da auditoria: cadastro 2025.09 consultado para 2026-07.
    return {
        "codigo": 5089,
        "descricao": "COMP4 ESQUADRIA (SOLO QUALITY)",
        "unidade": "m2",
        "grupo": "INSTALACOES",
        "status": "ATIVO",
        "custo_total": 123.45,
        "percentual_mo": 20.0,
        "created_at": None,
        "updated_at": None,
        "sinapi_versao": "2025.09",
        "versao_preco": "2026.07",
    }


def _insumo_row():
    return {
        "codigo": 1,
        "descricao": "ARGAMASSA CIMENTO AREIA 1:4",
        "unidade": "m3",
        "classificacao": "AGREGADOS",
        "status": "ATIVO",
        "preco_mediano": 89.9,
        "origem_preco": "SINAPI",
        "created_at": None,
        "updated_at": None,
        "sinapi_versao": "2026.02",
        "versao_preco": "2026.07",
    }


class TestVersaoPrecoSchema39:
    def test_schemas_expõem_versao_preco(self):
        """§3.9a: os modelos de resposta declararam o campo (OpenAPI incluído)."""
        assert "versao_preco" in schemas.Insumo.model_fields, (
            "§3.9: schemas.Insumo sem versao_preco"
        )
        assert "versao_preco" in schemas.Composicao.model_fields, (
            "§3.9: schemas.Composicao sem versao_preco"
        )


class TestVersaoPrecoComposicao39:
    def test_composicao_expoe_versao_do_preco_aplicado(self):
        """§3.9a/§3.9d: `versao_preco` vem da linha de preço; cadastro segue."""
        db = _db_with_row(_composicao_row())
        with patch.object(crud, "get_composicao_produtividade",
                          return_value={"mao_de_obra": 0.0, "total_custo": 0.0}):
            out = crud.get_composicao_by_codigo(
                db, codigo=5089, uf="SP",
                data_referencia="2026-07", regime="NAO_DESONERADO",
            )
        assert out is not None
        assert out.get("versao_preco") == "2026.07", (
            f"§3.9: versao_preco ausente/errada na composição: "
            f"{out.get('versao_preco')!r}"
        )
        assert out.get("sinapi_versao") == "2025.09", (
            "§3.9d: sinapi_versao do cadastro deixou de ser exposto"
        )

    def test_sql_seleciona_versao_da_linha_de_preco_com_fallback(self):
        """§3.9b/§3.9c: alias `versao_preco` vindo de `p.sinapi_versao` com
        COALESCE pela `data_referencia` (formato AAAA.MM) quando o ETL não
        carimbou a coluna (2026-03/04 e 2025-10..12 são NULL ao vivo)."""
        db = _db_with_row(_composicao_row())
        with patch.object(crud, "get_composicao_produtividade",
                          return_value={"mao_de_obra": 0.0, "total_custo": 0.0}):
            crud.get_composicao_by_codigo(
                db, codigo=5089, uf="SP",
                data_referencia="2026-07", regime="NAO_DESONERADO",
            )
        sql = _captured_sql(db)
        assert "AS versao_preco" in sql, (
            "§3.9: SQL da composição não seleciona `versao_preco`"
        )
        assert "COALESCE" in sql.upper(), (
            "§3.9c: sem fallback por data_referencia (meses NULL no ETL)"
        )
        assert "YYYY.MM" in sql, (
            "§3.9c: fallback não deriva AAAA.MM da data_referencia"
        )


class TestVersaoPrecoInsumo39:
    def test_insumo_expoe_versao_do_preco_aplicado(self):
        db = _db_with_row(_insumo_row())
        out = crud.get_insumo_by_codigo(
            db, codigo=1, uf="SP",
            data_referencia="2026-07", regime="NAO_DESONERADO",
        )
        assert out is not None
        assert out.get("versao_preco") == "2026.07", (
            f"§3.9: versao_preco ausente/errada no insumo: "
            f"{out.get('versao_preco')!r}"
        )
        assert out.get("sinapi_versao") == "2026.02", (
            "§3.9d: sinapi_versao do cadastro deixou de ser exposto"
        )

    def test_sql_do_insumo_seleciona_versao_da_linha_de_preco(self):
        db = _db_with_row(_insumo_row())
        crud.get_insumo_by_codigo(
            db, codigo=1, uf="SP",
            data_referencia="2026-07", regime="NAO_DESONERADO",
        )
        sql = _captured_sql(db)
        assert "AS versao_preco" in sql, (
            "§3.9: SQL do insumo não seleciona `versao_preco`"
        )
        assert "COALESCE" in sql.upper() and "YYYY.MM" in sql, (
            "§3.9c: sem fallback por data_referencia no insumo"
        )
