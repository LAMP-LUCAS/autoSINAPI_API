"""api/reports/render.py — `Relatorio` → HTML de e-mail.

Puro: recebe o modelo, devolve string. Sem I/O, sem data de agora (a data
entra pelo `Contexto`, o que mantém o HTML reprodutível).

Ordem de leitura deliberada
---------------------------
1. **Resumo** — a conclusão em uma frase. Quem lê só isso já sai sabendo.
2. **Destaques** — no máximo 3 números grandes.
3. **Tabela** — a fonte da verdade, em texto.
4. **Gráfico** — reforço visual, por último.
5. **Nota do INCC** — estado, não número novo.

A tabela vem **antes** do gráfico de propósito: SVG inline é melhor esforço
(cliente antigo, sanitizador corporativo, modo texto). Se o gráfico não
renderizar, o número continua legível.

Estilos são inline e sem media query — é o que sobrevive a cliente de
e-mail. Largura 600px (conteúdo dos templates atuais).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional, Sequence

from . import charts
from .model import Bloco, DESTAQUES_MAX, Formato, Metrica, Relatorio, Serie

# Tokens alinhados aos templates já em produção.
COR_TEXTO = "#0f1419"
COR_SUAVE = "#42505e"
COR_FRACA = "#8b98a5"
COR_BORDA = "#e6eaee"
COR_FUNDO = "#f4f6f8"
COR_LINHA_ACAO = "#3b82f6"

_ESC = (("&", "&amp;"), ("<", "&lt;"), (">", "&gt;"), ('"', "&quot;"))


def _esc(t: object) -> str:
    s = str(t)
    for a, b in _ESC:
        s = s.replace(a, b)
    return s


def _pct(v: Decimal, casas: int = 2) -> str:
    q = Decimal(1).scaleb(-casas)
    s = f"{v.quantize(q) * 100:,.{casas}f}"
    return s.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def _tabela(metricas: Sequence[Metrica]) -> str:
    """Tabela de duas colunas: rótulo à esquerda, valor à direita.

    Duas colunas, e não três: em 600px, uma coluna de detalhe estreita demais
    obriga o cliente a quebrar o número em duas linhas. O detalhe vai abaixo,
    em linha própria, só quando existe.
    """
    linhas = []
    for m in metricas:
        var = (f'<span style="color:{COR_LINHA_ACAO};font-weight:700">'
               f"{_esc(m.variacao)}</span> ") if m.variacao else ""
        linhas.append(
            f'<tr>'
            f'<td style="padding:7px 0;border-bottom:1px solid {COR_BORDA};'
            f'font-size:14px;color:{COR_SUAVE};vertical-align:top">'
            f'{_esc(m.rotulo)}'
            + (f'<br><span style="font-size:12px;color:{COR_FRACA}">'
               f"{_esc(m.detalhe)}</span>" if m.detalhe else "")
            + f"</td>"
            f'<td style="padding:7px 0;border-bottom:1px solid {COR_BORDA};'
            f'text-align:right;font-size:14px;font-weight:700;color:{COR_TEXTO};'
            f'white-space:nowrap">{var}{_esc(m.valor)}</td>'
            f"</tr>")
    return (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="border-collapse:collapse;margin:0 0 16px">'
        + "".join(linhas) + "</table>"
    )


def _destaques(destaques: Sequence[Metrica]) -> str:
    if not destaques:
        return ""
    celulas = []
    for m in destaques:
        var = (f'<div style="font-size:12px;color:{COR_FRACA};margin-top:3px">'
               f"{_esc(m.variacao)}</div>" if m.variacao else "")
        celulas.append(
            f'<td width="33%" style="padding:0 6px;text-align:center;'
            f'vertical-align:top">'
            f'<div style="font:700 22px/1.2 Arial,Helvetica,sans-serif;'
            f'color:{COR_TEXTO}">{_esc(m.valor)}</div>'
            f'<div style="font-size:11px;color:{COR_FRACA};margin-top:4px;'
            f'line-height:1.3">{_esc(m.rotulo)}</div>{var}</td>')
    return (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="background:{COR_FUNDO};border:1px solid {COR_BORDA};'
        'border-radius:10px;margin:0 0 18px"><tr>'
        '<td style="padding:14px 8px">'
        + ('<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>'
           + "".join(celulas) + "</tr></table>")
        + "</td></tr></table>"
    )


def _texto_bloco(b: Bloco) -> str:
    partes = []
    if b.texto:
        partes.append(
            f'<p style="margin:0 0 12px;font:14px/1.6 Arial,Helvetica,sans-serif;'
            f'color:{COR_SUAVE}">{_esc(b.texto)}</p>')
    if b.metricas:
        partes.append(_tabela(b.metricas))
    if b.nota:
        partes.append(
            f'<p style="margin:0 0 14px;font:12px/1.5 Arial,Helvetica,sans-serif;'
            f'color:{COR_FRACA}">{_esc(b.nota)}</p>')
    return "".join(partes)


def _svg(series: Sequence[Serie]) -> str:
    """Só o markup do gráfico, **sem** o wrapper de layout.

    O `<div>` de `_graficos` é layout do HTML gerado em Python. Quando o
    relatório viaja como variáveis para o MessageDispatcher, quem monta o
    layout é o template — então o que sai daqui é o SVG cru, embutido com
    `{{ grafico_svg }}` (o renderizador do MD não escapa HTML).

    Escolha registrada: SVG como variável + tabela montada no template. O SVG
    sozinho não basta porque Gmail/Outlook removem `<svg>` do corpo; a tabela
    numérica é a fonte da verdade e o gráfico é o reforço.
    """
    if len(series) >= 2 and not series[0].vazia and not series[1].vazia:
        return charts.duas_seris(series[0], series[1])
    return "".join(charts.linha_serie(s) for s in series if not s.vazia)


def _graficos(series: Sequence[Serie]) -> str:
    svg = _svg(series)
    return f'<div style="margin:0 0 16px">{svg}</div>' if svg else ""


def svg_do_relatorio(rel: Relatorio) -> str:
    """SVG inline do relatório, pronto para a variável `grafico_svg`."""
    return _svg(rel.series)


def nota_incc(nota: Optional[str]) -> str:
    """Rodapé de estado do INCC.

    Diz *o que* o índice está fazendo e *quando* foi atualizado — nunca
    promete número novo. Sem isso, um relatório semanal mostraria 0,00% três
    semanas seguidas e o leitor pararia de abrir o e-mail.
    """
    if not nota:
        return ""
    return (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="background:{COR_FUNDO};border-left:3px solid {COR_LINHA_ACAO};'
        f'margin:4px 0 16px"><tr><td style="padding:10px 12px;font:12px/1.5 '
        f'Arial,Helvetica,sans-serif;color:{COR_SUAVE}">'
        f'<strong>INCC</strong> — {_esc(nota)}</td></tr></table>'
    )


def renderizar(rel: Relatorio, *, nome_destinatario: str = "Lead",
               nota: Optional[str] = None,
               assunto: Optional[str] = None,
               link_primario: Optional[str] = None,
               texto_link: str = "Abrir a análise completa",
               rodape_extra: Optional[str] = None) -> str:
    """HTML completo do e-mail. Determinístico: mesma entrada, mesma saída."""
    destaques = [m for b in rel.blocos for m in b.metricas if m.destaque][:DESTAQUES_MAX]

    corpo = "".join(_texto_bloco(b) for b in rel.blocos)
    cta = ""
    if link_primario:
        cta = (
            f'<p style="margin:4px 0 18px"><a href="{_esc(link_primario)}" '
            f'style="display:inline-block;background:{COR_LINHA_ACAO};color:#ffffff;'
            f'text-decoration:none;font-weight:700;font-size:14px;padding:11px 20px;'
            f'border-radius:8px">{_esc(texto_link)}</a></p>')

    rodape = "".join(filter(None, [
        f'<p style="margin:20px 0 0;font-size:12px;line-height:1.5;color:{COR_FRACA}">'
        f"{_esc(rel.rodape)}</p>" if rel.rodape else "",
        f'<p style="margin:6px 0 0;font-size:12px;color:{COR_FRACA}">{_esc(rodape_extra)}</p>'
        if rodape_extra else "",
    ]))

    return (
        '<div style="font-family:Arial,Helvetica,sans-serif;color:' + COR_TEXTO + '">'
        f'<h1 style="margin:0 0 8px;font-size:21px;line-height:1.3;color:{COR_TEXTO}">'
        f"{_esc(rel.titulo)}</h1>"
        f'<p style="margin:0 0 16px;font-size:14px;line-height:1.6;color:{COR_SUAVE}">'
        f"Olá <strong>{_esc(nome_destinatario)}</strong> — este é o resumo do "
        f"dado mais recente do ecossistema.</p>"
        f'<p style="margin:0 0 16px;font:15px/1.6 Arial,Helvetica,sans-serif;'
        f'color:{COR_TEXTO}">{_esc(rel.resumo)}</p>'
        + _destaques(destaques)
        + corpo
        + _graficos(rel.series)
        + nota_incc(nota)
        + cta
        + rodape
        + "</div>"
    )


def assunto_de(rel: Relatorio) -> str:
    """Assunto com o número, que é o que decide o clique.

    Assunto genérico ("Resumo semanal") é o caminho mais curto para cair em
    spam — o filtro lê o assunto antes do corpo.
    """
    return rel.titulo[:78]


__all__ = ["renderizar", "assunto_de", "nota_incc", "svg_do_relatorio",
           "COR_LINHA_ACAO"]
