# Sprint de Enriquecimento Visual — AutoSINAPI Demo

> **Objetivo:** Mostrar todo o potencial do banco de dados SINAPI através da interface demo, transformando dados brutos em **insights acionáveis** para tomada de decisão em orçamentos, compras e planejamento de obras.

---

## Arquitetura e Convenções

### Stack
- **Backend:** FastAPI + SQLAlchemy raw SQL + Redis cache + PostgreSQL
- **Frontend:** ES Modules + Dependency Injection (DI) + Chart.js + CSS `@layer`
- **Testes:** JS puro via `tests.js` (console-based, sem dependências externas)

### Padrões Obrigatórios (DRY, DDD, Modularidade)

1. **DI Wiring (`main.js`)**: Toda nova factory module deve ser instanciada em `main.js` e injetada via `createEvents(dom, { ...novoModulo })`. Nunca usar singletons ou módulos que se auto-instanciam.

2. **Factory Pattern**: Cada módulo é uma factory function que recebe `(config, state, dom, utils, api, toast)` na ordem. Se precisar de mais dependências, adicione no final da assinatura.

3. **Centralização de DOM**: Toda referência a elemento do DOM vai em `dom.js`. Nunca usar `document.getElementById` dentro de modules — importe de `dom`.

4. **Estado Centralizado**: Toda mutação de estado de UI vai em `state.js`. O objeto `state` é a única fonte de verdade.

5. **API Layer**: Toda chamada HTTP passa por `api.js`. Usar `api.request()` para consistência de tratamento de erros e toast.

6. **Testes (TDD)**: Todo novo módulo/feature deve:
   - Adicionar testes em `tests.js` na categoria correspondente (unit, interface, E2E)
   - Testar existência do módulo em `window.AutoSINAPI` (dev only)
   - Testar estrutura de retorno dos schemas
   - Testar interações via DOM presence + attribute checks

7. **CSS**: Novos estilos seguem `@layer tokens, components, utilities, responsive`. Novos componentes vão em arquivo próprio (e.g., `14-admin.css`).

### Convenções de Código

```js
// Factory signature — ordem fixa
export function createModal(config, state, dom, utils, api, toast) { ... }

// Export SEMPRE retorna objeto de métodos públicos
return { show, close, setBomView };

// API request unificada
const data = await api.request(`${config.API_BASE}/path?uf=...`);

// DOM sempre via dom.js
if (dom.modalContainer) dom.modalContainer.innerHTML = '...';

// XSS sempre via utils.escapeHtml()
utils.escapeHtml(userInput);
```

---

## Sprint 1a — Quick Wins (dias 1-2)

### 1.1 Badge de Classificação + Filtro por Categoria (Insumos)

**Backend** (`api/schemas.py`, `api/crud.py`, `api/main.py`):
- Adicionar `classificacao: Optional[str]` ao schema `Insumo`
- Modificar `search_insumos_by_descricao()` para SELECT `i.classificacao`
- Adicionar query param opcional `classificacao` no endpoint `GET /insumos`
- Criar novo endpoint `GET /filters?type=classificacoes` ou extender `GET /filters`

**Frontend**:
- `dom.js`: Adicionar `dom.classificacaoFilter`, `dom.modalClassificacao`
- `api.js`: `populateClassificacoes()` — popular dropdown de classificação
- `modules/search.js`: Exibir badge `classificacao` nos cards de insumo (grid e list)
- `modules/modal.js`: Exibir `classificacao` no modal hero e statsRow
- `index.html`: Adicionar `<select id="classificacaoFilter">` nos filtros de pesquisa

**Testes** (`tests.js`):
- Unit: Verificar schema `Insumo.classificacao` não nulo após fetch
- Interface: Verificar `#classificacaoFilter` existe e tem options
- Manual: Checklist item "Filtrar insumos por classificação funciona"

**Critério de aceite:** Usuário vê categoria (ex: "MATERIAL CERÂMICO") badge no card de busca e pode filtrar por ela.

**Arquivos afetados:** `api/schemas.py`, `api/crud.py`, `api/main.py`, `dom.js`, `api.js`, `search.js`, `modal.js`, `state.js`, `index.html`, `tests.js`

---

### 1.2 Badge de Grupo + Filtro por Tipo (Composições)

**Backend**:
- Adicionar `grupo: Optional[str]` ao schema `Composicao`
- Modificar `search_composicoes_by_descricao()` para SELECT `c.grupo`
- Query param `grupo` opcional no endpoint `GET /composicoes`

**Frontend**:
- `dom.js`: `dom.grupoFilter`, `dom.modalGrupo`
- `api.js`: `populateGrupos()`
- `modules/search.js`: Exibir badge `grupo` nos cards de composição
- `modules/modal.js`: Exibir `grupo` no modal

**Testes:** Análogo ao 1.1

**Critério de aceite:** Usuário vê grupo (ex: "ESTRUTURA", "INSTALAÇÕES") nos cards de composição.

---

### 1.3 Indicador de Status (Ativo/Inativo)

**Backend**:
- Adicionar `status: Optional[str]` aos schemas `Insumo` e `Composicao`
- Modificar queries para SELECT `status`
- Opcional: query param `include_inactive` default `false`

**Frontend**:
- `modules/search.js`: Se `status !== 'ATIVO'`, exibir badge vermelho "INATIVO" no card com tooltip
- `modules/modal.js`: Exibir badge de status no header do modal
- CSS: Classe `.status-badge--inactive` com `var(--error)` background

**Testes:** Verificar badge condicional no DOM

**Critério de aceite:** Insumos/composições desativados são visualmente identificáveis.

---

### 1.4 Custo BOM vs Custo Oficial

**Backend** (puro frontend — zero alteração na API):
- O custo oficial já está em `itemData.custo_total`
- O custo BOM total já é calculado em `modal.js:156`: `totalBomCost = rows.reduce(...)`

**Frontend** (`modules/modal.js`):
- Após calcular `totalBomCost` e tendo `itemData.custo_total`, adicionar no BOM section header:
  ```html
  <div class="bom-cost-comparison">
    <span>BOM Total: ${formatCurrency(totalBomCost)}</span>
    <span>Custo Oficial: ${formatCurrency(itemData.custo_total)}</span>
    <span class="bom-delta ${deltaClass}">Δ ${deltaPct}%</span>
  </div>
  ```
- CSS: `.bom-cost-comparison` com 3 colunas no grid, destaque no delta se > 5%

**Testes:**
- E2E: Verificar se `.bom-cost-comparison` aparece no modal de composição
- Verificar se delta < 5% está verde e > 5% está laranja

**Critério de aceite:** Usuário vê divergência entre soma do BOM e custo oficial da composição.

---

### 1.5 Busca Dentro do BOM

**Frontend** (`modules/modal.js`, `dom.js`, CSS):
- Adicionar input de busca no header da BOM section (client-side)
- `dom.js`: `dom.bomSearchInput`, `dom.bomSearchContainer`
- No `show()`, após renderizar BOM, adicionar listener de input que filtra `rows` por `descricao || item_codigo`
- CSS: mantém `display: none` nos cards/rows que não match

**Critério de aceite:** Usuário digita "cimento" na busca do BOM e vê apenas os cards/linhas que contêm "cimento".

---

### 1.6 Exportar Gráfico de Histórico como PNG

**Frontend** (`modules/modal.js`, `dom.js`):
- Adicionar botão "Exportar Gráfico" acima do canvas `#historyChart`
- No click: `dom.historyChart.toDataURL('image/png')` → `utils.downloadAsFile()`
- Reutilizar `utils.downloadAsFile()` que já existe para export search

**Critério de aceite:** Usuário clica "Exportar Gráfico" e baixa PNG do chart.

---

## Sprint 1b — Médio Esforço (dias 3-4)

### 1.7 Histórico de Manutenção (Lifecycle do Item)

**Backend**:
- Novo schema `HistoricoManutencao` em `schemas.py`:
  ```python
  class HistoricoManutencao(BaseModel):
      item_codigo: int
      tipo_item: str
      data_referencia: date
      tipo_manutencao: str
      descricao_item: Optional[str]
  ```
- Nova função `get_manutencoes_historico()` em `crud.py`:
  ```python
  def get_manutencoes_historico(db: Session, codigo: int, tipo_item: str):
      query = text("""
          SELECT item_codigo, tipo_item, data_referencia,
                 tipo_manutencao, descricao_item
          FROM manutencoes_historico
          WHERE item_codigo = :codigo AND tipo_item = :tipo_item
          ORDER BY data_referencia DESC
      """)
      return db.execute(query, {"codigo": codigo, "tipo_item": tipo_item}).fetchall()
  ```
- Novo endpoint `GET /api/v1/public/item/{tipo}/{codigo}/manutencoes`
- Cache: sim (24h, raramente muda)

**Frontend**:
- `modules/modal.js`: Nova aba/section "Histórico de Manutenção" no modal
- Timeline visual: cada entrada com `data_referencia`, badge `tipo_manutencao` (ATIVACAO verde / DESATIVACAO vermelha), `descricao_item`
- Se vazio, mostrar "Sem histórico de manutenção"

**Critério de aceite:** Usuário vê timeline de ativações/desativações de insumos no modal.

---

### 1.8 Curva ABC Agrupada por Classificação

**Backend**:
- Nova função `get_abc_by_classificacao()` em `crud.py` — reusa `get_abc_curve_for_composicoes()` CTE + GROUP BY `i.classificacao`:
  ```sql
  WITH bom_expanded AS (...)
  SELECT i.classificacao,
         SUM(bom.custo_impacto_total) as custo_total,
         COUNT(DISTINCT bom.insumo_filho_codigo) as total_items
  FROM bom_expanded bom
  JOIN insumos i ON i.codigo = bom.insumo_filho_codigo
  GROUP BY i.classificacao
  ORDER BY custo_total DESC
  ```
- Novo schema `AbcPorClassificacao` em `schemas.py`
- Novo endpoint `POST /bi/curva-abc/por-classificacao` (mesmo body + query params)

**Frontend**:
- `modules/abc.js`: Novo toggle "Agrupar por Classificação"
- Quando ativo: chama novo endpoint, renderiza stacked bar chart com cores por classificação + tabela com `classificacao`, `custo_total`, `total_items`, `%`
- Chart: bar chart simples em vez de bar+line (não faz sentido % acumulado por nome de categoria)

**Critério de aceite:** Usuário vê "CONCRETO: 40% do custo total" em vez de itens individuais.

---

### 1.9 Seção Admin: UI de População do Banco

**Frontend** (novo módulo `modules/admin.js`):
- Factory: `createAdmin(config, state, dom, utils, api, toast)`
- Nova section no `index.html` (oculta por padrão, visível apenas em dev ou via `?admin=true`):
  ```html
  <section id="admin" class="tool-section hidden">
    <h2>Administração — População do Banco</h2>
    <form id="adminForm">
      <input type="number" id="adminYear" placeholder="Ano (ex: 2024)">
      <input type="number" id="adminMonth" placeholder="Mês (ex: 1-12)">
      <select id="adminUf"><option value="">Todas as UFs</option></select>
      <button type="submit">Iniciar Carga</button>
    </form>
    <div id="adminTaskStatus">
      <pre id="adminTaskResult"></pre>
    </div>
  </section>
  ```
- `api.js`: Adicionar `triggerPopulation(year, month, uf)` e `checkTaskStatus(taskId)`
- `events.js`: Wires admin form submit + task polling a cada 3s

**Backend:** Endpoints já existem (`POST /admin/populate-database`, `GET /admin/tasks/{task_id}`)

**Critério de aceite:** Admin pode disparar ETL e ver progresso em tempo real.

---

## Sprint 1c — Alto Esforço / Futuro (dias 5+)

### 1.10 Dashboard de Volatilidade por Categoria

Nova seção "Tendências" com:
- Agregação de `precos_insumos_mensal` por `classificacao` ao longo do tempo
- Line chart com múltiplas séries (uma por classificação)
- Tabela de inflação acumulada por categoria

**Backend:** Novo endpoint agregado, cache 24h.
**Frontend:** Novo módulo `modules/trends.js`, nova section no HTML.

### 1.11 Mapa de Calor Regional

Integração Leaflet/Mapbox para visualização geográfica de preços.

**Backend:** Novo endpoint que retorna preço de um item em TODAS as UFs (não só selecionadas).
**Frontend:** Novo módulo `modules/heatmap.js`, dependência Leaflet via CDN.

### 1.12 Comparação Cruzada de Composições

Side-by-side BOM de duas composições.

**Frontend:** Novo módulo `modules/comparison.js`, seleção de 2 composições, tabela comparativa com delta, radar chart.
**Backend:** Reusa `get_composicao_bom()` — tudo client-side.

---

## Resumo de Esforço

| ID | Feature | Backend | Frontend | Testes | Total |
|----|---------|---------|----------|--------|-------|
| 1.1 | Classificação badge + filtro | 3h | 3h | 1h | **7h** |
| 1.2 | Grupo badge + filtro | 2h | 2h | 1h | **5h** |
| 1.3 | Status indicator | 1h | 2h | 0.5h | **3.5h** |
| 1.4 | Custo BOM vs Oficial | 0h | 2h | 0.5h | **2.5h** |
| 1.5 | Busca no BOM | 0h | 2h | 0.5h | **2.5h** |
| 1.6 | Exportar gráfico PNG | 0h | 1h | 0.5h | **1.5h** |
| 1.7 | Histórico manutenção | 4h | 3h | 1h | **8h** |
| 1.8 | ABC por classificação | 4h | 4h | 1h | **9h** |
| 1.9 | Admin population UI | 0h | 6h | 2h | **8h** |
| 1.10 | Volatilidade categoria | 6h | 6h | 2h | **14h** |
| 1.11 | Mapa calor regional | 4h | 10h | 2h | **16h** |
| 1.12 | Comparação cruzada | 0h | 8h | 2h | **10h** |
| **Total** | | **24h** | **49h** | **14h** | **87h** |

### Priorização Recomendada

```
Sprint 1a (20h): 1.1 → 1.2 → 1.3 → 1.4 → 1.5 → 1.6
Sprint 1b (25h): 1.7 → 1.8 → 1.9
Sprint 1c (40h): 1.10 → 1.11 → 1.12
```

---

## Verificação de Qualidade

Para cada feature, antes de considerar completa:

- [ ] Testes automatizados passam (`?runTests=true` ou `AutoSINAPITests.runAll()`)
- [ ] Funciona em dark mode e light mode
- [ ] Responsivo: testar em 375px, 768px, 1440px
- [ ] Teclado: Tab navigation + Enter/Space + Escape funciona
- [ ] Leitor de tela: ARIA labels corretas, `aria-live` para updates
- [ ] Console: zero `console.error` ou warnings não-capturados
- [ ] XSS: inputs do usuário passam por `utils.escapeHtml()`
- [ ] Semântica: elementos usam tags corretas (`<section>`, `<table>`, `<button>`)
