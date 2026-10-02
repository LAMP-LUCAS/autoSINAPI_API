"""Testes da grade: sequência, cadência e o corte do que não mudou.

A grade é onde o calendário vira decisão. Erro aqui é e-mail na hora errada
para pessoa errada — por isso os testes cobrem também o que NÃO deve sair.
"""

import datetime as _dt

from api.reports.grade import (DIA_ARTIGO, DIA_ENRIQUECIMENTO,
                              MAX_POR_SEMANA, PULA_SEM_NOVIDADE, SLOTS,
                              TRILHA_ENRIQUECIMENTO, ciclo_completo,
                              deve_pular, excedeu_semana, pode_receber,
                              proximo_relatorio, semanas_ate_ciclo, slot_do_dia)


# ── a trilha ─────────────────────────────────────────────────────────────────

def test_trilha_tem_nove_episodios_na_ordem_aprovada():
    assert TRILHA_ENRIQUECIMENTO == (
        "incc_leitura_mes", "incc_timing_m_di", "cub_dispersao",
        "sinapi_cobertura", "incc_aceleracao", "cub_estado_projeto",
        "sinapi_foco_custo", "incc_horizonte_36m", "sinapi_competencia",
    )


def test_chaves_sao_unicas():
    """Chave repetida faria o dedupe esconder um relatório nunca enviado."""
    assert len(set(TRILHA_ENRIQUECIMENTO)) == len(TRILHA_ENRIQUECIMENTO)


def test_sequencia_anda_na_ordem_e_nao_pula():
    enviados = list(TRILHA_ENRIQUECIMENTO[:3])
    assert proximo_relatorio(enviados) == TRILHA_ENRIQUECIMENTO[3]


def test_sequencia_nao_reinicia_no_fim():
    """Reenviar o episódio 1 no episódio 10 é o que a trilha evita."""
    assert proximo_relatorio(list(TRILHA_ENRIQUECIMENTO)) is None
    assert ciclo_completo(list(TRILHA_ENRIQUECIMENTO))


def test_ordem_de_envio_nao_altera_a_sequencia():
    """A trilha é do lead, não da data: bagunhar o histórico não muda o eixo."""
    a = list(TRILHA_ENRIQUECIMENTO[:2])
    assert proximo_relatorio(a) == proximo_relatorio(list(reversed(a)))


def test_so_competencia_depende_de_noveldade():
    """Oito são ângulos do mesmo dado; só um precisa de competência nova."""
    assert PULA_SEM_NOVIDADE == {"sinapi_competencia"}
    assert len(TRILHA_ENRIQUECIMENTO) - len(PULA_SEM_NOVIDADE) == 8


def test_relatorio_de_competencia_pula_sem_novidade():
    """Reenviar 'atualizado em agosto' na semana 6 ensina que o e-mail mente."""
    assert deve_pular("sinapi_competencia", houve_novidade=False) is True
    assert deve_pular("sinapi_competencia", houve_novidade=True) is False


def test_angulo_nao_pula_mesmo_sem_competencia_nova():
    """Ângulo novo é informação nova: renderiza bem com o dado do mês."""
    assert deve_pular("incc_leitura_mes", houve_novidade=False) is False


# ── os dias ──────────────────────────────────────────────────────────────────

def test_enriquecimento_na_terca_e_artigo_na_quinta():
    # 2026-10-06 é terça, 2026-10-08 é quinta
    assert slot_do_dia(_dt.date(2026, 10, 6)).tipo == "enriquecimento"
    assert slot_do_dia(_dt.date(2026, 10, 8)).tipo == "artigo"


def test_dias_sem_slot_nao_disparam_nada():
    """Quarta e segunda não têm e-mail de conteúdo."""
    for d in (_dt.date(2026, 10, 5), _dt.date(2026, 10, 7),
              _dt.date(2026, 10, 10), _dt.date(2026, 10, 11)):
        assert slot_do_dia(d) is None, f"{d} não deveria ter slot"


def test_os_dois_slots_sao_em_dias_distintos():
    assert DIA_ENRIQUECIMENTO != DIA_ARTIGO
    assert len(SLOTS) == 2


# ── a cadência por segmento ──────────────────────────────────────────────────

def test_lead_novo_recebe_menos():
    """Um por semana enquanto ainda está sendo presentations ao produto."""
    assert pode_receber("novo", dias_desde_ultimo=4) is False   # < 6 dias
    assert pode_receber("novo", dias_desde_ultimo=7) is True
    assert pode_receber("madura", dias_desde_ultimo=3) is True  # >= 3 dias


def test_quem_nunca_recebeu_pode_receber():
    assert pode_receber("novo", dias_desde_ultimo=None) is True


def test_teto_semanal_por_segmento():
    assert MAX_POR_SEMANA["novo"] == 1
    assert MAX_POR_SEMANA["madura"] == 2
    assert MAX_POR_SEMANA["cliente"] == 2
    assert excedeu_semana("novo", enviados_esta_semana=1) is True
    assert excedeu_semana("madura", enviados_esta_semana=2) is True
    assert excedeu_semana("madura", enviados_esta_semana=1) is False


def test_duracao_da_trilha_por_cadencia():
    """Reportar o horizonte: 9 episódios são 9 semanas a 1/sem, ~5 a 2."""
    assert semanas_ate_ciclo(0) == 9
    assert semanas_ate_ciclo(1) == 5
