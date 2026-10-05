"""Reconciliador Mercado Pago × saas.

O QUE FAZ
---------
Lê o MP pelo `mp_client`, grava o espelho em `saas.mp_resources` e compara com
o estado local. É a REDE DE SEGURANÇA do webhook: quando o webhook falha (e já
falhou — 06/09, `MP API error 404`), a assinatura ainda é materializada por
aqui.

A REGRA QUE IMPORTA
--------------------
**Nunca reverte ajuste manual.** Se o suporte marcou `manual_override`, o
reconciliador registra que o MP discorda e segue em frente. Sem isso, uma
correção humana seria desfeita em até 15 minutos e o painel perderia a confiança
de quem o usa — que é o ativo inteiro deste trabalho.

O inverso também vale: uma assinatura que NÃO é override e diverge do MP é
corrigida para o que o MP diz, porque aí quem está errado é o nosso banco, não
a pessoa. (Um `pending` que o MP já aprovou é o webhook perdido, que é
exatamente o caso a resolver.)

CONTRATO
--------
* Idempotente: rodar duas vezes no mesmo minuto não muda nada.
* Degrada: MP fora do ar → retorna contagem, não levanta. Uma falha externa
  nunca pode derrubar o worker e, com ele, as outras tarefas do beat.
* Auditável: toda decisão registra em `saas.client_events`.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from .mp_client import MPClient, MPResource, MPUnavailable

logger = logging.getLogger(__name__)

# Status que, no MP, significam "assinatura de pé".
MP_ACTIVE = {"authorized", "active"}
# Status que, no MP, significam "encerrada".
MP_CANCELLED = {"cancelled", "paused"}
# Pagamento aprovado — o que prova que houve dinheiro.
MP_PAID = {"approved", "authorized"}

def _log_event(db: Session, client_id: str, event: str, payload: dict[str, Any]) -> None:
    """Espelha `admin_crm._client_event`.

    O `begin_nested()` NÃO é decoração. No Postgres, um erro de statement deixa a
    transação inteira em estado abortado: as instruções seguintes falham com
    "current transaction is aborted" e o `commit()` final descarta TUDO o que
    foi escrito antes.

    Foi exatamente o que aconteceu em 05/10/2026: a coluna se chamava `payload`
    (é `details`), o INSERT falhava, a exceção era engolida, e o `commit()` do
    fim da sincronização descartava o espelho inteiro — devolvendo "sucesso".
    Um savepoint isola a auditoria: se ela falhar, só ela volta.
    """
    try:
        with db.begin_nested():
            db.execute(text("""
                INSERT INTO saas.client_events (client_id, event_type, actor, details, occurred_at)
                VALUES (:cid, :etype, :actor, CAST(:details AS jsonb), NOW())
            """), {"cid": client_id, "etype": event, "actor": "mp_sync",
                  "details": json.dumps(payload or {}, default=str)})
    except Exception:
        # Auditoria é nice-to-have. Perder um registro é aceitável; perder a
        # sincronização inteira por causa da auditoria não é.
        logger.warning("client_events indisponível para %s", event, exc_info=True)


def upsert_mirror(db: Session, res: MPResource) -> None:
    row = res.to_row()
    db.execute(text("""
        INSERT INTO saas.mp_resources
            (resource_type, resource_id, status, status_detail, amount_cents,
             currency_id, payer_email, payer_id, external_reference, reason,
             preapproval_plan_id, preapproval_id, mp_created_at, mp_updated_at,
             raw, synced_at)
        VALUES
            (:resource_type, :resource_id, :status, :status_detail, :amount_cents,
             :currency_id, :payer_email, :payer_id, :external_reference, :reason,
             :preapproval_plan_id, :preapproval_id, :mp_created_at, :mp_updated_at,
             CAST(:raw AS jsonb), NOW())
        ON CONFLICT (resource_type, resource_id) DO UPDATE SET
            status = EXCLUDED.status,
            status_detail = EXCLUDED.status_detail,
            amount_cents = EXCLUDED.amount_cents,
            currency_id = EXCLUDED.currency_id,
            payer_email = EXCLUDED.payer_email,
            payer_id = EXCLUDED.payer_id,
            external_reference = EXCLUDED.external_reference,
            reason = EXCLUDED.reason,
            preapproval_plan_id = EXCLUDED.preapproval_plan_id,
            preapproval_id = EXCLUDED.preapproval_id,
            mp_created_at = EXCLUDED.mp_created_at,
            mp_updated_at = EXCLUDED.mp_updated_at,
            raw = EXCLUDED.raw,
            synced_at = NOW()
    """), {**row, "raw": __import__("json").dumps(row["raw"], default=str)})


def _find_client(db: Session, email: str | None) -> dict | None:
    if not email:
        return None
    return db.execute(text("""
        SELECT id, email, name, mp_customer_id FROM saas.clients
         WHERE lower(email) = lower(:e) AND deleted_at IS NULL
         ORDER BY created_at DESC LIMIT 1
    """), {"e": email}).mappings().first()


def _create_client(db: Session, res: MPResource) -> str | None:
    if not res.payer_email:
        return None
    # `name` é NOT NULL. A primeira versão passava o e-mail como nome, o que é
    # ruído no painel de clientes — e um nome ruim é pior que nenhum nome,
    # porque alguém vai ler e achar que é o nome real da pessoa.
    nome = (res.payer_name or "").strip() or res.payer_email.split("@")[0]
    cid = db.execute(text("""
        INSERT INTO saas.clients (email, name, mp_customer_id, source)
        VALUES (:email, :name, :mp, 'mp_sync')
        RETURNING id
    """), {"email": res.payer_email, "name": nome,
           "mp": res.payer_id or ""}).scalar_one()
    _log_event(db, str(cid), "client_created_from_mp", {"mp_id": res.resource_id})
    return str(cid)


def _resolve_plan(db: Session, res: MPResource) -> str | None:
    """Plano local, nesta ordem: external_reference → preapproval_plan_id.

    O `external_reference` é `"plan_slug:customer_email"` (posto no checkout).
    Sem ele, cai no `preapproval_plan_id` do MP, que é o id do plano lá.
    """
    if res.external_reference and ":" in res.external_reference:
        slug = res.external_reference.split(":", 1)[0].strip()
        if slug:
            found = db.execute(text(
                "SELECT id FROM saas.plans WHERE slug = :s LIMIT 1"), {"s": slug}).scalar_one_or_none()
            if found:
                return str(found)
    if res.preapproval_plan_id:
        found = db.execute(text(
            "SELECT id FROM saas.plans WHERE mp_plan_id = :p LIMIT 1"),
            {"p": res.preapproval_plan_id}).scalar_one_or_none()
        if found:
            return str(found)
    return None


def _materialize_preapproval(db: Session, res: MPResource) -> dict[str, Any]:
    """Cria/atualiza a assinatura a partir de um preapproval.

    Devolve `{"action": ...}` para o relatório — o painel precisa distinguir
    "criada pelo reconciliador" de "já existia", porque a primeira é a prova
    de que o webhook falhou.
    """
    existing = db.execute(text("""
        SELECT id, client_id, status, manual_override FROM saas.subscriptions
         WHERE mp_preapproval_id = :pid AND deleted_at IS NULL LIMIT 1
    """), {"pid": res.resource_id}).mappings().first()

    mp_active = (res.status or "").lower() in MP_ACTIVE

    # ── A assinatura JÁ EXISTE: sincronizar/registrar, sem depender do payer ──
    #
    # A ordem importa, e na primeira versão estava errada. A resolução do
    # cliente vinha ANTES, e saía com `skipped` quando o preapproval não tinha
    # `payer.email` — que é o caso de todos os 19 preapprovals reais do MP
    # (medido: `payer` ausente). Ou seja: o caminho de atualização nunca
    # executava, e com ele a regra do override e a detecção de drift.
    #
    # Uma assinatura que já existe TEM `client_id`. Não há motivo nenhum para
    # exigir e-mail do pagador para decidir o que fazer com ela.
    if existing is not None:
        return _sync_existing(db, res, existing, mp_active)

    # ── Não existe: precisa resolver cliente e plano para criar ───────────────
    client = _find_client(db, res.payer_email)
    if client is None:
        client_id = _create_client(db, res)
    else:
        client_id = str(client["id"])
    if client_id is None:
        return {"action": "skipped", "motivo": "sem payer_email para localizar/criar cliente"}

    plan_id = _resolve_plan(db, res)
    if plan_id is None:
        return {"action": "skipped", "motivo": "plano não resolvido (mp_plan_id/external_reference)"}

    # `current_period_end` é NOT NULL. A primeira versão passava `None`
    # quando o preapproval vinha sem `last_modified` — o caso de uma assinatura
    # recem-criada no MP, exatamente o que este reconciliador existe para
    # cobrir.
    #
    # O efeito era pior que a exceção: a violação abortava a TRANSAÇÃO toda, e
    # o `except Exception` do `sync()` fazia rollback — descartando o espelho
    # inteiro e devolvendo "sucesso". Nada era criado e nenhum dos recursos
    # lidos ficava salvo.
    ancoragem = res.mp_updated_at or res.mp_created_at or datetime.now(timezone.utc)
    period_end = ancoragem + timedelta(days=30)
    sub_id = db.execute(text("""
        INSERT INTO saas.subscriptions
            (client_id, plan_id, status, mp_preapproval_id,
             mp_subscription_id, source, granted_by,
             current_period_end, created_at, updated_at)
        VALUES
            (:cid, :pid, :status, :mpid, :mpid, 'mp_sync', 'reconciliador',
             :pend, NOW(), NOW())
        RETURNING id
    """), {"cid": client_id, "pid": plan_id,
            "status": "active" if mp_active else "pending",
            "mpid": res.resource_id, "pend": period_end}).scalar_one()
    _log_event(db, client_id, "subscription_materialized_from_mp", {
        "mp_preapproval_id": res.resource_id,
        "mp_status": res.status,
        "motivo": "webhook não materializou (reconciliação)",
    })
    return {"action": "created", "subscription_id": str(sub_id)}


def _sync_existing(db: Session, res: MPResource, existing, mp_active: bool) -> dict[str, Any]:
    """Assinatura que já existe: aplica o override, ou alinha com o MP.

    Isolado em função própria porque este é O CAMINHO QUE IMPORTA — é a rede de
    segurança do webhook — e ele não pode depender de nada que só a criação
    precisa (payer, resolução de plano).
    """
    sub_id = str(existing["id"])
    client_id = str(existing["client_id"])

    # A REGRA QUE O SUPORTE APROVOU: nunca reverter ajuste manual.
    if existing["manual_override"]:
        # NÃO mexe. Registra a divergência para decisão humana.
        db.execute(text("""
            UPDATE saas.subscriptions
               SET mp_status = :mp, mp_synced_at = NOW(), mp_status_differs = TRUE
             WHERE id = :id
        """), {"mp": res.status, "id": sub_id})
        return {"action": "override_respeitado", "subscription_id": sub_id,
                "motivo": "ajuste manual do suporte preservado"}

    # `differs` compara o ALVO com o que estava, e não o MP com o que estava.
    #
    # A primeira versão media a divergência ANTES de corrigir, então o painel
    # ficava mostrando "decisão humana" em cima de algo que o próprio
    # reconciliador tinha acabado de resolver — por até 15 minutos, até a
    # rodada seguinte corrigir o próprio marcador.
    #
    # `mudou` e "discordam" são coisas diferentes, e confundi-las era o bug:
    #   `mudou`     → o status local era outro e foi corrigido. Serve para o
    #                 relatório e para o evento de auditoria.
    #   `discordam` → MP e local discordam AGORA. Depois de aplicar um alvo
    #                 derivado do próprio MP, eles concordam por construção —
    #                 então é SEMPRE falso neste caminho.
    local = (existing["status"] or "").lower()
    mp_st = (res.status or "").lower()
    if mp_active:
        target = "active"
    elif mp_st in MP_CANCELLED:
        target = "cancelled"
    else:
        # O MP diz algo que não sabemos mapear (pending, paused, vazio).
        # Não mexer é a única escolha honesta: 'saber menos' não é motivo para
        # inventar um estado.
        target = local
    mudou = target != local

    db.execute(text("""
        UPDATE saas.subscriptions
           SET status = :status, mp_status = :mp, mp_synced_at = NOW(),
               mp_status_differs = FALSE, updated_at = NOW()
         WHERE id = :id
    """), {"status": target, "mp": res.status, "id": sub_id})

    if mudou:
        _log_event(db, client_id, "subscription_status_synced_from_mp", {
            "subscription_id": sub_id,
            "de": local, "para": target, "mp_status": res.status,
        })
    return {"action": "atualizada" if mudou else "sem_divergencia",
            "subscription_id": sub_id}


def sync(db: Session, days: int = 30, client_factory=None) -> dict[str, Any]:
    """Um ciclo de reconciliação. Idempotente."""
    summary: dict[str, Any] = {
        "lidos": 0, "materializados": 0, "atualizados": 0,
        "override_respeitados": 0, "ignorados": 0,
        "mp_indisponivel": False, "detalhe": None,
    }
    factory = client_factory or MPClient
    since = datetime.now(timezone.utc) - timedelta(days=days)

    try:
        mp = factory()
    except Exception as exc:
        summary["mp_indisponivel"] = True
        summary["detalhe"] = f"cliente: {exc}"
        return summary

    try:
        if not getattr(mp, "configured", False):
            summary["mp_indisponivel"] = True
            summary["detalhe"] = "MP_ACCESS_TOKEN ausente"
            return summary

        recursos: list[MPResource] = []
        falhas: list[str] = []
        try:
            recursos.extend(mp.search_payments(since))
        except MPUnavailable as exc:
            logger.warning("busca de pagamentos falhou: %s", exc)
            falhas.append(f"payments: {exc}")
        try:
            recursos.extend(mp.search_preapprovals(since))
        except MPUnavailable as exc:
            logger.warning("busca de preapprovals falhou: %s", exc)
            falhas.append(f"preapprovals: {exc}")

        if not recursos:
            # Distingue "não houve venda" de "não deu para perguntar" — a
            # confusão que faz o painel mentir na direção mais perigosa.
            #
            # Se TODAS as buscas falharam, o MP estava fora: dizer "nada no
            # período" seria afirmar que ninguém comprou quando na verdade não
            # fomos capazes de perguntar. (Este é o mesmo falso-negativo que
            # existia no relatório do teste sandbox.)
            if len(falhas) == 2:
                summary["mp_indisponivel"] = True
                summary["detalhe"] = "; ".join(falhas)
                return summary
            # Falhou só uma das duas: a outra respondeu. É resposta parcial
            # válida, mas declaramos o limite para não ler como "completo".
            summary["detalhe"] = ("; ".join(falhas) + " — leitura parcial"
                                   if falhas else "MP respondeu: nada no período")
            return summary

        for res in recursos:
            summary["lidos"] += 1
            upsert_mirror(db, res)
            if res.resource_type == "preapproval":
                out = _materialize_preapproval(db, res)
                act = out.get("action")
                if act == "created":
                    summary["materializados"] += 1
                elif act == "atualizada":
                    summary["atualizados"] += 1
                elif act == "override_respeitado":
                    summary["override_respeitados"] += 1
                else:
                    summary["ignorados"] += 1
        db.commit()
    except MPUnavailable as exc:
        db.rollback()
        summary["mp_indisponivel"] = True
        summary["detalhe"] = str(exc)
    except Exception as exc:  # nunca derrubar o beat
        db.rollback()
        summary["mp_indisponivel"] = True
        summary["detalhe"] = f"erro inesperado: {exc}"
        logger.exception("sync MP falhou")
    finally:
        try:
            mp.close()
        except Exception:
            pass

    _propagar_status_pagamento(db)
    return summary


def _propagar_status_pagamento(db: Session) -> None:
    """Liga `mp_payment_id` quando existe pagamento APROVADO no espelho.

    Sem isto, `subs_com_cobranca` e o "MRR com cobrança" do painel ficam em 0
    mesmo com o cliente tendo pago — que era o número que o painel mostrava.
    """
    try:
        db.execute(text("""
            UPDATE saas.subscriptions s
               SET mp_payment_id = m.resource_id,
                   updated_at = NOW()
              FROM saas.mp_resources m
             WHERE m.resource_type = 'payment'
               AND m.status = 'approved'
               AND m.preapproval_id = s.mp_preapproval_id
               AND s.mp_payment_id IS NULL
        """))
        db.commit()
    except Exception:
        db.rollback()
        logger.debug("propagação de mp_payment_id falhou", exc_info=True)


def drift(db: Session) -> list[dict[str, Any]]:
    """Divergências entre MP e local, com a ação sugerida.

    Cada linha carrega `requer_decisao_humana`: é o filtro que separa "o sistema
    já corrigiu" de "alguém precisa olhar".
    """
    rows = db.execute(text("""
        SELECT
          -- Pagamento aprovado que NENHUMA assinatura local referencia: a venda
          -- aconteceu e não entrou no sistema (webhook perdido ou ausente).
          (SELECT COALESCE(count(*),0) FROM saas.mp_resources m
            WHERE m.resource_type='payment' AND m.status='approved'
              AND m.resource_id NOT IN (
                    SELECT COALESCE(mp_payment_id,'') FROM saas.subscriptions
                    WHERE mp_payment_id IS NOT NULL)
              AND m.preapproval_id IS NULL
          ) AS eventos_perdidos,
          (SELECT COALESCE(count(*),0) FROM saas.subscriptions s
            WHERE s.manual_override AND s.mp_status_differs AND s.deleted_at IS NULL
          ) AS override_divergente,
          (SELECT COALESCE(count(*),0) FROM saas.subscriptions
            WHERE mp_status_differs AND NOT manual_override AND deleted_at IS NULL
          ) AS divergencia_auto,
          (SELECT COALESCE(count(*),0) FROM saas.subscriptions
            WHERE deleted_at IS NULL AND mp_preapproval_id IS NOT NULL AND mp_payment_id IS NULL
          ) AS sem_comprovante,
          (SELECT max(synced_at) FROM saas.mp_resources) AS ultima_sincronia,
          (SELECT count(*) FROM saas.mp_resources) AS total_espelho
    """)).mappings().first()
    out = dict(rows)
    out["requer_decisao_humana"] = int(out["eventos_perdidos"]) + int(out["override_divergente"])
    return [out]


def mrr_real(db: Session) -> dict[str, Any]:
    """MRR/churn a partir dos COBRANÇAS no MP, não dos campos locais.

    MRR local conta assinatura marcada ativa; MRR real conta assinatura que
    teve cobrança aprovada. No estado atual (0 pagamentos) ambos são 0 — a
    diferença é que este passa a ser verdade assim que existir uma venda.
    """
    row = db.execute(text("""
        WITH pagas AS (
          SELECT DISTINCT preapproval_id
            FROM saas.mp_resources
           WHERE resource_type = 'payment' AND status = 'approved'
             AND preapproval_id IS NOT NULL
        )
        SELECT
          COALESCE(SUM(p.price_cents), 0) AS mrr_pago_cents,
          COALESCE(SUM(p.price_cents), 0) / 100.0 * 12 AS arr_pago_brl,
          (SELECT count(*) FROM pagas) AS assinaturas_com_cobranca,
          (SELECT count(*) FROM saas.mp_resources
            WHERE resource_type='payment' AND status='rejected') AS pagamentos_recusados,
          (SELECT count(*) FROM saas.mp_resources
            WHERE resource_type='authorized_payment'
              AND mp_created_at >= date_trunc('month', NOW())
          ) AS recorrentes_no_mes
        FROM saas.subscriptions s
        JOIN saas.plans p ON p.id = s.plan_id
        JOIN pagas ON pagas.preapproval_id = s.mp_preapproval_id
       WHERE s.deleted_at IS NULL AND p.price_cents > 0
    """)).mappings().first()
    return dict(row or {})