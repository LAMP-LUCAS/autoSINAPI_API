"""TDD — seleção do próximo artigo da trilha de KB.

Por que a seleção mora aqui e não no Code node do n8n
------------------------------------------------------
O nurture segmenta em poucas linhas e isso coube no Code. A trilha de KB é
outra coisa: precisa de pool por persona, ordenação por nível, cursor sem
repetição e desempate por **índice de afinidade** dentro da lista `personas`.
Isso é lógica de domínio — testá-la dentro do Code node do n8n exigiria o
runtime do n8n de pé. Aqui é função pura, com pytest.

Invariantes que os testes exigem
--------------------------------
1. Respeita o nível: um lead novo recebe `nivel: 1` antes de 2. Sem isso a
   série começa por artigo avançado e o leitor desiste no primeiro e-mail.
2. Não repete artigo até esgotar o pool — sobravam 109 artigos ÷ 2/semana.
3. **Nunca** devolve o mesmo artigo duas vezes para o mesmo lead.
4. A lista `personas` é ORDENADA: `office` no índice 0 vale mais que no 1.
5. Sem `personas` (estado de hoje: 0 de 109 classificados) o pool geral
   funciona. Degradar é o comportamento; quebrar não é.
6. Lead sem persona usa o pool geral.
"""

import pytest

from api.kb_sequence import selecionar_artigo


# ── catálogo de teste ────────────────────────────────────────────────────────
# Reproduz o que o build_kb_catalog.py produz hoje: 3 classificados, resto
# sem persona (pool geral).

def _art(slug, personas=None, nivel=1, ordem=0):
    return {"slug": slug, "url": f"https://mundoaec.com/kb/{slug}/",
            "title": slug.replace("-", " ").title(), "description": "d",
            "category": "Tutorial", "tags": [], "personas": personas or [],
            "nivel": nivel, "ordem": ordem}


CATALOGO = [
    # Nível 1 — escritório
    _art("oficina-custos", ["office", "builder"], 1, 0),
    _art("planilha-orcamento", ["office"], 1, 1),
    # Nível 1 — geral (sem persona)
    _art("guia-primeiro-acesso", [], 1, 2),
    # Nível 2
    _art("curva-s", ["office", "builder"], 2, 3),
    # Nível 3
    _art("evm-avancado", ["office"], 3, 4),
]


def _cat(catalogo=None):
    # `catálogo or CATALOGO` trataria `[]` como ausente e usaria o catálogo
    # padrão — exatamente o tipo de teste que passa sem testar nada.
    return {"artigos": CATALOGO if catalogo is None else catalogo}


# ── 1. nível primeiro ────────────────────────────────────────────────────────

def test_lead_novo_recebe_nivel_1_e_nao_avancado():
    art = selecionar_artigo(_cat(), persona="office", ja_enviados=set())
    assert art is not None
    assert art["nivel"] == 1, f"começou por nível {art['nivel']}"


def test_nao_pula_para_nivel_3_enquanto_houver_nivel_1():
    """A progressão é por nível, não por 'o que parece mais interessante'."""
    enviados = {"oficina-custos", "planilha-orcamento"}
    art = selecionar_artigo(_cat(), persona="office", ja_enviados=enviados)
    # Sobra `guia-primeiro-acesso` (nível 1, pool geral) antes de `evm-avancado`.
    assert art is not None
    assert art["nivel"] == 1


# ── 2/3. sem repetição ──────────────────────────────────────────────────────

def test_nao_repete_ate_esgotar_o_pool():
    enviados: set = set()
    vistos = []
    for _ in range(len(CATALOGO)):
        art = selecionar_artigo(_cat(), persona="office", ja_enviados=enviados)
        assert art is not None, "pool esgotado antes do previsto"
        assert art["slug"] not in enviados, f"repetiu {art['slug']}"
        enviados.add(art["slug"])
        vistos.append(art["slug"])
    assert len(set(vistos)) == len(CATALOGO)


def test_pool_esgotado_devolve_none_e_nao_excecao():
    enviados = {a["slug"] for a in CATALOGO}
    assert selecionar_artigo(_cat(), persona="office", ja_enviados=enviados) is None


def test_nao_devolve_artigo_ja_enviado_apos_reinicio_do_cursor():
    """O cursor reinicia quando o pool esgota — mas nunca para no mesmo artigo."""
    cat = _cat()
    pool_office = {a["slug"] for a in CATALOGO if "office" in a["personas"]}
    enviados = set(pool_office)
    art = selecionar_artigo(cat, persona="office", ja_enviados=enviados)
    # Esgotou o pool da persona: cai no geral, e ainda assim algo novo.
    assert art is not None
    assert art["slug"] not in enviados


# ── 4. lista ordenada = afinidade ───────────────────────────────────────────

def test_indice_zero_tem_precedencia_sobre_indice_um():
    """`[office, builder]`: office é a persona primária deste artigo.

    Este é O teste do requisito: a lista é ordenada e a ordem carrega a
    afinidade. `a-primario` tem office no índice 0; `b-secundario` também é
    para office, mas no índice 1. O primeiro tem de ir antes.
    """
    cat = {"artigos": [
        _art("a-primario", ["office", "builder"], 1, 0),
        _art("b-secundario", ["builder", "office"], 1, 1),
    ]}
    art = selecionar_artigo(cat, persona="office", ja_enviados=set())
    assert art["slug"] == "a-primario"

    # E o inverso: para `builder`, `b-secundario` (índice 0) vai antes.
    art = selecionar_artigo(cat, persona="builder", ja_enviados=set())
    assert art["slug"] == "b-secundario"


def test_ordem_declarada_vence_a_ordem_do_arquivo():
    """A afinidade declarada tem de ganhar da posição no catálogo.

    Sem isto, a ordem seria só a do diretório e a lista ordenada não
    significaria nada.
    """
    cat = {"artigos": [
        # office no índice 1, mas aparece PRIMEIRO no catálogo
        _art("office-1", ["builder", "office"], 1, 0),
        # office no índice 0, aparece segundo
        _art("office-0", ["office", "builder"], 1, 1),
    ]}
    art = selecionar_artigo(cat, persona="office", ja_enviados=set())
    assert art["slug"] == "office-0", "o índice 0 declarado tem de vencer o catálogo"


# ── 5/6. degradação ─────────────────────────────────────────────────────────

def test_sem_classificacao_usa_pool_geral():
    """Estado de hoje: 0 de 109 com `personas`. Tem de funcionar assim."""
    geral = [_art("g1", [], 1, 0), _art("g2", [], 1, 1)]
    art = selecionar_artigo(_cat(geral), persona="office", ja_enviados=set())
    assert art is not None
    assert art["personas"] == []


def test_lead_sem_persona_usa_pool_geral():
    geral = [_art("g1", [], 1, 0)]
    art = selecionar_artigo(_cat(geral), persona=None, ja_enviados=set())
    assert art is not None
    assert art["slug"] == "g1"


def test_catalogo_vazio_devolve_none():
    assert selecionar_artigo(_cat([]), persona="office", ja_enviados=set()) is None


def test_persona_desconhecida_cai_para_pool_geral():
    cat = _cat([_art("classificado", ["office"], 1, 0), _art("geral", [], 1, 1)])
    art = selecionar_artigo(cat, persona="engenheiro-novo", ja_enviados=set())
    assert art["slug"] == "geral", "persona fora do vocabulário deve usar o pool geral"


# ── cadência: 1-2 por semana ───────────────────────────────────────────────

def test_nivel_avanca_somente_apos_esgotar_o_nivel_anterior():
    """Sequência formativa: não mistura nível 3 com nível 1 na mesma série."""
    cat = _cat()
    # Office tem 2 de nível 1. Enviados só 1 deles: ainda falta nível 1.
    art = selecionar_artigo(cat, persona="office", ja_enviados={"oficina-custos"})
    assert art["nivel"] == 1
    # Enviados os 2 de nível 1: agora pode subir.
    # Sobra `guia-primeiro-acesso`, que é nível 1 mas pool GERAL. A regra do
    # nível vale sobre a segmentação: enquanto houver nível 1 por enviar, o
    # lead não sobe — começar por `curva-s` e deixar o introdutório para
    # depois é o que faz a série não LINEAR.
    art = selecionar_artigo(cat, persona="office",
                            ja_enviados={"oficina-custos", "planilha-orcamento"})
    assert art["slug"] == "guia-primeiro-acesso"
    assert art["nivel"] == 1

    # Esgotado o nível 1 inteiro (segmentado + geral), aí sim sobe.
    art = selecionar_artigo(
        cat, persona="office",
        ja_enviados={"oficina-custos", "planilha-orcamento", "guia-primeiro-acesso"})
    assert art["nivel"] == 2, "deveria ter subido para nível 2"
