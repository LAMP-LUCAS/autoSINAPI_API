"""api/kb_sequence.py — escolhe o próximo artigo da trilha de um lead.

A trilha é a parte do nurture que não é cadência de venda: em vez de D+3/D+7,
o lead recebe **conteúdo da Base de Conhecimento** a 1–2 por semana. O
objetivo éiconductor de volta ao portal e, por ele, às ferramentas e ao app.

Por que aqui
------------
Precisa de pool por persona, ordem por nível, cursor sem repetição e desempate
por índice de afinidade. Isso é regra de negócio, e regra de negócio testável
é função pura — dentro do Code node do n8n exigiria o runtime do n8n de pé
para ser testada.

Contrato dos dados
------------------
O catálogo vem de `repos/saas-gateway/emails/kb-catalog.json`, gerado por
`scripts/build_kb_catalog.py` a partir do front-matter da KB do portal.

    personas: [office, builder]   # ORDENADA — índice 0 é a mais afim
    nivel: 1                      # 1=introdução · 2=intermediário · 3=avançado

Hoje **0 de 109** artigos declaram `personas`: o pipeline opera no pool geral
e, quando a classificação entrar, passa a segmentar sem mudança de código.
Ausência de campo é o estado esperado, não erro.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Iterable, Optional

logger = logging.getLogger("autosinapi.kb_sequence")

# Vocabulário fechado (ADR-090). Persona fora daqui não segmenta: vira pool
# geral, para que um valor novo não esvazie a trilha do lead.
VALID_PERSONAS = ("investor", "office", "builder", "developer")

# Onde o catálogo vive. Fora do container o path é relativo ao repo; dentro,
# é montado pelo caller (ver `_catalogo_path`).
_CATALOGO_REL = Path("emails/kb-catalog.json")


def _catalogo_path() -> Path:
    """Resolve o catálogo no container de runtime e no host de teste.

    Inclui a raiz do repo: o container monta `emails/` em `/app`, mas quem
    roda os testes está na raiz — sem os dois caminhos, a seleção cairia no
    "catálogo ausente" e os testes passariam por vazio.
    """
    for candidato in (Path("/app/emails/kb-catalog.json"),
                      _CATALOGO_REL,
                      Path(__file__).resolve().parents[2] / "emails/kb-catalog.json"):
        if candidato.is_file():
            return candidato
    return _CATALOGO_REL


def carregar_catalogo(path: Optional[Path] = None) -> dict:
    """Lê o catálogo e normaliza o que a seleção precisa.

    A normalização aqui (e não na seleção) é o que mantém `selecionar_artigo`
    livre de parsing — e é o que permite trocar a origem do catálogo sem tocar
    na regra.
    """
    alvo = Path(path) if path else _catalogo_path()
    if not alvo.is_file():
        logger.warning("Catálogo da KB ausente (%s): trilha sem artigo", alvo)
        return {"artigos": []}

    try:
        bruto = json.loads(alvo.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        # Catálogo corrompido não pode derrubar a seleção — degrada para vazio.
        logger.error("Catálogo da KB ilegível (%s): %s", alvo, exc)
        return {"artigos": []}

    artigos = []
    for ordem, a in enumerate(bruto.get("artigos", [])):
        if not a.get("slug"):
            continue
        personas = [p for p in (a.get("personas") or []) if p in VALID_PERSONAS]
        try:
            nivel = int(a.get("nivel") or 1)
        except (TypeError, ValueError):
            nivel = 1
        artigos.append({
            "slug": a["slug"],
            "url": a.get("url") or f"https://mundoaec.com/kb/{a['slug']}/",
            "title": a.get("title") or a["slug"],
            "description": a.get("description") or "",
            "category": a.get("category") or "",
            "tags": a.get("tags") or [],
            "personas": personas,
            "nivel": nivel if 1 <= nivel <= 3 else 1,
            "ordem": ordem,   # desempate estável entre artigos equivalentes
        })
    return {"artigos": artigos}


def _pool(catalogo: Iterable[dict], persona: Optional[str], enviados: set[str]) -> list[dict]:
    """Artigos elegíveis: persona (por afinidade) + pool geral, já enviados fora.

    A ordem é: nível 1 primeiro, e dentro do nível a **ordem de declar��ão do
    front-matter**. A lista `personas` do artigo influences o desempate: entre
    dois artigos do mesmo nível, o que tem a persona mais perto do índice 0
    vai antes.
    """
    persona = persona if persona in VALID_PERSONAS else None
    disponiveis = [a for a in catalogo if a["slug"] not in enviados]

    if not disponiveis:
        return []

    def afinidade(a: dict) -> int:
        """Índice da persona na lista do artigo. Sem match: fim da fila.

        Não é um score: é a **posição declarada**. `personas: [office, builder]`
        diz que este artigo é para escritório antes de ser para canteiro.
        """
        if not persona:
            # Lead sem persona (ou persona fora do vocabulário): sem
            # segmentação, todo artigo vale o mesmo. O pool geral não pode
            # ficar atrás de artigo classificado para OUTRA persona — esse
            # artigo foi escrito para outra audience e não é conteúdo
            # seguro para este lead.
            return 0 if not a["personas"] else len(VALID_PERSONAS) + 1
        if not a["personas"]:
            return len(VALID_PERSONAS) + 1   # pool geral depois da segmentada
        try:
            return a["personas"].index(persona)
        except ValueError:
            return len(VALID_PERSONAS)       # persona não listada: último

    return sorted(disponiveis, key=lambda a: (a["nivel"], afinidade(a), a["ordem"]))


def selecionar_artigo(catalogo: dict, persona: Optional[str],
                      ja_enviados: set[str]) -> Optional[dict]:
    """Próximo artigo da trilha, ou `None` se nada estiver disponível.

    Regra do nível: só sobe de nível quando **esgotou** os artigos do nível
    anterior. Sem isso a série começa por EVM e o leitor desiste no primeiro
    e-mail — que é o oposto de "formar o usuário".
    """
    disponiveis = _pool(catalogo.get("artigos", []), persona, ja_enviados)
    if not disponiveis:
        return None

    menor_nivel = min(a["nivel"] for a in disponiveis)
    mesmo_nivel = [a for a in disponiveis if a["nivel"] == menor_nivel]
    return mesmo_nivel[0]


def step_para(indice: int) -> str:
    """Rótulo do passo na `nurture_state` (`kb_01`, `kb_02`, …).

    Sequencial e ordenável — `step` é o que dá idempotência por (lead, passo);
    o `slug` do artigo é o que impede reenvio do mesmo conteúdo.
    """
    return f"kb_{indice:02d}"
