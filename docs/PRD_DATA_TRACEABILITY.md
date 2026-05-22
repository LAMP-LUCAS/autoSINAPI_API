# PRD: AutoSINAPI Data Reliability & Traceability Enhancement

## 1. Executive Summary

O AutoSINAPI atual possui **zero rastreabilidade** de dados. Não há `created_at`, `updated_at`, versão SINAPI ou identificação de retificações. O ETL usa `APPEND + DO NOTHING` para dados mensais, o que **ignora retificações oficiais**. Este PRD define as mudanças necessárias para atingir nível profissional de confiabilidade e auditoria.

---

## 2. Current State Audit

### 2.1 DataModel Toolkit (ETL) - Gaps Críticos

| Tabela | PK | Traceability Columns | Problema |
|--------|-----|---------------------|----------|
| `insumos` | codigo | **Nenhuma** | Status muda via manutenção mas não há rastro de quando/por que |
| `composicoes` | codigo | **Nenhuma** | Idem |
| `precos_insumos_mensal` | (codigo, uf, data_ref, regime) | **Nenhuma** | `DO NOTHING` ignora retificações de preços |
| `custos_composicoes_mensal` | (codigo, uf, data_ref, regime) | **Nenhuma** | Idem |
| `composicao_insumos` | (pai, filho) | **Nenhuma** | TRUNCATE apaga estruturas de meses anteriores |
| `composicao_subcomposicoes` | (pai, filho) | **Nenhuma** | Idem |
| `manutencoes_historico` | (codigo, tipo, data, tipo_manut) | **Nenhuma** | Não liga manutenção à modificação real do dado |

### 2.2 API DataModel - Gaps

| Endpoint | Traceability Info | Problema |
|----------|------------------|----------|
| `/historico` | data_referencia, valor | Não informa se dado foi retificado |
| `/manutencoes` | tipo_manutencao, data | Não liga manutenção à modificação real do dado |
| Response models | Sem campos de auditoria | Consumidor não sabe a proveniência |

### 2.3 Maintenance File Analysis

Arquivo processado em `processor.py:168-204`:
```
Colunas originais SINAPI → Mapeadas no ETL:
- REFERENCIA → data_referencia (data da manutenção)
- TIPO → tipo_item (INSUMO/COMPOSICAO)
- CODIGO → item_codigo
- DESCRICAO → descricao_item
- MANUTENCAO → tipo_manutencao (ATIVACAO, DESATIVACAO, etc.)
```

**O que o arquivo de manutenção tem**: O quê, Quando, Qual item
**O que FALTA**: Versão SINAPI do arquivo, Motivo oficial, Link com alteração de preço/custo

---

## 3. Requirements

### 3.1 Functional Requirements

#### FR1: Traceability Columns (All Tables)
Adicionar a **todas** as tabelas SINAPI:
```sql
ALTER TABLE tabela ADD COLUMN created_at TIMESTAMPTZ DEFAULT NOW();
ALTER TABLE tabela ADD COLUMN updated_at TIMESTAMPTZ DEFAULT NOW();
ALTER TABLE tabela ADD COLUMN sinapi_versao VARCHAR(20);  -- ex: "2024.12" ou hash do arquivo
ALTER TABLE tabela ADD COLUMN etl_run_id UUID;  -- identifica qual execução do ETL inseriu
```

#### FR2: Retification Handling (UPSERT instead of APPEND)
Alterar política de carga para dados mensais (`precos_insumos_mensal`, `custos_composicoes_mensal`):
- De: `INSERT ... ON CONFLICT DO NOTHING` (ignora retificações)
- Para: `INSERT ... ON CONFLICT DO UPDATE SET preco_mediano = EXCLUDED.preco_mediano, updated_at = NOW(), sinapi_versao = EXCLUDED.sinapi_versao`

#### FR3: Structure Preservation (DELETE by Period instead of TRUNCATE)
Alterar carga de estruturas (`composicao_insumos`, `composicao_subcomposicoes`):
- De: `TRUNCATE TABLE` (apaga TUDO)
- Para: `DELETE FROM tabela WHERE data_referencia = :ref` (apaga só o mês processado)

#### FR4: Maintenance-Data Linkage
Criar tabela de auditoria que liga manutenção à modificação:
```sql
CREATE TABLE sinapi_audit_log (
    id BIGSERIAL PRIMARY KEY,
    table_name VARCHAR NOT NULL,
    record_pk JSONB NOT NULL,  -- ex: {"insumo_codigo": 123, "uf": "SP"}
    operation VARCHAR NOT NULL,  -- INSERT, UPDATE, DELETE
    old_values JSONB,
    new_values JSONB,
    sinapi_versao VARCHAR,
    etl_run_id UUID,
    motivo_manutencao VARCHAR,  -- tipo_manutencao do arquivo SINAPI
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

#### FR5: SINAPI Version Tracking
Extrair versão do arquivo SINAPI (nome do arquivo ou metadados) e propagar para todos os registros inseridos/atualizados naquela execução.

#### FR6: API Exposure of Traceability
Adicionar aos schemas de resposta:
```python
class Insumo(BaseModel):
    # ... campos atuais
    created_at: datetime | None
    updated_at: datetime | None
    sinapi_versao: str | None
    historico_manutencoes: List[HistoricoManutencao] | None
```

---

## 4. Non-Functional Requirements

| Req | Descrição |
|-----|-----------|
| **NFR1: Performance** | UPSERT em tabelas grandes deve usar índices na PK; `sinapi_audit_log` deve ter particionamento por mês |
| **NFR2: Idempotency** | Reexecutar ETL para o mesmo mês deve ser safe: atualiza se houver mudança, não duplica |
| **NFR3: Data Integrity** | Não permitir que `updated_at < created_at`; validar sinapi_versao não nula em inserts |
| **NFR4: Rollback** | `sinapi_audit_log` deve permitir reconstruir estado anterior (old_values) |

---

## 5. Implementation Plan

### Phase 1: Schema Migration (Database)
1. Criar migration Alembic `002_add_traceability_columns.py`:
   - Adicionar colunas `created_at`, `updated_at`, `sinapi_versao`, `etl_run_id` a todas as tabelas
   - Criar tabela `sinapi_audit_log`
   - Criar índices em `updated_at` para consultas de retificações

2. Atualizar `database.py:create_tables()` com novo DDL

### Phase 2: ETL Enhancement
1. **`database.py`**: Alterar `_append_data` para fazer UPSERT com DO UPDATE
2. **`database.py`**: Alterar `_replace_data` para também atualizar estruturas por período
3. **`etl_pipeline.py`**: Extrair versão SINAPI do nome do arquivo nos métodos `run()`
4. **`etl_pipeline.py`**: Propagar `sinapi_versao` e `etl_run_id` via `kwargs` no `save_data`
5. **`etl_pipeline.py`**: Alterar `_process_composition_data` para usar DELETE por período em vez de TRUNCATE

### Phase 3: Audit Log Implementation
1. Após cada UPSERT/UPDATE, inserir em `sinapi_audit_log` com `old_values` e `new_values`
2. Ligar `manutencoes_historico.tipo_manutencao` ao `sinapi_audit_log.motivo_manutencao`

### Phase 4: API Enhancement
1. Atualizar `api/schemas.py` com novos campos de traceability
2. Atualizar endpoints `/historico` e `/manutencoes` para expor dados de auditoria
3. Criar novo endpoint `GET /api/v1/public/audit/{tipo}/{codigo}` para histórico completo de retificações

---

## 6. Success Metrics

| Métrica | Atual | Target |
|---------|-------|--------|
| Tabelas com `created_at`/`updated_at` | 0/9 | 9/9 |
| Retificações processadas corretamente | 0% (ignoradas) | 100% |
| Rastro de ETL run por registro | Não existe | UUID em todos |
| Consulta de histórico de alterações via API | Não disponível | Disponível |
| Estrutura de composição preservada por mês | Não (TRUNCATE) | Sim (DELETE por período) |

---

## 7. Risks & Mitigations

| Risco | Impacto | Mitigação |
|-------|---------|-----------|
| UPSERT degrade performance | Médio | Usar índices; `sinapi_audit_log` particionada |
| Versão SINAPI não extraída corretamente | Alto (perde rastro) | Fallback para hash do arquivo; validação obrigatória |
| `sinapi_audit_log` cresce rápido | Médio | Particionamento mensal; retention policy |
| Mudança quebra idempotência atual | Alto | Testes: reexecutar mesmo mês 2x e validar |

---

## 8. Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        SINAPI OFFICIAL                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌───────────────┐   │
│  │ Insumos  │  │Composic. │  │ Preços   │  │ Manutencões   │   │
│  │ .xlsx    │  │ .xlsx    │  │ .xlsx    │  │ .xlsx         │   │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └───────┬───────┘   │
│       │              │              │                │           │
└───────┼──────────────┼──────────────┼────────────────┼───────────┘
        │              │              │                │
        ▼              ▼              ▼                ▼
┌─────────────────────────────────────────────────────────────────┐
│                        ETL PIPELINE                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌───────────────┐   │
│  │ Extract  │→ │ Transform│→ │  UPSERT  │→ │  Audit Log    │   │
│  │          │  │ +Version │  │ +Update  │  │ +Traceability │   │
│  └──────────┘  └──────────┘  └──────────┘  └───────┬───────┘   │
└─────────────────────────────────────────────────────┼───────────┘
                                                      │
                                                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                     POSTGRESQL DATABASE                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌───────────────┐   │
│  │ insumos  │  │ preços   │  │ estrutura│  │ sinapi_audit  │   │
│  │ +trace   │  │ +trace   │  │ +trace   │  │ log           │   │
│  └──────────┘  └──────────┘  └──────────┘  └───────────────┘   │
└─────────────────────────────────────────────────────────────────┘
        │              │              │                │
        ▼              ▼              ▼                ▼
┌─────────────────────────────────────────────────────────────────┐
│                        FASTAPI API                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌───────────────┐   │
│  │ /insumos │  │ /precos  │  │ /historico│ │ /audit/{tipo} │   │
│  │ +trace   │  │ +trace   │  │ +retif   │ │               │   │
│  └──────────┘  └──────────┘  └──────────┘  └───────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 9. Glossary

| Termo | Definição |
|-------|-----------|
| **Traceability** | Capacidade de rastrear origem e evolução de cada dado |
| **Retificação** | Correção oficial de dados SINAPI já publicados |
| **SINAPI Versão** | Identificador do arquivo SINAPI (ex: "2024.12") |
| **ETL Run ID** | UUID único por execução do pipeline |
| **Audit Log** | Registro imutável de todas as operações de escrita |
| **UPSERT** | INSERT + UPDATE em caso de conflito na PK |
