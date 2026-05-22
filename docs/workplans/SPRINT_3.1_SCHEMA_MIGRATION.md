# Sprint 3.1: Schema Migration & Traceability Foundation

## Objetivo
Criar a base de rastreabilidade em todas as tabelas do AutoSINAPI via migration Alembic e atualizar o DDL do toolkit.

## Escopo
- Migration Alembic `002_add_traceability_columns.py`
- Atualização de `database.py:create_tables()`
- Tabela `sinapi_audit_log`
- Índices para performance

## Tasks

### Task 1: Criar Migration Alembic 002
**Arquivo**: `alembic/versions/002_add_traceability_columns.py`

**Colunas a adicionar em TODAS as tabelas**:
- `created_at TIMESTAMPTZ DEFAULT NOW()`
- `updated_at TIMESTAMPTZ DEFAULT NOW()`
- `sinapi_versao VARCHAR(20)`
- `etl_run_id UUID`

**Tabelas afetadas**:
1. `insumos`
2. `composicoes`
3. `precos_insumos_mensal`
4. `custos_composicoes_mensal`
5. `composicao_insumos`
6. `composicao_subcomposicoes`
7. `manutencoes_historico`
8. `insumos_familias`
9. `coeficientes_familia_mensal`
10. `composicoes_mix_mao_de_obra`

**SQL exemplo**:
```python
def upgrade():
    tables = [
        "insumos", "composicoes", "precos_insumos_mensal",
        "custos_composicoes_mensal", "composicao_insumos",
        "composicao_subcomposicoes", "manutencoes_historico",
        "insumos_familias", "coeficientes_familia_mensal",
        "composicoes_mix_mao_de_obra"
    ]
    for table in tables:
        op.add_column(table, sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
        op.add_column(table, sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()))
        op.add_column(table, sa.Column("sinapi_versao", sa.String(20), nullable=True))
        op.add_column(table, sa.Column("etl_run_id", sa.UUID(), nullable=True))
```

### Task 2: Criar Tabela `sinapi_audit_log`
**Arquivo**: Mesma migration (002)

```sql
CREATE TABLE sinapi_audit_log (
    id BIGSERIAL PRIMARY KEY,
    table_name VARCHAR(100) NOT NULL,
    record_pk JSONB NOT NULL,
    operation VARCHAR(10) NOT NULL,  -- INSERT, UPDATE, DELETE
    old_values JSONB,
    new_values JSONB,
    sinapi_versao VARCHAR(20),
    etl_run_id UUID,
    motivo_manutencao VARCHAR(200),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_audit_table_name ON sinapi_audit_log(table_name);
CREATE INDEX idx_audit_created_at ON sinapi_audit_log(created_at);
CREATE INDEX idx_audit_etl_run ON sinapi_audit_log(etl_run_id);
```

### Task 3: Atualizar `database.py:create_tables()`
**Arquivo**: `AutoSINAPI/autosinapi/core/database.py`

Atualizar o DDL em `database.py:99-151` para incluir as novas colunas em todas as tabelas. O DDL deve refletir o estado pós-migration.

**Exemplo para `insumos`**:
```sql
CREATE TABLE insumos (
    codigo INTEGER PRIMARY KEY,
    descricao TEXT NOT NULL,
    unidade VARCHAR,
    classificacao TEXT,
    status VARCHAR DEFAULT 'ATIVO',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    sinapi_versao VARCHAR(20),
    etl_run_id UUID
);
```

### Task 4: Criar Índices de Performance
**Arquivo**: Mesma migration (002)

```sql
CREATE INDEX idx_insumos_updated_at ON insumos(updated_at);
CREATE INDEX idx_composicoes_updated_at ON composicoes(updated_at);
CREATE INDEX idx_precos_updated_at ON precos_insumos_mensal(updated_at);
CREATE INDEX idx_custos_updated_at ON custos_composicoes_mensal(updated_at);
CREATE INDEX idx_manutencoes_data ON manutencoes_historico(data_referencia);
```

## Critérios de Aceitação
- [ ] Migration `002` roda sem erros em banco vazio
- [ ] Migration `002` roda sem erros em banco com dados existentes (downgrade seguro)
- [ ] Todas as 10 tabelas possuem as 4 novas colunas
- [ ] Tabela `sinapi_audit_log` criada com índices
- [ ] `database.py:create_tables()` reflete o novo schema
- [ ] `alembic upgrade head` e `alembic downgrade -1` funcionam

## Arquivos Modificados
| Arquivo | Mudança |
|---------|---------|
| `alembic/versions/002_add_traceability_columns.py` | **Novo** |
| `AutoSINAPI/autosinapi/core/database.py` | DDL atualizado |
| `alembic/env.py` | Se necessário, atualizar imports |

## Estimativa
- Complexidade: **Média**
- Tempo estimado: **2-3 horas**
- Riscos: Baixo (migration pura, sem alteração de lógica)
