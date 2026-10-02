"""api/reports/fontes_cub.py — CUB (Custo Unitário Básico) → `Relatorio`.

CUB é o custo do metro quadrado por UF, apurado pelos Sinduscon. É o número
que o escritório usa para orçar, e o que o construtor usa para dizer por que
a mesma obra custa diferente em cada estado.

Como o INCC, o coleta é pela API do produto (o backend não fala com o banco
do AutoCUB — a fronteira é a API, como para os demais).

Relatórios
----------
`cub_dispersao`     — por que o m² varia tanto entre regiões (curva de barras)
`cub_estado_projeto` — um estado, um número, o que isso significa numa obra
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
import os
import urllib.request
from decimal import Decimal

D = Decimal
from typing import Optional

from .fontes import num, pct
from .model import Bloco, Categoria, Metrica, Relatorio, Serie
from .rotacao import escolher_estado, regioes_rotativas

logger = logging.getLogger("autosinapi.reports.cub")

_CUB_URLS = [
    os.getenv("CUB_API_URL", "").rstrip("/"),
    "http://api-gateway-kong:8000",
    "http://autocub_api:8002",
    os.getenv("MUNDOAEC_CUB_API_URL", "https://autocub.mundoaec.com").rstrip("/"),
]

_FONTES = "Fonte Sinduscon (CUB)"


def _get(caminho: str) -> Optional[dict]:
    """Chama o primeiro base que responder. `None` em vez de exceção: a grade
    trata dado ausente como "não monta", e um relatório que não sai é melhor
    que um e-mail com erro."""
    for base in [b for b in _CUB_URLS if b]:
        try:
            with urllib.request.urlopen(f"{base}{caminho}", timeout=8) as r:
                return json.loads(r.read().decode())
        except Exception as exc:
            logger.debug("CUB indisponível em %s: %s", base, exc)
    logger.warning("CUB indisponível em todas as bases para %s", caminho)
    return None


def _d(v) -> Optional[Decimal]:
    """JSON → Decimal. Na fronteira, porque `float` quebrava o `quantize`."""
    if v is None:
        return None
    return Decimal(str(v))


def coletar_br() -> Optional[dict]:
    d = _get("/v1/cub/br")
    if not d or not d.get("estados"):
        return None
    return {
        "data_referencia": d.get("data_referencia"),
        "desoneracao": d.get("desoneracao"),
        "media_br": _d(d.get("cub_medio_brasil")),
        "regioes": {k: _d(v) for k, v in (d.get("por_regiao") or {}).items()},
        "estados": [{
            "uf": e.get("uf"),
            "valor_m2": _d(e.get("valor_m2")),
            "peso": _d(e.get("peso_relativo")),
            "participacao": _d(e.get("participacao_efetiva_pct")),
            "sinduscon": e.get("sinduscon_nome"),
        } for e in d["estados"] if e.get("valor_m2") is not None],
        "total_estados": d.get("total_estados_ponderados"),
    }


def montar_cub_dispersao(br: Optional[dict],
                         cursor: int = 0) -> Optional[Relatorio]:
    """Relatório 3 — o m² varia quanto entre os estados, e por quê.

    A dispersão não é ruído: R$ 565/m² entre o mais caro e o mais barato é
    diferença de projeto, não de arredondamento. Por isso o relatório mostra
    a amplitude absoluta e traduz em obra de 2.000 m².
    """
    if not br or not br.get("estados") or not br.get("media_br"):
        return None
    est = sorted(br["estados"], key=lambda e: e["valor_m2"])
    mais_barato, mais_caro = est[0], est[-1]
    amplitude = mais_caro["valor_m2"] - mais_barato["valor_m2"]
    # Razão devezes 100 vem pronta; passar por `pct` (que multiplica por 100)
    # daria 4.955,96% em vez de 49,56%.
    pct_amplitude = (amplitude / br["media_br"]) * Decimal(100)
    pct_txt = f"{pct_amplitude.quantize(D('0.01')):+}".replace(".", ",") + "%"
    obra = Decimal(2000)
    custo_obra = amplitude * obra

    regioes = sorted(br["regioes"].items(), key=lambda kv: kv[1], reverse=True)
    # O destaque da região gira com o cursor: sem isso a mesma região aparece
    # em todos os ciclos e o relatório não tem nada de novo. O gráfico
    # continua mostrando todas.
    if regioes:
        giro = regioes_rotativas(br, cursor)
        mais_alta = giro[0]
    else:
        mais_alta = ("—", Decimal(0))
    mais_baixa = regioes[-1] if regioes else ("—", Decimal(0))

    return Relatorio(
        chave="cub_dispersao",
        titulo=f"Custo do m² varia {pct_txt} entre os estados",
        resumo=(f"O CUB médio é {num(br['media_br'])} por m², mas vai de "
                f"{num(mais_barato['valor_m2'])} em {mais_barato['uf']} a "
                f"{num(mais_caro['valor_m2'])} em {mais_caro['uf']}. Numa obra "
                f"de 2.000 m², escolher o estado é uma decisão de "
                f"{num(custo_obra / Decimal(1_000_000), 2)} milhões."),
        blocos=[Bloco(
            metricas=[
                Metrica("CUB médio Brasil", f"R$ {num(br['media_br'])}",
                        destaque=True, detalhe=br.get("data_referencia")),
                Metrica("Mais barato", f"{mais_barato['uf']} · R$ {num(mais_barato['valor_m2'])}",
                        destaque=True),
                Metrica("Mais caro", f"{mais_caro['uf']} · R$ {num(mais_caro['valor_m2'])}",
                        destaque=True),
                Metrica("Amplitude", f"R$ {num(amplitude)}/m²",
                        detalhe=f"{pct_txt} da média"),
                Metrica(f"Região em foco ({cursor % max(len(regioes), 1) + 1}/{len(regioes)})",
                        f"{mais_alta[0]} · R$ {num(mais_alta[1])}",
                        detalhe="destaque que gira a cada envio"),
                Metrica("Região mais barata", f"{mais_baixa[0]} · R$ {num(mais_baixa[1])}",
                        detalhe="o outro extremo da curva"),
                Metrica("Em 2.000 m²", f"R$ {num(custo_obra / Decimal(1_000_000), 2)} mi",
                        detalhe="diferença entre os extremos"),
            ],
            texto=("O mesmo projeto custa valores diferentes conforme o estado "
                   "por causa do custo da mão de obra e dos materiais "
                   "locais — não por erro de orçamento."),
        )],
        series=[Serie("CUB por região",
                      [(r, v) for r, v in regioes], sufixo="", em_percentual=False)],
        categoria=Categoria.INSIGHT,
        rodape=f"{_FONTES} · competência {br.get('data_referencia')} · "
               f"{br.get('desoneracao')} · {br.get('total_estados')} estados ponderados",
    )


def montar_cub_estado(br: Optional[dict],
                      cursor: int = 0) -> Optional[Relatorio]:
    """Relatório 6 — um estado, um número, o que ele significa.

    O estado **gira com o cursor**. Antes era sempre o de maior participação
    efetiva, e o lead via o mesmo número em todos os ciclos — com 9 estados
    na base, nove vezes a mesma informação.

    A ordem começa pelo de maior participação (o que a maior parte da obra
    executa) e passa por todos os outros, então o ciclo cobre a base
    inteira antes de repetir.
    """
    if not br or not br.get("estados"):
        return None
    alvo = escolher_estado(br, cursor)
    if alvo is None:
        return None
    uf = alvo
    br_estados = {e["uf"]: e for e in br["estados"]}
    ref = br_estados.get(uf["uf"], uf)
    obra = Decimal(2000)
    custo = (ref["valor_m2"] or Decimal(0)) * obra
    desvio = (((ref["valor_m2"] or Decimal(0)) - br["media_br"]) / br["media_br"]
              * Decimal(100)) if br.get("media_br") else None

    return Relatorio(
        chave="cub_estado_projeto",
        titulo=f"{uf['uf']}: R$ {num(ref['valor_m2'])} por m², o que dá numa obra",
        resumo=(f"Em {ref['uf']} o custo é {num(ref['valor_m2'])} por m² — "
                f"{desvio.quantize(D('0.01')):+}% "
                f"{'acima' if (desvio or 0) > 0 else 'abaixo'} da média "
                f"nacional. Numa área de 2.000 m², são "
                f"R$ {num(custo / Decimal(1_000_000), 2)} milhões só em "
                f"estrutura."),
        blocos=[Bloco(
            metricas=[
                Metrica(f"CUB {ref['uf']}", f"R$ {num(ref['valor_m2'])}",
                        destaque=True, detalhe=ref.get("sinduscon")),
                Metrica("Média nacional", f"R$ {num(br['media_br'])}",
                        destaque=True),
                # `desvio` já está em percentual (×100 aplicado uma vez);
                # passar por `pct` de novo multiplicaria por 100 outra vez.
                Metrica(f"Desvio vs média",
                        (f"{desvio.quantize(D('0.01')):+}".replace(".", ",") + "%")
                        if desvio is not None else "—",
                        variacao="▲" if (desvio or 0) > 0 else "▼",
                        destaque=True),
                Metrica(f"Obra de 2.000 m² em {ref['uf']}",
                        f"R$ {num(custo / Decimal(1_000_000), 2)} mi"),
                Metrica("Participação efetiva",
                        f"{num(uf.get('participacao'))}%",
                        detalhe="peso do estado na amostra nacional"),
                Metrica("Posição na rotação",
                        f"{cursor % len(br['estados']) + 1} de {len(br['estados'])}",
                        detalhe="o ciclo passa por todos antes de repetir"),
            ],
            texto=("Escolher o estado não é detalhe de planilha: o mesmo "
                   "escopo muda de valor conforme o CUB local."),
        )],
        series=[Serie(f"CUB {ref['uf']} vs média",
                      [("média", br.get("media_br") or Decimal(0)),
                       (ref["uf"], ref["valor_m2"] or Decimal(0))],
                      em_percentual=False)],
        categoria=Categoria.INSIGHT,
        rodape=f"{_FONTES} · competência {br.get('data_referencia')}",
    )


__all__ = ["coletar_br", "montar_cub_dispersao", "montar_cub_estado"]
