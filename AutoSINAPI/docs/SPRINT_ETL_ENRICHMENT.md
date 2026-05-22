# 🛠️ Sprint: Correção e Enriquecimento do Motor ETL — AutoSINAPI Toolkit

> **Status:** Planejada (não iniciada)
> **Período:** A definir (Sprint independente)
> **Objetivo:** Corrigir o pipeline de Extração, Transformação e Carga (ETL) para que os campos `classificacao` (insumos) e `grupo` (composições) sejam populados a partir das planilhas SINAPI, resolvendo o "Data Mismatch" entre o modelo de dados e o banco real.

---

## 📋 Contexto e Motivação

### Problema Detectado

O `DataModel.md` especifica que:

| Tabela | Coluna | Tipo | Descrição |
|---|---|---|---|
| `insumos` | `classificacao` | TEXT | Classificação hierárquica do insumo |
| `composicoes` | `grupo` | VARCHAR | Grupo ao qual a composição pertence |

Porém, no banco de dados de produção (`sinapi`):

| Coluna | Total ATIVO | Com valor | NULO |
|---|---|---|---|
| `insumos.classificacao` | 6.036 | **0** | **100%** |
| `composicoes.grupo` | 10.378 | **0** | **100%** |

### Causa Raiz

Analisando o código do toolkit (`autosinapi/core/processor.py`), o pipeline ETL **nunca extrai** as colunas `CLASSIFICACAO` e `GRUPO` das planilhas Excel. Os catálogos são montados com apenas 3 colunas:

```python
# processor.py:338 — extração de catálogo de insumos
catalogo_df = df[["CODIGO", "DESCRICAO", "UNIDADE"]].copy()

# processor.py:392 — extração de catálogo de composições
catalogo_df = df[["CODIGO", "DESCRICAO", "UNIDADE"]].copy()
```

E o mapeamento final (`config.py:80-82`) também ignora esses campos:

```python
"FINAL_CATALOG_COLUMNS": {
    "CODIGO": "codigo",
    "DESCRICAO": "descricao",
    "UNIDADE": "unidade"
    # FALTA: "CLASSIFICACAO" e "GRUPO"
}
```

### Impacto

Todas as features de frontend que dependem desses campos retornam vazio:
- Badge de classificação nos cards de pesquisa
- Filtro por classificação/grupo
- Curva ABC agrupada por classificação
- Dashboard de tendências por classificação
- Badge de grupo nos cards de composição

---

## 🎯 Escopo da Sprint

### Tarefa 1: Extrair `CLASSIFICACAO` do catálogo de insumos

**Arquivo:** `autosinapi/core/processor.py`

**Método:** `_process_precos_sheet()` (linha ~327)

**Problema:** A linha 338 extrai apenas `CODIGO`, `DESCRICAO`, `UNIDADE`:
```python
catalogo_df = df[["CODIGO", "DESCRICAO", "UNIDADE"]].copy()
```

**Correção:** Adicionar `CLASSIFICACAO` se a coluna existir no DataFrame:
```python
cols_catalogo = ["CODIGO", "DESCRICAO", "UNIDADE"]
if "CLASSIFICACAO" in df.columns:
    cols_catalogo.append("CLASSIFICACAO")
catalogo_df = df[cols_catalogo].copy()
```

**Validação:** Verificar se o nome normalizado da coluna é `CLASSIFICACAO` (via `_normalize_cols()` executado na linha 333 antes da extração).

### Tarefa 2: Extrair `GRUPO` do catálogo de composições

**Arquivo:** `autosinapi/core/processor.py`

**Método:** `_process_custos_sheet()` (linha ~348)

**Problema:** A linha 392 extrai apenas `CODIGO`, `DESCRICAO`, `UNIDADE`:
```python
catalogo_df = df[["CODIGO", "DESCRICAO", "UNIDADE"]].copy()
```

**Correção:** Adicionar `GRUPO` se a coluna existir no DataFrame:
```python
cols_catalogo = ["CODIGO", "DESCRICAO", "UNIDADE"]
if "GRUPO" in df.columns:
    cols_catalogo.append("GRUPO")
catalogo_df = df[cols_catalogo].copy()
```

**Validação:** Verificar qual nome normalizado `_normalize_cols()` produz para "GRUPO". Confirmar se nas planilhas SINAPI a coluna aparece como "Grupo", "GRUPO" ou similar.

### Tarefa 3: Atualizar o mapeamento de colunas finais

**Arquivo:** `autosinapi/config.py` (linha ~80)

**Problema:** O dicionário `FINAL_CATALOG_COLUMNS` não mapeia `CLASSIFICACAO` nem `GRUPO`:
```python
"FINAL_CATALOG_COLUMNS": {
    "CODIGO": "codigo",
    "DESCRICAO": "descricao",
    "UNIDADE": "unidade"
}
```

**Correção:** Adicionar as duas colunas:
```python
"FINAL_CATALOG_COLUMNS": {
    "CODIGO": "codigo",
    "DESCRICAO": "descricao",
    "UNIDADE": "unidade",
    "CLASSIFICACAO": "classificacao",
    "GRUPO": "grupo"
}
```

### Tarefa 4: Atualizar placeholders para incluir os novos campos

**Arquivo:** `autosinapi/etl_pipeline.py`

**Método:** `_handle_missing_items_placeholders()` (linha ~301)

**Problema:** Os placeholders para insumos/composições ausentes não incluem `classificacao`/`grupo`:
```python
missing_insumos_data = {
    'codigo': ...,
    'descricao': ...,
    'unidade': ...
}
```

**Correção:** Adicionar os campos aos placeholders:
```python
missing_insumos_data = {
    'codigo': ...,
    'descricao': ...,
    'unidade': ...,
    'classificacao': 'NAO_CLASSIFICADO'
}
```

### Tarefa 5: Reprocessamento histórico

**Problema:** Os 14 meses já carregados no banco não serão corrigidos automaticamente.

**Opções:**
1. **Recomendado — Script SQL único:** Executar um `UPDATE` que popula `classificacao` e `grupo` a partir dos dados mais recentes disponíveis nas planilhas. Como esses campos não mudam entre meses (são do catálogo, não da série temporal), basta processar um mês recente.
2. **Reprocessar tudo:** Executar o ETL novamente para cada mês. Mais demorado, porém a abordagem mais limpa.

### Tarefa 6 (Opcional): Criar/Documentar teste de integração

**Arquivo:** `tests/` (a criar)

Criar teste que:
1. Executa `run_etl()` para um mês de teste
2. Verifica se `SELECT classificacao FROM insumos WHERE classificacao IS NOT NULL LIMIT 1` retorna um registro
3. Verifica se `SELECT grupo FROM composicoes WHERE grupo IS NOT NULL LIMIT 1` retorna um registro

---

## 🔍 Investigação Necessária (Pontos Abertos)

Antes de implementar, o agente deve verificar:

1. **Nome real da coluna nas planilhas:**
   - Baixar/examinar um arquivo `SINAPI_Referência_AAAA_MM.xlsx`
   - Verificar se a aba `ISD` (insumos não desonerados) tem uma coluna como "Classificação", "CLASSE", "CATEGORIA" ou similar
   - Verificar se a aba `CSD` (custos não desonerados) tem uma coluna "Grupo" ou similar
   - Usar `pd.read_excel()` com `header=9` para ver os cabeçalhos reais

2. **Testar o nome normalizado:**
   - Aplicar `_normalize_cols()` em um DataFrame de teste para confirmar que o nome final será `CLASSIFICACAO` e `GRUPO`

3. **Coluna `UNIDADE` também é extraída das abas de custos?**
   - Confirmar se as abas CSD/CCD/CSE têm coluna "Unidade" para composições

---

## 📦 Arquivos Afetados

| Arquivo | Tarefa |
|---|---|
| `autosinapi/core/processor.py` | Tarefas 1 e 2 |
| `autosinapi/config.py` | Tarefa 3 |
| `autosinapi/etl_pipeline.py` | Tarefa 4 |
| `docs/DataModel.md` | (opcional) Revisar se precisa de atualização |

---

## ✅ Critérios de Aceite (DoD)

1. [ ] Após executar o ETL para um mês, a query `SELECT COUNT(classificacao) FROM insumos WHERE status='ATIVO'` retorna > 0
2. [ ] Após executar o ETL para um mês, a query `SELECT COUNT(grupo) FROM composicoes WHERE status='ATIVO'` retorna > 0
3. [ ] Os placeholders para itens ausentes têm `classificacao = 'NAO_CLASSIFICADO'`
4. [ ] O UPSERT de catálogos não sobrescreve `classificacao`/`grupo` com NULL quando a planilha não contém esses dados para um item específico
5. [ ] Nenhum teste existente quebra com as alterações
6. [ ] As bases já carregadas (14 meses) podem ser corrigidas via script SQL ou reprocessamento

---

## 🔗 Dependências

- Nenhuma. Esta sprint é independente — pode ser executada em paralelo com outras sprints de frontend/demo.
- O banco de dados `sinapi` já existe com 14 meses de dados — é o ambiente de teste ideal.