"""O payload de cada slot tem que ser o do slot.

Regressão que estes testes travam: `_envelope` escolhia template por
`isinstance(rel, Relatorio)`, que só separa relatório de artigo. Recuperação e
promoção também são dicts — as duas caíam no ramo do artigo e saíam com
assunto "— Knowledge Base" e variáveis `article_*`. Nenhum erro, nenhum log:
apenas um e-mail que ninguém desenhou.

Também trava que cada template recebe as variáveis que o `registry.yaml`
declara. O `gateway_reengagement` interpola `{{ desconto }}`/`{{ cupom }}` sem
guarda — sem eles o e-mail sai "Volte com % off ... use o cupom .".
"""

from api.crm_conteudo import (AGENDA_URL, PORTAL_URL, TEMPLATE_ARTIGO,
                              TEMPLATE_ID, TEMPLATE_PROMO, TEMPLATE_REENGAGEMENT,
                              TOOLS_URL, UNSUBSCRIBE, WINBACK_CUPOM,
                              WINBACK_DESCONTO, _envelope)
from api.reports.model import Contexto


class _Artigo(dict):
    """Disfarça de relatório para o `_envelope` cair no ramo errado."""


CTX = Contexto(lead_id="l1", email="alguem@exemplo.invalid", nome="Ana")


def _relatorio():
    from api.reports.model import Bloco, Categoria, Relatorio
    return Relatorio(chave="incc_leitura_mes", titulo="INCC 08/2026",
                     resumo="Panorama",
                     categoria=Categoria.INSIGHT,
                     blocos=[Bloco(texto="Mercado sobe +0,66%")])


# ── winback ──────────────────────────────────────────────────────────────────

def test_winback_usa_o_template_de_reengajamento():
    env = _envelope("winback", {"chave": "winback_30d", "titulo": "x"}, "x",
                    "<p></p>", CTX)
    assert env["template_id"] == TEMPLATE_REENGAGEMENT
    assert env["topic"] == "gateway.reengagement"
    assert env["topic"] != "gateway.lead_welcome"


def test_winback_nao_vaza_assunto_de_artigo():
    env = _envelope("winback", {"chave": "winback_30d", "titulo": "x"}, "x",
                    "<p></p>", CTX)
    assert "Knowledge Base" not in env["assunto"]


def test_winback_traz_a_oferta_que_o_template_interpola():
    """Sem `desconto`/`cupom` o corpo sai truncado — o liquid não tem guarda."""
    env = _envelope("winback", {"chave": "winback_30d", "titulo": "x"}, "x",
                    "<p></p>", CTX)
    v = env["vars"]
    assert v["desconto"] == WINBACK_DESCONTO and str(v["desconto"]) != ""
    assert v["cupom"] == WINBACK_CUPOM and v["cupom"] != ""
    assert v["lead_name"] == "Ana"
    assert v["agenda_url"] == AGENDA_URL
    assert v["portal_url"] == PORTAL_URL
    assert v["unsubscribe_url"] == UNSUBSCRIBE


def test_winback_nao_herda_variaveis_de_artigo():
    env = _envelope("winback", {"chave": "winback_30d", "titulo": "x"}, "x",
                    "<p></p>", CTX)
    assert "article_title" not in env["vars"]
    assert "article_description" not in env["vars"]


# ── promo ───────────────────────────────────────────────────────────────────

def test_promo_usa_o_template_de_panorama():
    env = _envelope("promo", {"chave": "promo", "titulo": "x"}, "x",
                    "<p></p>", CTX)
    assert env["template_id"] == TEMPLATE_PROMO
    assert env["topic"] == "gateway.update_incc"


def test_promo_nao_vaza_assunto_de_artigo():
    env = _envelope("promo", {"chave": "promo", "titulo": "x"}, "x",
                    "<p></p>", CTX)
    assert "Knowledge Base" not in env["assunto"]


def test_promo_carrega_competencia_e_destaque(monkeypatch):
    """A campanha antiga mandava sem os dois, e o liquid caía no genérico."""
    from api.reports import registro
    monkeypatch.setattr(registro, "panorama_incc",
                        lambda: ("08/2026", "08/26: +0,66% · acelerando"))
    env = _envelope("promo", {"chave": "promo", "titulo": "x"}, "x",
                    "<p></p>", CTX)
    assert env["vars"]["competencia"] == "08/2026"
    assert env["vars"]["destaque"] == "08/26: +0,66% · acelerando"
    assert "08/2026" in env["assunto"]


def test_promo_sem_incc_nao_quebra(monkeypatch):
    from api.reports import registro
    monkeypatch.setattr(registro, "panorama_incc", lambda: ("", ""))
    env = _envelope("promo", {"chave": "promo", "titulo": "x"}, "x",
                    "<p></p>", CTX)
    assert env["vars"]["competencia"] == ""
    assert env["assunto"]  # sem INCC ainda precisa de assunto legível


# ── relatório e artigo continuam como eram ──────────────────────────────────

def test_relatorio_continua_no_kb_digest():
    env = _envelope("enriquecimento", _relatorio(), "INCC 08/2026", "<p></p>", CTX)
    assert env["template_id"] == TEMPLATE_ID
    assert env["topic"] == "gateway.kb_digest"
    assert env["vars"]["article_title"] == "INCC 08/2026"


def test_artigo_continua_no_lead_welcome():
    env = _envelope("artigo", {"chave": "kb_x", "titulo": "Como orçar",
                               "descricao": "d", "url": "u"}, "Como orçar",
                    "<p></p>", CTX)
    assert env["template_id"] == TEMPLATE_ARTIGO
    assert env["topic"] == "gateway.lead_welcome"
    assert env["assunto"].endswith("— Knowledge Base")


# ── panorama_incc ───────────────────────────────────────────────────────────

def test_panorama_separa_competencia_do_destaque():
    """A competência não pode aparecer duas vezes no mesmo e-mail."""
    import datetime
    from decimal import Decimal
    from api.reports import registro
    # `var_m` é fração: 0.0066 vira "+0,66%" depois do ×100 de `pct`.
    linhas = [{"var_m": Decimal("0.0066"), "data_id": datetime.date(2026, 8, 1)},
              {"var_m": Decimal("0.0040"), "data_id": datetime.date(2026, 7, 1)}]
    monkey = registro._incc
    registro._incc = lambda: linhas
    try:
        comp, destaque = registro.panorama_incc()
    finally:
        registro._incc = monkey
    assert comp == "08/2026"
    assert "08/2026" not in destaque
    assert "0,66" in destaque


def test_panorama_sem_dado_devolve_vazio():
    from api.reports import registro
    monkey = registro._incc
    registro._incc = lambda: []
    try:
        assert registro.panorama_incc() == ("", "")
    finally:
        registro._incc = monkey