"""api/reports/rotacao.py — escolher a "parte" que o relatório vai olhar.

O problema que resolve
---------------------
Um relatório que sempre mostra o mesmo recorte **não tem nada de novo**,
mesmo que o texto mude. `cub_estado_projeto` escolhia o estado de maior
participação — e mandava PR toda vez, para sempre. Com 9 estados na base, o
leitor via o mesmo número 9 vezes.

Rotação aqui não é enfeite: é o que faz "informação nova" ser verdade. O
número do mês continua sendo o mesmo; o **ângulo sobre ele** é que gira.

Como rotaciona
--------------
Determinístico e sem estado: o índice vem do **cursor do lead** (quantos
relatórios ele já recebeu), então o mesmo lead vê a mesma sequência e dois
leads não veem exatamente a mesma coisa na mesma semana.

    Escolha = estados_ordenados[cursor % len(estados_ordenados)]

Ordenar por participação efetiva (não por UF) faz a rotação começar pelo
que a maior parte da obra executa — e o ciclo passar por todo o resto, em vez
de alternar só entre Paraná e São Paulo.

Ao esgotar o pool, o índice **reinicia** para 0: a base tem 9 estados e a
trilha dura anos, então repetir é melhor que parar de enviar. E o cursor é
mod 9, então o ciclo fecha limpo.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional, Sequence


def estados_ordenados(br: dict) -> list[dict]:
    """Estados por participação efetiva decrescente.

    Empate vai para o menor `valor_m2` — determinismo puro, sem depender da
    ordem da API, que pode mudar sem aviso.
    """
    est = [e for e in (br.get("estados") or []) if e.get("valor_m2") is not None]
    return sorted(est, key=lambda e: (-(e.get("participacao") or Decimal(0)),
                                      e["valor_m2"], e.get("uf") or ""))


def escolher_estado(br: dict, cursor: int) -> Optional[dict]:
    """O estado que este lead vê agora.

    `cursor` é o número de relatórios de conteúdo já enviados. Não é o número
    de estados vistos: é o que o roteiro sabe e o que sobrevive a uma falha
    no meio da sequência.
    """
    pool = estados_ordenados(br)
    if not pool:
        return None
    return pool[cursor % len(pool)]


def regioes_rotativas(br: dict, cursor: int) -> list[tuple[str, Decimal]]:
    """Ótima região a destacar, girando com o cursor.

    O relatório de dispersão mostra a região mais cara; sem rotação, a mesma
    regiãoiaparece em todos os ciclos. Aqui a ordem é decrescente e o cursor
    escolhe qual vai para o destaque — o gráfico continua mostrando todas.
    """
    reg = sorted((br.get("regioes") or {}).items(), key=lambda kv: -kv[1])
    if not reg:
        return []
    inicio = cursor % len(reg)
    return reg[inicio:] + reg[:inicio]


def variacao_de_rotacao(disponiveis: int, cursor: int) -> int:
    """Índice normalizado. Isola o `mod` para o cálculo ser testável."""
    return 0 if disponiveis <= 0 else cursor % disponiveis


__all__ = ["estados_ordenados", "escolher_estado", "regioes_rotativas",
           "variacao_de_rotacao"]
