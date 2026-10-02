"""api/kb_admin.py — ponte entre a trilha de KB e o n8n.

Por que um endpoint e não a lógica no Code node
------------------------------------------------
A regra de seleção (pool por persona, nível, cursor, índice de afinidade) está
em `kb_sequence.py`, testada com pytest. O n8n orquestra; ele **não decide**.

O workflow só faz o que já fazia no nurture v2: buscar, reclamar o passo de
forma atômica, enviar, marcar. A seleção vem daqui — um só dono da regra.

Cadência
--------
1–2 por semana por lead. O passo é `kb_<NN>` e cresce a cada envio; o que
limita a frequência é o `last_kb_sent_at` no lead, respeitado aqui — um lead
que recebeu há 3 dias não recebe mais, mesmo que ainda tenha pool.

Autenticação
------------
Endpoints `admin` (token do painel). O workflow já carrega uma credencial
(do MessageDispatcher); levar a do admin para cá é o mesmo padrão, e a seleção
não é pública — expor "qual o próximo artigo deste lead" para anônimo seria
informação de terceiro.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from .admin_auth import verify_admin_token
from .database import get_saas_db
from .kb_sequence import carregar_catalogo, selecionar_artigo, step_para

logger = logging.getLogger("autosinapi.kb")
router = APIRouter(tags=["Admin", "KB"], dependencies=[Depends(verify_admin_token)])

# Intervalo mínimo entre dois artigos do mesmo lead. 2/semana ≈ 3,5 dias;
# uso 3 dias para tolerar o horário do cron sem deixar virar diário.
_MIN_DIAS_ENTRE_ARTIGOS = 3
# Passos já tentados: teto de segurança para um lead com pool pequeno. Acima
# disso a trilha para em vez de reciclar conteúdo.
_MAX_PASSOS = 200


@router.get("/api/v1/admin/kb/next", summary="Próximo artigo da trilha de um lead")
def proximo_artigo(
    lead_id: str = Query(..., description="UUID do lead em saas.leads"),
    db: Session = Depends(get_saas_db),
) -> dict:
    """Artigo que este lead deve receber agora, ou `{"due": false}`.

    **Não** reserva o passo — a reserva é do workflow (`saas.nurture_state`),
    para que a seleção continue sendo pura e testável. Aqui só há leitura.
    """
    # O cast é sobre o VALOR extraído do jsonb, não sobre a chave:
    # `metadata->>'x'::timestamptz` converte a string "last_kb_sent_at" e
    # quebra. `NULLIF(...,'')` protege o caso de a chave existir vazia.
    lead = db.execute(text("""
        SELECT id, email, name, persona,
               (NOW() - COALESCE(
                   NULLIF(metadata->>'last_kb_sent_at', '')::timestamptz,
                   created_at))::interval AS desde_ultimo
          FROM saas.leads
         WHERE id = :id AND deleted_at IS NULL
    """), {"id": lead_id}).mappings().first()

    if lead is None:
        raise HTTPException(status_code=404, detail="lead nao encontrado")

    # Passos já registrados para este lead — é o cursor. `kb_%` é o prefixo da
    # trilha; d3/d7 do nurture não contam.
    passos = db.execute(text("""
        SELECT step FROM saas.nurture_state
         WHERE lead_id = :id AND step LIKE 'kb\\_%'
    """), {"id": lead_id}).scalars().all()

    if len(passos) >= _MAX_PASSOS:
        return {"due": False, "motivo": "teto de passos atingido",
                "passos": len(passos)}

    # Já enviou este artigo antes? A trilha não repete — o cursor conta os
    # passos, mas o slug é o que garante conteúdo novo.
    # `n.metadata` sem aspas não compila: `metadata` é palavra reservada no
    # Postgres quando é coluna de tabela (aqui é jsonb, mas o parser não
    # distingue). As aspas são obrigatórias.
    slugs_enviados = db.execute(text("""
        SELECT n."metadata"->>'slug' AS slug
          FROM saas.nurture_state n
         WHERE n.lead_id = :id AND n.step LIKE 'kb\\_%'
           AND n."metadata" ? 'slug'
    """), {"id": lead_id}).scalars().all()

    dias = lead["desde_ultimo"].total_seconds() / 86400 if lead["desde_ultimo"] else 999
    if dias < _MIN_DIAS_ENTRE_ARTIGOS:
        return {"due": False,
                "motivo": f"cadencia ({dias:.1f}d < {_MIN_DIAS_ENTRE_ARTIGOS}d)",
                "proximo_dia": _MIN_DIAS_ENTRE_ARTIGOS - dias,
                "passos": len(passos)}

    catalogo = carregar_catalogo()
    artigo = selecionar_artigo(catalogo, persona=lead["persona"],
                               ja_enviados=set(slugs_enviados))
    if artigo is None:
        return {"due": False, "motivo": "pool esgotado", "passos": len(passos)}

    return {
        "due": True,
        "lead_id": str(lead["id"]),
        "recipient": lead["email"],
        "lead_name": lead["name"] or "Lead",
        "persona": lead["persona"],
        "step": step_para(len(passos) + 1),
        "indice": len(passos),
        "article_slug": artigo["slug"],
        "article_title": artigo["title"],
        "article_description": artigo["description"],
        "article_url": artigo["url"],
        "nivel": artigo["nivel"],
    }


@router.get("/api/v1/admin/kb/status", summary="Cobertura e progresso da trilha")
def status_trilha(db: Session = Depends(get_saas_db)) -> dict:
    """Quanto da trilha está em uso e quanto do catálogo está classificado."""
    catalogo = carregar_catalogo()
    artigos = catalogo.get("artigos", [])

    classificados = [a for a in artigos if a["personas"]]
    em_uso = db.execute(text("""
        SELECT count(DISTINCT lead_id) AS leads,
               count(*) AS envios,
               count(*) FILTER (WHERE status = 'sent') AS enviados
          FROM saas.nurture_state
         WHERE step LIKE 'kb\\_%'
    """)).mappings().one() or {}

    return {
        "catalogo": {
            "total": len(artigos),
            "classificados": len(classificados),
            "cobertura_pct": round(100.0 * len(classificados) / len(artigos), 1) if artigos else 0,
            "pool_por_persona": catalogo.get("pool_por_persona", {}),
        },
        "trilha": {
            "leads_com_passo": em_uso.get("leads", 0),
            "passos_registrados": em_uso.get("envios", 0),
            "envios_confirmados": em_uso.get("enviados", 0),
        },
        "cadencia_dias": _MIN_DIAS_ENTRE_ARTIGOS,
        "max_passos_por_lead": _MAX_PASSOS,
        "gerado_em": datetime.now(timezone.utc).isoformat(),
    }
