"""Testes das regras de formatação e montagem (sem banco).

`_montar` é pura de propósito: o teste verifica a *decisão editorial*
("acelerando", "spread negativo") com literais, em vez de popular o INCC.
"""

from datetime import date
from decimal import Decimal as D

from api.reports.fontes import (montar_incc_leitura, montar_incc_timing, num,
                                nota_incc_atual, pct)


def _linhas(n=6, variacoes=None, var_m="0.0066", var_di="0.0085"):
    """Uma linha por mês, da mais recente para trás."""
    out = []
    for i in range(n):
        vm = D(variacoes[i]) if variacoes and i < len(variacoes) else D(var_m)
        out.append({
            "data_id": date(2026, 8 - i, 1),
            "var_m": vm,
            "idx_m": D("1296.3269") + D(i),
            "y12_m": D("0.066077"),
            "var_di": D(var_di),
            "idx_di": D("119.1153"),
            "y12_di": D("0.065542"),
        })
    return out


def _metricas(r):
    return {m.rotulo: m for b in r.blocos for m in b.metricas}


# ── formatação: o erro clássico ──────────────────────────────────────────────

def test_pct_nao_acumula_erro_de_float():
    """Casos onde float e Decimal divergem de verdade.

    `0.005` arredonda igual nos dois — não prova nada. O erro aparece com
    dígito a mais: `0.0050000001 * 100` em float dá 0.5000000099999999, que
    quantizado vira "+0,50" do jeito errado só em outros casos. O que
    garantimos aqui é o comportamento observável: o resultado tem sempre
    exatamente `casas` decimais, nunca 3 nem 1.
    """
    # 0.00015 é divergência real: float*100 arredonda 0,01, Decimal dá 0,02.
    for bruto, esperado in (("0.005", "+0,50%"), ("0.0066", "+0,66%"),
                            ("-0.0019", "-0,19%"), ("0.0050000001", "+0,50%"),
                            ("1.0", "+100,00%"), ("0", "+0,00%"),
                            ("0.00015", "+0,02%"), ("0.00025", "+0,02%")):
        obtido = pct(D(bruto))
        assert obtido == esperado, f"{bruto}: {obtido} != {esperado}"
        # casas fixas: nunca 1 nem 3 decimais
        inteiro, _, dec = obtido.lstrip("+-").replace("%", "").partition(",")
        assert len(dec) == 2, f"{bruto} saiu com {len(dec)} casas: {obtido}"


def test_pct_sem_unidade_nao_duplica():
    """Rótulo 'p.p.' + '+0,19%' vira unidade dupla."""
    assert pct(D("-0.0019"), unidade=False) == "-0,19"
    assert pct(D("-0.0019")) == "-0,19%"


def test_pct_marca_sinal():
    assert pct(D("0.01")).startswith("+")
    assert pct(D("-0.01")).startswith("-")


def test_num_usa_separador_brasileiro():
    assert num(D("1296.3269")) == "1.296,33"
    assert num(D("119.1153")) == "119,12"


# ── regra editorial ──────────────────────────────────────────────────────────

def test_tendencia_acelera_quando_a_variacao_sobe():
    r = montar_incc_leitura(_linhas(variacoes=["0.0066", "0.0061"]))
    assert r is not None
    assert "acelerando" in r.resumo
    assert _metricas(r)["Tendência"].valor == "acelerando"


def test_tendencia_desacelera_quando_a_variacao_cai():
    r = montar_incc_leitura(_linhas(variacoes=["0.0054", "0.0061"]))
    assert "desacelerando" in r.resumo
    assert _metricas(r)["Tendência"].valor == "desacelerando"


def test_tendencia_estavel_quando_nao_muda():
    r = montar_incc_leitura(_linhas(variacoes=["0.0066", "0.0066"]))
    assert "estável" in r.resumo


def test_spread_negativo_e_explicito():
    """M abaixo do DI = a janela do mês fechado puxou a alta."""
    # M constante abaixo do DI: o spread é persistente, não ruído de um mês.
    r = montar_incc_timing(_linhas(n=6, var_m="0.0066", var_di="0.0085"))
    dif = _metricas(r)["Diferença entre janelas"]
    assert "-0,19 p.p." in dif.valor
    assert dif.variacao == "▼"




def test_dados_insuficientes_nao_geram_relatorio_fake():
    """Sem histórico suficiente, não inventar relatório."""
    assert montar_incc_leitura([]) is None
    assert montar_incc_leitura(_linhas(n=1)) is None
    assert montar_incc_timing(_linhas(n=2)) is None


def test_relatorio_tem_rodape_com_competencia():
    """Sem competência no rodapé, não dá para saber de que quando é o dado."""
    r = montar_incc_leitura(_linhas(variacoes=["0.0066", "0.0061"]))
    assert "08/2026" in (r.rodape or "")

def test_nota_e_estado_nao_numero_novo():
    """A nota semanal promete estado, nunca número novo."""
    n = nota_incc_atual(_linhas(variacoes=["0.0066", "0.0061"]))
    assert "acelerando" in n
    assert "competência 08/2026" in n


def test_nota_sem_historico_nao_inventa():
    assert nota_incc_atual([]) is None


# ── A terminologia das siglas ─────────────────────────────────────────────────
# Erro real (2026-10-02): o relatório rotulava INCC-M como "materiais" e
# atribuía a diferença M×DI a categorias (mão de obra pesando mais).
# Ambos factualmente errados — INCC-M é *Mercado* e cobre materiais,
# equipamentos, serviços e mão de obra; o DI cobre o mesmo. O que os separa
# é a janela de coleta.
#
# Estes testes existem para travar a terminologia na fonte, porque um rótulo
# errado aqui vira conseil errada na obra de quem lê o e-mail.

def test_rotulos_usam_os_nomes_oficiais_das_siglas():
    r = montar_incc_leitura(_linhas())
    rotulos = " ".join(m.rotulo for b in r.blocos for m in b.metricas)
    assert "Mercado" in rotulos, f"rótulo do INCC-M sem 'Mercado': {rotulos}"
    assert "Disponibilidade Interna" in rotulos, "rótulo do INCC-DI incorreto"
    assert "(materiais)" not in rotulos, "INCC-M rotulado como 'materiais'"
    assert "INCC-M (janela" not in rotulos


def test_nenhum_texto_diz_que_m_e_somente_materiais():
    """Varre TODOS os textos do relatório, não só os rótulos.

    Inclui o relatório de timing, que é onde o erro original estava: é nele
    que a diferença era atribuída a "mão de obra e serviços pesam".
    """
    r = montar_incc_leitura(_linhas())
    textos = " ".join([r.titulo, r.resumo, r.rodape or ""]
                      + [b.texto or "" for b in r.blocos])
    proibidos = ("índice de materiais", "materiais subiu", "materiais pressionam",
                 "só materiais", "materiais caem")
    for p in proibidos:
        assert p not in textos.lower(), f"texto afirma que M é sobre materiais: {p}"


def test_timing_explica_a_diferenca_como_janela_e_nao_como_categoria():
    """A leitura correta é: mesmo objeto, janelas diferentes."""
    r = montar_incc_timing(_linhas(n=6, var_m="0.0066", var_di="0.0085"))
    txt = " ".join([r.titulo, r.resumo, r.rodape or ""]
                  + [b.texto or "" for b in r.blocos]).lower()
    assert "janela" in txt, "a diferença não foi explicada pela janela de coleta"
    assert "mesmo" in txt, "não diz que os dois índices medem o mesmo objeto"
    # a leitura antiga: DI pesado porque mão de obra pesa mais
    assert "pesam" not in txt, "atribui a diferença a categoria, não a janela"
    assert "pesa mais" not in txt, "atribui a diferença a categoria, não a janela"
    assert "pressiona" not in txt, "atribui a diferença a categoria, não a janela"
    assert "antecipada" in txt, "não menciona a janela antecipada (dia 21→20)"


def test_timing_nao_afirma_deslocamento_dentro_do_ruido():
    """O spread é pequeno e ruidoso; um mês dentro do desvio não é sinal."""
    # série toda igual → spread ~0 e desvio ~0: precisa cair no "padrão"
    r = montar_incc_timing(_linhas(n=6, var_m="0.0066", var_di="0.0066"))
    assert "dentro do padrão" in r.resumo, (
        "afirmou deslocamento onde o mês está dentro do ruído histórico")


def test_timing_reporta_media_e_desvio_com_base_na_serie():
    """A afirmação de 'dentro do padrão' precisa de base comparável."""
    r = montar_incc_timing(_linhas(n=6, var_m="0.0066", var_di="0.0085"))
    m = _metricas(r)
    assert "6 meses" in m["Média histórica"].detalhe
    assert "desvio" in m["Média histórica"].detalhe
