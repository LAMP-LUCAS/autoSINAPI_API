"""api/crm_conteudo.py — a ponte que o n8n chama nos dias de slot.

Um endpoint só, com três respostas possíveis:

* **não envia** — diz por quê (sem consentimento, teto, cadência, dado parado)
* **envia** — devolve o passo, a assinatura e as variáveis do e-mail

O n8n não decide nada: ele pede, a API responde, ele despacha. Toda a política
fica aqui, onde é testável — no Code node do workflow ela exigiria o runtime do
n8n de pé para ser verificada.

Um passo por chamada (devolve uma lista, não um objeto) porque o workflow
precisa claims **independentes** por lead: com um objeto só, um claim ruins
contaminaria o lote inteiro.

A reserva é atômica (`saas.nurture_state`), então dois workers no mesmo
minuto não duplicam — que era a razão de o nurture v2 existir.
"""

from __future__ import annotations

import datetime as _dt
import logging
import os as _os
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from .admin_auth import verify_admin_token
from .database import SaasSessionLocal, get_saas_db
from .reports import registro
from .reports.fontes import nota_incc_atual
from .reports.model import Categoria, Contexto, Relatorio
from .reports.recoveredor import ContextoRecuperacao
from .reports.roteiro import EstadoSemana, Roteiro
from .links import AGENDA_URL, PORTAL_URL, TOOLS_URL
# `EVENTO_LOGIN_APP` é SSOT do outro lado: quem **grava** é o `portal/me`.
# Importar em vez de repetir o literal é o que impede o leitor da cascata
# de procurar um tipo de evento que o app nunca escreve.
from .portal import EVENTO_LOGIN_APP
from .reports.render import renderizar, svg_do_relatorio
from .reports.recoveredor import decidir_promo, decidir_winback

logger = logging.getLogger("autosinapi.crm.conteudo")
router = APIRouter(tags=["Admin", "CRM"],
                   dependencies=[Depends(verify_admin_token)])

# Funil de conteúdo: **um template por slot**, e o slot é quem escolhe.
# SSOT do que existe: `saas-gateway/emails/registry.yaml`; o teste
# `saas-gateway/tests/test_email_funnel_slots.py` compara os dois lados.
#
# `gateway_lead_welcome` (66666666) NÃO aparece aqui — é exclusivo da
# captura (`public_leads.LEAD_WELCOME_TEMPLATE_ID`). Ele foi usado pelo slot
# de artigo e foi por isso que o artigo "não era enviado": o template
# declara `lead_name, portal_url, tools_url`, o produtor lhe passava
# `article_*` sem `portal_url`, e o href `{{ portal_url }}/app/sinapi` saía
# relativo — link morto — enquanto o título e a URL do artigo eram
# descartados pelo render.
TEMPLATE_RELATORIO = "f5555555-5555-5555-5555-555555555555"  # gateway_report_weekly
TEMPLATE_ARTIGO = "f4444444-4444-4444-4444-444444444444"     # gateway_kb_digest

# Templates de recuperação e promoção. Antes, os dois caíam no ramo "artigo" e
# saíam com o assunto "— Knowledge Base" e as variáveis `article_*`: o corpo
# promotional ficava errado sem dar erro nenhum.
#
# `gateway_winback` (f3333333) NÃO serve aqui: o registry o descreve como
# win-back de **cancelamento**, com `plan_name` e `discount_days` — é conceito
# de cliente. O slot é de **lead** que parou de usar, que é `reengagement`.
TEMPLATE_REENGAGEMENT = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"  # gateway_reengagement
TEMPLATE_PROMO = "99999999-9999-9999-9999-999999999999"        # gateway_promo_weekly

# A oferta do winback é decisão comercial, não editorial — por isso fica
# sobrescrevível por ambiente em vez de enterrada no texto. O default reproduz
# o que o workflow antigo já enviava (30%, cupom VOLTEI30): o template
# `gateway_reengagement` interpola `{{ desconto }}`/`{{ cupom }}` sem guarda, e
# sem eles o e-mail sai como "Volte com % off ... use o cupom .".
WINBACK_DESCONTO = _os.getenv("WINBACK_DESCONTO_PCT", "30")
WINBACK_CUPOM = _os.getenv("WINBACK_CUPOM", "VOLTEI30")
# `validade_dias` foi removido em 03/10: nenhuma das 18 entradas do
# `registry.yaml` o declara e nenhum body o usa — era variável enviada ao
# nada, e o teste de contrato (vars iguais às declaradas) agora reprova
# qualquer sobra desse tipo.

# `UNSUBSCRIBE` também saiu daqui em 03/10, na Fase 2. O link de preferências
# é do **rodapé compartilhado** que o `EmailSmtpAdapter` aplica a todos os
# e-mails (Fase 2), e a URL assinada é calculada pelo `SendOS` a partir de
# `MD_PUBLIC_URL`. O produtor mantinha uma cópia estática sem token — que
# apontava para o host errado e, mesmo corrigida, daria 404 por design
# (anti-enumeração sem `?tk=`, ADR-0011). O footer é atributo do
# transportador: nenhum template o declara e nenhum produtor o envia.

# ── URLs do produtor ────────────────────────────────────────────────────────
# SSOT: `api/links.py` — módulo único, lido também por `public_leads`, que
# antes repetia o literal com path errado. Mantidos re-exportados aqui
# porque `test_producer_contract.py` e `test_crm_envelope_slot.py` importam
# por este caminho.

# Quanto tempo um claim vale antes de outro worker poder tomá-lo. Uma só fonte:
# `_reservar` decide quem reenvia e `orfaos` reporta quem ficou preso — se
# divergirem, a varredura passa a accuse coisa que já se recuperou sozinha.
JANELA_CLAIM_MINUTOS = 15

# Janela de competência já anunciada: o que impede o relatório 9 de repetir.
SQL_ULTIMA_COMPETENCIA = """
    SELECT competencia FROM saas.notifications_state
     WHERE status = 'announced' ORDER BY competencia DESC LIMIT 1
"""


def _contexto_lead(db: Session, lead_id: str) -> Optional[Contexto]:
    """Estado do lead: o que o roteiro precisa para decidir.

    `eh_cliente` sai da assinatura **ativa** — é isso que separa o segmento
    que recebe 2 por semana do que recebe 1.
    """
    row = db.execute(text("""
        SELECT l.id, l.email, l.name, l.persona, l.created_at,
               EXISTS (SELECT 1 FROM saas.subscriptions s
                         JOIN saas.clients c ON c.id = s.client_id
                        WHERE lower(c.email) = lower(l.email)
                          AND s.status = 'active' AND s.deleted_at IS NULL
                          AND COALESCE(c.is_test, FALSE) = FALSE) AS eh_cliente,
               COALESCE(l.metadata->>'marketing_optin', 'true') AS optin
          FROM saas.leads l
         WHERE l.id = :id AND l.deleted_at IS NULL
           AND COALESCE(l.is_test, FALSE) = FALSE
    """), {"id": lead_id}).mappings().first()
    if row is None:
        return None

    etapas = db.execute(text("""
        SELECT n.step FROM saas.nurture_state n
         WHERE n.lead_id = :id AND n.status = 'sent'
           AND n.step NOT IN ('d3', 'd7')
    """), {"id": lead_id}).scalars().all()

    assinaturas = db.execute(text("""
        SELECT metadata->>'slug' AS s FROM saas.nurture_state
         WHERE lead_id = :id AND step LIKE 'kb\\_%'
           AND metadata ? 'slug'
    """), {"id": lead_id}).scalars().all()

    dias = (_dt.date.today() - row["created_at"].date()).days
    return Contexto(
        lead_id=str(row["id"]), email=row["email"],
        nome=row["name"] or "Lead",
        persona=row["persona"],
        eh_cliente=bool(row["eh_cliente"]),
        dias_de_relacionamento=dias,
        etapas_enviadas=tuple(etapas),
        consentimento_marketing=str(row["optin"]).lower() == "true",
        ultima_assinatura=None,
    ), tuple(assinaturas)


@router.get("/api/v1/admin/crm/conteudo/elegiveis",
            summary="Leads a considerar no slot de hoje")
def leads_elegiveis(hoje: Optional[str] = Query(None),
                    db: Session = Depends(get_saas_db)) -> dict:
    """Quem o workflow deve consultar hoje.

    A elegibilidade fina (cadência, teto, dado parado) fica em `decidir` — aqui
    vai só o **recorte grosso**, para o workflow não carregar a base inteira a
    cada dia. Duplicar o filtro aqui e lá seria duas regras que divergem.
    """
    from .reports.grade import slot_do_dia
    dia = _dt.date.fromisoformat(hoje) if hoje else _dt.date.today()
    slot = slot_do_dia(dia)

    rows = db.execute(text("""
        -- Sem JOIN em `clients`: quem nunca virou cliente é justamente o
        -- público do nurture, e um JOIN os apagaria da fila. O filtro de
        -- teste do cliente, quando existir, é aplicado por EXISTS.
        SELECT l.id
          FROM saas.leads l
         WHERE l.status IN ('contacted','qualified')
           AND l.deleted_at IS NULL
           AND COALESCE(l.is_test, FALSE) = FALSE
           AND COALESCE(l.metadata->>'marketing_optin', 'true') = 'true'
           AND (l.last_activity_at IS NULL
                OR l.last_activity_at >= NOW() - INTERVAL '180 days')
           AND NOT EXISTS (SELECT 1 FROM saas.clients c
                            WHERE lower(c.email) = lower(l.email)
                              AND c.deleted_at IS NULL
                              AND COALESCE(c.is_test, FALSE) = TRUE)
    """)).scalars().all()

    return {"hoje": dia.isoformat(),
            "slot": slot.tipo if slot else None,
            "lead_ids": [str(r) for r in rows],
            "total": len(rows)}


@router.get("/api/v1/admin/crm/conteudo/orfaos",
            summary="Passos presos em in_progress por worker que morreu")
def listar_orfaos(minutos: int = Query(JANELA_CLAIM_MINUTOS, ge=1, le=1440),
                  db: Session = Depends(get_saas_db)) -> dict:
    """Varredura de passos órfãos — **observabilidade, não limpeza**.

    Um passo em `in_progress` mais velho que a janela significa que o worker
    morreu entre reservar e confirmar. Ele **se recupera sozinho**: `_reservar`
    só recusa o claim quando `status = 'sent'` ou o claim tem menos de 15 min,
    e `etapas_enviadas` só conta `sent` — então o passo volta a ser elegível e é
    reenviado no próximo disparo.

    Por isso este endpoint **não** reseta nada. Resetar pareceria jeito de
    consertar, mas só mudaria o mesmo estado que o reclaim já resolve, e
    esconderia o sintoma que importa: se há passo preso, há workflow quebrado
    entre a reserva e a confirmação, e alguém precisa saber.

    Reenvio não duplica e-mail: a `idempotency_key` é `crm:{step}:{lead_id}`,
    determinística, e o MessageDispatcher devolve `duplicate` sem reenfileirar.
    """
    rows = db.execute(text("""
        SELECT n.lead_id, lower(l.email) AS email, n.step, n.claimed_at,
               n.claimed_by, n.attempts, n.error,
               EXTRACT(MINUTE FROM (now() - n.claimed_at))::int AS minutos,
               l.status AS lead_status
          FROM saas.nurture_state n
          JOIN saas.leads l ON l.id = n.lead_id AND l.deleted_at IS NULL
         WHERE n.status = 'in_progress'
           AND n.claimed_at < now() - make_interval(mins => :minutos)
         ORDER BY n.claimed_at
    """), {"minutos": minutos}).mappings().all()

    orfaos = [{
        "lead_id": str(r["lead_id"]), "email": r["email"], "step": r["step"],
        "lead_status": r["lead_status"], "minutos": r["minutos"],
        "attempts": r["attempts"], "claimed_by": r["claimed_by"],
        "erro": r["error"],
        "recuperavel": r["lead_status"] in ("contacted", "qualified"),
    } for r in rows]

    # Lead de teste não é perda real — separar para o número não assustar.
    return {
        "janela_minutos": minutos,
        "total": len(orfaos),
        "recuperaveis": sum(1 for o in orfaos if o["recuperavel"]),
        "orfaos": orfaos,
        "nota": ("Nada a fazer: o reclaim de 15 min reenvia sozinho e o MD "
                 "deduplica pela idempotency_key. Se aparecer aqui repetidamente, "
                 "o workflow está falhando entre reservar e confirmar."),
    }


@router.post("/api/v1/admin/crm/conteudo/decidir",
             summary="Decide e reserva o conteúdo de um lead")
def decidir_conteudo(
    lead_ids: list[str] = Query(..., description="IDs dos leads"),
    hoje: Optional[str] = Query(None, description="AAAA-MM-DD (default: hoje)"),
    db: Session = Depends(get_saas_db),
) -> dict:
    """Devolve o que deve ser enviado hoje, um item por lead.

    Reservar aqui (e não no workflow) é o que torna dois workers seguros: o
    `INSERT ... ON CONFLICT` decide quem manda, sem coordenamento.
    """
    dia = (_dt.date.fromisoformat(hoje) if hoje else _dt.date.today())
    registro.limpar_cache()
    # O cache de recuperação é por **requisição**, não por processo. Cacheado no
    # módulo, o primeiro cálculo de um lead congelava para sempre: o consumo
    # parava de avançar, e o lead nunca mais cruzava o marco de 30 ou 45 dias.
    # O roteiro decide vários leads numa chamada, e é isso que o cache evita
    # repetir — não a próxima requisição.
    _RECUP.clear()

    ultima_comp = db.execute(text(SQL_ULTIMA_COMPETENCIA)).scalar()

    ctx_atual: list = [None]

    def _roteiro():
        return Roteiro(
            montar_relatorio=lambda c: registro.montar(c, ctx_atual[0], ultima_comp),
            houve_novidade=lambda: _houve_novidade(db, ultima_comp),
            montar_artigo=_montar_artigo,
            montar_winback=_montar_winback,
            montar_promo=_montar_promo,
        )

    decisoes = []
    for lead_id in lead_ids:
        obtido = _contexto_lead(db, lead_id)
        if obtido is None:
            decisoes.append({"lead_id": lead_id, "enviar": False,
                             "motivo": "lead inexistente"})
            continue
        ctx, _slugs_vistos = obtido
        ctx_atual[0] = ctx
        estado = _estado(db, lead_id, ctx)
        dec = _roteiro().decidir(ctx, estado, dia)
        if not dec.enviar or dec.relatorio is None:
            decisoes.append({"lead_id": lead_id, "enviar": False,
                             "motivo": dec.motivo})
            continue

        reservado = _reservar(db, ctx.lead_id,
                               dec.relatorio.chave if isinstance(dec.relatorio, Relatorio)
                               else dec.relatorio["chave"],
                               _template_do_slot(dec.slot))
        if not reservado:
            decisoes.append({"lead_id": lead_id, "enviar": False,
                             "motivo": "passo já reservado por outro worker"})
            continue

        rel = dec.relatorio
        chave = rel.chave if isinstance(rel, Relatorio) else rel["chave"]
        titulo = rel.titulo if isinstance(rel, Relatorio) else rel["titulo"]
        html = _html(rel, ctx)
        ass = (rel.assinatura() if isinstance(rel, Relatorio)
               else f"kb:{chave}")
        envelope = _envelope(dec.slot, rel, titulo, html, ctx)
        decisoes.append({
            "lead_id": lead_id, "enviar": True, "slot": dec.slot,
            "step": reservado["step"],
            "template_id": envelope["template_id"],
            "topic": envelope["topic"],
            "idempotency_key": f"crm:{reservado['step']}:{lead_id}",
            "recipient": ctx.email,
            "assunto": envelope["assunto"],
            "ass": ass, "titulo": titulo, "corpo_html": html,
            "vars": envelope["vars"],
        })
    return {"hoje": dia.isoformat(), "decisoes": decisoes}


def _montar_artigo(ctx: Contexto) -> Optional[dict]:
    """Próximo artigo da trilha de KB, como um "relatório" do slot de artigo.

    Reaproveita `kb_sequence.selecionar_artigo` — a mesma função que a trilha de
    artigo usa, com a mesma ordem por nível e o mesmo cursor. O roteiro só
    precisa de algo com `chave`, `titulo` e `assinatura()`, e um artigo da KB
    satisfaz os três.
    """
    if ctx is None:
        return None
    try:
        from .kb_sequence import carregar_catalogo, selecionar_artigo
        catalogo = carregar_catalogo()
        vistos = ctx.etapas_enviadas
        art = selecionar_artigo(catalogo, persona=ctx.persona,
                                ja_enviados={k for k in vistos if k.startswith("kb_")})
        if art is None:
            return None
        return {
            "chave": art["slug"], "titulo": art["title"],
            "descricao": art.get("description") or "",
            "url": art.get("url") or f"https://mundoaec.com/kb/{art['slug']}/",
            "nivel": art.get("nivel"),
        }
    except Exception as exc:
        logger.warning("Trilha de artigo indisponível: %s", exc)
        return None


def _houve_novidade(db: Session, ultima: Optional[str]) -> bool:
    """A competência do SINAPI avançou desde o último anúncio?

    É o que decide se o relatório 9 — o único que depende de novidade — sai.
    Base de construção civil não muda na semana: sem esta checagem, o lead
    receberia "atualizado em agosto" todas as semanas e aprenderia a ignorar
    o e-mail.
    """
    return _competencia_atual() != ultima


def _competencia_atual() -> Optional[str]:
    try:
        from .reports.fontes_sinapi import coletar_base
        base = coletar_base()
        return (base or {}).get("competencia")
    except Exception:
        return None


# Consumo: uso da API e leitura do portal. O `min` dos dois é o que vale —
# atividade em qualquer canal significa lead ativo (decisão do usuário).
SQL_CONSUMO = """
    SELECT EXTRACT(DAY FROM (now() - MAX(u.requested_at)))::int AS dias_api
      FROM saas.usage_logs u
     WHERE u.client_id IN (SELECT c.id FROM saas.clients c
                           WHERE lower(c.email) = lower(:email)
                             AND c.deleted_at IS NULL)
"""
SQL_CONSUMO_PORTAL = """
    SELECT EXTRACT(DAY FROM (now() - GREATEST(
             COALESCE(l.last_activity_at, l.created_at), l.created_at)))::int
      FROM saas.leads l
     WHERE lower(l.email) = lower(:email) AND l.deleted_at IS NULL
"""

# Login no app — o sinal **canônico**. Login não é chamada de API: é o ato
# de abrir o produto. Quem paga assinante e só navega (sem integrador, sem
# script) tem `usage_logs` vazio e aparecia como inativo, o que fazia o
# winback falar com quem estava usando.
#
# Lê `client_events` (gravado pelo `portal/me`), **não** `leads.last_activity_at`
# — que é a mesma coluna que o portal escreve pela ponte de formulário. Ler
# os dois da mesma fonte os tornaria idênticos e a cascata um no-op, que foi
# exatamente o defeito medido antes de existir o evento de login.
SQL_CONSUMO_APP = """
    SELECT EXTRACT(DAY FROM (now() - MAX(e.occurred_at)))::int AS dias_app
      FROM saas.client_events e
      JOIN saas.clients c ON c.id = e.client_id
     WHERE e.event_type = :evento
       AND lower(c.email) = lower(:email)
       AND c.deleted_at IS NULL
"""


def _contexto_recuperacao(db: Session, ctx: Contexto) -> ContextoRecuperacao:
    """Monta o contexto de recuperação a partir do banco.

    `dias_sem_consumo_portal` usa `last_activity_at` da **tabela de leads**,
    que o portal alimenta via captura e a ponte via envio. É proxy de leitura
    do portal; não existe evento de pageview no banco, e inventar um seria
   Persistir páginas vistas de todo visitante sem necessidade.
    """
    api = db.execute(text(SQL_CONSUMO), {"email": ctx.email}).scalar()
    portal = db.execute(text(SQL_CONSUMO_PORTAL), {"email": ctx.email}).scalar()
    app = db.execute(text(SQL_CONSUMO_APP),
                       {"email": ctx.email,
                        "evento": EVENTO_LOGIN_APP}).scalar()
    promo = db.execute(text("""
        SELECT EXTRACT(DAY FROM (now() - MAX(sent_at)))::int
          FROM saas.nurture_state
         WHERE lead_id = :id AND step = 'promo' AND status = 'sent'
    """), {"id": ctx.lead_id}).scalar()

    pagante = db.execute(text("""
        SELECT EXISTS (SELECT 1 FROM saas.subscriptions s
                         JOIN saas.clients c ON c.id = s.client_id
                        WHERE lower(c.email) = lower(:email)
                          AND s.status = 'active' AND s.deleted_at IS NULL
                          AND COALESCE(c.is_test, FALSE) = FALSE)
    """), {"email": ctx.email}).scalar()

    return ContextoRecuperacao(
        lead_id=ctx.lead_id, email=ctx.email, eh_cliente_pagante=bool(pagante),
        dias_sem_consumo_api=int(api) if api is not None else None,
        dias_sem_consumo_portal=int(portal) if portal is not None else None,
        dias_sem_consumo_app=int(app) if app is not None else None,
        etapas_enviadas=ctx.etapas_enviadas,
        consentimento=ctx.consentimento_marketing,
        dias_sem_promocao=int(promo) if promo is not None else None,
    )


def _texto_recuperacao(step: str, cr, ctx: Contexto) -> str:
    """Descrição do passo, montada do número — não do modelo."""
    dias = cr.dias_sem_consumo
    if step == "winback_30d":
        return (f"Faz {int(dias) if dias is not None else '?'} dias que você não "
                "abre as ferramentas. O acesso continua pronto — e a base de "
                "conhecimento fica aberta.")
    if step == "winback_45d":
        return ("Faz {d} dias que você não volta. Não é cobrança: é só uma "
                "conta de que a ferramenta continua aqui se fizer sentido.").format(
                    d=int(dias) if dias is not None else "?")
    return "O que há de novo nas ferramentas do ecossistema neste mês."


# Estado de recuperação por lead, montado uma vez por requisição. Sem cache,
# cada lead abriria a própria sessão — e o `decidir` roda sobre vários.
_RECUP: dict = {}


def _montar_winback(ctx: Contexto) -> Optional[dict]:
    """Slot de recuperação (4ª-feira).

    `None` quando este lead não é elegível. A elegibilidade é por **lead**,
    não global: o roteiro decide um por vez, e só quem tem marco pendente
    ocupa a vaga.
    """
    cr = _RECUP.get(ctx.lead_id)
    if cr is None:
        with SaasSessionLocal() as db:
            cr = _contexto_recuperacao(db, ctx)
        _RECUP[ctx.lead_id] = cr
    step = decidir_winback(cr)
    if step is None:
        return None
    return _registro_recuperacao(step, cr, ctx)


def _montar_promo(ctx: Contexto) -> Optional[dict]:
    """Slot de promoção (2ª/6ª). Só não-pagante, espaçada."""
    cr = _RECUP.get(ctx.lead_id)
    if cr is None:
        with SaasSessionLocal() as db:
            cr = _contexto_recuperacao(db, ctx)
        _RECUP[ctx.lead_id] = cr
    step = decidir_promo(cr)
    if step is None:
        return None
    return _registro_recuperacao(step, cr, ctx)


def _registro_recuperacao(step: str, cr, ctx: Contexto) -> dict:
    """Formato comum ao roteiro: `chave`, `titulo`, `descricao`, `url`.

    `chave` é o passo — vira `nurture_state.step`, e é o `UNIQUE (lead_id,
    step)` que impede reenviar a mesma etapa de recuperação.
    """
    titulo = ("Voltamos a falar com você" if step.startswith("winback")
              else "O que há de novo no ecossistema")
    return {
        "chave": step, "titulo": titulo,
        "descricao": _texto_recuperacao(step, cr, ctx),
        "url": TOOLS_URL,
        "nivel": 0,
    }


def _estado(db: Session, lead_id: str, ctx: Contexto) -> EstadoSemana:
    """Conta o que já saiu nesta semana e há quantos dias."""
    semana = db.execute(text("""
        SELECT count(*) AS n FROM saas.nurture_state
         WHERE lead_id = :id AND status = 'sent'
           AND sent_at >= date_trunc('week', now())
           AND step NOT IN ('d3', 'd7')
    """), {"id": lead_id}).scalar() or 0

    dias = db.execute(text("""
        SELECT MIN(EXTRACT(DAY FROM (now() - sent_at)))::int FROM saas.nurture_state
         WHERE lead_id = :id AND status = 'sent'
           AND step NOT IN ('d3', 'd7')
    """), {"id": lead_id}).scalar()
    return EstadoSemana(enviados_esta_semana=int(semana),
                        dias_ate_slot={"enriquecimento": int(dias) - 1
                                               if dias is not None else None})


def _reservar(db: Session, lead_id: str, chave: str, tpl: str) -> Optional[dict]:
    """Claim atômico. `None` quando outro worker já reservou."""
    row = db.execute(text("""
        INSERT INTO saas.nurture_state
            (lead_id, step, template_id, status, claimed_at, claimed_by, attempts)
        VALUES (:lead, :step, :tpl, 'in_progress', now(), 'crm-conteudo', 1)
        ON CONFLICT (lead_id, step) DO UPDATE
            -- `template_id` também é atualizado, não só o status. O mapeamento
            -- slot→template mudou (o `artigo` saiu de `66666666` para
            -- `f4444444`), e o ON CONFLICT que não tocava nessa coluna deixava
            -- a linha asserting que o artigo tinha sido enviado como
            -- "boas-vindas a lead". Não afeta o envio — a OS usa o template do
            -- `_envelope` — mas a tabela passa a mentir sobre o histórico.
            SET status = 'in_progress', claimed_at = now(),
                template_id = EXCLUDED.template_id,
                attempts = saas.nurture_state.attempts + 1, updated_at = now()
         WHERE saas.nurture_state.status <> 'sent'
           AND (saas.nurture_state.claimed_at IS NULL
                OR saas.nurture_state.claimed_at
                   < now() - make_interval(mins => :janela))
        RETURNING step
    """), {"lead": lead_id, "step": chave, "tpl": tpl,
           "janela": JANELA_CLAIM_MINUTOS}
    ).scalar()
    # Commit aqui: a sessão da requisição é descartada no fim, e sem isto a
    # reserva vive só em memória — a próxima chamada devolveria `enviar: true`
    # de novo e dois workers duplicariam o e-mail.
    db.commit()
    return {"step": row} if row else None


def _template_do_slot(slot) -> str:
    """Template do slot — e só dele.

    Fechado de propósito: um slot novo obriga a decidir o template aqui e a
    declará-lo no `registry.yaml`, em vez de cair num ramo por acaso do tipo
    do objeto. O teste `test_email_funnel_slots.py` compara os dois lados.
    """
    if slot == "enriquecimento":
        return TEMPLATE_RELATORIO
    if slot == "artigo":
        return TEMPLATE_ARTIGO
    if slot == "winback":
        return TEMPLATE_REENGAGEMENT
    if slot == "promo":
        return TEMPLATE_PROMO
    # Falhar alto é o que queremos: um slot desconhecido não pode mandar
    # e-mail errado em silêncio — e `/decidir` retornando 500 não envia nada.
    raise ValueError(f"slot sem template definido: {slot!r}")


def _metricas_planas(rel: Relatorio) -> list:
    """Tabela numérica do relatório, achata — é ela a fonte da verdade.

    Todos os 9 relatórios do catálogo construem um único `Bloco`, então
    achat aqui não perde nada; achata sempre, porque um segundo bloco no
    futuro não pode sumir do e-mail. O gráfico é o reforço e o Gmail/Outlook
    removem `<svg>` — sem a tabela o e-mail sairia sem nenhum número.
    """
    return [{"rotulo": m.rotulo, "valor": m.valor,
             "detalhe": m.detalhe or "", "variacao": m.variacao or "",
             "destaque": bool(m.destaque)}
            for b in rel.blocos for m in b.metricas]


def _envelope(slot: str, rel, titulo: str, html: str,
              ctx: Contexto) -> dict:
    """Template, tópico, assunto e variáveis — decididos pelo **slot**.

    Antes isso vinha de `isinstance(rel, Relatorio)`, que só separa relatório
    de artigo. Recuperação e promoção também são dicts, então as duas caíam no
    ramo do artigo e saíam como "Knowledge Base" com `article_*` — sem erro,
    sem log, só um e-mail que não é o que ninguém desenhou.

    O mesmo buraco, do lado contrário: o **artigo** foi parar no
    `gateway_lead_welcome`, que declara `lead_name, portal_url, tools_url` e
    não tem `article_*`. O href `{{ portal_url }}/app/sinapi` saía relativo e
    o artigo não era enviado — verificado em 03/10.

    Cada template recebe **exatamente** as variáveis que o `registry.yaml`
    declara para ele; o resto é o motivo de existirem `topic` e `vars`
    separados. Sobra esconde drift, falta quebra o render.
    """
    template = _template_do_slot(slot)

    if slot == "winback":
        return {
            "template_id": template,
            "topic": "gateway.reengagement",
            "assunto": f"{ctx.nome}, seu acesso continua ativo",
            "vars": {
                "lead_name": ctx.nome,
                "desconto": WINBACK_DESCONTO,
                "cupom": WINBACK_CUPOM,
                "portal_url": PORTAL_URL,
                "agenda_url": AGENDA_URL,
            },
        }

    if slot == "promo":
        competencia, destaque = registro.panorama_incc()
        return {
            "template_id": template,
            "topic": "gateway.update_incc",
            "assunto": (f"Panorama do INCC — {competencia}" if competencia
                        else "O que há de novo nas ferramentas"),
            "vars": {
                "lead_name": ctx.nome,
                "competencia": competencia,
                "destaque": destaque,
                "portal_url": PORTAL_URL,
                "tools_url": TOOLS_URL,
            },
        }

    if slot == "artigo":
        if not isinstance(rel, dict):
            raise ValueError(f"slot 'artigo' espera dict, veio {type(rel).__name__}")
        return {
            "template_id": template,
            "topic": "gateway.kb_digest",
            "assunto": f"{titulo} — Knowledge Base",
            "vars": {"lead_name": ctx.nome, "article_title": titulo,
                     "article_description": rel.get("descricao", ""),
                     "article_url": rel.get("url", ""),
                     "tools_url": TOOLS_URL},
        }

    # slot == "enriquecimento" — o relatório semanal.
    if not isinstance(rel, Relatorio):
        raise ValueError(
            f"slot 'enriquecimento' espera Relatorio, veio {type(rel).__name__}")
    return {
        "template_id": template,
        "topic": "gateway.report_weekly",
        # O `subject_liquid` do registry (`{{ titulo }}`) tem precedência no
        # `SendOS`; este fica como fallback para o caso de o template ir sem
        # assunto. Sem emoji e sem ser extenso — decisão registrada.
        "assunto": titulo,
        "vars": {
            "lead_name": ctx.nome,
            "titulo": titulo,
            "resumo": rel.resumo or "",
            "texto": next((b.texto for b in rel.blocos if b.texto), ""),
            "nota": next((b.nota for b in rel.blocos if b.nota), ""),
            "metricas": _metricas_planas(rel),
            "grafico_svg": svg_do_relatorio(rel),
            "serie_rotulo": rel.series[0].rotulo if rel.series else "",
            "rodape": rel.rodape or "",
            "link_relatorio": _url_do_relatorio(rel),
            "tools_url": TOOLS_URL,
        },
    }


def _html(rel, ctx: Contexto) -> str:
    """HTML do e-mail.

    `Relatorio` (enriquecimento) e o dict do artigo seguem caminhos
    diferentes: o primeiro usa o renderizador com nota do INCC e link primário;
    o artigo é uma mensagem própria da trilha de KB.
    """
    if not isinstance(rel, Relatorio):
        return _html_artigo(rel, ctx)

    nota = None
    try:
        from .reports.fontes import coletar_incc
        nota = nota_incc_atual(coletar_incc())
    except Exception:
        nota = None
    return renderizar(rel, nome_destinatario=ctx.nome, nota=nota,
                      link_primario=_url_do_relatorio(rel))


def _html_artigo(art: dict, ctx: Contexto) -> str:
    """HTML do e-mail de artigo — reaproveita o bloco de destaque do
    renderizador para manter o visual da família consistente."""
    from .reports.model import Bloco, Metrica, Relatorio as _R
    fake = _R(
        chave=art["chave"], titulo=art["titulo"],
        resumo=(art.get("descricao") or "")[:280],
        blocos=[Bloco(metricas=[Metrica("Tempo de leitura", "~12 min"),
                               Metrica("Origem", "Base de Conhecimento")])],
        rodape=f"Artigo da Base de Conhecimento · {art.get('nivel', 1)}",
    )
    return renderizar(fake, nome_destinatario=ctx.nome,
                      link_primario=art.get("url"),
                      texto_link="Ler o artigo completo")


# Destino do CTA do relatório por família de índice — só destinos que o gate
# de URL confirma com 200 (`/tools/incc`, `/tools/cub`, `/app/sinapi`,
# `/tools`). O relatório não tem página própria: **ele é o e-mail**.
_URL_CTA_POR_FAMILIA = (
    ("incc_", f"{TOOLS_URL}/incc"),
    ("cub_", f"{TOOLS_URL}/cub"),
    ("sinapi_", f"{PORTAL_URL}/app/sinapi"),
)


def _url_do_relatorio(rel: Relatorio) -> str:
    """Destino do CTA do relatório — um destino que existe.

    Antes era `https://mundoaec.com/kb/{rel.chave}`. As 9 chaves da trilha
    (`incc_leitura_mes`, `sinapi_competencia`, `cub_dispersao`…) **não são
    slug de KB** — `/kb/` só aceita os 109 artigos do catálogo — e as 9
    davam 404: o botão "Abrir a análise completa" era link morto no e-mail
    de terça, toda semana. Verificado em 03/10.

    `rel.chave` identifica o *relatório*, não uma página. Como o relatório
    não tem página, o CTA leva à ferramenta do índice que ele mede, com
    fallback para o índice de ferramentas. Os quatro destinos são os
    únicos com 200 confirmado.
    """
    chave = (rel.chave or "").lower()
    for familia, destino in _URL_CTA_POR_FAMILIA:
        if chave.startswith(familia):
            return destino
    return TOOLS_URL


@router.post("/api/v1/admin/crm/conteudo/{lead_id}/confirmar",
             summary="Marca o conteúdo como enviado")
def confirmar(lead_id: str, step: str = Query(...),
              assinatura: Optional[str] = Query(None),
              db: Session = Depends(get_saas_db)) -> dict:
    """Fecha o passo: sem isso, o roteiro continua vendo como pendente e a
    próxima decisão devolve o mesmo relatório."""
    db.execute(text("""
        UPDATE saas.nurture_state
           SET status = 'sent', sent_at = now(),
               metadata = metadata || CAST(:ass AS jsonb), updated_at = now()
         WHERE lead_id = :lead AND step = :step AND status = 'in_progress'
    """), {"lead": lead_id, "step": step,
           "ass": _json({"assinatura": assinatura})})
    db.commit()
    return {"ok": True, "lead_id": lead_id, "step": step}


def _json(obj: dict) -> str:
    import json
    return json.dumps(obj, ensure_ascii=False)


__all__ = ["router"]
