# 🚀 Sprint: Profissionalização e Melhoria Contínua AutoSINAPI

**Período:** Maio 2026
**Objetivo:** Elevar a robustez, performance e governança da API AutoSINAPI para patamar Enterprise.

---

## 📋 Backlog da Sprint

### 1. ⚡ Camada de Cache Analítico (Foco Inicial)
*   **Descrição:** Implementar cache em Redis para queries de alto custo computacional (BOM Recursivo e Curva ABC).
*   **Impacto:** Redução do tempo de resposta de ~2s para < 50ms em consultas repetitivas. Proteção do PostgreSQL contra picos de carga.
*   **Definição de Pronto (DoD):** Testes TDD confirmando hit/miss de cache e TTL configurado.

### 2. 🗄️ Versionamento de Banco de Dados (Migrations)
*   **Descrição:** Integrar Alembic para gerenciar o esquema do banco de dados.
*   **Impacto:** Segurança em deploys, histórico de alterações de esquema e facilidade de rollbacks.
*   **Definição de Pronto (DoD):** Script de migração inicial gerado e comando `alembic upgrade head` funcional no CI.

### 3. 🔍 Observabilidade e SRE Avançado
*   **Descrição:** Implementar Structured Logging (JSON) e endpoints de `/health` detalhados.
*   **Impacto:** Diagnóstico ultra-rápido de falhas e integração com ferramentas de monitoramento modernas.
*   **Definição de Pronto (DoD):** Endpoint `/health` retornando status de DB, Redis e conectividade externa.

### 4. 🛡️ Data Quality Guardrails (Ingest Validation)
*   **Descrição:** Validação de Schema no processo de ETL usando Pydantic/Pandera.
*   **Impacto:** Impede a entrada de dados inconsistentes ou layouts corrompidos da Caixa no banco oficial.
*   **Definição de Pronto (DoD):** Teste de ETL falhando graciosamente ao receber planilha com colunas renomeadas.

---

## 🛠️ Execução da Tarefa 1: Camada de Cache

### Abordagem Técnica
1.  **Cache Key Strategy:** Chave composta por `uf:ano:mes:regime:codigo_item:tipo_query`.
2.  **Tecnologia:** Redis (já disponível na stack).
3.  **Mecanismo:** Decorator ou Wrapper no `crud.py`.
4.  **TTL (Time-To-Live):** 24 horas por padrão para dados SINAPI (que são mensais).

### Ciclo TDD (Próximos Passos)
*   [ ] **RED:** Criar `tests/test_cache.py` simulando chamadas repetidas ao BOM e falhando por falta de cache.
*   [ ] **GREEN:** Implementar `api/cache_utils.py` e aplicar no `get_composicao_bom`.
*   [ ] **REFACTOR:** Generalizar para outros endpoints de BI.
