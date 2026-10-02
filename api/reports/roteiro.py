"""api/reports/roteiro.py — o slot do dia vira decisão de envio.

A `grade` diz *quando* e *em que ordem*. O roteiro diz *se* aquele slot sai,
para aquele lead, hoje — e é onde a política de frequency cap vira código.

Ordem de decisão (a primeira que responder vence)
--------------------------------------------------
1. **Não é dia de slot** → não envia.
2. **Sem consentimento de marketing** → não envia (e-mail de conteúdo é
   marketing por definição, mesmo que o texto seja informativo).
3. **Ciclo já completo** → não envia. A trilha acaba; não se repete.
4. **Teto da semana atingido** → não envia. É o que impede a segunda-feira
   de virar dia de promo + artigo + campanha.
5. **Cadência do segmento não respeitada** → não envia.
6. **O dado não mudou e o relatório é de competência** → não envia.
7. Envia.

O relatório é montado **depois** dessas checagens, e só se for enviar. Montar
antes gasta uma chamada à API do INCC para um e-mail que não sai — num dia em
que o workflow roda para todos os leads, isso é a diferença entre 50 requisições
e 3.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from typing import Callable, Optional

from .grade import (PULA_SEM_NOVIDADE, Slot, excedeu_semana, pode_receber,
                    proximo_relatorio, slot_do_dia)
from .model import Contexto, Decisao, Relatorio


@dataclass(frozen=True)
class EstadoSemana:
    """O que já saiu nesta semana, para o teto semanal ter base."""

    enviados_esta_semana: int = 0
    dias_desde_ultimo_conteudo: Optional[int] = None
    # Dias desde o último envio **por tipo de slot**. A cadência é por tipo:
    # terça e quinta são o mesmo ciclo semanal, e repetir um artigo 2 dias
    # depois precisa ser visto — o que `dias_desde_ultimo_conteudo` (do tipo
    # que saiu por último) não distingue.
    dias_ate_slot: Optional[dict] = None
    ultimo_tipo: Optional[str] = None

    @property
    def semana(self) -> str:
        return "atual"


class Roteiro:
    """Decide e monta. Recebe as funções de coleta; não conhece SQL nem HTTP.

    A injeção é o que torna o roteiro testável com dublês: `montar_relatorio`
    pode devolver um `Relatorio` fixo, e o teste verifica a decisão sem tocar
    rede — que é como o roteiro é exercitado nos testes.
    """

    def __init__(self, *, montar_relatorio: Callable[[str], Optional[Relatorio]],
                 houve_novidade: Callable[[], bool],
                 montar_artigo: Optional[Callable[[Contexto], Optional[Relatorio]]] = None):
        self._montar = montar_relatorio
        self._novidade = houve_novidade
        # O slot de artigo é uma trilha separada, com fonte própria: o
        # relatório e o artigo não disputam o mesmo eixo. Sem isto, a quinta
        # entregava o relatório de terça — e o lead maduro recebia 1/semana
        # em vez de 2, sem nenhum aviso.
        self._montar_artigo = montar_artigo

    def _decidir_artigo(self, ctx: Contexto, slot: Slot) -> Decisao:
        """Slot de artigo: trilha própria, escolhida pelo persona e nível.

        A ordem de recusas é a mesma do enriquecimento (consentimento, teto,
        cadência) — verificada em `decidir` antes de chegar aqui.
        """
        if self._montar_artigo is None:
            return Decisao(False,
                           motivo="trilha de artigo não configurada",
                           slot=slot.tipo)
        art = self._montar_artigo(ctx)
        if art is None:
            return Decisao(False,
                           motivo="sem artigo disponível para este lead",
                           slot=slot.tipo)
        return Decisao(True, relatorio=art, slot=slot.tipo,
                       motivo="slot artigo liberado")

    def decidir(self, ctx: Contexto, estado: EstadoSemana,
                hoje: _dt.date) -> Decisao:
        slot = slot_do_dia(hoje)
        if slot is None:
            return Decisao(False, motivo="dia sem slot de conteúdo")

        # E-mail de conteúdo é marketing, mesmo quando informativo. Sem
        # consentimento, não sai — e a decisão vale igual para artigo e
        # relatório, porque os dois são propulsion de marca.
        if not ctx.consentimento_marketing:
            return Decisao(False, motivo="sem consentimento de marketing",
                           slot=slot.tipo)

        # Só o enriquecimento anda por sequência de relatório; artigo,
        # winback e promo têm fonte própria (ver os blocos abaixo). Sem este
        # guarda, `chave` fica indefinida nos outros slots e quebra neles.
        chave = None
        if slot.tipo == "enriquecimento":
            chave = proximo_relatorio(ctx.etapas_enviadas)
            if chave is None:
                return Decisao(False, motivo="ciclo de conteúdo concluído",
                               slot=slot.tipo)

        if excedeu_semana(ctx.segmento, estado.enviados_esta_semana):
            return Decisao(False,
                           motivo=f"teto semanal do segmento "
                                  f"({ctx.segmento}) atingido",
                           slot=slot.tipo)

        # A cadência é **por tipo de slot**, não global. Terça (relatório) e
        # quinta (artigo) são o mesmo ciclo semanal: aplicar a cadência global
        # bloquearia o segundo envio da semana do maduro, que é justamente o
        # que a segmentação promete.
        #
        # `dias_ate_slot` guarda o intervalo por tipo. Usar "dias desde o
        # último envio" deixava passar um artigo 2 dias depois de outro
        # artigo, porque o último envio tinha sido o relatório de terça.
        dias_ate = (estado.dias_ate_slot or {}).get(slot.tipo)
        if dias_ate is not None and not pode_receber(ctx.segmento, dias_ate):
            return Decisao(False,
                           motivo=f"cadência de {ctx.segmento} não respeitada",
                           slot=slot.tipo)

        # O corte de "não mudou" é o que torna a cadência possível: sem ele o
        # relatório do mês que não avançou sairia toda semana.
        if slot.tipo == "enriquecimento":
            novidade = self._novidade() if chave in PULA_SEM_NOVIDADE else True
            if not novidade:
                return Decisao(False,
                               motivo=f"{chave} sem novidade — competência não avançou",
                               slot=slot.tipo)

        if slot.tipo == "artigo":
            return self._decidir_artigo(ctx, slot)
        if slot.tipo in ("winback", "promo"):
            # Slot móvel do 3º lugar. Sem montador, não dispara — e o
            # relatório de conteúdo não é usado para eles.
            return Decisao(False,
                           motivo=f"slot {slot.tipo} sem montador configurado",
                           slot=slot.tipo)

        rel = self._montar(chave)
        if rel is None:
            return Decisao(False,
                           motivo=f"{chave} não pôde ser montado (dado insuficiente)",
                           slot=slot.tipo)

        # Segunda trava: mesmo que a competência seja "nova", se o conteúdo é
        # idêntico ao último, não sai. `assinatura` é do conteúdo, não da
        # data — então competência nova com número igual não engana.
        if rel.assinatura() == getattr(ctx, "ultima_assinatura", None):
            return Decisao(False,
                           motivo=f"{chave} idêntico ao último enviado",
                           slot=slot.tipo)

        return Decisao(True, relatorio=rel, slot=slot.tipo,
                       motivo=f"slot {slot.tipo} liberado")


def agenda_proximos_dias(ctx: Contexto, estado: EstadoSemana,
                         roteiro: Roteiro, inicio: _dt.date,
                         dias: int = 28) -> list[tuple[str, _dt.date, Decisao]]:
    """Calendário previsto: o que sairia em cada dia do horizonte.

    Serve para o painel mostrar ao operador a fila antes dela existir, e
    para o teste verificar o calendário inteiro sem esperar semanas.
    `montar_relatorio` é chamado uma vez por chave e memorizado, para a
    previsão não custar uma chamada por dia.
    """
    cache: dict[str, Optional[Relatorio]] = {}
    previa: list[tuple[str, _dt.date, Decisao]] = []
    enviados = list(ctx.etapas_enviadas)
    semana_cont = estado.enviados_esta_semana
    ultimo_dia: Optional[int] = estado.dias_desde_ultimo_conteudo

    for offset in range(dias):
        dia = inicio + _dt.timedelta(days=offset)
        chave = proximo_relatorio(enviados)
        if chave not in cache:
            cache[chave] = roteiro._montar(chave)
        rel = cache[chave]

        ctx_dia = Contexto(ctx.lead_id, ctx.email, ctx.nome, ctx.persona,
                           ctx.eh_cliente, ctx.dias_de_relacionamento,
                           tuple(enviados), ctx.consentimento_marketing)
        dec = roteiro.decidir(ctx_dia, EstadoSemana(semana_cont, ultimo_dia), dia)

        if dec.enviar and dec.relatorio is not None:
            enviados.append(dec.relatorio.chave)
            semana_cont += 1
            ultimo_dia = 0
        elif ultimo_dia is not None:
            ultimo_dia += 1

        # A semana vira na segunda.
        if dia.weekday() == 0 and offset > 0:
            semana_cont = 0

        previa.append((dec.relatorio.chave if dec.relatorio else "-", dia, dec))
    return previa


__all__ = ["EstadoSemana", "Roteiro", "agenda_proximos_dias"]
