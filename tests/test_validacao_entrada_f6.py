"""STORY-MCP-007 · Onda 1 — fail-loud (ADR 010). S-01, S-03, S-04, S-05.

Certificação funcional de 2026-09-30 mediu, ao vivo, três modos de falha que
não sinalizam erro ao agente:

* **S-01** `curva_abc([99803, 4750])` devolvia a curva **só** de 99803 com
  `isError:false` — 4750 (PEDREIRO) é *insumo*, não composição, e sumia sem
  aviso. Resultado parcial é erro nomeado (ADR 010).
* **S-03** `uf:"XX"` e `data_referencia:"2030-01"` respondiam `200` com
  `items: []`; termo sem match não carregava nenhuma dica.
* **S-04** `get_audit(insumo, 4750, 2026-08)` respondia "não encontrado" — o
  único evento do insumo é de **2021-12**, e o erro não dizia isso. Além disso
  `get_audit_events` comparava `tipo_item` sem normalizar, perdendo as linhas
  `COMPOSIÇÃO` (com cedilha) que existem no banco.
* **S-05** o rótulo do erro fixava "do insumo N" mesmo com
  `tipo_item="composicao"` (o `resolver` do MCP só tinha padrão para o path
  `/bi/insumo/...`).

Rede: sessão mockada (mesmo padrão de `test_versao_preco_39.py`); `cache_result`
é fail-open sem Redis.
"""
from __future__ import annotations

from unittest.mock import Mock

import pytest
from sqlalchemy import text

from api import crud, schemas, validation
from api.validation import EntradaInvalida, NaoResolvido

# ───────────────────────── S-03 · validação de entrada ───────────────────────

def test_validar_uf_rejeita_sigla_desconhecida():
    with pytest.raises(EntradaInvalida) as exc:
        validation.validar_uf("XX")
    assert exc.value.codigo == "INVALID_UF"
    assert "XX" in exc.value.mensagem
    # a mensagem entrega a lista válida (o agente corrige sem docs)
    assert "SP" in exc.value.mensagem and "27" in exc.value.mensagem


def test_validar_uf_normaliza_caixa_e_espacos():
    assert validation.validar_uf(" sp ") == "SP"
    assert len(validation.BR_UFS) == 27


def test_validar_data_referencia_rejeita_competencia_futura():
    with pytest.raises(EntradaInvalida) as exc:
        validation.validar_data_referencia("2030-01", max_ref="2026-08")
    assert exc.value.codigo == "INVALID_DATE_REFERENCE"
    # nomeia a competência válida — erro acionável, não "vazio"
    assert "2026-08" in exc.value.mensagem


@pytest.mark.parametrize("ruim", ["2026-13", "202608", "26-08", "", "ontem"])
def test_validar_data_referencia_rejeita_formato(ruim):
    with pytest.raises(EntradaInvalida) as exc:
        validation.validar_data_referencia(ruim)
    assert exc.value.codigo == "INVALID_DATE_REFERENCE"


def test_validar_data_referencia_aceita_igual_ao_maximo():
    assert validation.validar_data_referencia("2026-08", max_ref="2026-08") == "2026-08"


def test_validar_tipo_item():
    assert validation.validar_tipo_item("Composicao") == "composicao"
    with pytest.raises(EntradaInvalida) as exc:
        validation.validar_tipo_item("banana")
    assert exc.value.codigo == "INVALID_TIPO_ITEM"


# ───────────────────────── S-01 · curva ABC não descarta códigos ─────────────

def _db_exec(sequences):
    """Sessão mockada whose `.execute(...).fetchall()` returns each row list."""
    db = Mock()
    results = list(sequences)

    def _execute(*_args, **_kwargs):
        res = Mock()
        res.fetchall.return_value = results.pop(0) if results else []
        res.fetchone.return_value = None
        res.first.return_value = None
        return res

    db.execute.side_effect = _execute
    return db


def _row(**kw):
    r = Mock()
    r._mapping = kw
    return r


def test_curva_abc_codigo_nao_resolvido_e_erro_nomeado():
    """4750 é insumo: a curva NÃO pode responder 200 com o subconjunto."""
    db = _db_exec([
        [_row(codigo=99803)],                       # composições ativas encontradas
        [],                                          # curva vazia (irrelevante)
    ])
    with pytest.raises(NaoResolvido) as exc:
        crud.get_abc_curve_for_composicoes(
            db, codigos=[99803, 4750], uf="SP", data_referencia="2026-08", regime="NAO_DESONERADO",
        )
    assert exc.value.codigo == "CODES_NAO_RESOLVIDOS"
    assert "4750" in str(exc.value)
    assert "99803" not in str(exc.value).split("4750")[0].split("não")[-1]


def test_curva_abc_somente_composicao_ativa_conta():
    """A checagem de existência filtra `status` — composition inativa não vale."""
    db = Mock()
    captured = {}

    def _execute(query, *_a, **_k):
        captured["sql"] = str(query)
        captured["params"] = _a[0] if _a else {}
        res = Mock()
        res.fetchall.return_value = [_row(codigo=99803)]
        res.first.return_value = None
        return res

    db.execute.side_effect = _execute
    with pytest.raises(NaoResolvido):
        crud.get_abc_curve_for_composicoes(
            db, codigos=[99803, 4750], uf="SP", data_referencia="2026-08", regime="NAO_DESONERADO",
        )
    assert "status" in captured["sql"].lower()
    assert captured["params"].get("status")


def test_curva_abc_todas_composicoes_validas_processa_todas():
    """Sem código órfão, a curva segue aggregating all requested composições."""
    db = _db_exec([
        [_row(codigo=99803), _row(codigo=98676)],
        [_row(codigo=6111, descricao="SERVENTE", unidade="H", custo_impacto_total=60.0),
         _row(codigo=4750, descricao="PEDREIRO", unidade="H", custo_impacto_total=40.0)],
    ])
    itens = crud.get_abc_curve_for_composicoes(
        db, codigos=[99803, 98676], uf="SP", data_referencia="2026-08", regime="NAO_DESONERADO",
    )
    assert [i["codigo"] for i in itens] == [6111, 4750]
    assert round(sum(i["percentual_individual"] for i in itens), 2) == 100.0


# ───────────────────────── S-04 · auditoria ─────────────────────────────────

def test_audit_normaliza_tipo_item_com_cedilha():
    """O banco guarda `COMPOSICAO` e `COMPOSIÇÃO`: a comparação sem
    normalizar perde 24k linhas. Reusa `_SQL_TIPO_NORM`."""
    db = Mock()
    captured = {}

    def _execute(query, params=None, *_a, **_k):
        captured["sql"] = str(query)
        captured["params"] = params or {}
        res = Mock()
        res.fetchall.return_value = []
        return res

    db.execute.side_effect = _execute
    crud.get_audit_events(db, tipo_item="composicao", codigo=1, data_referencia=None)
    assert "TRANSLATE" in captured["sql"].upper()
    assert captured["params"].get("tipo_norm") == "COMPOSICAO"


def test_ultima_data_auditoria_devolve_a_data_do_evento():
    """O 404 passa a nomear a última data com evento (2021-12 para o 4750)."""
    db = Mock()
    row = Mock()
    row._mapping = {"ultima": "2021-12-01"}
    res = Mock()
    res.first.return_value = row
    db.execute.return_value = res
    assert crud.get_ultima_data_auditoria(db, "insumo", 4750) == "2021-12"


def test_ultima_data_auditoria_none_quando_nao_ha_evento():
    db = Mock()
    res = Mock()
    res.first.return_value = None
    db.execute.return_value = res
    assert crud.get_ultima_data_auditoria(db, "insumo", 999999) is None


# ───────────────────────── S-05 · rótulo do tipo ────────────────────────────

def test_rota_onde_usado_existe_para_insumo_e_composicao():
    """O path passa a carregar o tipo — o `resolver` do MCP nomeia o item certo."""
    from api import main as api_main

    paths = {r.path for r in api_main.app.routes if getattr(r, "path", "").endswith("/onde-usado")}
    assert "/api/v1/public/bi/item/{tipo_item}/{codigo}/onde-usado" in paths
    assert "/api/v1/public/bi/insumo/{codigo}/onde-usado" in paths  # alias legado


def test_schema_aceita_erro_nomeado():
    """`detail` é string prefixed with the code — todo client do ecossistema lê."""
    exc = EntradaInvalida("INVALID_UF", "mensagem")
    assert exc.detail.startswith("INVALID_UF: ")
    assert isinstance(exc.detail, str)
    assert issubclass(NaoResolvido, EntradaInvalida)
    assert NaoResolvido.status_code == 404 and EntradaInvalida.status_code == 400
    assert schemas  # import guard: o módulo continua exposto


# ───────────────────────── S-03 · envelope de busca vazia ────────────────────

def test_build_meta_expoe_motivo():
    """Resultado vazio carrega `motivo` (a busca é resposta, não silêncio)."""
    from api.search import build_meta

    meta = build_meta(["trigram"], total=0, motivo="SEM_RESULTADOS_PARA_O_TERMO")
    assert meta["motivo"] == "SEM_RESULTADOS_PARA_O_TERMO"
    assert meta["total"] == 0
    # `motivo` só aparece quando vazio — busca com resultado não seosta
    assert build_meta(["trigram"], total=5)["motivo"] is None


def test_schema_search_meta_tem_motivo():
    assert schemas.SearchMeta(providers=["trigram"], total=0).model_dump()["motivo"] is None
    assert schemas.SearchMeta(
        providers=["trigram"], total=0, motivo="SEM_RESULTADOS_PARA_O_TERMO",
    ).motivo == "SEM_RESULTADOS_PARA_O_TERMO"


# ───────────────────────── S-02 · preço ausente nunca é 0.0 ───────────────────

def test_aplicar_preco_indisponivel_marca_zero():
    """`0.0` no banco → `null` + sinal. R$ 0,00 silencioso é o pior modo de
    falha num orçamento (o agente soma, formata e entrega)."""
    item = {"valor": 0.0, "descricao": "CONCRETO MAGRO PARA LASTRO"}
    assert crud._aplicar_preco_indisponivel(item) is True
    assert item["valor"] is None
    assert item["preco_disponivel"] is False
    assert item["motivo_indisponivel"] == "SEM_COTACAO_NA_UF"


def test_aplicar_preco_indisponivel_preserva_preco_valido():
    item = {"valor": 27.39}
    assert crud._aplicar_preco_indisponivel(item) is False
    assert item["valor"] == 27.39
    assert item["preco_disponivel"] is True
    assert "motivo_indisponivel" not in item


def test_aplicar_preco_indisponivel_aceita_none_e_texto():
    for valor in (None, "", "abc"):
        item = {"valor": valor}
        assert crud._aplicar_preco_indisponivel(item) is True
        assert item["valor"] is None


def test_run_search_conta_itens_sem_preco():
    """O envelope avisa QUANTOS itens vieram sem preço (o agente precisa)."""
    db = Mock()
    linhas = [
        _row(codigo=1, valor=10.0, total_count=4),
        _row(codigo=2, valor=0.0, total_count=4),
        _row(codigo=3, valor=None, total_count=4),
        _row(codigo=4, valor=5.0, total_count=4),
    ]
    res = db.execute.return_value
    res.fetchall.return_value = linhas
    out = crud._run_search(db, text("SELECT 1"), {})
    assert out["total"] == 4
    assert out["total_itens_sem_preco"] == 2
    assert out["proporcao_sem_preco"] == 50.0
    assert [i["valor"] for i in out["items"]] == [10.0, None, None, 5.0]


def test_run_search_sem_itens_sem_preco_nao_inventa_contador():
    db = Mock()
    db.execute.return_value.fetchall.return_value = [_row(codigo=1, valor=3.0, total_count=1)]
    out = crud._run_search(db, text("SELECT 1"), {})
    assert "total_itens_sem_preco" not in out
    assert "proporcao_sem_preco" not in out


def test_composicao_sem_preco_vira_null_com_motivo():
    """§3.4 já sinalizava; S-02 tira o 0.0 e nomeia o motivo."""
    db = _db_with_row_composicao(custo_total=0)
    out = crud.get_composicao_by_codigo(db, codigo=98676, uf="SP",
                                        data_referencia="2026-08", regime="NAO_DESONERADO")
    assert out["preco_disponivel"] is False
    assert out["custo_total"] is None
    assert out["motivo_indisponivel"] == "SEM_COTACAO_NA_UF"


def _db_with_row_composicao(custo_total):
    db = Mock()
    row = Mock()
    row._mapping = {
        "codigo": 98676, "descricao": "COMPOSICAO", "unidade": "m2", "grupo": "ESTRUTURA",
        "status": "ATIVO", "custo_total": custo_total, "percentual_mo": None,
        "created_at": None, "updated_at": None, "sinapi_versao": "2026.08",
        "versao_preco": "2026.08",
    }
    db.execute.return_value.first.return_value = row
    return db
