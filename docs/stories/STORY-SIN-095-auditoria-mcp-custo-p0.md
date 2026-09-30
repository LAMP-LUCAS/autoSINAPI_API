# STORY-SIN-095 — Auditoria MCP de Custo: correções P0 (tendências, busca, BOM)

> Relacionado: ADR-004, ADR-005, ADR-008, SPEC-RULE-search-pipeline-graceful-degradation.
> Origem: auditoria externa 2026-09-29 (`PLAN-auditoria-mcp-custo-p0.md` da casa;
> auditoria integral em `docs/audits/autosinapi/2026-09-29_MCP-CUSTO-CONSTRUCAO-AUDIT.md`).
> Status: **P0 concluído (2026-09-29) · P1 §3.4/§3.5/§3.6 concluídos (2026-09-30)** —
> gate da casa completo: 12 OK / 4 RED (restam §3.8 + §4.3 + §5.3 + §5.4).

## Objetivo

Eliminarmos os defeitos **S1/P0** da auditoria que vivem nesta API — todos de
**erro numérico silencioso** (número plausível, sem sinal de erro) — com TDD:
cada fix tem primeiro uma asserção RED reproduzida por request real.

## Causa-raiz provada por leitura (a confirmar no RED)

1. **§3.7 tendências zeradas** — `_compute_variacao` lê `item['valor']`
   (`crud.py` L699-721), mas `get_tendencias` seleciona `AVG(...) as preco_medio`
   (L926) → `valor=0` em todos os pontos → `variacao_mensal=0.0` e
   `variacao_pct=None` (prev=0). Sintoma idêntico ao auditado.
2. **§3.2 score constante** — `score` correlaciona com o tipo do item, não com
   relevância (2,2 composição / 1,1 insumo), violando SPEC-RULE
   (score 0..1 por prefixo/trigrama).
3. **§3.3 vetorial indisponível** — `sinapi_search(vector="on")` dá timeout do
   gateway; SPEC-RULE exige degradação graciosa com `meta.degraded`, não timeout.
4. **§3.1 BOM** — ADR-008 já decidiu a semântica (pais+filhos na mesma lista;
   somar linear superconta); o consumidor MCP não recebe essa semântica embutida.

## Aceite (P0) — GREEN 2026-09-29 (gate `--p0` 7/7)

- [x] §3.7: `get_tendencias(uf=SP, item, 12m)` retorna `variacao_mensal` ≠ 0.0
      em todo ponto após o primeiro e `variacao_pct` calculado; 1º ponto `null`.
      Conferência: preço 520,26 → 511,06 implica variação negativa real.
      → GREEN: 11 pontos, var ≠ 0 em 6, pct não-nulo (`99b7b85`).
- [x] §3.2: `sinapi_search("cimento")` ordena por relevância — "CIMENTO PORTLAND"
      (ou equivalente com o token exato) antes de item sem o token; `score` ∈ [0,1]
      derivado de similaridade, nunca constante por tipo.
      → GREEN: top1 inicia com o token, 2/10 scores distintos (`5026f17`).
- [x] §3.3: `vector="on"` **não propaga timeout ao cliente** — degrada para
      trigram/ILIKE com camada registrada como degradada (SPEC-RULE §4:
      nunca 5xx/timeout por falha de camada opcional), e `health` expõe o status
      do índice vetorial. → GREEN: 6867 ms, `degraded=['vector']` (`5d5579a`).
- [x] §3.1: payload de `get_composicao_bom` declara a semântica de nível e entrega
      total reconciliável (Σ folhas/nível 1 ≈ `custo_total`, ±0,5%) sem exigir que
      o consumidor adivinhe — consistente com ADR-008.
      → GREEN: guia presente ≈ oficial, Σnivel1 646,82 × oficial 646,8 (mcp `9c5a750`).
- [x] Suíte completa verde; guarda da casa verde; nenhum breaking change de contrato
      legado (SPEC-RULE §2).

## P1 — §3.4 / §3.5 / §3.6 (GREEN 2026-09-30)

RED: `tests/test_p1_sinalizacao_composicao.py` (6 RED comportamentais) +
gate da casa `verify_mcp_audit_claims.py`. Causas-raiz provadas:

- [x] **§3.4 `custo_total=0.0` sem sinal** — `custos_composicoes_mensal` tem
      2,68 M linhas com `custo_total=0` (sem preço publicado para UF/data);
      a resposta não distinguia "custo zero" de "sem preço".
      Fix: `preco_disponivel: bool` em `get_composicao_by_codigo` + schema
      `Composicao` (adição). GREEN ao vivo: `custo_total=0.0 preco_disponivel=False`.
- [x] **§3.5 `total_hora_homem=0.0` para horista** — `get_composicao_man_hours`
      só executava a query recursiva de COMPOSIÇÕES; o código 1213
      (CARPINTEIRO… HORISTA, unidade `H`) é INSUMO → 0.0 silencioso.
      Fix: fallback — insumo com unidade `H` responde `1.0` HH
      (o insumo horista É 1 hora-homem). GREEN ao vivo: `total_hora_homem=1.0`.
- [x] **§3.6 `percentual_mo=NULL`** — coluna da migration 005 é NULL em
      **100%** das 13,7 M linhas (o ETL nunca gravou).
      Fix: fallback on-read calculando %MO do BOM (mesmo split de
      `get_composicao_produtividade`), com prioridade para valor armazenado;
      sem preço → continua `null`. GREEN ao vivo: `percentual_mo=4.0` (0<x<100).
- [ ] **§3.8 lacuna SINAPI 2026-01/2026-02** → reprocesso com backup
      (próximo passo; único P1 restante deste repo).

Suíte: `301 passed` + 9 novos; 2 falhas `test_post_schemas` **pré-existentes**
(falam com Redis/Postgres reais indisponíveis no host — idênticas com stash).

## Tasks (TDD) — P0 concluídos

- [x] Fase 0: RED comportamental via `automation/scripts/verify_mcp_docs_facts.py`
      irmão `verify_mcp_audit_claims.py` (request real no gateway; commit por achado).
- [x] §3.7: teste de unidade `_compute_variacao` com serie `{preco_medio}` (RED) →
      fix (aceitar chave de valor parametrizada ou mapear `preco_medio→valor` em
      `get_tendencias`) → GREEN.
- [x] §3.2: teste de ranking (token exato > substring > sem token) (RED) → fix em
      `api/crud.py`/`api/search.py` dentro da SPEC-RULE → GREEN.
- [x] §3.3: teste de degradação com timeout do vetor simulado (RED) → `try/except`
      + `meta.degraded` + status em `health` → GREEN.
- [x] §3.1: teste de reconciliação Σnível/folhas × `custo_total` (RED) → payload
      com semântica declarada → GREEN.
- [x] Suítes: `pytest` completo + varredura de segredo antes do push.

## Arquivos

`api/crud.py`, `api/search.py`, `api/main.py`, `api/schemas.py`,
`tests/test_bi_enrichment.py` (+ novos), `docs/stories/STORY-SIN-095-*.md`.

## Fora de escopo (registrado)

- §3.9 · §3.10 → **P2**.
- §3.8 lacuna 2026-01/02 → P1 (reprocesso com backup) — único pendente deste repo.
- Descriptions/notes do MCP wrapper (`autosinapi_mcp`) → plano do repo irmão.
