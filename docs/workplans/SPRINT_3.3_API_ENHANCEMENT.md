# Sprint 3.3: API Enhancement - Traceability Exposure

## Objetivo
Expor informações de rastreabilidade e retificações via API, permitindo que consumidores saibam a proveniência e histórico de alterações de cada dado.

## Escopo
- Atualizar schemas Pydantic com campos de traceability
- Atualizar endpoints existentes para expor dados de auditoria
- Criar novo endpoint `/audit/{tipo}/{codigo}`
- Expor histórico de retificações nos endpoints `/historico` e `/manutencoes`

## Tasks

### Task 1: Atualizar Schemas Pydantic
**Arquivo**: `api/schemas.py`

**Novos schemas**:
```python
class TraceabilityMixin(BaseModel):
    created_at: datetime | None = None
    updated_at: datetime | None = None
    sinapi_versao: str | None = None

class Insumo(TraceabilityMixin):
    codigo: int
    descricao: str
    unidade: str | None = None
    preco_mediano: float | None = None
    classificacao: str | None = None
    origem_preco: str | None = None
    status: str | None = None

class Composicao(TraceabilityMixin):
    codigo: int
    descricao: str
    unidade: str | None = None
    custo_total: float | None = None
    grupo: str | None = None
    percentual_mo: float | None = None
    status: str | None = None

class AuditEvent(BaseModel):
    id: int
    table_name: str
    record_pk: dict
    operation: str
    old_values: dict | None = None
    new_values: dict | None = None
    sinapi_versao: str | None = None
    motivo_manutencao: str | None = None
    created_at: datetime

class HistoricoCusto(TraceabilityMixin):
    data_referencia: date
    valor: float
    foi_retificado: bool = False
    versao_original: str | None = None
    versao_atual: str | None = None
```

### Task 2: Atualizar CRUD para Retornar Campos de Traceability
**Arquivo**: `api/crud.py`

**Atualizar queries** para incluir `created_at`, `updated_at`, `sinapi_versao` nos resultados.

**Exemplo**:
```python
def get_insumo(db: Session, codigo: int, uf: str, data_referencia: date, regime: str):
    query = text("""
        SELECT i.codigo, i.descricao, i.unidade, i.classificacao, i.status,
               p.preco_mediano, p.origem_preco,
               i.created_at, i.updated_at, i.sinapi_versao
        FROM insumos i
        LEFT JOIN precos_insumos_mensal p 
            ON i.codigo = p.insumo_codigo 
            AND p.uf = :uf 
            AND p.data_referencia = :data_referencia
            AND p.regime = :regime
        WHERE i.codigo = :codigo
    """)
    result = db.execute(query, {
        "codigo": codigo, "uf": uf, 
        "data_referencia": data_referencia, "regime": regime
    })
    row = result.fetchone()
    if not row:
        return None
    return schemas.Insumo(**dict(row._mapping))
```

### Task 3: Criar Endpoint `/audit/{tipo}/{codigo}`
**Arquivo**: `api/main.py`

```python
@app.get(
    "/api/v1/public/bi/audit/{tipo_item}/{codigo}",
    response_model=List[schemas.AuditEvent],
    tags=["Audit"],
    summary="Get audit trail for an item"
)
def get_audit_trail(
    tipo_item: str,
    codigo: int,
    data_referencia: date = Query(...),
    db: Session = Depends(get_db)
):
    """Retorna histórico completo de alterações para um item.
    
    Inclui retificações de preços, mudanças de status, 
    e modificações de estrutura.
    """
    query = text("""
        SELECT id, table_name, record_pk, operation, 
               old_values, new_values, sinapi_versao, 
               motivo_manutencao, created_at
        FROM sinapi_audit_log
        WHERE record_pk->>'codigo' = :codigo
           OR record_pk->>'insumo_codigo' = :codigo
           OR record_pk->>'composicao_codigo' = :codigo
        ORDER BY created_at DESC
        LIMIT 100
    """)
    result = db.execute(query, {"codigo": str(codigo)})
    rows = result.fetchall()
    return [schemas.AuditEvent(**dict(r._mapping)) for r in rows]
```

### Task 4: Atualizar Endpoint `/historico` com Retificações
**Arquivo**: `api/crud.py` e `api/main.py`

**Lógica**: Comparar `sinapi_versao` do registro mais antigo com o mais recente para detectar retificações.

```python
def get_historico_custo(db: Session, tipo_item: str, codigo: int):
    query = text("""
        SELECT data_referencia, valor, sinapi_versao, created_at, updated_at,
               LAG(sinapi_versao) OVER (ORDER BY data_referencia) as versao_anterior
        FROM (
            SELECT data_referencia, preco_mediano as valor, sinapi_versao, created_at, updated_at
            FROM precos_insumos_mensal p
            JOIN insumos i ON p.insumo_codigo = i.codigo
            WHERE i.codigo = :codigo
            UNION ALL
            SELECT data_referencia, custo_total as valor, sinapi_versao, created_at, updated_at
            FROM custos_composicoes_mensal c
            JOIN composicoes co ON c.composicao_codigo = co.codigo
            WHERE co.codigo = :codigo
        ) sub
        ORDER BY data_referencia
    """)
    result = db.execute(query, {"codigo": codigo})
    rows = result.fetchall()
    
    historico = []
    for row in rows:
        d = dict(row._mapping)
        d["foi_retificado"] = d["sinapi_versao"] != d["versao_anterior"] if d["versao_anterior"] else False
        d["versao_original"] = d["versao_anterior"]
        d["versao_atual"] = d["sinapi_versao"]
        historico.append(schemas.HistoricoCusto(**d))
    return historico
```

### Task 5: Atualizar Endpoint `/manutencoes` com Link de Auditoria
**Arquivo**: `api/crud.py`

**Lógica**: Cruzar `manutencoes_historico` com `sinapi_audit_log` para mostrar o que foi modificado em cada manutenção.

```python
def get_manutencoes(db: Session, tipo_item: str, codigo: int):
    query = text("""
        SELECT m.item_codigo, m.tipo_item, m.data_referencia, 
               m.tipo_manutencao, m.descricao_item,
               a.id as audit_id, a.operation, a.old_values, a.new_values
        FROM manutencoes_historico m
        LEFT JOIN sinapi_audit_log a 
            ON a.motivo_manutencao = m.tipo_manutencao
            AND a.table_name = CASE m.tipo_item 
                WHEN 'INSUMO' THEN 'insumos' 
                WHEN 'COMPOSICAO' THEN 'composicoes' 
            END
            AND a.record_pk->>'codigo' = CAST(m.item_codigo AS TEXT)
        WHERE m.item_codigo = :codigo AND m.tipo_item = :tipo_item
        ORDER BY m.data_referencia DESC
    """)
    result = db.execute(query, {"codigo": codigo, "tipo_item": tipo_item})
    rows = result.fetchall()
    return [schemas.HistoricoManutencao(**dict(r._mapping)) for r in rows]
```

## Critérios de Aceitação
- [ ] Todos os schemas Pydantic possuem campos de traceability
- [ ] Endpoint `/audit/{tipo}/{codigo}` retorna eventos de auditoria
- [ ] Endpoint `/historico` indica se dado foi retificado
- [ ] Endpoint `/manutencoes` cruza com audit log
- [ ] Respostas JSON incluem `created_at`, `updated_at`, `sinapi_versao`
- [ ] Testes de integração validam campos de traceability

## Arquivos Modificados
| Arquivo | Mudança |
|---------|---------|
| `api/schemas.py` | `TraceabilityMixin`, `AuditEvent`, `HistoricoCusto` |
| `api/crud.py` | Queries atualizadas com traceability |
| `api/main.py` | Novo endpoint `/audit/{tipo}/{codigo}` |
| `tests/test_api.py` | Testes de traceability (se existir) |

## Estimativa
- Complexidade: **Média**
- Tempo estimado: **3-4 horas**
- Riscos: Baixo (apenas adição de campos, sem quebra de compatibilidade)
