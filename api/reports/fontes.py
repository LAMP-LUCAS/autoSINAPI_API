"""api/reports/fontes.py — números do banco → `Relatorio`.

Cada função tem duas metades:
  * `_coletar`  — lê o dado bruto (SQL);
  * `_montar`   — aplica a regra editorial sobre números já coletados.

A separação existe para o teste: `_montar` é pura e se verifica com literais,
sem banco. Sem isso, testar "o spread está em −0,19 p.p." exigiria popular o
INCC inteiro.

Nada aqui chama LLM. A frase do resumo é montada por condição sobre o
número — é por isso que o mesmo dado produz o mesmo relatório sempre, e que
"não mudou" é verificável em vez de Palpite.
"""

from __future__ import annotations

import datetime as _dt
import logging
import os
from decimal import Decimal
from typing import Optional

from .model import Bloco, Categoria, Metrica, Relatorio, Serie

logger = logging.getLogger("autosinapi.reports.fontes")

Q = Decimal("0.0001")


def pct(v: Decimal, casas: int = 2, unidade: bool = True) -> str:
    """Percentual já em real (0.0066 → "+0,66%").

    `unidade=False` devolve só o número ("-0,19"), para os casos em que a
    unidade já está escrita no rótulo — como "Spread" e "Diferença", que
   写成 "p.p." na mesma célula. Escrever "+0,19% p.p." é unidade dupla.

    O `Decimal` não é preciosismo: `0.005 * 100` em float dá
    0.5000000000000004, e o e-mail publicaria "+0,50%" num lugar e "+0,5%"
    noutro.
    """
    q = Decimal(1).scaleb(-casas)
    s = f"{(v * 100).quantize(q):+,.{casas}f}"
    s = s.replace(",", "\x00").replace(".", ",").replace("\x00", ".")
    return f"{s}%" if unidade else s


def num(v: Decimal, casas: int = 2) -> str:
    q = Decimal(1).scaleb(-casas)
    s = f"{v.quantize(q):,.{casas}f}"
    return s.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def _sinal(v: Decimal, casas: int = 2) -> str:
    return "▲" if v > 0 else ("▼" if v < 0 else "=")


# ── INCC ─────────────────────────────────────────────────────────────────────

# A base do AutoINCC não é exposta ao backend (e não deve ser): a fronteira é
# a API, igual aos outros produtos. A série vem de `/incc/history`, que aceita
# um índice por requisição.
# Prefere o gateway interno: é a fronteira do produto e não exige chave de
# negócio no backend. Cai para o AutoINCC direto (rede interna) e, por último,
# para o domínio público — que responderia 403 sem `X-API-Key`.
_INCC_URLS = [
    os.getenv("INCC_API_URL", "").rstrip("/"),
    "http://api-gateway-kong:8000",
    "http://autoincc_api:8003",
    os.getenv("MUNDOAEC_INCC_API_URL", "https://autoincc.mundoaec.com").rstrip("/"),
]
_MESES = 14


def coletar_incc(db=None) -> list[dict]:
    """Série do INCC (M e DI) mesclada por competência, mais recente primeiro.

    `db` é aceito e ignorado: assinatura estável desde que a coleta era SQL,
    para não quebrar quem já chama. Só isto toca rede — `montar_*` recebem as
    linhas prontas, o que mantém a regra editorial testável com literais.
    """
    import json
    import urllib.parse
    import urllib.request

    fim = _dt.date.today().replace(day=1)
    inicio = (fim.replace(day=1) - _dt.timedelta(days=32 * _MESES))
    por_sigla: dict[str, dict] = {}

    # O parâmetro é `sigla`, não `codigo`. `codigo` é aceito e **ignorado**
    # pelo endpoint: as duas chamadas voltavam com INCC-M e o spread M×DI
    # saía 0,00 — sem erro, sem aviso, só um número falso.
    for sigla in ("INCC-M", "INCC-DI"):
        q = urllib.parse.urlencode({
            "sigla": sigla,
            "data_inicio": inicio.isoformat(), "data_fim": fim.isoformat()})
        itens = None
        for base in [u for u in _INCC_URLS if u]:
            try:
                with urllib.request.urlopen(f"{base}/api/v1/incc/history?{q}",
                                            timeout=8) as r:
                    itens = json.loads(r.read().decode()).get("items", [])
                break
            except Exception as exc:
                logger.debug("INCC %s indisponível em %s: %s", sigla, base, exc)
        if itens is None:
            logger.warning("INCC %s indisponível em todas as bases", sigla)
            continue
        for it in itens:
            dia = it.get("data_id")
            if not dia:
                continue
            d = _dt.date.fromisoformat(dia[:10])
            # A API devolve float (JSON não tem decimal). Converter aqui, na
            # fronteira, é o único ponto onde isso acontece — depois de ca,
            # tudo é `Decimal` e o arredondamento é exato. Deixar float
            # passar quebra `quantize` e reintroduz o erro que o Decimal
            # justamente evita.
            it = {k: (Decimal(str(v)) if isinstance(v, (int, float))
                      and not isinstance(v, bool) else v)
                  for k, v in it.items()}
            linha = por_sigla.setdefault(dia, {
                "data_id": d, "var_m": None, "idx_m": None, "y12_m": None,
                "var_di": None, "idx_di": None, "y12_di": None})
            if sigla == "INCC-M":
                linha["var_m"] = it.get("variacao_mensal")
                linha["idx_m"] = it.get("numero_indice")
                linha["y12_m"] = it.get("variacao_12m")
            else:
                linha["var_di"] = it.get("variacao_mensal")
                linha["idx_di"] = it.get("numero_indice")
                linha["y12_di"] = it.get("variacao_12m")

    return sorted(por_sigla.values(), key=lambda l: l["data_id"], reverse=True)


def montar_incc_leitura(linhas: list[dict]) -> Optional[Relatorio]:
    """Relatório 1 — o número novo do mês."""
    linhas = list(linhas)
    if len(linhas) < 2 or linhas[0]["var_m"] is None:
        return None
    atual, ant = linhas[0], linhas[1]
    spread = (atual["var_m"] or 0) - (atual["var_di"] or 0)
    var_m = atual["var_m"] or Decimal(0)
    delta = var_m - (ant["var_m"] or Decimal(0))

    if delta > 0:
        tend = "acelerando"
    elif delta < 0:
        tend = "desacelerando"
    else:
        tend = "estável"

    return Relatorio(
        chave="incc_leitura_mes",
        titulo=f"INCC {atual['data_id'].strftime('%m/%Y')} — Mercado "
               f"{'sobe' if var_m >= 0 else 'cai'} {pct(abs(var_m))}",
        resumo=(f"O INCC-M, índice de mercado usado em reajuste de contratos, "
                f"mudou {pct(delta, unidade=False)} ponto em relação ao mês "
                f"anterior — está {tend}."),
        blocos=[Bloco(
            metricas=[
                Metrica("INCC-M · Mercado", num(atual["idx_m"]), destaque=True,
                        variacao=_sinal(var_m),
                        detalhe=atual["data_id"].strftime("%m/%Y")),
                Metrica("Variação mensal", pct(var_m), destaque=True,
                        variacao=_sinal(var_m),
                        detalhe=f"vs {pct(ant['var_m'])} em "
                                f"{ant['data_id'].strftime('%m/%Y')}"),
                Metrica("Acumulado 12 meses", pct(atual["y12_m"] or 0),
                        destaque=True),
                Metrica("INCC-DI · Disponibilidade Interna",
                        num(atual["idx_di"], 2),
                        detalhe=f"var. mensal {pct(atual['var_di'] or 0)}"),
                Metrica("Spread M × DI", f"{pct(spread, unidade=False)} p.p.",
                        detalhe="diferença entre as janelas de coleta"),
                Metrica("Tendência", tend,
                        detalhe=f"{pct(delta, unidade=False)} p.p. vs mês anterior"),
            ],
            texto=("Ambos os índices cobrem materiais, serviços e mão de obra — "
                   "o que os separa é a janela de coleta, não o que medem."),
        )],
        series=[Serie("INCC-M",
                      [(r["data_id"].strftime("%m/%y"), r["var_m"])
                       for r in reversed(linhas) if r["var_m"] is not None],
                      em_percentual=True)],
        categoria=Categoria.INSIGHT,
        rodape=(f"Fonte BCB/SGS · competência {atual['data_id'].strftime('%m/%Y')}"
                f" · ambos os índices no mesmo período de referência"),
    )


def montar_incc_timing(linhas: list[dict]) -> Optional[Relatorio]:
    """Relatório 2 — a diferença entre M e DI lida como **janela**, não escopo.

    Os dois índices cobrem o mesmo objeto: materiais e equipamentos, serviços
    e mão de obra (metodologia FGV IBRE). INCC-M é "Mercado"; INCC-DI é
    "Disponibilidade Interna". O que os separa é **quando** collectam:

        INCC-M   dia 21 do mês anterior → dia 20 do mês de referência
        INCC-DI  primeiro → último dia do mês civil

    Então o spread mede o deslocamento entre as janelas, não o peso de uma
    categoria sobre outra. Quando o M está à frente, a janela antecipada já
    capturou pressão de preço que a janela cheia ainda vai ver. Quando está
    atrás, o mês fechado puxou alta que a janela do dia 20 ainda não tinha
    consolidado.

    Cuidado de leitura: o spread é pequeno (média histórica de ~0,09 p.p.) e
    **não é tendência**. Um mês isolado não diz nada sobre direção — por isso
    o relatório compara com a média de 32 meses em vez de afirmar.
    """
    linhas = list(linhas)
    if len(linhas) < 4:
        return None
    spreads = [((r["var_m"] or 0) - (r["var_di"] or 0)) for r in linhas]
    media = sum(spreads) / Decimal(len(spreads))
    desvio = (sum((x - media) ** 2 for x in spreads) / Decimal(len(spreads))) ** Decimal("0.5")
    atual = linhas[0]
    spread = spreads[0]

    a_frente = spread > 0
    leitura = ("a janela do M, que fecha no dia 20, jáincorporou a alta"
               if a_frente else
               "o mês fechado do DI puxou uma alta que a janela do M não viu")
    # Só afirma direção quando o mês está fora do próprio ruído histórico.
    if abs(spread - media) <= desvio:
        leitura = "dentro do padrão histórico — sem deslocamento entre janelas"

    return Relatorio(
        chave="incc_timing_m_di",
        titulo="INCC-M e INCC-DI: o que a diferença entre janelas mostra",
        resumo=(f"Em {atual['data_id'].strftime('%m/%Y')} a diferença foi de "
                f"{pct(spread, unidade=False)} ponto — {leitura}."),
        blocos=[Bloco(
            metricas=[
                Metrica("INCC-M · Mercado (dia 21→20)",
                        pct(atual["var_m"] or 0),
                        detalhe="janela antecipada"),
                Metrica("INCC-DI · Disp. Interna (mês cheio)",
                        pct(atual["var_di"] or 0),
                        detalhe="janela do mês fechado"),
                Metrica("Diferença entre janelas",
                        f"{pct(spread, unidade=False)} p.p.",
                        variacao=_sinal(spread)),
                Metrica("Média histórica",
                        f"{pct(media, unidade=False)} p.p.",
                        detalhe=f"{len(spreads)} meses, desvio "
                                f"{pct(desvio, unidade=False)} p.p."),
            ],
            texto=("Os dois índices medem o mesmo — materiais e equipamentos, "
                   "serviços e mão de obra. O INCC-M é o de mercado e coleta "
                   "na janela antecipada (do dia 21 do mês anterior ao dia 20); "
                   "o INCC-DI é o de disponibilidade interna e coleta o mês "
                   "cheio. A diferença entre eles é a janela, não o escopo."),
        )],
        series=[
            Serie("INCC-M",
                  [(r["data_id"].strftime("%m/%y"), r["var_m"])
                   for r in reversed(linhas) if r["var_m"] is not None],
                  em_percentual=True),
            Serie("INCC-DI",
                  [(r["data_id"].strftime("%m/%y"), r["var_di"])
                   for r in reversed(linhas) if r["var_di"] is not None],
                  em_percentual=True),
        ],
        categoria=Categoria.INSIGHT,
        rodape=("Fonte FGV IBRE / BCB (SGS) · ambos abrangem materiais, "
                "serviços e mão de obra · a diferença é de janela de coleta"),
    )


def _enriquecer_com_overview(linhas: list[dict]) -> list[dict]:
    """Completa a série com o `overview` (YTD, 24m, 36m).

    `/history` traz a série mensal; `/overview` traz as janelas acumuladas.
    Sem esta etapa o relatório de horizonte longo não teria do que falar —
    e o título anunciaria 36 meses com o dado de 12.
    """
    ov = None
    try:
        import json as _json
        import urllib.request as _rq
        for base in [b for b in _INCC_URLS if b]:
            try:
                with _rq.urlopen(f"{base}/api/v1/incc/overview", timeout=6) as r:
                    ov = _json.loads(r.read().decode())
                break
            except Exception:
                continue
    except Exception as exc:
        logger.debug("overview do INCC indisponível: %s", exc)

    # `ov` fica `None` quando nenhuma base respondeu: sem o overview, o
    # relatório de horizonte sai só com o dado de 12 meses — o que o próprio
    # relatório declara no título. Degradar é melhor que inventar 36 meses.
    if not ov:
        return linhas

    m = (ov.get("incc_m") or {})
    di = (ov.get("incc_di") or {})
    acc = (ov.get("aceleracao_incc_m") or {})
    if not linhas:
        return linhas
    atual = linhas[0]
    atual.update({
        "ytd_m": m.get("variacao_ytd_percentual"),
        "m24_m": m.get("variacao_24m_percentual"),
        "m36_m": m.get("variacao_36m_percentual"),
        "ytd_di": di.get("variacao_ytd_percentual"),
        "m24_di": di.get("variacao_24m_percentual"),
        "m36_di": di.get("variacao_36m_percentual"),
        "spread_pp": ov.get("spread_mensal_pontos"),
        "aceleracao": acc,
    })
    return linhas


def _serie_incc(linhas, campo="var_m"):
    return [(r["data_id"].strftime("%m/%y"), r[campo])
            for r in reversed(linhas) if r.get(campo) is not None]


def montar_incc_aceleracao(linhas: list[dict]) -> Optional[Relatorio]:
    """Ângulo 5 — acelerando ou desacelerando, e há quanto tempo.

    A variação mensal sozinha não diz nada: 0,66% é alta ou baixa depende do
    que veio antes. O que informa é a **sequência** de variações — três meses
    caindo e depois um subindo é mudança de direção, não ruído.
    """
    linhas = [r for r in list(linhas) if r.get("var_m") is not None]
    if len(linhas) < 4:
        return None
    var = [r["var_m"] for r in linhas]          # mais recente primeiro
    atual = linhas[0]
    seq = list(reversed(var[-5:]))              # mais antigo → mais recente

    # Conta quantas variações MQ são crescentes de forma seguida.
    alta_seguida = 0
    for a, b in zip(seq, seq[1:]):
        alta_seguida = alta_seguida + 1 if b > a else 0

    if alta_seguida >= 2:
        leitura = "acelerando há semanas"
    elif alta_seguida == 1:
        leitura = "voltou a subir depois de queda"
    else:
        leitura = "ainda em desaceleração"

    seq_txt = " · ".join(pct(v) for v in seq)
    return Relatorio(
        chave="incc_aceleracao",
        titulo=f"INCC-M {leitura}: {seq_txt}",
        resumo=(f"Em {atual['data_id'].strftime('%m/%Y')} o índice variou "
                f"{pct(atual['var_m'])}. A sequência dos últimos "
                f"{len(seq)} meses é {leitura} — a variação do mês, sozinha, "
                f"não diz se a alta está acelerando ou chegando ao fim."),
        blocos=[Bloco(
            metricas=[
                Metrica("Variação mensal", pct(atual["var_m"]), destaque=True),
                Metrica("Mês anterior", pct(linhas[1]["var_m"]), destaque=True),
                Metrica("Sequência recente", seq_txt,
                        detalhe="do mais antigo ao mais recente"),
                Metrica("Leitura", leitura, destaque=True),
            ],
            texto=("Quem olha só o número do mês não sabe se está olhando "
                   "uma aceleração ou o fim de uma desaceleração."),
        )],
        series=[Serie("INCC-M mensal", _serie_incc(linhas), em_percentual=True)],
        categoria=Categoria.INSIGHT,
        rodape=(f"Fonte FGV IBRE / BCB (SGS) · competência "
                f"{atual['data_id'].strftime('%m/%Y')} · "
                f"{len(linhas)} meses na série"),
    )


def montar_incc_horizonte(linhas: list[dict]) -> Optional[Relatorio]:
    """Ângulo 8 — o horizonte longo, que o número do mês não mostra.

    0,66% no mês parece pouco; o acumulado em 36 meses é outro valor. É o
    ângulo que impede a leitura "custo parado" de quem só viu a variação
    mensal — que é o número que aparece primeiro em todo relatório.
    """
    atual = next((r for r in linhas if r.get("y12_m") is not None), None)
    if not atual:
        return None
    linhas = _enriquecer_com_overview(linhas)

    def _p(v) -> Optional[str]:
        return None if v is None else pct(Decimal(str(v)) / Decimal(100))

    p12, p24, p36 = _p(atual.get("y12_m")), _p(atual.get("m24_m")), _p(atual.get("m36_m"))
    ytd = _p(atual.get("ytd_m"))
    # Sem 36m na fonte, o título não pode prometê-lo.
    janela = "12 meses" if p36 is None else "36 meses"

    return Relatorio(
        chave="incc_horizonte_36m",
        titulo=(f"Em {janela} o INCC-M acumula {p36 or p12}"),
        resumo=(f"A variação mensal de {pct(atual['var_m'] or 0)} em "
                f"{atual['data_id'].strftime('%m/%Y')} parece pequena. "
                f"Acumulado, são {p12} em 12 meses"
                + (f" e {p36} em 36 meses" if p36 else "")
                + " — o mesmo dado lido na escala em que o contrato de "
                  "reajuste trabalha."),
        blocos=[Bloco(
            metricas=[
                Metrica("Acumulado 12 meses", p12, destaque=True,
                        detalhe="ago/2025 → ago/2026"),
                Metrica("Acumulado 24 meses", p24, destaque=True,
                        variacao="▲" if (atual.get("m24_m") or 0) > 0 else None),
                Metrica("Acumulado 36 meses", p36, destaque=True),
                Metrica("Acumulado no ano (YTD)", ytd),
                Metrica("Variação do mês", pct(atual["var_m"] or 0),
                        detalhe="o número que aparece primeiro"),
            ],
            texto=("Quem orça só com o número recente subestima o histórico. "
                   "A variação mensal é o que muda rápido — e o que mais "
                   "engana."),
        )],
        series=[Serie("INCC-M mensal", _serie_incc(linhas), em_percentual=True)],
        categoria=Categoria.INSIGHT,
        rodape=(f"Fonte FGV IBRE / BCB (SGS) · competência "
                f"{atual['data_id'].strftime('%m/%Y')}"),
    )


def nota_incc_atual(linhas: list[dict]) -> Optional[str]:
    """Rodapé de estado — o que o INCC está fazendo, sem prometer número novo."""
    linhas = list(linhas)
    if not linhas or linhas[0]["var_m"] is None:
        return None
    a = linhas[0]
    ant = linhas[1] if len(linhas) > 1 and linhas[1]["var_m"] is not None else None
    tend = ""
    if ant is not None:
        d = (a["var_m"] or 0) - (ant["var_m"] or 0)
        tend = " · acelerando" if d > 0 else (" · desacelerando" if d < 0 else " · estável")
    return (f"{a['data_id'].strftime('%m/%y')}: {pct(a['var_m'])}{tend} "
            f"· competência {a['data_id'].strftime('%m/%Y')}")


__all__ = ["montar_incc_leitura", "montar_incc_timing", "nota_incc_atual",
           "coletar_incc", "pct", "num"]
