"""api/reports/fontes_sinapi.py — SINAPI → `Relatorio`.

A competência da base é o que muda devagar: 10.840 composições, 6.333
insumos, milhões de registros. Nenhum desses números muda na semana — e é
por isso que os relatórios do SINAPI têm **um** que depende de novidade
(`sinapi_competencia`, o 9º da trilha) e os outros dois são ângulos sobre a
mesma competência.

Relatórios
----------
`sinapi_cobertura`    — o que há na base agora (depende de competência nova)
`sinapi_foco_custo`   — por onde começar a olhar custo (ângulo)
`sinapi_competencia`  — a competência nova em si (pula se não mudou)
"""

from __future__ import annotations

import json
import logging
import os
import urllib.request
from decimal import Decimal

from .fontes import num

D = Decimal
from typing import Optional

from .model import Bloco, Categoria, Metrica, Relatorio, Serie

logger = logging.getLogger("autosinapi.reports.sinapi")

_BASE_URLS = [
    os.getenv("SINAPI_BASE_URL", "").rstrip("/"),
    "http://localhost:8000",     # loopback: o backend é o próprio dono da base
    "http://api-gateway-kong:8000",
]

_FONTE = "Fonte SINAPI"


def _get(caminho: str) -> Optional[dict]:
    for base in [b for b in _BASE_URLS if b]:
        try:
            with urllib.request.urlopen(f"{base}{caminho}", timeout=8) as r:
                return json.loads(r.read().decode())
        except Exception as exc:
            logger.debug("SINAPI indisponível em %s: %s", base, exc)
    logger.warning("SINAPI indisponível para %s", caminho)
    return None


def _milhar(v) -> str:
    """Contagens grandes: `16.256.214` — sem o separador fica ilegível."""
    if v is None:
        return "—"
    return f"{int(v):,}".replace(",", ".")


def coletar_base() -> Optional[dict]:
    base = _get("/api/v1/public/base")
    stats = _get("/api/v1/public/stats")
    if not base and not stats:
        return None
    return {
        "competencia": (base or {}).get("available_base"),
        "consumida": (base or {}).get("consumed_base"),
        "status": (base or {}).get("status"),
        "atualizado_em": (base or {}).get("as_of"),
        "insumos": (stats or {}).get("insumos"),
        "composicoes": (stats or {}).get("composicoes"),
        "precos": (stats or {}).get("precos"),
        "custos": (stats or {}).get("custos"),
    }


def montar_sinapi_cobertura(b: Optional[dict]) -> Optional[Relatorio]:
    """Relatório 4 — o que há na base agora."""
    if not b or not b.get("composicoes"):
        return None
    comp = b["competencia"] or "—"
    return Relatorio(
        chave="sinapi_cobertura",
        titulo=f"Competência {comp}: {_milhar(b['composicoes'])} composições na base",
        resumo=(f"A base SINAPI está em {comp} com "
                f"{_milhar(b['composicoes'])} composições e "
                f"{_milhar(b['insumos'])} insumos. É sobre esse volume que "
                f"rodam curva ABC, composição e mão de obra."),
        blocos=[Bloco(
            metricas=[
                Metrica("Composições", _milhar(b["composicoes"]), destaque=True),
                Metrica("Insumos", _milhar(b["insumos"]), destaque=True),
                Metrica("Registros de custo", _milhar(b["custos"]), destaque=True),
                Metrica("Preços", _milhar(b["precos"])),
                Metrica("Competência disponível", comp),
                Metrica("Competência consumida", b.get("consumida") or "—",
                        detalhe=b.get("status") or ""),
            ],
        )],
        series=[Serie("Registros por competência",
                      [("preços", Decimal(str(b.get("precos") or 0))),
                       ("custos", Decimal(str(b.get("custos") or 0)))],
                      em_percentual=False)],
        categoria=Categoria.BASE,
        rodape=f"{_FONTE} · atualizado em {str(b.get('atualizado_em'))[:10]}",
    )


def montar_sinapi_foco_custo(b: Optional[dict]) -> Optional[Relatorio]:
    """Relatório 7 — por onde começar a olhar custo.

    Não é um dado do SINAPI: é a **ordem de intervenção** que o volume
    sustenta. Por isso o número principal é a razão custo/preço — o que diz
    quanta estrutura analítica existe por preço cadastrado.
    """
    if not b or not b.get("custos") or not b.get("precos"):
        return None
    razao = Decimal(str(b["custos"])) / Decimal(str(b["precos"]))
    total = b["custos"] + (b["precos"] or 0)

    return Relatorio(
        chave="sinapi_foco_custo",
        titulo=(f"Por onde começar: "
                f"{num(razao.quantize(D('0.1')), 1)} registros de custo por preço"),
        resumo=(f"Com {_milhar(b['custos'])} registros de custo para "
                f"{_milhar(b['precos'])} preços, a base sustenta análise de "
                f"composição em escala. A ordem abaixo é a que rende mais "
                f"primeiro."),
        blocos=[Bloco(
            metricas=[
                Metrica("Registros de custo", _milhar(b["custos"]),
                        destaque=True),
                Metrica("Preços", _milhar(b["precos"]), destaque=True),
                Metrica("Custo por preço cadastrado",
                        num(razao.quantize(D("0.1")), 1),
                        destaque=True, detalhe="quanto de estrutura há por preço"),
                Metrica("Registros no total", _milhar(total)),
            ],
            texto=("A ordem de intervenção que mais rende: insumo de maior "
                   "participação no custo, curva ABC, hora-homem acima da "
                   "média da UF, composições repetitivas e apropriação de BET "
                   "para enxergar o que hoje não aparece."),
        )],
        series=[Serie("Composição da base",
                      [("preços", Decimal(str(b.get("precos") or 0))),
                       ("custos", Decimal(str(b.get("custos") or 0)))],
                      em_percentual=False)],
        categoria=Categoria.INSIGHT,
        rodape=f"{_FONTE} · competência {b.get('competencia') or '—'}",
    )


def montar_sinapi_competencia(b: Optional[dict], ultima: Optional[str]) -> Optional[Relatorio]:
    """Relatório 9 — a competência nova. É o único que **pula** sem novidade.

    `ultima` é a competência já anunciada. Se for igual, `None` — o roteiro
    traduz em "sem novidade" e não ocupa slot. Sem isso, o lead receberia
    "atualizado em agosto" na semana 6.
    """
    if not b or not b.get("competencia"):
        return None
    comp = b["competencia"]
    if ultima and ultima == comp:
        logger.info("Competência %s já anunciada — relatório não é montado", comp)
        return None

    anterior = _competencia_anterior(comp)
    return Relatorio(
        chave="sinapi_competencia",
        titulo=f"Nova competência na base: {comp}",
        resumo=(f"A base SINAPI avançou para {comp}"
                + (f" (antes {anterior})." if anterior else ".")),
        blocos=[Bloco(
            metricas=[
                Metrica("Competência nova", comp, destaque=True),
                Metrica("Composições", _milhar(b.get("composicoes"))),
                Metrica("Insumos", _milhar(b.get("insumos"))),
                Metrica("Registros de custo", _milhar(b.get("custos"))),
            ],
            texto="Competência nova muda o resultado das análises de custo.",
        )],
        categoria=Categoria.BASE,
        rodape=f"{_FONTE} · substituindo {anterior or '—'}",
    )


def _competencia_anterior(comp: str) -> Optional[str]:
    """Competência anterior no formato AAAA-MM, para dizer 'de X para Y'."""
    try:
        ano, mes = (int(p) for p in comp.split("-")[:2])
        return f"{ano - 1}-12" if mes == 1 else f"{ano}-{mes - 1:02d}"
    except (ValueError, IndexError):
        return None


__all__ = ["coletar_base", "montar_sinapi_cobertura",
           "montar_sinapi_foco_custo", "montar_sinapi_competencia"]
