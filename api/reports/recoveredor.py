"""api/reports/recoveredor.py — quem entra no 3º slot (recuperação e promoção).

Duas regras que não podem ser o "mesmo workflow com nome diferente":

**Recuperação (winback)** — disparada por **falta de consumo**, não por data.
Consumo é uso de API **e** leitura do portal: quem só lê a KB toda semana e
nunca chama a API está ativo, e receber winback seria dizer "voltamos porque
você parou" para alguém que não parou.

Marcos em 30 e 45 dias sem consumo. O segundo só existe se o primeiro não
reconvenceu — por isso o guard de "já enviou a etapa 1".

**Promoção** — só para quem **não paga**. Promover pagante ativo é jogar fora
a única receita que existe e ainda desvalorizar o plano. E é espaçada: no
máximo a cada 15 dias, com padrão bimestral, porque promoção frequente cansa
e ainda rouba a atenção do conteúdo.

Nenhuma das duas marca o lead como `lost`: `lost` é decisão comercial, não
efeito colateral de e-mail nonEnviar.
"""

from __future__ import annotations

import datetime as _dt
import logging
from decimal import Decimal
from typing import Optional, Sequence

from .grade import PROMO_MIN_DIAS, PROMO_PADRAO_DIAS

logger = logging.getLogger("autosinapi.reports.recuperacao")

# Marcos de recuperação: dias sem consumo → envio.
MARCOS_WINBACK = (30, 45)
STEP_WINBACK = {30: "winback_30d", 45: "winback_45d"}
STEP_PROMO = "promo"


def _int(v) -> Optional[int]:
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _d(v) -> Optional[_dt.date]:
    try:
        return v.date() if hasattr(v, "date") and callable(getattr(v, "date")) else (
            _dt.date.fromisoformat(str(v)[:10]) if v else None)
    except (ValueError, TypeError):
        return None


class ContextoRecuperacao:
    """O que a decisão precisa saber sobre um lead/cliente.

    Montado a partir da base pelo `api.crm_conteudo`; aqui só a regra, para
    ficar testável sem banco.
    """

    def __init__(self, *, lead_id: str, email: str, eh_cliente_pagante: bool,
                 dias_sem_consumo_api: Optional[int],
                 dias_sem_consumo_portal: Optional[int],
                 etapas_enviadas: Sequence[str] = (),
                 consentimento: bool = True,
                 dias_sem_promocao: Optional[int] = None,
                 hoje: Optional[_dt.date] = None):
        self.lead_id = lead_id
        self.email = email
        self.eh_cliente_pagante = eh_cliente_pagante
        self.dias_sem_consumo_api = dias_sem_consumo_api
        self.dias_sem_consumo_portal = dias_sem_consumo_portal
        self.etapas_enviadas = tuple(etapas_enviadas)
        self.consentimento = consentimento
        # Dias desde a última promoção. `None` = nunca houve.
        self.dias_sem_promocao = dias_sem_promocao
        self.hoje = hoje or _dt.date.today()

    @property
    def dias_sem_consumo(self) -> Optional[int]:
        """O menor dos dois: atividade em qualquer canal conta como atividade.

        Usar só API puniria quem consome o produto lendo; usar só portal
        deixaria passar quem consome a API sem abrir o site. O menor é o
        conservador nos dois sentidos.
        """
        vals = [v for v in (self.dias_sem_consumo_api, self.dias_sem_consumo_portal)
                if v is not None]
        return min(vals) if vals else None

    def ja_enviou(self, step: str) -> bool:
        return step in self.etapas_enviadas


def decidir_winback(c: ContextoRecuperacao) -> Optional[str]:
    """Passo de recuperação a enviar, ou `None`.

    `None` é o caso comum: ativo, sem consentimento, pagante Recoverido, ou
    nenhum marco atingido.
    """
    if not c.consentimento:
        return None
    if c.eh_cliente_pagante:
        # Cliente que paga não é perdido. Não entra em recuperação.
        return None

    dias = c.dias_sem_consumo
    if dias is None:
        return None

    for marco in MARCOS_WINBACK:
        if dias >= marco and not c.ja_enviou(STEP_WINBACK[marco]):
            return STEP_WINBACK[marco]
    return None


def decidir_promo(c: ContextoRecuperacao) -> Optional[str]:
    """Passo de promoção a enviar, ou `None`.

    Recusa pagante ativo sempre: a receita existe, e a promoção seria o oposto
    devalorizar o plano.
    """
    if not c.consentimento:
        return None
    if c.eh_cliente_pagante:
        return None
    if c.ja_enviou(STEP_PROMO):
        return None

    dias = c.dias_sem_promocao
    if dias is None:
        # Nunca houve promoção: a primeira respeita o padrão mais espaçado,
        # para não abrir com um mapa de disparos.
        return None
    return STEP_PROMO if dias >= PROMO_PADRAO_DIAS else None


def promo_permite_hoje(dias_sem_promocao: Optional[int]) -> bool:
    """Espaçamento mínimo. Separado da decisão para ser testável sozinho."""
    if dias_sem_promocao is None:
        return False
    return dias_sem_promocao >= PROMO_MIN_DIAS


__all__ = ["MARCOS_WINBACK", "STEP_WINBACK", "STEP_PROMO",
           "ContextoRecuperacao", "decidir_winback", "decidir_promo",
           "promo_permite_hoje"]
