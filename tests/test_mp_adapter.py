"""Testes do adapter do Mercado Pago.

Foco nas DUAS regras que, se quebrassem, fariam mais estrago que uma exceção:

1. **Override manual nunca é revertido.** O reconciliador roda a cada 15 min;
   sem esta regra, ele desfaz em segundos o que o suporte acabou de corrigir.
2. **`get_preapproval` só aceita correspondência exata de id.** Medido em
   05/10/2026: o filtro `preapproval_id` do MP devolveu o primeiro item da lista
   19 vezes, sempre outro. Sem conferir, o espelho colapsava 19 assinaturas em 1
   linha — e materializava a assinatura errada, entregando acesso ao cliente
   errado.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from api import mp_sync
from api.mp_client import MPClient, MPResource, MPUnavailable


# ── fixtures ──────────────────────────────────────────────────────────────────

def _db_with_sub(*, status="active", manual_override=False):
    db = MagicMock()
    row = {"id": "sub-1", "client_id": "c-1", "status": status,
           "manual_override": manual_override}
    res = MagicMock()
    res.mappings.return_value.first.return_value = row
    db.execute.return_value = res
    db.execute.return_value.scalar_one_or_none.return_value = "plan-1"
    return db


def _preapproval(status="cancelled", payer_email="c@x.com", **kw):
    return MPResource(resource_type="preapproval", resource_id="mp-99", status=status,
                      payer_email=payer_email, preapproval_plan_id="pl-1", **kw)


# ── 1. a regra do override ────────────────────────────────────────────────────

def test_override_manual_nao_e_revertido():
    """MP diz `cancelled`, local diz `active` AJUSTADO À MÃO. O MP discorda —
    mas a mão do suporte vence, e a divergência fica registrada para decisão."""
    db = _db_with_sub(status="active", manual_override=True)
    out = mp_sync._materialize_preapproval(db, _preapproval("cancelled"))

    assert out["action"] == "override_respeitado"
    sql = " ".join(str(c) for c in db.execute.call_args_list)
    # Não pode ter escrito `status =` — só `mp_status`/`mp_status_differs`.
    assert "status = :status" not in sql


def test_sem_override_o_mp_prevalece():
    """Sem ajuste manual, quem está errado é o NOSSO banco (o webhook não
    materializou). O MP passa a valer."""
    db = _db_with_sub(status="pending", manual_override=False)
    out = mp_sync._materialize_preapproval(db, _preapproval("authorized"))
    assert out["action"] == "atualizada"


def test_override_e_ignorado_mesmo_com_mp_muito_distante():
    """Não existe 'distância' que autorize reverter: qualquer override vale,
    senão o suporte aprenderia que o sistema ignora o ajuste em algum dia."""
    for mp_status in ("cancelled", "paused", "authorized"):
        db = _db_with_sub(status="active", manual_override=True)
        out = mp_sync._materialize_preapproval(db, _preapproval(mp_status))
        assert out["action"] == "override_respeitado", mp_status


def test_criacao_quando_webhook_nunca_materializou():
    """O caso que justifica o projeto: MP tem assinatura ativa e não existe
    linha local. Deve criar."""
    db = MagicMock()
    res = MagicMock()
    res.mappings.return_value.first.return_value = None       # não existe
    db.execute.return_value = res
    db.execute.return_value.scalar_one.side_effect = ["c-novo", "plan-1", "sub-novo"]

    out = mp_sync._materialize_preapproval(db, _preapproval("authorized"))
    assert out["action"] == "created"


def test_sem_payer_e_sem_plano_nao_cria_nada():
    """Sem e-mail não há cliente; sem plano não há assinatura. Inventar os dois
    criaria um cliente fantasma na base."""
    db = MagicMock()
    res = MagicMock()
    res.mappings.return_value.first.return_value = None
    db.execute.return_value = res
    db.execute.return_value.scalar_one.side_effect = [None, "plan-1", "sub"]

    out = mp_sync._materialize_preapproval(db, _preapproval("authorized", payer_email=None))
    assert out["action"] == "skipped"


# ── 2. correspondência exata de id no MP ─────────────────────────────────────

def _fake_transport(status, payload):
    def _t(url, headers):
        return status, payload
    return _t


def test_preapproval_so_aceita_id_correspondente():
    """O MP pode devolver o primeiro item da lista em vez do pedido. O cliente
    tem que recusar — materializar o id errado é pior que não materializar."""
    payload = '{"results":[{"id":"OUTRO","status":"authorized","payer":{"email":"e@x.com"}}]}'
    mp = MPClient(token="t", transport=_fake_transport(200, payload))
    assert mp.get_preapproval("mp-99") is None


def test_preapproval_aceita_quando_o_id_bate():
    payload = ('{"results":[{"id":"outro","status":"authorized"},'
               '{"id":"mp-99","status":"authorized","payer":{"email":"e@x.com"}}]}')
    mp = MPClient(token="t", transport=_fake_transport(200, payload))
    res = mp.get_preapproval("mp-99")
    assert res is not None and res.resource_id == "mp-99"


def test_404_e_resposta_valida_nao_erro():
    mp = MPClient(token="t", transport=_fake_transport(404, ""))
    assert mp.get_payment("999") is None


def test_4xx_de_requisicao_vira_mp_unavailable():
    """401/403 é erro NOSSO (token). Mascarar como 'recurso inexistente' levaria
    o painel a dizer 'não houve venda' quando na verdade não conseguimos
    perguntar."""
    mp = MPClient(token="t", transport=_fake_transport(401, '{"message":"invalid token"}'))
    with pytest.raises(MPUnavailable):
        mp.get_payment("1")


def test_5xx_vira_mp_unavailable():
    mp = MPClient(token="t", transport=_fake_transport(503, ""))
    with pytest.raises(MPUnavailable):
        mp.get_payment("1")


# ── 3. normalização ──────────────────────────────────────────────────────────

def test_valor_vem_em_centavos_e_nao_em_reais():
    """`transaction_amount: 47.5` → 4750. Errar a escala por 100 é o erro que
    faria o MRR mostrar R$ 0,47 em vez de R$ 47 — e ninguém notaria."""
    payload = ('{"id":1,"status":"approved","transaction_amount":47.5,'
               '"currency_id":"BRL","date_created":"2026-10-05T16:34:51.000-04:00"}')
    mp = MPClient(token="t", transport=_fake_transport(200, payload))
    res = mp.get_payment("1")
    assert res.amount_cents == 4750


def test_timestamp_vira_utc_comparavel():
    """Sem converter para UTC, a comparação com NOW() erra por horas e a janela
    de sincronização perde recursos na borda."""
    payload = '{"id":1,"status":"approved","date_created":"2026-10-05T16:34:51.000-04:00"}'
    mp = MPClient(token="t", transport=_fake_transport(200, payload))
    res = mp.get_payment("1")
    assert res.mp_created_at.hour == 20      # 16:34 -04:00 == 20:34 UTC


def test_sem_token_configurado():
    mp = MPClient(token="")
    assert mp.configured is False
    assert mp.health()["reachable"] is False


# ── 4. degradação do sync
# ── 5. caminhos que já quebraram em produção (05/10/2026) ─────────────────────
#
# Estes quatro não são hipóteses: cada um foi um defeito real, encontrado
# testando contra o banco de verdade, e todos compartilham a mesma assinatura —
# devolvem "sucesso" enquanto não fizeram nada.


def test_override_e_atingido_mesmo_sem_payer_email():
    """O caminho de ATUALIZAÇÃO não pode depender de payer.

    Na ordem errada, os 19 preapproval reais (todos sem `payer`) saíam por
    `skipped` ANTES de chegar na regra do override — que é justamente o caminho
    que a decisão "nunca reverter ajuste manual" protege.
    """
    db = _db_with_sub(status="active", manual_override=True)
    res = _preapproval("cancelled", payer_email=None)   # sem payer, como no MP real
    out = mp_sync._materialize_preapproval(db, res)
    assert out["action"] == "override_respeitado", out


def test_atualizacao_nao_exige_resolucao_de_plano():
    """Plano só é necessário para CRIAR. Uma assinatura existente já tem o seu.

    Com a ordem antiga, um plano introuvável derrubava o caminho de atualização
    inteiro — que é o caminho da rede de segurança do webhook.
    """
    db = _db_with_sub(status="active", manual_override=False)
    db.execute.return_value.scalar_one_or_none.return_value = None  # plano introuvable
    out = mp_sync._materialize_preapproval(db, _preapproval("authorized", payer_email=None))
    assert out["action"] != "skipped", out
    assert out.get("subscription_id") == "sub-1", out


def test_period_end_nunca_e_none_para_preapproval_sem_last_modified():
    """`current_period_end` é NOT NULL.

    Um preapproval recem-criado no MP não tem `last_modified`. Passar `None`
    abortava a TRANSAÇÃO inteira, e o rollback descartava o espelho — com o
    relatório dizendo "sucesso". A assinatura nunca era criada.
    """
    db = MagicMock()
    r = MagicMock()
    r.mappings.return_value.first.return_value = None
    db.execute.return_value = r
    db.execute.return_value.scalar_one.side_effect = ["c-novo", "plan-novo", "sub-novo"]

    res = MPResource(resource_type="preapproval", resource_id="mp-novo",
                     status="authorized", payer_email="novo@exemplo.com.br",
                     external_reference="starter:novo@exemplo.com.br",
                     mp_created_at=datetime(2026, 10, 5, 19, 0, tzinfo=timezone.utc),
                     mp_updated_at=None)          # <- o caso que quebrava
    assert mp_sync._materialize_preapproval(db, res)["action"] == "created"

    params = [c.args[1] for c in db.execute.call_args_list
              if len(c.args) > 1 and isinstance(c.args[1], dict) and "pend" in c.args[1]]
    assert params, "o INSERT da assinatura não aconteceu"
    assert params[0]["pend"] is not None, "current_period_end None violaria NOT NULL"


def test_drift_e_medido_apos_alinhar_nao_antes():
    """Se o reconciliador acabou de corrigir, NÃO há divergência para o painel.

    Gravar "mudou" no lugar de "discordam" deixava `mp_status_differs = true`
    sobre um estado já resolvido, e o suporte via "decisão humana" pendente por
    até 15 minutos — até a rodada seguinte corrigir o próprio marcador.
    """
    db = _db_with_sub(status="active", manual_override=False)
    out = mp_sync._materialize_preapproval(db, _preapproval("cancelled", payer_email=None))
    assert out["action"] == "atualizada", out

    sql = " ".join(str(c.args[0]) for c in db.execute.call_args_list
                   if c.args and hasattr(c.args[0], "text"))
    assert "status = :status" in sql
    # Autorregado: o alvo veio do MP, então o resultado concorda com o MP.
    assert "mp_status_differs = FALSE" in sql, \
        "divergência marcada em algo que o próprio reconciliador resolveu"


def test_status_do_mp_que_nao_sabemos_mapear_nao_move_nada():
    """MP em `pending` não é motivo para inventar um estado local."""
    db = _db_with_sub(status="active", manual_override=False)
    out = mp_sync._materialize_preapproval(db, _preapproval("pending", payer_email=None))
    assert out["action"] == "sem_divergencia", out


def test_auditoria_nao_derruba_a_transacao():
    """`client_events` usa a coluna `details`, não `payload`.

    Com `payload`, o INSERT falhava, a exceção era engolida, e — porque no
    Postgres um erro aborta a transação — o `commit()` seguinte DESCARTAVA o
    trabalho real devolvendo sucesso. Um savepoint isola a auditoria.
    """
    db = MagicMock()
    ctx = MagicMock()
    db.begin_nested.return_value.__enter__ = lambda s: s
    db.begin_nested.return_value.__exit__ = lambda s, *a: False
    db.execute.side_effect = RuntimeError('column "payload" does not exist')

    mp_sync._log_event(db, "c-1", "teste", {"a": 1})   # não deve levantar
    db.begin_nested.assert_called_once(), "sem savepoint, a auditoria abortaria a transação"


def test_coluna_da_auditoria_e_details():
    """Trava o nome da coluna: `payload` é o erro que causou o rollback."""
    import inspect
    src = inspect.getsource(mp_sync._log_event)
    assert "details" in src and "payload," not in src.replace("payload = ", "")

def test_sync_degrada_sem_derrubar_quando_mp_cai():
    """Falha externa não pode virar exceção: o beat carrega outras tarefas."""
    db = MagicMock()

    class _Down:
        configured = True
        def search_payments(self, *a, **k): raise MPUnavailable("rede: down")
        def search_preapprovals(self, *a, **k): raise MPUnavailable("rede: down")
        def close(self): pass

    out = mp_sync.sync(db, client_factory=lambda: _Down())
    assert out["lidos"] == 0
    assert "rede" in (out["detalhe"] or "") or out["mp_indisponivel"] is True


def test_sync_nao_materializa_o_que_o_mp_nao_devolveu():
    """Resposta vazia do MP é RESPOSTA VÁLIDA (não houve venda), não queda."""
    db = MagicMock()

    class _Empty:
        configured = True
        def search_payments(self, *a, **k): return []
        def search_preapprovals(self, *a, **k): return []
        def close(self): pass

    out = mp_sync.sync(db, client_factory=lambda: _Empty())
    assert out["lidos"] == 0
    assert out["mp_indisponivel"] is False