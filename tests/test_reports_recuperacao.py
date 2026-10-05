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


def test_promo_espera_um_ciclo_da_trilha_antes_da_primeira():
    """Sem nada recebido antes, não abre com disparo.

    Exigir histórico de *promoção* seria circular — a primeira é a que cria o
    histórico, então o impasse nunca acabaria. O corte é um ciclo da trilha:
    relatório **e** artigo.
    """
    assert decidir_promo(_c(dias_sem_promocao=None)) is None
    assert decidir_promo(_c(dias_sem_promocao=None,
                            etapas_enviadas=("incc_leitura_mes",))) is None
    assert decidir_promo(_c(dias_sem_promocao=None,
                            etapas_enviadas=("kb_curva_abc",))) is None


def test_primeira_promo_apos_o_ciclo_completo():
    c = _c(dias_sem_promocao=None,
           etapas_enviadas=("incc_leitura_mes", "kb_curva_abc"))
    assert decidir_promo(c) == "promo"


def test_artigo_gravado_com_slug_tambem_completa_o_ciclo():
    """O slot de artigo grava o **slug** em `step`, não `kb_NN`.

    Regressão que aconteceu em produção: lead com relatório + artigo enviados,
    e a promoção recusava com "nenhum lead elegível a promo". Dois formatos
    convivem na `nurture_state`, porque vêm de dois códigos:

    * `kb_01`, `kb_02` — o rótulo de `kb_sequence.step_para`, usado por
      `kb_admin`;
    * o slug cru (`analise-tendencia-preco-insumos`) — o que o slot de artigo
      do `crm_conteudo` grava, porque `UNIQUE (lead_id, step)` é o que garante
      "um artigo, uma vez" e o slug é o identificador estável do conteúdo.

    `startswith("kb_")` enxergava só o primeiro. O teste acima passava porque
    a fixture usava o formato bonito; este usa o formato real — o que a base
    mostra (`SELECT DISTINCT step FROM saas.nurture_state`).
    """
    c = _c(dias_sem_promocao=None,
           etapas_enviadas=("incc_leitura_mes",
                            "analise-tendencia-preco-insumos"))
    assert decidir_promo(c) == "promo", "artigo real não contou como ciclo"


def test_so_artigo_sem_relatorio_nao_abre_a_promocao():
    """Metade do ciclo não é ciclo — e o slug não pode virar 'relatório'."""
    c = _c(dias_sem_promocao=None,
           etapas_enviadas=("analise-tendencia-preco-insumos",))
    assert decidir_promo(c) is None


def test_passo_de_nurture_nao_conta_como_conteudo():
    """`d3`/`d7` são follow-up do nurture, não relatório nem artigo.

    Se fossem tratados como "não-artigo" virariam relatório por exclusão —
    e um lead só com follow-up abriria promoção sem nunca ter recebido nada
    da trilha.
    """
    assert decidir_promo(_c(dias_sem_promocao=None,
                            etapas_enviadas=("d3",))) is None
    assert decidir_promo(_c(dias_sem_promocao=None,
                            etapas_enviadas=("d3", "d7"))) is None


def test_winback_sozinho_nao_abre_a_promocao():
    """Recuperação não é conteúdo — não vale como ciclo."""
    c = _c(dias_sem_promocao=None, etapas_enviadas=("winback_30d",))
    assert decidir_promo(c) is None


def test_winback_junto_do_relatorio_tambem_nao_e_ciclo():
    """Recuperação + relatório não é 'relatório + artigo'.

    Se o passo de recuperação fosse classificado como artigo (ele não é
    relatório e não é nurture), este lead destravaria promoção sem jamais
    ter recebido um artigo da KB.
    """
    c = _c(dias_sem_promocao=None,
           etapas_enviadas=("incc_leitura_mes", "winback_30d"))
    assert decidir_promo(c) is None


def test_promo_anterior_nao_conta_como_artigo():
    """`promo` é passo de controle, não conteúdo da trilha.

    Testado em `trilha_completada` e não em `decidir_promo`: lá a guarda
    `ja_enviou("promo")` já devolveria `None` e esconderia a classificação.
    """
    c = _c(etapas_enviadas=("incc_leitura_mes", "promo"))
    assert c.trilha_completada is False, "promoção contou como artigo"


def test_winback_nao_conta_como_artigo_na_trilha():
    c = _c(etapas_enviadas=("incc_leitura_mes", "winback_30d"))
    assert c.trilha_completada is False, "winback contou como artigo"


def test_followup_de_nurture_nao_conta_como_artigo():
    c = _c(etapas_enviadas=("incc_leitura_mes", "d3", "d7"))
    assert c.trilha_completada is False, "follow-up contou como artigo"


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
