# 🔍 Relatório de Auditoria e Plano de Modernização - AutoSINAPI

**Data:** 18 de Maio de 2026
**Status:** Planejamento Aprovado / Início da Execução

---

## 1. Diagnóstico da Auditoria (Problemas Críticos)

### 🔴 C0: O "Bug do Placebo" (Toolkit)
A função `run_etl` em `autosinapi/__init__.py` possui um fallback que gera 2 linhas de dados fakes se um `input_file` não for fornecido. Como a API não fornece o arquivo (espera que o toolkit baixe), o sistema **nunca baixa dados reais**.

### 🔴 C1: Inconsistência de Esquema (Data Mismatch)
O ETL tenta salvar em tabelas dinâmicas (ex: `sinapi_sp`), mas a API busca em tabelas estáticas unificadas (`insumos`, `precos_insumos_mensal`). O sistema é incapaz de ler o que escreve.

### 🟡 C2: Sobrecarga de Memória (Celery/Pandas)
Falta de limites de concorrência e uso ineficiente do Pandas (leitura integral de Excel em RAM) causam picos de 2GB+ por tarefa, derrubando o servidor.

### 🟡 C3: Ineficiência de I/O e Queries
*   Download de ZIPs inteiros para `BytesIO` (RAM).
*   Queries com `TO_CHAR` em colunas indexadas, forçando *Full Table Scans*.
*   Views de BI referenciadas na API mas ausentes no DDL de inicialização.

---

## 2. Plano de Ação (Arquitetura de Resiliência)

### Fase 1: Fundação e Sandbox (Não-Destrutivo)
*   **Ação:** Implementar o conceito de `Environment Tiering`.
*   **Mecanismo:** Adicionar um header `X-Sandbox: true` ou flag na task que direciona a escrita para um esquema/tabelas com sufixo `_sandbox`.
*   **Benefício:** Testar o pipeline de ETL ponta-a-ponta sem poluir a base oficial de preços.

### Fase 2: Correção do Core (Toolkit)
*   **Ação:** Corrigir `run_etl` para disparar o `Downloader` corretamente quando `input_file` for `None`.
*   **Ação:** Unificar o mapeamento de tabelas no `Database.save_data`.
*   **TDD:** Criar teste que valida a persistência correta de 100+ linhas reais.

### Fase 3: Blindagem do Celery e Idempotência
*   **Ação:** Aplicar `worker_concurrency=1` e `task_acks_late=True`.
*   **Ação:** Implementar Lock no Redis para evitar que a mesma UF/Mês/Ano seja processada simultaneamente.

### Fase 4: Otimização de Performance
*   **Ação:** Refatorar `crud.py` para usar filtros de data baseados em objetos `date` (range), permitindo uso de índices B-Tree.
*   **Ação:** Adicionar o DDL das Views no `Database.create_tables()`.

---

## 3. Matriz de Testes (TDD)

| Nível | Teste | Objetivo |
|---|---|---|
| **Unitário** | `test_date_range_logic` | Validar que a conversão AAAA-MM -> Range está correta. |
| **Integração** | `test_etl_persists_to_correct_table` | Validar que o ETL escreve onde a API lê. |
| **Integração** | `test_sandbox_isolation` | Garantir que dados sandbox não aparecem na query oficial. |
| **Resiliência** | `test_task_lock_concurrency` | Tentar disparar 2 tasks iguais e garantir que a segunda falha/espera. |

---

## 4. Próximos Passos Imediatos

1.  Criar `api/sandbox_utils.py` para gestão de contextos de teste.
2.  Modificar `api/database.py` para suportar prefixos de tabela dinâmicos.
3.  Implementar o primeiro teste de integração falho (Red phase).
