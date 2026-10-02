"""Testes das fontes CUB e SINAPI.

`_montar` recebe o dicionário pronto, então nenhum teste toca rede — é o que
permite verificar a regra editorial com números inventados, e confiar que a
entrada real (com ruído de API) não muda a decisão.
"""

from decimal import Decimal as D

from api.reports.fontes_cub import (coletar_br, montar_cub_dispersao,
                                    montar_cub_estado)
from api.reports.fontes_sinapi import (coletar_base, montar_sinapi_competencia,
                                       montar_sinapi_cobertura,
                                       montar_sinapi_foco_custo)

# ── fixtures ─────────────────────────────────────────────────────────────────

BR = {
    "data_referencia": "2026-08-01",
    "desoneracao": "SEM_DESONERACAO",
    "media_br": D("2537.27"),
    "total_estados": 9,
    "regioes": {"SUL": D("2746.16"), "SUDESTE": D("2282.54"),
                "CENTRO-OESTE": D("2724.90"), "NORDESTE": D("2180.64")},
    "estados": [
        {"uf": "PR", "valor_m2": D("2730.31"), "peso": D("6.98"),
         "participacao": D("19.79"), "sinduscon": "Sinduscon-PR"},
        {"uf": "SP", "valor_m2": D("2980.10"), "peso": D("24.0"),
         "participacao": D("68.0"), "sinduscon": "Sinduscon-SP"},
        {"uf": "MA", "valor_m2": D("1990.00"), "peso": D("2.0"),
         "participacao": D("4.0"), "sinduscon": "Sinduscon-MA"},
    ],
}

BASE = {
    "competencia": "2026-08", "consumida": "2026-08", "status": "current",
    "atualizado_em": "2026-09-29T10:00:00",
    "insumos": 6333, "composicoes": 10840,
    "precos": 5654970, "custos": 16256214,
}


def _m(r):
    return {x.rotulo: x for b in r.blocos for x in b.metricas}


# ── CUB: dispersão ───────────────────────────────────────────────────────────

def test_percentual_da_dispersao_nao_e_duplicado():
    """(2980.10 − 1990.00) / 2537.27 = 39,0% da média.

    A razão já vem com ×100 aplicado uma vez; passar por `pct` (que
    multiplica por 100) daria +3.900% — o título inteiro fica errado.
    """
    r = montar_cub_dispersao(BR)
    # (2980.10 − 1990.00) / 2537.27 = 39,02%
    assert "4.955,96%" not in r.titulo, f"percentual duplicado: {r.titulo}"
    assert "+39,02%" in r.titulo, r.titulo


def test_titulo_do_foco_usa_virgula():
    """`2.9` com ponto é inconsistente com todo o resto do relatório."""
    r = montar_sinapi_foco_custo(BASE)
    assert "2,9" in r.titulo
    assert "2.9" not in r.titulo, f"ponto decimal no título: {r.titulo}"


def test_dispersao_calcula_amplitude_entre_extremos():
    r = montar_cub_dispersao(BR)
    assert r is not None
    # 2980,10 (SP) − 1990,00 (MA) = 990,10
    assert "990,10" in _m(r)["Amplitude"].valor


def test_dispersao_converte_amplitude_em_obra():
    """Amplitude só significa alguma coisa traduzida em dinheiro de obra."""
    r = montar_cub_dispersao(BR)
    texto = r.titulo + r.resumo
    assert "2.000 m²" in texto or "2.000 m" in texto
    assert "milhão" in texto.lower() or "milhões" in texto.lower()


def test_dispersao_identifica_o_mais_caro_e_o_mais_barato():
    m = _m(montar_cub_dispersao(BR))
    assert "SP" in m["Mais caro"].valor
    assert "MA" in m["Mais barato"].valor


def test_dispersao_nao_inventa_com_dado_insuficiente():
    assert montar_cub_dispersao(None) is None
    assert montar_cub_dispersao({"estados": [], "media_br": None}) is None
    assert montar_cub_dispersao({"estados": BR["estados"]}) is None   # sem média


def test_regiao_mais_cara_e_mais_barata():
    m = _m(montar_cub_dispersao(BR))
    assert "SUL" in m["Região mais cara"].valor
    assert "NORDESTE" in m["Região mais barata"].valor


def test_grafico_de_regiao_nao_e_percentual():
    """O CUB é R$/m²; rotular como taxa viraria '2.746,16%'."""
    r = montar_cub_dispersao(BR)
    assert r.series and r.series[0].em_percentual is False


# ── CUB: estado/projeto ──────────────────────────────────────────────────────

def test_estado_escolhe_maior_participacao():
    """Escolhe o estado mais executado na amostra, não o mais caro.

    Neste fixture SP é **os dois** (mais caro e maior participação), o que
    mascara a regra. Por isso o teste compara com um fixture onde os dois
    divergem: MT é o mais caro, mas SP domina a amostra — escolher por preço
    daria MT, que quase ninguém executa.
    """
    divergente = {
        **BR,
        "estados": [
            {"uf": "SP", "valor_m2": D("2800.00"), "peso": D("24"),
             "participacao": D("70.0"), "sinduscon": "Sinduscon-SP"},
            {"uf": "MT", "valor_m2": D("3300.50"), "peso": D("5"),
             "participacao": D("2.0"), "sinduscon": "Sinduscon-MT"},
            {"uf": "MA", "valor_m2": D("1990.00"), "peso": D("2"),
             "participacao": D("3.0"), "sinduscon": "Sinduscon-MA"},
        ],
    }
    m = _m(montar_cub_estado(divergente))
    # MT é o mais caro (3.300,50) com 2% de participação; SP tem 70%.
    assert "CUB SP" in m, "escolheu por preço em vez de por participação"
    assert "CUB MT" not in m
    assert m["Participação efetiva"].valor == "70,00%"


def test_estado_conta_desvio_vs_media_com_sinal():
    m = _m(montar_cub_estado(BR))
    desvio = m["Desvio vs média"]
    assert desvio.variacao == "▲", "SP está acima da média neste fixture"
    # (2980.10 - 2537.27) / 2537.27 = 17,45%
    # Passar por `pct` aqui daria +1.745,30%: `pct` multiplica por 100 e o
    # desvio JÁ está em percentual.
    assert desvio.valor == "+17,45%", f"percentual duplo: {desvio.valor}"
    assert "1.745" not in desvio.valor


def test_estado_traduz_em_obra():
    m = _m(montar_cub_estado(BR))
    assert "mi" in m["Obra de 2.000 m² em SP"].valor


def test_estado_sem_dado_nao_monta():
    assert montar_cub_estado(None) is None
    assert montar_cub_estado({"estados": []}) is None


# ── SINAPI: cobertura ────────────────────────────────────────────────────────

def test_cobertura_formata_contagem_grande():
    """16.256.214 sem separador é ilegível."""
    m = _m(montar_sinapi_cobertura(BASE))
    assert m["Registros de custo"].valor == "16.256.214"
    assert m["Composições"].valor == "10.840"


def test_cobertura_mostra_competencia_disponivel_e_consumida():
    m = _m(montar_sinapi_cobertura(BASE))
    assert m["Competência disponível"].valor == "2026-08"
    assert "2026-08" in m["Competência consumida"].valor


def test_cobertura_nao_monta_sem_stats():
    assert montar_sinapi_cobertura(None) is None
    assert montar_sinapi_cobertura({"competencia": "2026-08"}) is None


def test_cobertura_e_categoria_base():
    """Só competência e base são categoria BASE — a grade usa isso no corte."""
    from api.reports.model import Categoria
    assert montar_sinapi_cobertura(BASE).categoria is Categoria.BASE


# ── SINAPI: foco de custo ────────────────────────────────────────────────────

def test_foco_calcula_razao_custo_por_preco():
    m = _m(montar_sinapi_foco_custo(BASE))
    # 16.256.214 / 5.654.970 = 2,8747 → "2,9" em 1 casa
    assert m["Custo por preço cadastrado"].valor == "2,9"


def test_foco_traz_a_ordem_de_intervencao():
    r = montar_sinapi_foco_custo(BASE)
    txt = r.blocos[0].texto.lower()
    assert "curva abc" in txt
    assert "hora-homem" in txt


def test_foco_nao_monta_sem_os_dois_numeros():
    assert montar_sinapi_foco_custo(None) is None
    assert montar_sinapi_foco_custo({"custos": 100}) is None
    assert montar_sinapi_foco_custo({"precos": 100}) is None


# ── SINAPI: competência (o que pula) ─────────────────────────────────────────

def test_competencia_monta_quando_a_base_advanced():
    r = montar_sinapi_competencia({**BASE, "competencia": "2026-09"}, "2026-08")
    assert r is not None
    assert "2026-09" in r.titulo


def test_competencia_nao_monta_se_ja_anunciada():
    """O corte da trilha: sem isso, 'atualizado em agosto' sai toda semana."""
    assert montar_sinapi_competencia(BASE, "2026-08") is None


def test_competencia_monta_sem_historico():
    """Primeira execução não tem 'anterior' — ainda assim deve mandar."""
    r = montar_sinapi_competencia(BASE, None)
    assert r is not None


def test_competencia_diz_a_anterior():
    r = montar_sinapi_competencia({**BASE, "competencia": "2026-03"}, "2026-02")
    assert "2026-02" in r.resumo


def test_competencia_anterior_vira_ano_em_janeiro():
    assert montar_sinapi_competencia(
        {**BASE, "competencia": "2026-01"}, "2025-12").rodape.endswith("2025-12")
