# 🚀 autoSINAPI API — Documentação do Core API

Bem-vindo à documentação do **autoSINAPI API**, a API RESTful mínima e open-source (GPLv3) baseada em FastAPI para expor dados, preços, composições e inteligência de negócio (BI) da base SINAPI.

---

## 🗺️ Mapeamento do Bounded Context (DDD)

A API fornece a camada de entrega (Delivery Layer) dos dados processados pelo ETL.

*   **Lógica Core (Domain):** Estrutura de busca textual, inteligência analítica (BOM, ABC, HH, Produtividade).
*   **Portas de Entrada (Inbound Ports):** Endpoints HTTP públicos (ex: `/api/v1/public/insumos`), rotas de BI.
*   **Portas de Saída (Outbound Ports):** Repositório de dados via banco de dados relacional e conexões Redis.

---

## 📂 Índice da Documentação (Template Unificado)

Navegue pelos arquivos da especificação técnica local:

1.  **[Requisitos do Produto (prd.md)](./prd.md):** Especificação funcional da API, histórico de retificações e rastreabilidade de dados.
2.  **[Arquitetura Híbrida MVC-Hexagonal (architecture.md)](./architecture.md):** Divisão de pacotes, controllers (FastAPI), interfaces (Ports) e conexões do banco de dados (Adapters).
3.  **[Regras de Rastreabilidade (data_traceability_rules.md)](./data_traceability_rules.md):** Políticas de inserção (UPSERT), colunas de auditoria obrigatórias e tracking de retificações da Caixa.
4.  **[Decisões de Arquitetura (adrs/)](./adrs/):**
    *   **[ADR 003 — Transição para Programação Assíncrona](./adrs/003-asyncpg-transition.md):** Decisão sobre adoção de drivers `asyncpg` e concorrência massiva.
    *   **[ADR 004 — Busca Textual Otimizada com GIN e Trigram](./adrs/004-trigram-gin-search.md):** Abandono de `ILIKE` simples por busca de similaridade performática. **Implementado.**
    *   **[ADR 005 — Busca Híbrida em Camadas](./adrs/005-hybrid-search-enrichment-layers.md):** Pipeline de 5 camadas com degradação graciosa.
    *   **[ADR 006 — Embeddings Vetoriais Distribuídos](./adrs/006-distributed-vector-embeddings.md):** Tabela `vec_<dims>_<model>` por modelo (pgvector). **Implementado (Fase 4) — bge-m3, 16.731 embeddings.**
    *   **[ADR 007 — Query Expansion Client-First](./adrs/007-query-expansion-client-first.md):** Expansão no browser com fallback server (LLM opcional).

> **EPIC em andamento:** [EPIC-GOOGLE-POWERBI-SINAPI](./epics/EPIC-search-engine-google-powerbi.md) — Motor de busca ("Google") + BI analítico ("PowerBI").
> **Spec-Rule:** [Search Pipeline com Degradação Graciosa](./spec-rules/SPEC-RULE-search-pipeline-graceful-degradation.md).
> **Audit:** [Busca e BI 2026-08-14](./audits/2026-08-14_SEARCH-ENHANCEMENT-AUDIT.md).
> **Auditoria MCP Custo 2026-09-29:** texto integral na casa
> (`SistemaServerLight/docs/audits/autosinapi/2026-09-29_MCP-CUSTO-CONSTRUCAO-AUDIT.md`)
> · Story: [STORY-SIN-095 — correções P0](./stories/STORY-SIN-095-auditoria-mcp-custo-p0.md).
> **Sprint:** [workplans/SPRINT-SEARCH-GOOGLE-POWERBI](./workplans/SPRINT-SEARCH-GOOGLE-POWERBI.md).
4.  **[Agilidade e Histórico (agile/)](./agile/):**
    *   **[Sprint - Enriquecimento de API](./agile/SPRINT_ENRIQUECIMENTO.md)**
    *   **[Sprint - Cronograma de Trabalho (WorkPlan)](./agile/WorkPlan.md)**
5.  **[Loops de Qualidade (loops/)](./loops/):**
    *   **[Audit Report — Plano de Refatoração](./loops/AUDIT_AND_REFACTOR_PLAN_20260518.md)**
    *   **[Review Report — Modernização](./loops/FINAL_MODERNIZATION_REPORT_20260518.md)**
    *   **[Review Report — Resolução de Gargalos](./loops/URGENT_SERVER_OVERLOAD_FIX.md)**
