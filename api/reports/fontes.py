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
        titulo=f"INCC {atual['data_id'].strftime('%m/%Y')}: materiais "
               f"{'sobem' if var_m >= 0 else 'caem'} {pct(abs(var_m))}",
        resumo=f"O índice de materiais mudou {pct(delta).lstrip('+')} ponto em "
               f"relação ao mês anterior — está {tend}.",
        blocos=[Bloco(
            metricas=[
                Metrica("INCC-M (materiais)", num(atual["idx_m"]), destaque=True,
                        variacao=_sinal(var_m),
                        detalhe=atual["data_id"].strftime("%m/%Y")),
                Metrica("Variação mensal", pct(var_m), destaque=True,
                        variacao=_sinal(var_m),
                        detalhe=f"vs {pct(ant['var_m'])} em "
                                f"{ant['data_id'].strftime('%m/%Y')}"),
                Metrica("Acumulado 12 meses", pct(atual["y12_m"] or 0),
                        destaque=True),
                Metrica("INCC-DI (total)", num(atual["idx_di"], 2),
                        detalhe=f"var. mensal {pct(atual['var_di'] or 0)}"),
                Metrica("Spread materiais × total",
                        f"{pct(spread, unidade=False)} p.p.",
                        detalhe="negativo = materiais pressionam menos"),
                Metrica("Tendência", tend,
                        detalhe=f"{pct(delta, unidade=False)} p.p. vs mês anterior"),
            ],
            texto="Materiais e total não andam juntos: o spread mede isso.",
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
    """Relatório 2 — M × DI lidos como **timing**, não como número.

    As janelas de coleta são diferentes: o M coleta do dia 21 do mês anterior
    ao dia 20 do mês de referência; o DI coleta o mês inteiro. Quando o M
    está *acima* do DI, o mercado antecipou a alta de material — a janela
    antecipada capturou pressão de preço que a janela cheia ainda não viu.
    """
    linhas = list(linhas)
    if len(linhas) < 4:
        return None
    spreads = [((r["var_m"] or 0) - (r["var_di"] or 0)) for r in linhas]
    media = sum(spreads) / Decimal(len(spreads))
    atual = linhas[0]
    spread = spreads[0]

    antecipou = spread > 0
    leitura = ("o mercado antecipou a alta de material" if antecipou
               else "o total puxou mais que o material — mão de obra e serviços pesam")
    return Relatorio(
        chave="incc_timing_m_di",
        titulo=("INCC-M à frente do DI: o mercado antecipou o preço"
                if antecipou else
                "INCC-DI puxando: onde está a pressão do custo"),
        resumo=f"Em {atual['data_id'].strftime('%m/%Y')} a diferença entre os "
               f"dois índices foi de {pct(spread, unidade=False)} ponto — "
               f"{leitura}.",
        blocos=[Bloco(
            metricas=[
                Metrica("INCC-M (janela antecipada)", pct(atual["var_m"] or 0)),
                Metrica("INCC-DI (mês cheio)", pct(atual["var_di"] or 0)),
                Metrica("Diferença", f"{pct(spread).replace('%', '')} p.p.",
                        variacao=_sinal(spread)),
                Metrica("Média histórica", f"{pct(media, unidade=False)} p.p.",
                        detalhe=f"{len(spreads)} meses"),
            ],
            texto=("Quando o M está acima do DI, a janela antecipada capturou "
                   "pressão de preço antes da janela cheia. Quando está abaixo, "
                   "o DI pegou alta de serviço que o M ainda não senteu."),
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
        rodape="INCC-M coleta do dia 21 ao dia 20 · INCC-DI coleta o mês cheio",
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
