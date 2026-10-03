"""O payload de cada slot tem que ser o do slot.

Regressão que estes testes travam: `_envelope` escolhia template por
`isinstance(rel, Relatorio)`, que só separa relatório de artigo. Recuperação e
promoção também são dicts — as duas caíam no ramo do artigo e saíam com
assunto "— Knowledge Base" e variáveis `article_*`. Nenhum erro, nenhum log:
apenas um e-mail que ninguém desenhou.

A mesma falha, do lado oposto, continuava depois daquele arranjo: o **artigo**
ia para `gateway_lead_welcome` (declara `lead_name, portal_url, tools_url`,
não tem `article_*`), então o conteúdo era descartado e o href
`{{ portal_url }}/app/sinapi` saía relativo — em 03/10 o artigo **não era
enviado**, só um e-mail de boas-vindas. O slot, e não o tipo do objeto, é
quem escolhe.

Também trava que cada template recebe as variáveis que o `registry.yaml`
declara. O `gateway_reengagement` interpola `{{ desconto }}`/`{{ cupom }}` sem
guarda — sem eles o e-mail sai "Volte com % off ... use o cupom .".

O contrato cruzado completo (produtor × registry) vive em
`saas-gateway/tests/test_email_funnel_slots.py`.
"""

from api.crm_conteudo import (AGENDA_URL, PORTAL_URL, TEMPLATE_ARTIGO,
                              TEMPLATE_PROMO, TEMPLATE_RELATORIO,
                              TEMPLATE_REENGAGEMENT, TOOLS_URL,
                              WINBACK_CUPOM, WINBACK_DESCONTO, _envelope)
from api.reports.model import Contexto


class _Artigo(dict):
    """Disfarça de relatório para o `_envelope` cair no ramo errado."""


CTX = Contexto(lead_id="l1", email="alguem@exemplo.invalid", nome="Ana")


def _relatorio():
    """Formato real: métrica + série, como os 9 relatórios do catálogo.

    Um relatório sem `metricas` e sem `series` não existe em produção — e o
    contrato da Fase 4 é que a tabela numérica e o SVG **sempre** saiam. Sem
    isso aqui, o teste passaria sem nunca exercitar a parte nova.
    """
    from decimal import Decimal
    from api.reports.model import (Bloco, Categoria, Metrica, Relatorio,
                                   Serie)
    return Relatorio(chave="incc_leitura_mes", titulo="INCC 08/2026",
                     resumo="Panorama",
                     categoria=Categoria.INSIGHT,
                     blocos=[Bloco(metricas=[Metrica("INCC-M", "1.296,33",
                                                     "vs +0,61% em julho",
                                                     destaque=True,
                                                     variacao="+0,66%")],
                                   texto="Mercado sobe +0,66%")],
                     series=[Serie(rotulo="INCC-M",
                                   pontos=[("jun", Decimal("1280.00")),
                                           ("jul", Decimal("1288.00")),
                                           ("ago", Decimal("1296.33"))],
                                   em_percentual=False)])


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
    # Fase 2: o link de preferências saiu do payload. Ele é do rodapé que o
    # `EmailSmtpAdapter` aplica a todo e-mail, com URL assinada por
    # destinatário (`SendOS#unsubscribe_url_for`) — o produtor não manda mais
    # uma cópia estática sem token, que dava 404.
    assert "unsubscribe_url" not in env["vars"]


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


# ── relatório e artigo: cada slot com o seu template ────────────────────────

def test_relatorio_vai_para_o_template_de_relatorio():
    """Fase 3: o relatório deixou de ser um "digest de artigo".

    Antes saía por `gateway_kb_digest` com `article_*` — o texto estava
    certo no sentido de que o título viajava, mas o dado não: nenhum número,
    nenhuma tabela, nenhum gráfico. O slot `enriquecimento` agora tem
    template próprio e variáveis granulares ("blocos separados").
    """
    env = _envelope("enriquecimento", _relatorio(), "INCC 08/2026", "<p></p>", CTX)
    assert env["template_id"] == TEMPLATE_RELATORIO
    assert env["topic"] == "gateway.report_weekly"
    assert env["vars"]["titulo"] == "INCC 08/2026"
    assert env["vars"]["metricas"], "tabela numérica vazia"
    assert env["vars"]["grafico_svg"].lstrip().lower().startswith("<svg")
    assert env["vars"]["link_relatorio"].startswith("https://")


def test_artigo_vai_para_o_template_de_artigo():
    """Fase 3: o artigo voltou para `gateway_kb_digest`.

    Ele estava em `gateway_lead_welcome` — template que declara
    `lead_name, portal_url, tools_url` e não tem `article_*`. O render
    descartava o conteúdo e o href `{{ portal_url }}/app/sinapi` saía
    relativo, morto. Verificado em 03/10: o artigo **não era enviado**.
    """
    env = _envelope("artigo", {"chave": "kb_x", "titulo": "Como orçar",
                               "descricao": "d", "url": "u"}, "Como orçar",
                    "<p></p>", CTX)
    assert env["template_id"] == TEMPLATE_ARTIGO
    assert env["topic"] == "gateway.kb_digest"
    assert env["vars"]["article_title"] == "Como orçar"
    assert env["vars"]["article_url"] == "u"
    assert env["assunto"].endswith("— Knowledge Base")


def test_slot_desconhecido_falha_alto_em_vez_de_mandar_e_mail_errado():
    """Um slot novo não pode cair num ramo por acaso do tipo do objeto.

    `/decidir` devolvendo 500 não envia nada — é o comportamento que
    queremos: nada errado na caixa de entrada é melhor que errado em silêncio.
    """
    import pytest
    from api.crm_conteudo import _template_do_slot
    with pytest.raises(ValueError, match="slot sem template"):
        _template_do_slot("inexistente")


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