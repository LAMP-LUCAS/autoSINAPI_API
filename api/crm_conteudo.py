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
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from .admin_auth import verify_admin_token
from .database import get_saas_db
from .reports import registro
from .reports.fontes import nota_incc_atual
from .reports.model import Categoria, Contexto, Relatorio
from .reports.roteiro import EstadoSemana, Roteiro
from .reports.render import assunto_de, renderizar

logger = logging.getLogger("autosinapi.crm.conteudo")
router = APIRouter(tags=["Admin", "CRM"],
                   dependencies=[Depends(verify_admin_token)])

TEMPLATE_ID = "f4444444-4444-4444-4444-444444444444"   # gateway_kb_digest
TEMPLATE_ARTIGO = "66666666-6666-6666-6666-666666666666"  # gateway_lead_welcome
UNSUBSCRIBE = "https://autosinapi.mundoaec.com/preferencias"
TOOLS_URL = "https://mundoaec.com/ferramentas"

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

    ultima_comp = db.execute(text(SQL_ULTIMA_COMPETENCIA)).scalar()

    ctx_atual: list = [None]

    def _roteiro():
        return Roteiro(
            montar_relatorio=lambda c: registro.montar(c, ctx_atual[0], ultima_comp),
            houve_novidade=lambda: _houve_novidade(db, ultima_comp),
            montar_artigo=_montar_artigo,
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
                               TEMPLATE_ID if isinstance(dec.relatorio, Relatorio)
                               else TEMPLATE_ARTIGO)
        if not reservado:
            decisoes.append({"lead_id": lead_id, "enviar": False,
                             "motivo": "passo já reservado por outro worker"})
            continue

        rel = dec.relatorio
        chave = rel.chave if isinstance(rel, Relatorio) else rel["chave"]
        titulo = rel.titulo if isinstance(rel, Relatorio) else rel["titulo"]
        html = _html(rel, ctx)
        descricao = (rel.blocos[0].texto or "" if isinstance(rel, Relatorio)
                     else rel.get("descricao", ""))
        url = (_url_do_relatorio(rel) if isinstance(rel, Relatorio)
               else rel.get("url", ""))
        ass = (rel.assinatura() if isinstance(rel, Relatorio)
               else f"kb:{chave}")
        decisoes.append({
            "lead_id": lead_id, "enviar": True, "slot": dec.slot,
            "step": reservado["step"],
            "template_id": (TEMPLATE_ID if isinstance(rel, Relatorio)
                            else TEMPLATE_ARTIGO),
            "topic": ("gateway.kb_digest" if isinstance(rel, Relatorio)
                      else "gateway.lead_welcome"),
            "idempotency_key": f"crm:{reservado['step']}:{lead_id}",
            "recipient": ctx.email,
            "assunto": (assunto_de(rel) if isinstance(rel, Relatorio)
                        else f"{titulo} — Knowledge Base"),
            "ass": ass, "titulo": titulo, "corpo_html": html,
            "vars": {"lead_name": ctx.nome, "article_title": titulo,
                     "article_description": descricao, "article_url": url,
                     "tools_url": TOOLS_URL, "unsubscribe_url": UNSUBSCRIBE},
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
            SET status = 'in_progress', claimed_at = now(), attempts =
                saas.nurture_state.attempts + 1, updated_at = now()
         WHERE saas.nurture_state.status <> 'sent'
           AND (saas.nurture_state.claimed_at IS NULL
                OR saas.nurture_state.claimed_at < now() - interval '15 minutes')
        RETURNING step
    """), {"lead": lead_id, "step": chave, "tpl": tpl}
    ).scalar()
    # Commit aqui: a sessão da requisição é descartada no fim, e sem isto a
    # reserva vive só em memória — a próxima chamada devolveria `enviar: true`
    # de novo e dois workers duplicariam o e-mail.
    db.commit()
    return {"step": row} if row else None


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


def _url_do_relatorio(rel: Relatorio) -> str:
    return f"https://mundoaec.com/kb/{rel.chave}"


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
