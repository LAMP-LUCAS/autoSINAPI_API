# api/admin_mp.py
"""Painel CMS/CRM — visão do Mercado Pago.

POR QUE ISTO EXISTE
-------------------
Até 05/10/2026 o painel mostrava apenas a NOSSA versão das coisas:
`saas.webhook_events` (o que fomos avisados) e `saas.subscriptions.mp_*` (o que
guardamos). A pergunta que o suporte mais precisa responder — *"o cliente pagou
e nós não estamos entregando?"* — era indistinguível de *"ninguém comprou"*.

Este router fecha essa lacuna com um segundo caminho de leitura: o estado que o
Mercado Pago afirma existir, independente de qualquer webhook. O DIFF entre os
dois é o sinal, e é o que estas rotas expõem.

ESCOPO
------
SOMENTE LEITURA do MP, mais o disparo da reconciliação local. Não cancela, não
estorna, não reverte ajuste manual do suporte (decisão de 06/10/2026): um painel
que desfaz o trabalho do suporte é um painel em que ninguém confia.

Todas as rotas exigem o token admin (`Depends(verify_admin_token)`), igual ao
resto de `admin_crm`.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from .admin_auth import verify_admin_token
from .database import get_saas_db
from . import mp_sync
from .mp_client import MPClient, MPUnavailable

logger = logging.getLogger("autosinapi.admin.mp")
router = APIRouter(tags=["Admin", "Mercado Pago"], dependencies=[Depends(verify_admin_token)])


def _row(r: Any) -> dict:
    return dict(r) if r is not None else {}


class MpOverride(BaseModel):
    """Liga/desliga o \"esta assinatura foi corrigida à mão\"."""

    # `motivo` é obrigatório ao ATIVAR, e opcional de propósito ao desativar.
    # Ativar sem dizer por quê cria um estado que ninguém consegue explicar
    # depois — e o reconciliador vai obedecer a ele indefinidamente. O motivo é
    # o que dá sentido ao sinal; sem ele, a regra vira um ponto cego.
    ativo: bool
    motivo: Optional[str] = Field(None, max_length=500)
    by: Optional[str] = Field(None, max_length=80)


@router.post("/api/v1/admin/subscriptions/{sub_id}/mp-override",
             summary="Marcar assinatura como ajuste manual (protegido do reconciliador)")
def set_mp_override(sub_id: str, req: MpOverride, db: Session = Depends(get_saas_db)):
    """O contraponto que faltava: `manual_override` era lido, nunca escrito.

    Sem esta rota a decisão \"nunca reverter ajuste manual\" era respeitada — e
    inalcançável: não havia como marcar nada. Com ela, o suporte protege o que
    corrigiu e o painel mostra a divergência em vez de silenciá-la.
    """
    sub = db.execute(text("""
        SELECT s.id, s.client_id, s.status, s.mp_status, s.mp_status_differs,
               c.email
          FROM saas.subscriptions s
          LEFT JOIN saas.clients c ON c.id = s.client_id
         WHERE s.id = :id AND s.deleted_at IS NULL
    """), {"id": sub_id}).mappings().first()
    if not sub:
        raise HTTPException(status_code=404, detail="Assinatura não encontrada")

    if req.ativo and not (req.motivo or "").strip():
        raise HTTPException(
            status_code=400,
            detail="Diga o motivo: o reconciliador vai obedecer a este estado "
                   "sem questionar, e sem motivo ele vira um ponto cego.")

    if req.ativo:
        db.execute(text("""
            UPDATE saas.subscriptions
               SET manual_override = TRUE, override_reason = :motivo,
                   override_at = NOW(), override_by = :by, updated_at = NOW()
             WHERE id = :id
        """), {"motivo": (req.motivo or "").strip(), "by": req.by or "admin", "id": sub_id})
        evento = "mp_override_ativado"
    else:
        # Ao DESATIVAR, zeramos `mp_status_differs`: a divergência que o
        # override mantinha visível deixa de ser responsabilidade do suporte,
        # e o próximo ciclo do reconciliador passa a valer de novo.
        #
        # O `status` em si NÃO é mexido aqui de propósito — quem alinha com o
        # MP é o reconciliador, e duplicar essa lógica aqui criaria duas
        # fontes de verdade para a mesma decisão. A resposta diz o que fazer
        # em seguida para não deixar o suporte olhando um status velho sem
        # saber disso.
        db.execute(text("""
            UPDATE saas.subscriptions
               SET manual_override = FALSE, override_reason = NULL,
                   override_at = NULL, override_by = NULL,
                   mp_status_differs = FALSE, updated_at = NOW()
             WHERE id = :id
        """), {"id": sub_id})
        evento = "mp_override_desativado"

    # Savepoint pelo mesmo motivo do `mp_sync._log_event`: um erro de auditoria
    # em Postgres aborta a transação e faz o `commit()` abaixo DESCARTAR o
    # `UPDATE` do override — devolvendo 200 sem ter gravado nada. Foi assim que
    # o override "funcionava" (200) e não persistia.
    try:
        with db.begin_nested():
            db.execute(text("""
                INSERT INTO saas.client_events (client_id, event_type, actor, details, occurred_at)
                VALUES (:cid, :etype, 'admin', CAST(:details AS jsonb), NOW())
            """), {"cid": sub["client_id"], "etype": evento,
                  "details": json.dumps({
                      "subscription_id": sub_id,
                      "motivo": req.motivo, "by": req.by or "admin",
                      "status_local": sub["status"], "status_mp": sub["mp_status"],
                  }, ensure_ascii=False)})
    except Exception:
        logger.warning("client_events indisponível para %s", evento, exc_info=True)
    db.commit()

    # LER DE VOLTA, não ecoar o request. O eco escondia um bug real: o endpoint
    # devolvia `manual_override: true` com 200 mesmo quando nada tinha sido
    # gravado. Um 200 que confirma o que o banco tem é a diferença entre
    # "funciona" e "parece que funciona".
    salvo = db.execute(text("""
        SELECT manual_override, override_reason, override_at, override_by,
               mp_status_differs, status
          FROM saas.subscriptions WHERE id = :id
    """), {"id": sub_id}).mappings().first()
    s2 = _row(salvo)

    return {
        "subscription_id": sub_id,
        "manual_override": s2.get("manual_override"),
        "override_reason": s2.get("override_reason"),
        "override_at": s2.get("override_at"),
        "override_by": s2.get("override_by"),
        "status_local": s2.get("status"),
        "mp_status_differs": s2.get("mp_status_differs"),
        "proximo_passo": (
            "Protegido: o reconciliador registra a divergência e não altera o status."
            if s2.get("manual_override") else
            "O reconciliador volta a valer no próximo ciclo (até 15 min). "
            "Para alinhar agora, use 'Sincronizar com o MP agora'."
        ),
    }


@router.get("/api/v1/admin/mp/health", summary="Prova de vida do MP (token)")
def mp_health():
    """Token válido? MP alcançável?

    Existe separado dos outros números porque um token expirado produz a MESMA
    aparência de "não houve venda" — que é exatamente a confusão que este
    trabalho existe para eliminar.
    """
    with MPClient() as mp:
        return mp.health()


@router.get("/api/v1/admin/mp/summary", summary="Resumo financeiro real (MP)")
def mp_summary(db: Session = Depends(get_saas_db)):
    real = mp_sync.mrr_real(db)
    espelho = db.execute(text("""
        SELECT
          (SELECT count(*) FROM saas.mp_resources WHERE resource_type='payment')        AS pagamentos,
          (SELECT count(*) FROM saas.mp_resources WHERE resource_type='payment'
             AND status='approved')                                                      AS pagamentos_aprovados,
          (SELECT count(*) FROM saas.mp_resources WHERE resource_type='payment'
             AND status='rejected')                                                      AS pagamentos_recusados,
          (SELECT count(*) FROM saas.mp_resources WHERE resource_type='preapproval')     AS assinaturas_mp,
          (SELECT count(*) FROM saas.mp_resources WHERE resource_type='authorized_payment') AS cobrancas_recorrentes,
          (SELECT max(synced_at) FROM saas.mp_resources)                                 AS ultima_sincronia
    """)).mappings().first()
    out = _row(espelho)
    out["mrr_pago_cents"] = int(real.get("mrr_pago_cents") or 0)
    out["arr_pago_brl"] = real.get("arr_pago_brl")
    out["assinaturas_com_cobranca"] = int(real.get("assinaturas_com_cobranca") or 0)
    out["recorrentes_no_mes"] = int(real.get("recorrentes_no_mes") or 0)
    out["drift"] = mp_sync.drift(db)
    out["aviso"] = (
        "Sem pagamentos no espelho: MRR real e churn são 0 até existir uma "
        "cobrança. Esse 0 é ausência de dado, não ausência de venda."
    )
    return out


@router.get("/api/v1/admin/mp/resources", summary="Espelho de recursos do MP")
def mp_resources(
    resource_type: str | None = Query(None, pattern="^(payment|preapproval|authorized_payment)$"),
    status: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_saas_db),
):
    """O que o MP afirma existir.

    `sincronizado` compara com `webhook_events`: um pagamento aprovado aqui sem
    evento nosso é justamente o "evento perdido" — a venda que aconteceu sem
    avisar.
    """
    cond, params = ["TRUE"], {"limit": limit}
    if resource_type:
        cond.append("m.resource_type = :t"); params["t"] = resource_type
    if status:
        cond.append("m.status = :s"); params["s"] = status

    rows = db.execute(text(f"""
        SELECT m.resource_type, m.resource_id, m.status, m.status_detail,
               m.amount_cents, m.currency_id, m.payer_email, m.external_reference,
               m.preapproval_id, m.mp_created_at, m.synced_at,
               (SELECT COUNT(*) FROM saas.webhook_events w
                 WHERE w.external_id = m.resource_id
                   AND w.topic IN ('payment','subscription_preapproval',
                                   'subscription_authorized_payment')
               ) AS eventos_webhook
          FROM saas.mp_resources m
         WHERE {' AND '.join(cond)}
         ORDER BY m.mp_created_at DESC NULLS LAST
         LIMIT :limit
    """), params).mappings().all()

    items = []
    for r in rows:
        d = _row(r)
        d["sincronizado"] = int(d.pop("eventos_webhook") or 0) > 0
        d["valor_brl"] = (d["amount_cents"] / 100.0) if d.get("amount_cents") else None
        items.append(d)
    return {"items": items}


@router.get("/api/v1/admin/mp/drift", summary="Divergências MP × local")
def mp_drift(db: Session = Depends(get_saas_db)):
    """O que precisa de olho humano.

    `requer_decisao_humana` > 0 é o sinal de que o automatismo não resolveu e
    alguém precisa decidir.
    """
    resumo = mp_sync.drift(db)[0]
    divergencias = db.execute(text("""
        SELECT s.id AS subscription_id, c.email, p.name AS plano, p.slug AS plano_slug,
               s.status AS status_local, s.mp_status AS status_mp,
               s.manual_override, s.override_reason, s.override_at,
               s.mp_status_differs, s.updated_at, s.current_period_end
          FROM saas.subscriptions s
          LEFT JOIN saas.clients c ON c.id = s.client_id
          LEFT JOIN saas.plans   p ON p.id = s.plan_id
         WHERE s.deleted_at IS NULL
           AND (s.mp_status_differs OR s.mp_status IS NOT NULL)
         ORDER BY s.mp_status_differs DESC NULLS LAST, s.updated_at DESC
         LIMIT 100
    """)).mappings().all()
    itens = []
    for r in divergencias:
        d = _row(r)
        d["acao_sugerida"] = (
            "revisar ajuste manual" if d.get("manual_override")
            else "sincronizável automaticamente" if d.get("mp_status_differs")
            else "em dia com o MP"
        )
        itens.append(d)
    return {"resumo": resumo, "itens": itens}


@router.get("/api/v1/admin/mp/payments/{payment_id}", summary="Consultar um pagamento no MP")
def mp_payment_detail(payment_id: str):
    """Leitura pontual sob demanda — o botão "consultar MP agora" do suporte."""
    with MPClient() as mp:
        try:
            res = mp.get_payment(payment_id)
        except MPUnavailable as exc:
            raise HTTPException(status_code=502, detail=f"Mercado Pago indisponível: {exc}")
    if res is None:
        raise HTTPException(status_code=404, detail="Pagamento não encontrado no MP")
    out = res.to_row()
    out["valor_brl"] = (res.amount_cents / 100.0) if res.amount_cents else None
    return out


@router.post("/api/v1/admin/mp/sync", summary="Disparar reconciliação agora")
def mp_sync_now(days: int = Query(30, ge=1, le=365)):
    """Roda um ciclo do reconciliador sob demanda.

    Devolve o relatório do ciclo em vez de um "ok": quem chamou precisa poder
    ver quantos recursos foram lidos e quantos foram materializados — um "ok"
    aqui seria indistinguível de "o MP estava fora e eu não percebi".
    """
    from .database import SaasSessionLocal

    db = SaasSessionLocal()
    try:
        return mp_sync.sync(db, days=days)
    finally:
        db.close()


@router.get("/api/v1/admin/subscriptions/{sub_id}/mp", summary="Estado do MP para uma assinatura")
def subscription_mp_state(sub_id: str, live: int = Query(0, ge=0, le=1),
                          db: Session = Depends(get_saas_db)):
    """A visão que faltava na tela da assinatura: o MP concorda?

    Inclui o HISTÓRICO de cobranças (inclusive recorrentes), que a assinatura
    não tem — `current_period_end` mostra só o período atual.

    `live=1` vai direto ao MP em vez de ler o espelho. É o "Consultar MP agora"
    do suporte: quando o espelho tem 15 minutos de idade e alguém está com um
    cliente na linha, esperar o beat não serve. A resposta distingue as duas
    origens (`fonte`) para que ninguém ache que uma leitura velha é atual.
    """
    sub = db.execute(text("""
        SELECT s.*, c.email, p.name AS plano_nome, p.slug AS plano_slug
          FROM saas.subscriptions s
          LEFT JOIN saas.clients c ON c.id = s.client_id
          LEFT JOIN saas.plans   p ON p.id = s.plan_id
         WHERE s.id = :id AND s.deleted_at IS NULL
    """), {"id": sub_id}).mappings().first()
    if not sub:
        raise HTTPException(status_code=404, detail="Assinatura não encontrada")
    s = _row(sub)

    mp_preapproval_id = s.get("mp_preapproval_id")

    # Leitura AO VIVO (sob demanda). O espelho tem até 15 min de idade por
    # natureza; este caminho existe para quando 15 min é demais.
    status_mp_live = None
    erro_live = None
    if live and mp_preapproval_id:
        try:
            with MPClient() as mp:
                res = mp.get_preapproval(str(mp_preapproval_id))
            status_mp_live = (res.status if res else None)
        except MPUnavailable as exc:
            erro_live = str(exc)

    recursos = db.execute(text("""
        SELECT resource_type, resource_id, status, amount_cents, currency_id,
               mp_created_at
          FROM saas.mp_resources
         WHERE preapproval_id = :pid OR resource_id = :rid
         ORDER BY mp_created_at DESC NULLS LAST
         LIMIT 50
    """), {"pid": mp_preapproval_id or "", "rid": mp_preapproval_id or ""}).mappings().all()

    # Três estados, não dois. "Não discorda" e "não sabemos" colapsar num só é
    # exatamente o defeito que este trabalho existe para não repetir: um
    # `concorda` inventado diria ao suporte que está tudo certo quando o
    # verdade é que ninguém perguntou ao MP.
    ATIVO_MP = {"authorized", "active"}
    CANC_MP = {"cancelled", "paused"}
    ATIVO_LOCAL = {"active", "authorized", "approved"}
    CANC_LOCAL = {"cancelled", "canceled", "expired"}

    status_espelho = s.get("mp_status")
    status_mp = status_mp_live if (live and status_mp_live is not None) else status_espelho
    local = (s.get("status") or "").lower()

    if status_mp is None:
        veredito = "nao_verificado"
    elif ((local in ATIVO_LOCAL and status_mp in ATIVO_MP)
          or (local in CANC_LOCAL and status_mp in CANC_MP)):
        veredito = "concorda"
    else:
        veredito = "divergencia"

    return {
        "subscription": {
            "id": s["id"], "email": s.get("email"), "plano": s.get("plano_nome"),
            "status_local": s.get("status"), "status_mp": status_mp,
            "mp_preapproval_id": mp_preapproval_id,
            "mp_payment_id": s.get("mp_payment_id"),
            "manual_override": s.get("manual_override"),
            "override_reason": s.get("override_reason"),
            "override_at": s.get("override_at"), "override_by": s.get("override_by"),
            "mp_status_differs": s.get("mp_status_differs"),
            "mp_synced_at": s.get("mp_synced_at"),
            "current_period_end": s.get("current_period_end"),
        },
        "veredito": veredito,
        "status_mp_espelho": status_espelho,
        # De onde veio o status. Sem isto, uma leitura de 14 min atrás se
        # apresenta como atual — e o suporte decide sobre dado velho sem saber.
        "fonte": ("mp" if (live and status_mp_live is not None)
                  else "espelho" if status_espelho else "nenhuma"),
        "consultado_em": datetime.now(timezone.utc).isoformat() if live else None,
        "erro_ao_consultar": erro_live,
        "mp_verificado": status_mp is not None,
        "recorrencias": [
            {**_row(r), "valor_brl": (r["amount_cents"] / 100.0) if r["amount_cents"] else None}
            for r in recursos
        ],
    }