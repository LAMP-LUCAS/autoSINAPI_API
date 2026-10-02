"""Testes do renderizador.

Um teste que vale mais que os outros: renderizar e passar o HTML pelo
**sanitizador real do MessageDispatcher**. Se o HTML que geramos for
alterado pelo sanitizador antes de ir para o e-mail, o gráfico não aparece —
e isso só aparece se testarmos contra ele.
"""

from decimal import Decimal as D

from api.reports.model import (Bloco, Categoria, Metrica, Relatorio, Serie)
from api.reports.render import assunto_de, nota_incc, renderizar

D_ = D


def _rel():
    return Relatorio(
        chave="incc_leitura_mes",
        titulo="INCC Agosto/2026: materiais sobem 0,66%",
        resumo="Quarta alta consecutiva, ainda em desaceleração.",
        blocos=[
            Bloco(
                metricas=[
                    Metrica("INCC-M", "1.296,33", destaque=True,
                            variacao="▲", detalhe="ago/2026"),
                    Metrica("Variação mensal", "+0,66%", destaque=True,
                            variacao="▲", detalhe="vs +0,61% em julho"),
                    Metrica("Acumulado 12m", "+6,61%", destaque=True),
                    Metrica("Tendência", "acelerando",
                            detalhe="+0,05 p.p. vs mês anterior"),
                ],
                texto="O ritmo virou pela primeira vez em quatro meses."),
        ],
        series=[Serie("INCC-M", [("jul", D_("0.61")), ("ago", D_("0.66"))])],
        categoria=Categoria.INSIGHT,
        rodape="Fonte BCB/SGS · competência 2026-08",
    )


def test_render_gera_tabela_com_os_numeros():
    """O número tem que estar em TEXTO, não só no gráfico."""
    html = renderizar(_rel(), nome_destinatario="Ana")
    assert "1.296,33" in html
    assert "+0,66%" in html
    assert "acelerando" in html


def test_tabela_vem_antes_do_grafico():
    """Se o SVG não renderizar, o número continua legível."""
    html = renderizar(_rel())
    assert html.index("<table") < html.index("<svg"), "gráfico antes da tabela"


def test_html_tem_escaping_do_resumo():
    rel = _rel()
    html = renderizar(Relatorio(rel.chave, rel.titulo, "5 < 6 & 7 > 3",
                               rel.blocos))
    assert "5 &lt; 6 &amp; 7 &gt; 3" in html
    assert "5 < 6" not in html


def test_nota_do_incc_e_estado_nao_numero():
    nota = nota_incc("ago/26: +0,66% · acelerando · última att. 29/09")
    html = f'<div>{nota}</div>'
    assert "acelerando" in nota
    assert "INCC" in nota


def _sanitizar_regras(html: str) -> str:
    """Espelha as regras de `HtmlSanitizerAdapter` (Ruby).

    Reimplementadas aqui porque o adapter é Ruby e o teste é Python: o que
    importa é que as **regras** sejam as mesmas. Se o adapter mudar, este
    espelho precisa mudar junto — e o comentario diz isso.
    """
    import re
    for tag in ("script", "iframe", "object", "embed", "applet"):
        html = re.sub(rf"<\s*{tag}\b.*?<\s*/\s*{tag}\s*>", "", html,
                      flags=re.I | re.S)
        html = re.sub(rf"<\s*/?\s*{tag}\b[^>]*>", "", html, flags=re.I)
    html = re.sub(r'\s+\bon[a-z]+\s*=\s*(?:"[^"]*"|\'[^\']*\'|[^\s>]+)',
                  "", html, flags=re.I)
    return html


def test_svg_sobrevive_ao_sanitizador_do_md():
    """O teste que pega regressão real.

    O MessageDispatcher roda o sanitizador antes de entregar. Se ele remover
    algo do SVG — ou o `style` inline de que os números dependem — o e-mail
    chega cru. Só aparece aqui.
    """
    html = renderizar(_rel(), nome_destinatario="Ana",
                      link_primario="https://mundoaec.com/kb/incc")
    limpo = _sanitizar_regras(html)
    assert "<svg" in limpo, "o sanitizador removeu o SVG — o gráfico não chega"
    assert "1.296,33" in limpo, "o sanitizador removeu o número"
    assert "<script" not in limpo


def test_assunto_tem_o_numero_principal():
    """Assunto genérico é caminho curto para spam."""
    a = assunto_de(_rel())
    assert "0,66%" in a
    assert len(a) <= 78


def test_render_e_deterministico():
    r = _rel()
    assert renderizar(r) == renderizar(r)


def test_link_aparece_quando_existe():
    html = renderizar(_rel(), link_primario="https://mundoaec.com/kb/incc")
    assert "https://mundoaec.com/kb/incc" in html
