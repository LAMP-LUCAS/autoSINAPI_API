"""api/reports/grade.py — a sequência de 9 relatórios e o dia em que saem.

O problema que a grade resolve
-----------------------------
Onze fontes de e-mail competes pela atenção do mesmo lead: artigo, relatório,
promo, win-back, além das notificações (boas-vindas, quota, base update). Sem
grade, `promo_weekly` mandava às segundas para todos e um lead recebia artigo
e campanha no mesmo dia.

Duas regras que não são sugestão
--------------------------------
1. **O eixo é a sequência, não o dia.** Cada slot recebe o *próximo relatório
   não enviado* da trilha. Se um dia não sair (lead novo, cadence), o próximo
   entra depois — o eixo não anda sozinho e não pula conteúdo.
2. **O que não mudou não entra.** Um relatório cuja `assinatura` bate com o
   último enviado é `pular`. Só isso viabiliza a cadência: sem ela, o relatório
   do mês que não mudou seria reenviado toda semana.

O corte de conteúdo novo
------------------------
O relatório de competência é o único que depende de dado novo, e é o único que
**pula** quando não há competência nova. Sem o corte, o lead recebe um
"atualizado em agosto" na semana 6, quando já existe setembro — e a primeira
coisa que ele aprende é que o e-mail mente.

A grade é determinística: mesma sequência, mesmo dia, mesmo relatório.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from typing import Optional, Sequence

from .model import Categoria, Relatorio

# A trilha, na ordem aprovada. Não é uma lista do que "seria legal enviar" —
# é a sequência que o lead percorre, e cada item é uma leitura diferente do
# mesmo dado.
TRILHA_ENRIQUECIMENTO: tuple[str, ...] = (
    "incc_leitura_mes",      # 1  🆕 o número novo do mês
    "incc_timing_m_di",      # 2  🔄 o que a diferença entre janelas mostra
    "cub_dispersao",         # 3  🔄 por que o m² varia tanto entre regiões
    "sinapi_cobertura",      # 4  🆕 competência nova
    "incc_aceleracao",       # 5  🔄 acelerando ou desacelerando
    "cub_estado_projeto",    # 6  🔄 um estado, um número, uma obra
    "sinapi_foco_custo",     # 7  🔄 onde mexer primeiro no orçamento
    "incc_horizonte_36m",    # 8  🔄 o que o número do mês não mostra
    "sinapi_competencia",    # 9  🆕 PULA se não houver competência nova
)

# O único que depende de dado novo. Os outros oito são ângulos: renders bem com
# competência do mês anterior, porque o ângulo é que muda.
PULA_SEM_NOVIDADE = frozenset({"sinapi_competencia"})

# Dia da semana: 0=segunda … 6=domingo.
#
# Três slots fixos mais duas vagas móveis:
#
#   terça    → relatório (enriquecimento)   trilha de 9
#   quinta   → artigo da KB                trilha de conteúdo
#   quarta   → recuperação (winback)        3º slot
#   2ª/6ª    → promoção                    3º slot, vaga
#
# Winback e promo **disputam o 3º slot**, não são trilhas paralelas: dois
# workflows independentes era o que permitia 3–4 e-mails na mesma semana.
DIA_ENRIQUECIMENTO = 1      # terça
DIA_ARTIGO = 3              # quinta
DIA_WINBACK = 2             # quarta
DIAS_PROMO = (0, 5)        # segunda, sábado

# Cadência por segmento. Lead novo recebe menos: ainda está sendo presentations
# ao produto, e dois e-mails por semana antes da primeira resposta cansa.
MIN_DIAS_NOVO = 6            # 1×/semana
MIN_DIAS_MADURO = 3          # 2×/semana
MAX_POR_SEMANA = {"novo": 1, "madura": 2, "cliente": 2}


@dataclass(frozen=True)
class Slot:
    """Um slot do calendário: dia, tipo e o que é candidato a ocupá-lo."""

    dia_semana: int
    tipo: str                   # 'enriquecimento' | 'artigo'
    hora: int


SLOTS = (
    Slot(DIA_ENRIQUECIMENTO, "enriquecimento", 10),
    Slot(DIA_WINBACK, "winback", 11),
    Slot(DIA_ARTIGO, "artigo", 16),
    Slot(DIAS_PROMO[0], "promo", 9),
    Slot(DIAS_PROMO[1], "promo", 9),
)

# Cadência do slot móvel. A promo é a mais espaçada de todas: máximo a cada
# 15 dias, e o padrão é bimestral (60) — promoção toda semana cansa e ainda
# ocupa a atenção que o conteúdo deveria ter.
PROMO_MIN_DIAS = 15
PROMO_PADRAO_DIAS = 60


def slot_do_dia(d: _dt.date) -> Optional[Slot]:
    for s in SLOTS:
        if d.weekday() == s.dia_semana:
            return s
    return None


def proximo_relatorio(chaves_enviadas: Sequence[str]) -> Optional[str]:
    """Próxima chave da trilha que o lead ainda não recebeu.

    A sequência **não reinicia** quando o pool acaba: devolve `None`. Reiniciar
    faria o lead receber de novo o relatório do mês 1 no mês 6, e a trilha
    existe justamente para não repetir.
    """
    enviados = set(chaves_enviadas)
    for chave in TRILHA_ENRIQUECIMENTO:
        if chave not in enviados:
            return chave
    return None


def ciclo_completo(chaves_enviadas: Sequence[str]) -> bool:
    """True quando o lead já recebeu a trilha inteira."""
    return set(TRILHA_ENRIQUECIMENTO).issubset(set(chaves_enviadas))


def semanas_ate_ciclo(n: int = 0) -> int:
    """Quantas semanas a trilha inteira leva, com o nº de e-mails por semana.

    Serve para o relatório de cobertura: "sua trilha tem 9 episódios, leva ~9
    semanas na cadência de 1/semana e ~5 na de 2".
    """
    total = len(TRILHA_ENRIQUECIMENTO) + n      # n = artigos por semana
    return max(1, -(-total // max(1, n + 1)))   # ceil(total / (n+1))


def pode_receber(segmento: str, dias_desde_ultimo: Optional[int]) -> bool:
    """A cadence do segmento foi respeitada?

    `dias_desde_ultimo is None` = nunca recebeu nada de conteúdo → pode.
    """
    if dias_desde_ultimo is None:
        return True
    minimo = MIN_DIAS_NOVO if segmento == "novo" else MIN_DIAS_MADURO
    return dias_desde_ultimo >= minimo


def excedeu_semana(segmento: str, enviados_esta_semana: int) -> bool:
    """O teto do segmento já foi atingido nesta semana?"""
    return enviados_esta_semana >= MAX_POR_SEMANA.get(segmento, 2)


def deve_pular(chave: str, houve_novidade: bool) -> bool:
    """O relatório épulável porque o dado não mudou?"""
    return chave in PULA_SEM_NOVIDADE and not houve_novidade


__all__ = ["TRILHA_ENRIQUECIMENTO", "PULA_SEM_NOVIDADE", "Slot", "SLOTS",
           "DIA_ENRIQUECIMENTO", "DIA_ARTIGO", "MIN_DIAS_NOVO",
           "MIN_DIAS_MADURO", "MAX_POR_SEMANA", "slot_do_dia",
           "proximo_relatorio", "ciclo_completo", "semanas_ate_ciclo",
           "pode_receber", "excedeu_semana", "deve_pular"]
