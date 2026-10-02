"""api/reports/charts.py — SVG inline determinístico.

Funções puras: mesma entrada → mesma string, sempre. Sem JS, sem `<img>`
externo, sem CDN. SVG inline é o único gráfico que sobrevive a Gmail e
Outlook modernos sem carregar nada de fora.

Por que SVG e não imagem hospedada
----------------------------------
`src/href` para um host externo quebra em clientes que bloqueiam rastreamento
— e o número some junto com a imagem. Como SVG, o gráfico viaja dentro do
próprio e-mail e não depende de nenhum terceiro.

Por que o número está sempre também em texto
--------------------------------------------
Renderização de SVG em e-mail é *melhor esforço*: cliente antigo, cliente
corporativo com sanitizador, modo texto. Por isso `render/html.py` escreve a
tabela **antes** do gráfico. O SVG reforça; nunca é o único portador.

Acessibilidade
--------------
`role="img"` com `<title>`/`aria-label`: leitor de tela lê o rótulo. O
conteúdo numérico também está na tabela, então nenhuma informação depende
exclusivamente do visual.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional, Sequence

from .model import Serie

# Largura de conteúdo dos e-mails atuais (os templates usam 100%). 600px é o
# mínimo confortável para uma linha e 2 colunas lado a lado.
LARGURA = 600
ALTURA_LINHA = 150
ALTURA_BARRAS = 160
MARGEM = 8

# Paleta derivada dos tokens dos templates: fundo claro, texto escuro.
# Contraste do texto sobre o fundo passa WCAG AA (verificado em teste).
COR_LINHA = "#3b82f6"
COR_LINHA_2 = "#f97316"
COR_EIXO = "#8b98a5"
COR_GRADE = "#e6eaee"
COR_FUNDO_AREA = "#f7f9fb"
COR_ROTULO = "#42505e"

# XML exige escaping. Um título com `&` quebraria o e-mail inteiro.
_ESCAPES = (("&", "&amp;"), ("<", "&lt;"), (">", "&gt;"), ('"', "&quot;"))


def _esc(t: str) -> str:
    for a, b in _ESCAPES:
        t = t.replace(a, b)
    return t


def _fmt(v: Decimal, casas: int = 2) -> str:
    """Formata Decimal com separador brasileiro, sem `float` no meio."""
    q = Decimal(1).scaleb(-casas)
    s = f"{v.quantize(q):,.{casas}f}"      # separador de milhar US
    return s.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def _pct(v: Decimal, casas: int = 2) -> str:
    """Percentual no formato brasileiro, a partir do decimal.

    As séries chegam em decimal (0.0066 = 0,66%). Reutiliza o mesmo formato
    de `fontes.pct` para que o rótulo do gráfico e o da tabela não divirjam —
    dois números diferentes para o mesmo dado no mesmo e-mail é o tipo de erro
    que faz o leitor desconfiar de todo o relatório.
    """
    return f"{_fmt(v * 100, casas)}%"


def _escala(valores: Sequence[Decimal], altura_util: int):
    """Mapeia valores → pixels Y. Retorna também o zero, para barras."""
    lo, hi = min(valores), max(valores)
    if hi == lo:
        hi = lo + Decimal(1)          # série constante não divide por zero
    return lo, hi, altura_util, Decimal(hi - lo) or Decimal(1)


def linha_serie(serie: Serie, largura: int = LARGURA,
                altura: int = ALTURA_LINHA, cor: str = COR_LINHA) -> str:
    """Linha temporal com rótulo do último ponto.

    Sem eixos numéricos: num e-mail o número exato já está na tabela. O
    gráfico serve para a *forma* — se está subindo, se está parado.
    """
    if serie.vazia:
        return ""
    rotulo = _esc(serie.rotulo)
    pontos = serie.pontos
    n = len(pontos)
    ux = largura - 2 * MARGEM
    uy = altura - 2 * MARGEM - 14        # 14px reservados ao rótulo
    lo, hi, _, span = _escala(serie.valores(), uy)

    def px(i: int) -> float:
        return MARGEM + (ux * i / (n - 1) if n > 1 else ux / 2)

    def py(v: Decimal) -> float:
        return MARGEM + uy - float((v - lo) / span) * uy

    d = " ".join(("M" if i == 0 else "L") + f"{px(i):.1f},{py(v):.1f}"
                 for i, (_, v) in enumerate(pontos))
    ultimo_x, ultimo_y = px(n - 1), py(pontos[-1][1])
    # A série vem em decimal (0.0066 = 0,66%): multiplica por 100 como `pct`,
    # senão o rótulo do gráfico mostra "0.01" enquanto a tabela diz "+0,66%".
    valor_final = (_pct if serie.em_percentual else _fmt)(pontos[-1][1])
    rotulo_val = _esc(f"{valor_final}{serie.sufixo}")

    return (
        f'<svg width="{largura}" height="{altura}" viewBox="0 0 {largura} {altura}" '
        f'role="img" aria-label="{rotulo}: {(_pct if serie.em_percentual else _fmt)(pontos[0][1])} a {(_pct if serie.em_percentual else _fmt)(pontos[-1][1])}" '
        f'style="display:block;width:100%;max-width:{largura}px;height:auto" '
        f'xmlns="http://www.w3.org/2000/svg">'
        f'<rect width="{largura}" height="{altura}" fill="{COR_FUNDO_AREA}" rx="8"/>'
        f'<path d="{d}" fill="none" stroke="{cor}" stroke-width="2.5" '
        f'stroke-linecap="round" stroke-linejoin="round"/>'
        f'<circle cx="{ultimo_x:.1f}" cy="{ultimo_y:.1f}" r="4" fill="{cor}"/>'
        f'<text x="{largura - MARGEM}" y="{altura - 4}" text-anchor="end" '
        f'font-family="Arial,Helvetica,sans-serif" font-size="13" font-weight="700" '
        f'fill="{COR_ROTULO}">{rotulo_val}</text>'
        f"</svg>"
    )


def barras(rotulo: str, pontos: Sequence[tuple[str, Decimal]],
            largura: int = LARGURA, altura: int = ALTURA_BARRAS,
            cor: str = COR_LINHA, formatar=None) -> str:
    """Barras verticais para comparação (ex.: CUB por região).

    `pontos` é [(rótulo, valor)]. Rótulos longos são truncados pelo
    chamador — aqui só entra o que cabe.
    """
    if len(pontos) < 2:
        return ""
    n = len(pontos)
    ux = largura - 2 * MARGEM
    uy = altura - 2 * MARGEM - 22
    valores = [v for _, v in pontos]
    maximo = max(valores)
    minimo = min(0, min(valores))
    span = (maximo - minimo) or Decimal(1)
    gap = 6
    bw = max(6.0, (ux - gap * (n - 1)) / n)
    fmt = formatar or (lambda v: _fmt(v, 2))

    barras_svg = []
    for i, (rot, v) in enumerate(pontos):
        x = MARGEM + i * (bw + gap)
        altura_barra = float((v - minimo) / span) * uy
        y = MARGEM + uy - altura_barra
        barras_svg.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" '
            f'height="{max(altura_barra, 1):.1f}" fill="{cor}" rx="3"/>'
            f'<text x="{x + bw / 2:.1f}" y="{altura - 12}" text-anchor="middle" '
            f'font-family="Arial,Helvetica,sans-serif" font-size="11" '
            f'fill="{COR_ROTULO}">{_esc(_curto(rot, 9))}</text>'
            f'<text x="{x + bw / 2:.1f}" y="{max(y - 5, 10):.1f}" text-anchor="middle" '
            f'font-family="Arial,Helvetica,sans-serif" font-size="11" font-weight="700" '
            f'fill="{COR_ROTULO}">{_esc(fmt(v))}</text>'
        )

    return (
        f'<svg width="{largura}" height="{altura}" viewBox="0 0 {largura} {altura}" '
        f'role="img" aria-label="{_esc(rotulo)}" '
        f'style="display:block;width:100%;max-width:{largura}px;height:auto" '
        f'xmlns="http://www.w3.org/2000/svg">'
        f'<rect width="{largura}" height="{altura}" fill="{COR_FUNDO_AREA}" rx="8"/>'
        f'<line x1="{MARGEM}" y1="{MARGEM + uy:.1f}" x2="{largura - MARGEM}" '
        f'y2="{MARGEM + uy:.1f}" stroke="{COR_GRADE}" stroke-width="1"/>'
        + "".join(barras_svg) + "</svg>"
    )


def _curto(t: str, n: int) -> str:
    t = t.strip()
    return t if len(t) <= n else t[: n - 1] + "…"


def duas_seris(s1: Serie, s2: Serie, largura: int = LARGURA,
               altura: int = ALTURA_LINHA) -> str:
    """Duas séries sobrepostas (ex.: INCC-M × INCC-DI).

    A comparação entre M e DI só é legível sobreposta: separado, vira dois
    gráficos que o leitor tem de somar de cabeça — que é o oposto de insight.
    """
    if s1.vazia and s2.vazia:
        return ""
    altura_legenda = 34
    uy = altura - 2 * MARGEM - altura_legenda
    ux = largura - 2 * MARGEM
    n = max(len(s1.pontos), len(s2.pontos))
    todos = list(s1.valores()) + list(s2.valores())
    lo, hi, _, span = _escala(todos, uy)

    def caminho(pontos):
        m = len(pontos)
        def px(i):
            return MARGEM + (ux * i / (n - 1) if n > 1 else ux / 2)
        def py(v):
            return MARGEM + uy - float((v - lo) / span) * uy
        return " ".join(("M" if i == 0 else "L") + f"{px(i):.1f},{py(v):.1f}"
                        for i, (_, v) in enumerate(pontos))

    partes = []
    for s, cor in ((s1, COR_LINHA), (s2, COR_LINHA_2)):
        if not s.vazia:
            partes.append(f'<path d="{caminho(s.pontos)}" fill="none" '
                          f'stroke="{cor}" stroke-width="2.5" '
                          f'stroke-linecap="round" stroke-linejoin="round"/>')
    legenda = "".join(
        f'<rect x="{MARGEM + i * 150}" y="{altura - 14}" width="10" height="10" '
        f'fill="{cor}" rx="2"/>'
        f'<text x="{MARGEM + i * 150 + 15}" y="{altura - 5}" '
        f'font-family="Arial,Helvetica,sans-serif" font-size="11" '
        f'fill="{COR_ROTULO}">{_esc(s.rotulo)}</text>'
        for i, (s, cor) in enumerate(((s1, COR_LINHA), (s2, COR_LINHA_2)))
        if not s.vazia)

    return (
        f'<svg width="{largura}" height="{altura}" viewBox="0 0 {largura} {altura}" '
        f'role="img" aria-label="{_esc(s1.rotulo)} e {_esc(s2.rotulo)}" '
        f'style="display:block;width:100%;max-width:{largura}px;height:auto" '
        f'xmlns="http://www.w3.org/2000/svg">'
        f'<rect width="{largura}" height="{altura}" fill="{COR_FUNDO_AREA}" rx="8"/>'
        + "".join(partes) + legenda + "</svg>"
    )


__all__ = ["linha_serie", "barras", "duas_seris", "LARGURA",
           "COR_LINHA", "COR_LINHA_2"]
