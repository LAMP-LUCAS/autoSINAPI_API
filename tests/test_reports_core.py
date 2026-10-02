"""Testes do núcleo: modelo determinístico e SVG.

Nenhum banco, nenhuma rede. Se estes testes precisam de ambiente, o desenho
está errado — o núcleo tem que ser testável em qualquer máquina.
"""

import re
from decimal import Decimal

from api.reports import charts
from api.reports.model import (Bloco, Categoria, Contexto, Metrica, Relatorio,
                               Serie)

D = Decimal


# ── Modelo ───────────────────────────────────────────────────────────────────

def test_relatorio_com_conteudo_igual_tem_assinatura_igual():
    """A assinatura é do CONTEÚDO, não da data de geração.

    É o que permite dizer "não mudou, não mando": se a assinatura bate, o
    lead já viu exatamente isso.
    """
    r = lambda: Relatorio(chave="incc_leitura_mes", titulo="INCC", resumo="Subiu",
                          blocos=[Bloco(metricas=[Metrica("Mês", "1.296,33")])])
    assert r().assinatura() == r().assinatura()


def test_assinatura_muda_quando_o_numero_muda():
    a = Relatorio("k", "t", "r", [Bloco(metricas=[Metrica("Mês", "1.296,33")])])
    b = Relatorio("k", "t", "r", [Bloco(metricas=[Metrica("Mês", "1.296,34")])])
    assert a.assinatura() != b.assinatura()


def test_assinatura_muda_quando_a_metrica_sai_do_lugar():
    """Reordenarput em outro bloco ainda é mudança de relatório.

    Se fosse igual, um reshuffle de seção passaria como "não mudou" e o lead
    receberia o mesmo e-mail com números trocados de posição — confuso sem
    ser novo.
    """
    m1 = Metrica("A", "1")
    m2 = Metrica("B", "2")
    x = Relatorio("k", "t", "r", [Bloco(metricas=[m1, m2])])
    y = Relatorio("k", "t", "r", [Bloco(metricas=[m2, m1])])
    assert x.assinatura() != y.assinatura()


def test_contexto_segmenta_por_estagio():
    novo = Contexto("1", "a@b.c", "A", dias_de_relacionamento=5)
    madura = Contexto("2", "a@b.c", "A", dias_de_relacionamento=45)
    cliente = Contexto("3", "a@b.c", "A", dias_de_relacionamento=5, eh_cliente=True)
    assert novo.segmento == "novo"
    assert madura.segmento == "madura"
    assert cliente.segmento == "cliente", "assinatura manda sobre tempo"


def test_contexto_lembra_o_que_ja_enviou():
    c = Contexto("1", "a@b.c", "A", etapas_enviadas=("incc_leitura_mes",))
    assert c.ja_enviou("incc_leitura_mes")
    assert not c.ja_enviou("cub_dispersao")


# ── Gráficos ─────────────────────────────────────────────────────────────────

def _serie(n=6):
    return Serie("INCC-M", [(f"2026-0{i+1}", D(str(1 + i * 0.1))) for i in range(n)])


def test_svg_tem_svg_valido_e_acessivel():
    svg = charts.linha_serie(_serie())
    assert svg.startswith("<svg") and svg.endswith("</svg>")
    assert 'role="img"' in svg, "sem role=img o leitor de tela não lê"
    assert "aria-label=" in svg


def test_svg_escapa_caractere_invalido():
    """`&` ou `<` no rótulo quebraria o XML e o e-mail inteiro."""
    svg = charts.linha_serie(Serie("INCC < M & DI", [(f"p{i}", D(i)) for i in range(3)]))
    rotulo = svg.split('aria-label="')[1].split('"')[0]
    assert "&amp;" in rotulo and "&lt;" in rotulo
    assert "<" not in rotulo and ">" not in rotulo


def test_svg_deterministico():
    s = _serie()
    assert charts.linha_serie(s) == charts.linha_serie(s), "mesma entrada, saída diferente"


def test_serie_vazia_nao_gera_svg():
    assert charts.linha_serie(Serie("vazia", [])) == ""
    assert charts.linha_serie(Serie("1 ponto", [("a", D(1))])) == ""


def test_serie_constante_nao_divide_por_zero():
    """Série plana é comum (índice parado); não pode explodir."""
    svg = charts.linha_serie(Serie("const", [(f"p{i}", D("1.0")) for i in range(5)]))
    assert svg.startswith("<svg")
    assert "NaN" not in svg and "inf" not in svg.lower()


def test_indice_nao_e_rotulado_como_percentual():
    """INCC-M é índice (1.296,33); a variação é taxa (0,66%).

    Sem a distinção explícita, o índice sai como "129.633,00%" — e as duas
    séries convivem no mesmo relatório.
    """
    indice = Serie("INCC-M", [("a", D("1296.33")), ("b", D("1296.33"))],
                   em_percentual=False)
    svg = charts.linha_serie(indice)
    rotulo = re.findall(r"<text[^>]*>([^<]+)</text>", svg)
    assert rotulo == ["1.296,33"], f"índice com rótulo errado: {rotulo}"
    assert "129.633" not in svg, "índice tratado como taxa"


def test_grafico_rotula_em_percentual_como_a_tabela():
    """A série vem em decimal (0.0066 = 0,66%).

    Sem multiplicar por 100, o rótulo do gráfico mostra "0.01" enquanto a
    tabela diz "+0,66%" — o mesmo dado com duas respostas no mesmo e-mail.
    """
    serie = Serie("INCC-M", [("jul", D("0.0061")), ("ago", D("0.0066"))])
    svg = charts.linha_serie(serie)
    assert "0,66%" in svg, "rótulo do gráfico não converteu para percentual"
    assert "0.01" not in svg, "gráfico ainda mostra o decimal cru"
    assert "0,61%" in svg and "0,66%" in svg, "aria-label sem percentual"


def test_barras_rotulam_e_valoram():
    svg = charts.barras("CUB", [("Sul", D("2746.16")), ("Sudeste", D("2282.54"))])
    assert svg.startswith("<svg")
    assert "Sul" in svg and "Sudeste" in svg
    assert "2.746,16" in svg


def test_barras_exigem_dois_pontos():
    assert charts.barras("CUB", [("Só um", D(1))]) == ""


def test_duas_series_tem_legenda():
    a = Serie("INCC-M", [(f"p{i}", D(i)) for i in range(4)])
    b = Serie("INCC-DI", [(f"p{i}", D(i + 0.5)) for i in range(4)])
    svg = charts.duas_seris(a, b)
    assert "INCC-M" in svg and "INCC-DI" in svg, "sem legenda não dá pra saber qual é qual"


def test_svg_nao_carrega_nada_externo():
    """Nada de recurso externo, script ou handler.

    `xmlns="http://www.w3.org/2000/svg"` é o namespace do SVG — não é
    carregamento. O que não pode aparecer é `https://` (imagem remota), `<img>`,
    `<script>` ou `on*=`.
    """
    svg = charts.linha_serie(_serie())
    for proibido in ("https://", "xlink:href", "<script", "<img", "onload=",
                     "onclick=", "<foreignObject"):
        assert proibido not in svg, f"SVG com referência externa: {proibido}"
    # o namespace é obrigatório para o SVG ser interpretado
    assert 'xmlns="http://www.w3.org/2000/svg"' in svg
