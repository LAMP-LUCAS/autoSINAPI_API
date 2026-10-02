"""api/reports/registro.py — a lista única que liga trilha a implementação.

A `grade` declara as 9 chaves na ordem aprovada; este registry diz qual função
monta cada uma. Sem ele, a trilha e o código andariam separados — e o roteiro
trataria chave sem implementação como "não pôde ser montado", que é certo por
acaso, não por desenho.

`None` explícito (ainda não implementado) é diferente de ausente: ausente
seria erro de configuração, `None` é "previsto, pendente".
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

from .fontes import (coletar_incc, montar_incc_leitura, montar_incc_timing,
                     nota_incc_atual)
from .fontes_cub import coletar_br, montar_cub_dispersao, montar_cub_estado
from .fontes_sinapi import (coletar_base, montar_sinapi_competencia,
                            montar_sinapi_cobertura, montar_sinapi_foco_custo)
from .model import Relatorio

logger = logging.getLogger("autosinapi.reports.registro")

_cache: dict[str, Optional[dict]] = {}


def _br() -> Optional[dict]:
    """Cache por execução. Guardado como `dict` ou `None` — nunca string:
    o `montar` recebe dict, e um texto aqui quebrava com AttributeError."""
    if "br" not in _cache:
        _cache["br"] = coletar_br()
    return _cache["br"]


# Caches separados por FONTE. Um cache único por engano fez o relatório do
# INCC receber o dicionário do CUB (regiões e estados) e quebrar em
# `r.get("y12_m")` — sem erro na origem, só no consumidor.
_cache: dict[str, Optional[dict]] = {}


def _br() -> Optional[dict]:
    """Cache do CUB por execução. `dict` ou `None` — nunca texto."""
    if "cub" not in _cache:
        _cache["cub"] = coletar_br()
    return _cache["cub"]


def _incc() -> list[dict]:
    """Série do INCC. É uma LISTA de dicts, não um dict — o que expôs o
    bug de cache compartilhado."""
    if "incc" not in _cache:
        _cache["incc"] = coletar_incc()
    return _cache["incc"]


def _base() -> Optional[dict]:
    """Cache da base SINAPI por execução."""
    if "sinapi" not in _cache:
        _cache["sinapi"] = coletar_base()
    return _cache["sinapi"]


def limpar_cache():
    """Chamado entre execuções: a competência muda e o cache não pode mentir."""
    _cache.clear()


def incc_leitura(_c=None) -> Optional[Relatorio]:
    return montar_incc_leitura(_incc())


def incc_timing(_c=None) -> Optional[Relatorio]:
    return montar_incc_timing(_incc())


def incc_aceleracao(_c=None) -> Optional[Relatorio]:
    """Ângulo 5 — acelerando ou desacelerando, sobre a série do M."""
    from .fontes import montar_incc_aceleracao
    return montar_incc_aceleracao(_incc())


def incc_horizonte(_c=None) -> Optional[Relatorio]:
    from .fontes import montar_incc_horizonte
    return montar_incc_horizonte(_incc())


def sinapi_cobertura(_c=None) -> Optional[Relatorio]:
    d = _base()
    return montar_sinapi_cobertura(d) if d else None


def sinapi_foco(_c=None) -> Optional[Relatorio]:
    d = _base()
    return montar_sinapi_foco_custo(d) if d else None


def sinapi_competencia(_c=None, ultima: Optional[str] = None) -> Optional[Relatorio]:
    d = _base()
    return montar_sinapi_competencia(d, ultima) if d else None


MONTADORES: dict[str, Callable[..., Optional[Relatorio]]] = {
    "incc_leitura_mes": incc_leitura,
    "incc_timing_m_di": incc_timing,
    "cub_dispersao": lambda c=None: montar_cub_dispersao(_br()),
    "sinapi_cobertura": sinapi_cobertura,
    "incc_aceleracao": incc_aceleracao,
    "cub_estado_projeto": lambda c=None: montar_cub_estado(_br()),
    "sinapi_foco_custo": sinapi_foco,
    "incc_horizonte_36m": incc_horizonte,
    "sinapi_competencia": sinapi_competencia,
}

PENDENTES: tuple[str, ...] = ()


def montar(chave: str, ctx=None, ultima: Optional[str] = None) -> Optional[Relatorio]:
    """Monta o relatório da chave, ou `None` se não há dado suficiente."""
    fn = MONTADORES.get(chave)
    if fn is None:
        logger.info("Relatório %s sem implementação — não ocupa slot", chave)
        return None
    try:
        if chave == "sinapi_competencia":
            return fn(ctx, ultima)
        return fn(ctx)
    except Exception as exc:
        # Um relatório que falha não pode derrubar o workflow inteiro — nem
        # gerar e-mail com meio número.
        logger.error("Falha ao montar %s: %s", chave, exc, exc_info=True)
        return None


def implementados() -> tuple[str, ...]:
    return tuple(sorted(MONTADORES))


__all__ = ["montar", "implementados", "nota_incc_atual", "limpar_cache",
           "MONTADORES", "PENDENTES"]
