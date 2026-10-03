"""api/links.py — SSOT dos links que todo produtor de e-mail compartilha.

O bloco `links:` do `saas-gateway/emails/registry.yaml` é a *declaração* do
contrato; aqui ficam os *valores* que os produtores runtime usam. São duas
metades da mesma regra — "links centraliza TODOS os links dos templates" e
"produtores runtime leem o .env mestre, mantenha os valores iguais aqui e
lá" — e `saas-gateway/tests/test_producer_contract.py` compara os lados.

Existe como módulo próprio porque a mesma classe de defeito apareceu duas
vezes, e sempre no produtor que ninguém fiscalizava:

* ``crm_conteudo.TOOLS_URL`` valia ``.../ferramentas`` (HTTP 404) enquanto o
  registry dizia ``.../tools`` (HTTP 200);
* ``public_leads`` repetia o literal — com o mesmo path errado — no
  ``gateway_lead_welcome``, que é o **primeiro** e-mail que um lead vê.

Enquanto cada produtor tiver o seu literal, o contrato é promessa. Módulo
único, lido por todos, transforma o desvio em falha de import.
"""

from __future__ import annotations

import os

# Rede de segurança quando o processo sobe sem `.env`. O valor é o do
# registry, nunca um path próprio — é o que o histórico mostra quebra.
LINKS_SSOT = {
    "portal_url": "https://mundoaec.com",
    "tools_url": "https://mundoaec.com/tools",
    "agenda_url": "https://mundoaec.com/contato",
}


def link(chave: str, *vars_env: str) -> str:
    """URL a partir do `.env` mestre, com fallback igual ao da SSOT.

    A ordem de `vars_env` importa: `PORTAL_URL` é override explícito e vem
    antes de `MUNDOAEC_SITE_URL`, seguindo o que `scripts/quota_alert.py`
    (outro produtor) já faz. `MUNDOAEC_PORTAL_URL` fica de fora de propósito:
    ele vale `.../portal`, que não é o `portal_url` do registry.
    """
    for nome in vars_env:
        valor = os.getenv(nome, "").strip()
        if valor:
            return valor
    return LINKS_SSOT[chave]


PORTAL_URL = link("portal_url", "PORTAL_URL", "MUNDOAEC_SITE_URL")
TOOLS_URL = link("tools_url", "TOOLS_URL", "MUNDOAEC_TOOLS_URL")
AGENDA_URL = link("agenda_url", "AGENDA_URL", "MUNDOAEC_AGENDA_URL")

__all__ = ["AGENDA_URL", "LINKS_SSOT", "PORTAL_URL", "TOOLS_URL", "link"]
