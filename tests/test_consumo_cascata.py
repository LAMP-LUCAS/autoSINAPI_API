"""Cascata de sinais de atividade — quem conta como "parou de usar".

O winback é a única peça do funil que **depende de um sinal** ("faz N dias
que você não usa"). Com sinal errado, ele ou nunca dispara — perder o
degrau de 45 dias — ou dispara para quem está ativo todo dia, que é pior:
ensina a pessoa a ignorar a caixa.

Regra decided em 03/10 (usuário): **o app é o marcador canônico**. É o que é
pago e o que vale. O consumo de API conta igual. A navegação pelo portal é
**chance** deEscape — quem não é marcado no app mas navega pelo site não deve
ser tratado como inativo.

Este arquivo trava as três propriedades. O `test_sinal_canonico_do_app...`
falhou antes da implementação: `dias_sem_consumo` era o **mínimo** entre API e
portal, e o portal nunca recebia atividade — o piso era sempre o
`created_at`, então o degrau de 45 dias era inalcançável por construção.
"""

import pytest

from api.reports.recoveredor import ContextoRecuperacao


def _ctx(**kw):
    base = dict(
        lead_id="l1",
        email="alguem@exemplo.invalid",
        eh_cliente_pagante=False,
        dias_sem_consumo_api=None,
        dias_sem_consumo_portal=None,
        etapas_enviadas=[],
        consentimento=True,
        dias_sem_promocao=None,
    )
    base.update(kw)
    return ContextoRecuperacao(**base)


class TestCascataDeSinais:
    def test_sem_nenhum_sinal_nao_inventa_inatividade(self):
        """Nunca houve sinal: não se pode afirmar que a pessoa parou.

        `None` ≠ 0 e ≠ 9999. O `None` é o que segura o `decidir` de enviar
        winback para quem nunca apareceu no sistema.
        """
        assert _ctx().dias_sem_consumo is None

    def test_api_recente_ganha_do_portal_que_nunca_move(self):
        """API usada ontem é atividade, mesmo com portal parado há 40 dias."""
        c = _ctx(dias_sem_consumo_api=1, dias_sem_consumo_portal=40)
        assert c.dias_sem_consumo == 1

    def test_app_login_marca_mesmo_sem_consumo_de_api(self):
        """Entrar no app é usar o produto — conta, mesmo sem chamar a API.

        Chamar a API e abrir o app são ações diferentes; alguém que só
        navega no app está ativo. Tratar isso como inatividade faz o
        winback falar com quem está usando o que foi pago.
        """
        c = _ctx(dias_sem_consumo_app=2, dias_sem_consumo_portal=90)
        assert c.dias_sem_consumo == 2

    def test_portal_da_chance_de_escape_para_quem_nao_entra_no_app(self):
        """O ponto do item 3: navegar pelo portal é atividade.

        Sem este sinal, quem nunca abriu o app mas lê a KB do portal seria
        tratado como inativo e receberia "seu acesso continua ativo" — para
        quem já está lendo o conteúdo.
        """
        c = _ctx(dias_sem_consumo_app=None, dias_sem_consumo_portal=5)
        assert c.dias_sem_consumo == 5

    def test_cascata_usa_o_mais_recente_e_nao_o_mais_antigo(self):
        """Com vários sinais, vale o mais recente — atividade em qualquer
        canal significa lead ativo.

        Este é o ponto que torna o degrau de 45 alcançável: antes, o portal
        fixado no `created_at` forçava o piso para cima para sempre e 45
        dias não chegava.
        """
        c = _ctx(
            dias_sem_consumo_api=50,
            dias_sem_consumo_app=60,
            dias_sem_consumo_portal=70,
        )
        assert c.dias_sem_consumo == 50

    def test_sinal_zero_e_valido(self):
        """`0` = atividade agora. Não pode virar `None` nem ser ignorado.

        É a diferença entre "usou agora" e "não há dado"; tratar `0` como
        ausente faria o winback disparar para quem acabou de usar.
        """
        assert _ctx(dias_sem_consumo_api=0).dias_sem_consumo == 0

    def test_valores_negativos_sao_ignorados(self):
        """Defeito de clock ou dado ruim não pode virar "ativo há 400 dias".

        Sem o clamp, `-3` seria o mínimo e diria "parou há menos 3 dias" →
        na prática, nunca atingiria 30 nem 45, e o degrau dispararia sempre.
        """
        assert _ctx(dias_sem_consumo_api=-3, dias_sem_consumo_portal=10).dias_sem_consumo == 10


class TestNurtureStateRegistraOTemplateCerto:
    """`nurture_state.template_id` precisa refletir o template **usado**.

    O `ON CONFLICT` do `_reservar` atualiza `status`, `claimed_at` e
    `attempts` — mas não `template_id`. Depois que o mapeamento slot→template
    mudou (o `artigo` saiu de `66666666` para `f4444444`), as linhas antigas
    continuaram afirmar que o artigo tinha sido enviado como "boas-vindas a
    lead".

    Não afeta o envio — a OS usa o template do `_envelope` — mas a tabela é o
    histórico auditável do funil, e histórico que mente é pior que histórico
    ausente. Este teste le o SQL de `_reservar` e exige que `template_id` seja
    atualizado, para o ON CONFLICT não voltar a omitir a coluna.
    """

    def test_on_conflict_atualiza_o_template_id(self):
        import inspect

        from api import crm_conteudo

        sql = inspect.getsource(crm_conteudo._reservar)
        conflict = sql.split("ON CONFLICT", 1)[1]
        set_clause = conflict.split("WHERE", 1)[0]

        assert "template_id = EXCLUDED.template_id" in set_clause, (
            "o ON CONFLICT do _reservar não atualiza `template_id`: um passo "
            "reenviado depois de uma mudança de mapeamento fica com o "
            "template antigo gravado. Sem efeito no envio, mas o histórico "
            "deixa de ser auditável."
        )


class TestDegrausWinback:
    """Os degraus só fazem sentido se 30 e 45 forem alcançáveis."""

    def test_30_dias_e_alcancavel(self):
        c = _ctx(dias_sem_consumo_app=31)
        assert c.dias >= 30

    def test_45_dias_e_alcancavel_quando_todos_os_sinais_estao_parados(self):
        """O degrau precisa ver 45, não ficar travado num número menor.

        Reprova a volta ao `min(api, portal)`: com o portal preso no
        `created_at` de um lead de 50 dias, o mínimo devolveria o outro
        canal e nunca chegaria a 45.
        """
        c = _ctx(dias_sem_consumo_api=50, dias_sem_consumo_app=50,
                 dias_sem_consumo_portal=50)
        assert c.dias >= 45

    def test_o_mais_antigo_nao_arrasta_o_resultado_para_baixo(self):
        """Um canal parado não pode segurar os outros.

        Este é o caso do bug real: portal preso no `created_at` (50 dias)
        ao lado de API usada ontem (1 dia). `min` devolveria 50 e o winback
        dispararia para quem usou a API ontem.
        """
        c = _ctx(dias_sem_consumo_api=1, dias_sem_consumo_app=None,
                 dias_sem_consumo_portal=50)
        assert c.dias == 1

    def test_dias_e_none_quando_nao_ha_sinal(self):
        assert _ctx().dias is None