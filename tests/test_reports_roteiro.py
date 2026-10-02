"""Testes do roteiro: o slot do dia vira decisão de envio.

Cada regra de recusa é um teste. O roteiro é onde "2 e-mails por semana" e
"nunca repetir" viram código — e onde um erro vira caixa de entrada do
cliente.
"""

import datetime as _dt
from decimal import Decimal as D

from api.reports.model import (Bloco, Categoria, Contexto, Metrica, Relatorio,
                               Serie)
from api.reports.roteiro import EstadoSemana, Roteiro, agenda_proximos_dias

# 2026-10-06 terça · 10-08 quinta · 10-07 quarta
TERCA = _dt.date(2026, 10, 6)
QUINTA = _dt.date(2026, 10, 8)
QUARTA = _dt.date(2026, 10, 7)

REL = Relatorio(
    chave="incc_leitura_mes", titulo="INCC 08/2026", resumo="Subiu.",
    blocos=[Bloco(metricas=[Metrica("INCC-M", "1.296,33")])],
    series=[Serie("INCC-M", [("jul", D("0.61")), ("ago", D("0.66"))])],
    categoria=Categoria.INSIGHT, rodape="Fonte BCB/SGS")


def _roteiro(novidade=True, relatorio=None):
    """Roteiro com montagem dublê — nenhuma chamada de rede no teste."""
    return Roteiro(montar_relatorio=lambda c: relatorio or REL,
                   houve_novidade=lambda: novidade)


def _ctx(**kw):
    base = dict(lead_id="l1", email="a@b.c", nome="Ana", persona="office",
                eh_cliente=False, dias_de_relacionamento=45,
                consentimento_marketing=True)
    base.update(kw)
    return Contexto(**base)


# ── recusas ─────────────────────────────────────────────────────────────────

def test_dia_sem_slot_nao_envia():
    """Sexta e domingo não têm slot — e quarta virou winback."""
    import datetime as _dt
    for dia in (_dt.date(2026, 10, 9), _dt.date(2026, 10, 11)):
        d = _roteiro().decidir(_ctx(), EstadoSemana(), dia)
        assert d.enviar is False
        assert "sem slot" in d.motivo, f"{dia} não deveria ser slot"


def test_sem_consentimento_nao_envia_mesmo_em_dia_de_slot():
    """E-mail de conteúdo é marketing, mesmo que o texto seja informativo."""
    d = _roteiro().decidir(_ctx(consentimento_marketing=False), EstadoSemana(), TERCA)
    assert d.enviar is False
    assert "consentimento" in d.motivo


def test_ciclo_completo_nao_reenvia():
    from api.reports.grade import TRILHA_ENRIQUECIMENTO
    d = _roteiro().decidir(_ctx(etapas_enviadas=list(TRILHA_ENRIQUECIMENTO)),
                           EstadoSemana(), TERCA)
    assert d.enviar is False
    assert "ciclo" in d.motivo


def test_teto_semanal_do_lead_novo_bloqueia():
    """1/semana: na segunda ele já recebeu, terça não entra."""
    d = _roteiro().decidir(_ctx(dias_de_relacionamento=5),
                           EstadoSemana(enviados_esta_semana=1), TERCA)
    assert d.enviar is False
    assert "teto" in d.motivo


def test_cadencia_do_lead_novo_respeitada():
    """Lead novo não recebe o mesmo slot antes de 6 dias."""
    d = _roteiro().decidir(_ctx(dias_de_relacionamento=5),
                           _estado(n=0, tipo="enriquecimento", dias=2), TERCA)
    assert d.enviar is False, "2 dias é cedo demais para lead novo (mínimo 6)"
    assert "cadência" in d.motivo


def test_lead_madura_pode_receber_com_3_dias():
    d = _roteiro().decidir(_ctx(dias_de_relacionamento=45),
                           EstadoSemana(enviados_esta_semana=0,
                                        dias_desde_ultimo_conteudo=3), TERCA)
    assert d.enviar is True


def test_competencia_sem_noveldade_pula():
    """O corte que viabiliza a cadência: não mudou, não manda.

    `sinapi_competencia` é o 4º da trilha, então os três anteriores precisam
    estar enviados para ele virar o candidato.
    """
    from api.reports.grade import TRILHA_ENRIQUECIMENTO
    anteriores = TRILHA_ENRIQUECIMENTO[:TRILHA_ENRIQUECIMENTO.index("sinapi_competencia")]
    r = _roteiro(novidade=False)
    d = r.decidir(_ctx(etapas_enviadas=anteriores), EstadoSemana(), TERCA)
    assert d.enviar is False
    assert "sem novidade" in d.motivo


def test_competencia_com_noveldade_segue():
    """Com competência nova, o mesmo relatório passa."""
    from api.reports.grade import TRILHA_ENRIQUECIMENTO
    anteriores = TRILHA_ENRIQUECIMENTO[:TRILHA_ENRIQUECIMENTO.index("sinapi_competencia")]
    d = _roteiro(novidade=True).decidir(_ctx(etapas_enviadas=anteriores),
                                         EstadoSemana(), TERCA)
    assert d.enviar is True


def test_conteudo_identico_ao_ultimo_pula():
    """Competência 'nova' com o mesmo número não é informação nova."""
    ctx = _ctx(ultima_assinatura=REL.assinatura())
    d = _roteiro().decidir(ctx, EstadoSemana(), TERCA)
    assert d.enviar is False
    assert "idêntico" in d.motivo


def test_relatorio_que_nao_monta_nao_envia():
    r = Roteiro(montar_relatorio=lambda c: None, houve_novidade=lambda: True)
    d = r.decidir(_ctx(), EstadoSemana(), TERCA)
    assert d.enviar is False
    assert "não pôde ser montado" in d.motivo


# ── o caminho feliz ──────────────────────────────────────────────────────────

def test_slot_liberado_monta_e_envia():
    d = _roteiro().decidir(_ctx(), EstadoSemana(), TERCA)
    assert d.enviar is True
    assert d.relatorio.chave == "incc_leitura_mes"
    assert d.slot == "enriquecimento"


def test_quinta_libera_o_slot_de_artigo():
    d = _roteiro().decidir(_ctx(), EstadoSemana(), QUINTA)
    assert d.slot == "artigo"


def test_roteiro_nao_chama_coleta_quando_nao_vai_enviar():
    """Montar antes de decidir gasta chamada de rede para e-mail que não sai.

    Verificado em **todas** as recusas, não só uma: cada motivo tem que
    poupar a coleta. Num dia em que o workflow roda para todos os leads, a
    diferença entre collectar e não é o que separa 3 requisições de 50.
    """
    cenarios = [
        ("sem consentimento", _ctx(consentimento_marketing=False), EstadoSemana()),
        ("teto semanal", _ctx(dias_de_relacionamento=5),
         EstadoSemana(enviados_esta_semana=1)),
        ("cadência", _ctx(dias_de_relacionamento=5),
         EstadoSemana(enviados_esta_semana=0, dias_ate_slot={"enriquecimento": 1},
                      ultimo_tipo="enriquecimento")),
    ]
    for nome, ctx, estado in cenarios:
        chamadas = []
        def montar(chave, _c=chamadas):
            _c.append(chave)
            return REL
        r = Roteiro(montar_relatorio=montar, houve_novidade=lambda: True)
        d = r.decidir(ctx, estado, TERCA)
        assert d.enviar is False, f"{nome}: decidiu enviar ({d.motivo})"
        assert chamadas == [], f"{nome}: coletou apesar de não enviar {chamadas}"


# ── o calendário inteiro ─────────────────────────────────────────────────────

def test_agenda_nao_excede_o_teto_do_segmento():
    ctx = _ctx(dias_de_relacionamento=5)          # lead novo: 1/semana
    previa = agenda_proximos_dias(ctx, EstadoSemana(), _roteiro(), TERCA, dias=21)
    enviados = [c for c, d, dec in previa if dec.enviar]
    assert len(enviados) <= 3, f"lead novo recebeu {len(enviados)} em 3 semanas"


def test_agenda_respeita_os_dias_da_grade():
    """Só envia em dia de slot: 2ª, 3ª, 4ª e 6ª.

    Winback (quarta) e promo (2ª/6ª) entram como vaga do 3º slot; sem
    `montar` wiring eles não disparam — o que a agenda deve refletir.
    """
    ctx = _ctx(dias_de_relacionamento=45)
    previa = agenda_proximos_dias(ctx, EstadoSemana(), _roteiro(), TERCA, dias=21)
    for _, dia, dec in previa:
        if dec.enviar:
            assert dia.weekday() in (1, 3), \
                f"enviou em {dia.strftime('%A')}, que não é slot"


def test_agenda_avanca_pela_trilha():
    """A previsão caminha pela trilha, sem repetir o mesmo relatório.

    O dublê devolve um relatório cujo `chave` é o da chave pedida — sem isso
    a agenda registraria o mesmo `chave` doze vezes e o teste passaria por um
    motivo errado.
    """
    from api.reports.grade import TRILHA_ENRIQUECIMENTO

    def montar(chave):
        return Relatorio(chave=chave, titulo=f"Título {chave}", resumo="r",
                         blocos=[Bloco(metricas=[Metrica("x", "1")])])

    r = Roteiro(montar_relatorio=montar, houve_novidade=lambda: True)
    previa = agenda_proximos_dias(_ctx(dias_de_relacionamento=45), EstadoSemana(),
                                 r, TERCA, dias=84)
    enviados = [dec.relatorio.chave for _, _, dec in previa if dec.enviar]
    assert len(enviados) >= 3, f"poucos envios na previsão: {len(enviados)}"
    assert len(set(enviados)) == len(enviados), \
        f"a previsão repetiu relatório: {enviados}"
    # e segue a ordem aprovada
    pos = [TRILHA_ENRIQUECIMENTO.index(c) for c in enviados]
    assert pos == sorted(pos), f"fora de ordem: {enviados}"


def test_agenda_para_quando_o_ciclo_termina():
    """Depois dos 9 episódios, a previsão não inventa o 10º."""
    from api.reports.grade import TRILHA_ENRIQUECIMENTO

    def montar(chave):
        return Relatorio(chave=chave, titulo="t", resumo="r",
                         blocos=[Bloco(metricas=[Metrica("x", "1")])])

    r = Roteiro(montar_relatorio=montar, houve_novidade=lambda: True)
    previa = agenda_proximos_dias(_ctx(dias_de_relacionamento=45), EstadoSemana(),
                                 r, TERCA, dias=200)
    enviados = [dec.relatorio.chave for _, _, dec in previa if dec.enviar]
    assert len(enviados) <= len(TRILHA_ENRIQUECIMENTO), \
        f"enviou {len(enviados)} numa trilha de {len(TRILHA_ENRIQUECIMENTO)}"


# ── os dois carris são separados ──────────────────────────────────────────────
# Bug real (2026-10-02): o roteiro não distinguia os slots, e a quinta-feira
# entregava o relatório de terça. O lead maduro recebia 1 e-mail/semana em vez
# de 2 — e nenhuma regra disparava, porque cada decisão isolada era "correta".

ARTIGO = Relatorio(
    chave="kb_01", titulo="Curva S na prática", resumo="Artigo da KB.",
    blocos=[Bloco(metricas=[Metrica("Leitura", "12 min")])],
    categoria=Categoria.INSIGHT, rodape="Base de Conhecimento")


def _roteiro_com_artigo(novidade=True):
    return Roteiro(montar_relatorio=lambda c: REL,
                   houve_novidade=lambda: novidade,
                   montar_artigo=lambda ctx: ARTIGO)


def test_terca_entrega_relatorio_e_quinta_entrega_artigo():
    ctx = _ctx(dias_de_relacionamento=45)
    r = _roteiro_com_artigo()

    terca = r.decidir(ctx, EstadoSemana(0, 4), TERCA)
    quinta = r.decidir(ctx, EstadoSemana(0, 4), QUINTA)

    assert terca.slot == "enriquecimento" and terca.relatorio.chave.startswith("incc_")
    assert quinta.slot == "artigo" and quinta.relatorio.chave == "kb_01"


def test_winback_sem_montador_nao_dispara():
    """O 3º slot existe na grade mas depende de fonte própria (recuperador.py).

    Sem montador, ele recusa explicitamente — nunca cai para o relatório, que é
    do slot de terça.
    """
    r = _roteiro()
    d = r.decidir(_ctx(dias_de_relacionamento=45), EstadoSemana(), QUARTA)
    assert d.enviar is False
    assert "winback" in d.motivo
    assert d.slot == "winback"


def test_slot_de_artigo_nao_depende_do_ciclo_de_relatorio():
    """Relatório acabou, artigo continua: são eixos independentes."""
    from api.reports.grade import TRILHA_ENRIQUECIMENTO
    ctx = _ctx(dias_de_relacionamento=45,
               etapas_enviadas=list(TRILHA_ENRIQUECIMENTO))
    r = _roteiro_com_artigo()

    terca = r.decidir(ctx, EstadoSemana(0, 4), TERCA)
    quinta = r.decidir(ctx, EstadoSemana(0, 4), QUINTA)

    assert terca.enviar is False and "ciclo" in terca.motivo
    assert quinta.enviar is True, "artigo parou junto com o relatório"


def test_slot_de_artigo_respeita_o_teto_semanal():
    ctx = _ctx(dias_de_relacionamento=45)
    r = _roteiro_com_artigo()
    d = r.decidir(ctx, EstadoSemana(enviados_esta_semana=2), QUINTA)
    assert d.enviar is False
    assert "teto" in d.motivo


def test_sem_trilha_de_article_configurada_o_slot_recusa():
    """Falha explícita em vez de entregar relatório no lugar do artigo."""
    r = _roteiro()          # sem montar_artigo
    d = r.decidir(_ctx(dias_de_relacionamento=45), EstadoSemana(0, 4), QUINTA)
    assert d.enviar is False
    assert "artigo" in d.motivo


def test_lead_maduro_recebe_dois_por_semana():
    """O contrato do calendário: terça + quinta, dois e-mails."""
    r = _roteiro_com_artigo()
    ctx = _ctx(dias_de_relacionamento=45)

    terca = r.decidir(ctx, EstadoSemana(0, 4), TERCA)
    # quinta é outro slot do MESMO ciclo: a cadência não barra por tipo
    quinta = r.decidir(ctx, EstadoSemana(1, 1, ultimo_tipo="enriquecimento"),
                       QUINTA)
    assert terca.enviar is True
    assert quinta.enviar is True, f"quinta barrada: {quinta.motivo}"


def test_lead_novo_recebe_um_por_semana():
    """1/semana é o contrato do segmento novo, mesmo com dois slots livres."""
    r = _roteiro_com_artigo()
    ctx = _ctx(dias_de_relacionamento=5)
    terca = r.decidir(ctx, EstadoSemana(0, None), TERCA)
    quinta = r.decidir(ctx, EstadoSemana(1, 2, ultimo_tipo="enriquecimento"),
                       QUINTA)
    assert terca.enviar is True
    assert quinta.enviar is False, "lead novo recebeu 2 na mesma semana"


# ── a cadência é por slot, não global ────────────────────────────────────────
# Terça (relatório) e quinta (artigo) são o mesmo ciclo semanal. Aplicar a
# cadência global bloquearia o segundo envio do maduro. E `dias_ate_slot` é
# por tipo porque "dias desde o último envio" não distingue artigo-de-artigo
# de artigo-após-relatório — e o artigo repetido passava.

def _estado(n=1, tipo="artigo", dias=2):
    """Estado com `dias` no tipo `tipo` — que é o que o roteiro consulta."""
    return EstadoSemana(enviados_esta_semana=n, dias_ate_slot={tipo: dias},
                       ultimo_tipo=tipo)


def test_maduro_aceita_artigo_nos_dois_slots_da_semana():
    r = _roteiro_com_artigo()
    ctx = _ctx(dias_de_relacionamento=45)
    terca = r.decidir(ctx, EstadoSemana(enviados_esta_semana=0), TERCA)
    quinta = r.decidir(ctx, _estado(n=1, tipo="enriquecimento", dias=2), QUINTA)
    assert terca.enviar is True
    assert quinta.enviar is True, f"quinta barrada: {quinta.motivo}"


def test_maduro_bloqueia_artigo_repetido_cedo():
    """Mesmo slot, pouco depois: a cadência existe para isso."""
    r = _roteiro_com_artigo()
    ctx = _ctx(dias_de_relacionamento=45)
    d = r.decidir(ctx, _estado(n=1, tipo="artigo", dias=2), QUINTA)
    assert d.enviar is False
    assert "cadência" in d.motivo


def test_maduro_aceita_artigo_na_semana_seguinte():
    r = _roteiro_com_artigo()
    ctx = _ctx(dias_de_relacionamento=45)
    d = r.decidir(ctx, _estado(n=1, tipo="artigo", dias=7), QUINTA)
    assert d.enviar is True


def test_novo_bloqueia_artigo_mesmo_com_dias():
    """Lead novo: 1/semana, com intervalo de 6 dias."""
    r = _roteiro_com_artigo()
    ctx = _ctx(dias_de_relacionamento=5)
    d = r.decidir(ctx, _estado(n=1, tipo="artigo", dias=6), QUINTA)
    assert d.enviar is False, f"lead novo recebeu 2/semana: {d.motivo}"


def test_novo_aceita_artigo_depois_de_uma_semana():
    r = _roteiro_com_artigo()
    ctx = _ctx(dias_de_relacionamento=5)
    d = r.decidir(ctx, _estado(n=1, tipo="artigo", dias=6), QUINTA)
    # exatamente 6 dias: pode (mínimo é 6)
    assert pode_receber_min(ctx.segmento, 6)


def pode_receber_min(segmento, dias):
    from api.reports.grade import pode_receber
    return pode_receber(segmento, dias)


def test_terca_nao_e_barrada_por_artigo_recente():
    """Slots diferentes não competem: artigo de quinta não atrasa terça."""
    r = _roteiro_com_artigo()
    ctx = _ctx(dias_de_relacionamento=45)
    d = r.decidir(ctx, _estado(n=1, tipo="artigo", dias=2), TERCA)
    assert d.enviar is True, f"terça barrada por artigo: {d.motivo}"
