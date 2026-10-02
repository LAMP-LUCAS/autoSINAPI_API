"""Testes da recuperação (winback) e da promoção — o 3º slot.

Regras do usuário: winback por **falta de consumo** (leitura do portal conta),
nos marcos 30 e 45 dias; promoção só para não-pagante, no máximo a cada 15
dias e com padrão bimestral.
"""

import datetime as _dt

from api.reports.grade import DIAS_PROMO, DIA_WINBACK, PROMO_MIN_DIAS, PROMO_PADRAO_DIAS
from api.reports.recoveredor import (MARCOS_WINBACK, ContextoRecuperacao,
                                     decidir_promo, decidir_winback)


def _c(**kw):
    base = dict(lead_id="l1", email="a@b.c", eh_cliente_pagante=False,
                dias_sem_consumo_api=None, dias_sem_consumo_portal=None,
                etapas_enviadas=(), consentimento=True,
                dias_sem_promocao=None, hoje=_dt.date(2026, 10, 7))
    base.update(kw)
    return ContextoRecuperacao(**base)


# ── consumo: os dois canais contam ───────────────────────────────────────────

def test_leitura_do_portal_conta_como_consumo():
    """Quem lê a KB toda semana e nunca chama a API está ativo.

    Caso que só falha se o cálculo usar API sozinha: `dias_sem_consumo_api`
    é `None` (nunca integrou). Com "primeiro não-nulo" o resultado seria
    `None` e o lead entraria em recuperação — o oposto do que o usuário pediu.
    """
    c = _c(dias_sem_consumo_api=None, dias_sem_consumo_portal=2)
    assert c.dias_sem_consumo == 2, "leitura do portal não contou como consumo"
    assert decidir_winback(c) is None, "recebeu winback apesar de ler o portal"

    # E o inverso: quem só usa API também está ativo.
    c2 = _c(dias_sem_consumo_api=1, dias_sem_consumo_portal=None)
    assert c2.dias_sem_consumo == 1
    assert decidir_winback(c2) is None


def test_uso_de_api_conta_como_consumo():
    c = _c(dias_sem_consumo_api=1, dias_sem_consumo_portal=None)
    assert c.dias_sem_consumo == 1
    assert decidir_winback(c) is None


def test_vale_o_menor_dos_dois_canais():
    """Ativo em qualquer canal é ativo — por isso o menor, não a média nem
    o primeiro disponível."""
    assert _c(dias_sem_consumo_api=2, dias_sem_consumo_portal=80).dias_sem_consumo == 2
    # Inverter a ordem dos argumentos não pode mudar o resultado.
    assert _c(dias_sem_consumo_api=80, dias_sem_consumo_portal=2).dias_sem_consumo == 2
    # E com ambos fora do marco, dispara pelo menor.
    assert decidir_winback(_c(dias_sem_consumo_api=31, dias_sem_consumo_portal=90)) \
        == "winback_30d"


def test_sem_consumo_em_nenhum_canal_nao_dispara():
    c = _c(dias_sem_consumo_api=None, dias_sem_consumo_portal=None)
    assert decidir_winback(c) is None


# ── winback: marcos 30 e 45 ─────────────────────────────────────────────────

def test_winback_dispara_em_30_dias():
    assert decidir_winback(_c(dias_sem_consumo_api=30)) == "winback_30d"


def test_winback_45d_so_apos_enviar_o_de_30():
    """45 dias é a segunda chance, não um disparo cego."""
    assert decidir_winback(_c(dias_sem_consumo_api=45)) == "winback_30d"
    c = _c(dias_sem_consumo_api=45, etapas_enviadas=("winback_30d",))
    assert decidir_winback(c) == "winback_45d"


def test_winback_nao_repete_o_mesmo_marco():
    c = _c(dias_sem_consumo_api=60, etapas_enviadas=("winback_30d", "winback_45d"))
    assert decidir_winback(c) is None


def test_winback_nao_vai_para_pagante():
    c = _c(dias_sem_consumo_api=60, eh_cliente_pagante=True)
    assert decidir_winback(c) is None, "cliente que paga entrou em recuperação"


def test_winback_respeita_consentimento():
    c = _c(dias_sem_consumo_api=60, consentimento=False)
    assert decidir_winback(c) is None


# ── promoção: só não-pagante, e espaçada ────────────────────────────────────

def test_promo_nunca_para_pagante():
    """A regra que o usuário definiu: promoção é para quem não paga nada."""
    c = _c(eh_cliente_pagante=True, dias_sem_promocao=365)
    assert decidir_promo(c) is None


def test_promo_para_nao_pagante_apos_padrao_bimestral():
    assert decidir_promo(_c(dias_sem_promocao=PROMO_PADRAO_DIAS)) == "promo"


def test_promo_nao_manda_antes_do_padrao():
    assert decidir_promo(_c(dias_sem_promocao=PROMO_PADRAO_DIAS - 1)) is None


def test_promo_nao_manda_na_primeira_vez():
    """Sem histórico, não abre com disparo — o padrão é o mais espaçado."""
    assert decidir_promo(_c(dias_sem_promocao=None)) is None


def test_promo_nao_repete_mesmo_tendo_passado_o_padrao():
    c = _c(dias_sem_promocao=999, etapas_enviadas=("promo",))
    assert decidir_promo(c) is None


def test_promo_respeita_consentimento():
    assert decidir_promo(_c(dias_sem_promocao=90, consentimento=False)) is None


def test_minimo_de_15_dias_entre_promocoes():
    from api.reports.recoveredor import promo_permite_hoje
    assert PROMO_MIN_DIAS == 15
    assert promo_permite_hoje(15) is True
    assert promo_permite_hoje(14) is False
    assert promo_permite_hoje(None) is False


# ── os dias fixos ───────────────────────────────────────────────────────────

def test_winback_na_quarta():
    import datetime
    assert DIA_WINBACK == 2
    assert datetime.date(2026, 10, 7).weekday() == DIA_WINBACK


def test_promo_na_segunda_ou_sabado():
    assert DIAS_PROMO == (0, 5)


def test_marcos_sao_30_e_45():
    assert MARCOS_WINBACK == (30, 45)
