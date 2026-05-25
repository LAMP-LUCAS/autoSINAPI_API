# Sprint 3.2: ETL Enhancement - UPSERT & Structure Preservation

## Objetivo
Transformar o ETL para suportar retificações oficiais do SINAPI, preservando histórico de estruturas e rastreando versão/etl_run_id em todas as operações.

## Escopo
- Alterar `_append_data` para UPSERT com DO UPDATE
- Alterar TRUNCATE para DELETE por período
- Extrair versão SINAPI do nome do arquivo
- Propagar `sinapi_versao` e `etl_run_id` via `save_data`

## Tasks

### Task 1: Alterar `_append_data` para UPSERT
**Arquivo**: `AutoSINAPI/autosinapi/core/database.py` (linhas 191-222)

**Atual**:
```python
insert_query = f'''
    INSERT INTO "{table_name}" ({cols})
    SELECT {cols} FROM "{temp_table_name}" 
    ON CONFLICT ({pk_cols_str}) DO NOTHING;
'''
```

**Novo**:
```python
update_cols = ", ".join([
    f'"{c}" = EXCLUDED."{c}"' 
    for c in data.columns 
    if c not in pk_cols
])
if update_cols:
    update_cols += f', updated_at = NOW()'
    insert_query = f'''
        INSERT INTO "{table_name}" ({cols})
        SELECT {cols} FROM "{temp_table_name}" 
        ON CONFLICT ({pk_cols_str}) DO UPDATE SET {update_cols};
    '''
else:
    insert_query = f'''
        INSERT INTO "{table_name}" ({cols})
        SELECT {cols} FROM "{temp_table_name}" 
        ON CONFLICT ({pk_cols_str}) DO NOTHING;
    '''
```

### Task 2: Alterar TRUNCATE para DELETE por Período
**Arquivo**: `AutoSINAPI/autosinapi/etl_pipeline.py` (linhas 378-379)

**Atual**:
```python
db.truncate_table(self.config.DB_TABLE_COMPOSICAO_INSUMOS)
db.truncate_table(self.config.DB_TABLE_COMPOSICAO_SUBCOMPOSICOES)
```

**Novo**:
```python
ref_date = f"{year}-{month:02d}-01"
db.execute_non_query(
    f'DELETE FROM "{self.config.DB_TABLE_COMPOSICAO_INSUMOS}" WHERE data_referencia = :ref',
    {"ref": ref_date}
)
db.execute_non_query(
    f'DELETE FROM "{self.config.DB_TABLE_COMPOSICAO_SUBCOMPOSICOES}" WHERE data_referencia = :ref',
    {"ref": ref_date}
)
```

### Task 3: Extrair Versão SINAPI do Nome do Arquivo
**Arquivo**: `AutoSINAPI/autosinapi/etl_pipeline.py` (método `run()`)

**Lógica de extração**:
```python
def extract_sinapi_version(filename: str) -> str:
    """Extrai versão SINAPI do nome do arquivo.
    
    Exemplos:
    - SINAPI_Composicoes_2024_12.xlsx -> "2024.12"
    - SINAPI_Insumos_2025_01.xlsx -> "2025.01"
    """
    match = re.search(r'(\d{4})_(\d{2})', filename)
    if match:
        return f"{match.group(1)}.{match.group(2)}"
    return datetime.now().strftime("%Y.%m")  # fallback
```

### Task 4: Propagar `sinapi_versao` e `etl_run_id` via `save_data`
**Arquivo**: `AutoSINAPI/autosinapi/core/database.py` (método `save_data`)

**Atual**:
```python
def save_data(self, data: pd.DataFrame, table_name: str, policy: str, **kwargs):
```

**Novo**:
```python
def save_data(self, data: pd.DataFrame, table_name: str, policy: str, **kwargs):
    sinapi_versao = kwargs.get("sinapi_versao")
    etl_run_id = kwargs.get("etl_run_id")
    
    if sinapi_versao and "sinapi_versao" in data.columns:
        data["sinapi_versao"] = sinapi_versao
    if etl_run_id and "etl_run_id" in data.columns:
        data["etl_run_id"] = etl_run_id
```

### Task 5: Adicionar Colunas de Traceability aos DataFrames
**Arquivo**: `AutoSINAPI/autosinapi/core/processor.py`

Após cada método de processamento (`process_insumos`, `process_composicoes`, etc.), adicionar:
```python
df["sinapi_versao"] = None  # será preenchido pelo ETL
df["etl_run_id"] = None     # será preenchido pelo ETL
df["created_at"] = None
df["updated_at"] = None
```

### Task 6: Criar Método `_log_audit_event`
**Arquivo**: `AutoSINAPI/autosinapi/core/database.py`

```python
def _log_audit_event(self, table_name: str, record_pk: dict, operation: str, 
                     old_values: dict = None, new_values: dict = None,
                     sinapi_versao: str = None, etl_run_id: str = None,
                     motivo_manutencao: str = None):
    """Registra evento no sinapi_audit_log."""
    query = text("""
        INSERT INTO sinapi_audit_log 
        (table_name, record_pk, operation, old_values, new_values, 
         sinapi_versao, etl_run_id, motivo_manutencao)
        VALUES (:table_name, :record_pk, :operation, :old_values, :new_values,
                :sinapi_versao, :etl_run_id, :motivo_manutencao)
    """)
    params = {
        "table_name": table_name,
        "record_pk": json.dumps(record_pk),
        "operation": operation,
        "old_values": json.dumps(old_values) if old_values else None,
        "new_values": json.dumps(new_values) if new_values else None,
        "sinapi_versao": sinapi_versao,
        "etl_run_id": etl_run_id,
        "motivo_manutencao": motivo_manutencao,
    }
    with self._engine.connect() as conn:
        conn.execute(query, params)
        conn.commit()
```

## Critérios de Aceitação
- [ ] `_append_data` atualiza registros existentes (não ignora)
- [ ] Estruturas de composição preservadas por mês (DELETE por período)
- [ ] `sinapi_versao` extraído corretamente do nome do arquivo
- [ ] `etl_run_id` propagado para todos os registros
- [ ] `_log_audit_event` registra operações de UPSERT
- [ ] Reexecutar ETL para o mesmo mês 2x não duplica dados

## Arquivos Modificados
| Arquivo | Mudança |
|---------|---------|
| `AutoSINAPI/autosinapi/core/database.py` | `_append_data`, `_log_audit_event`, `save_data` |
| `AutoSINAPI/autosinapi/etl_pipeline.py` | `run()`, extrair versão, DELETE por período |
| `AutoSINAPI/autosinapi/core/processor.py` | Adicionar colunas de traceability |

## Estimativa
- Complexidade: **Alta**
- Tempo estimado: **4-6 horas**
- Riscos: Médio (mudança de comportamento do ETL)
