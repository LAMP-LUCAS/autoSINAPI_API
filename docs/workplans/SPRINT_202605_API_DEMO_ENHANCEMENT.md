# 🚀 Sprint: Aprimoramento da API e Demo — AutoSINAPI

**Período:** Maio 2026
**Objetivo:** Corrigir bugs, profissionalizar a API (cache, logging, health, migrations), implementar novos endpoints de BI, e concluir o mapa Leaflet no demo.
**Exclui:** Qualquer modificação no toolkit ETL (`AutoSINAPI/autosinapi/`).

---

## Arquitetura e Convenções

### Stack
- **Backend:** FastAPI + SQLAlchemy raw SQL + Redis cache + PostgreSQL
- **Frontend:** ES Modules + Dependency Injection (DI) + Chart.js + CSS `@layer`
- **Testes:** PyTest (API) + `tests.js` console-based (demo)

### Padrões (TDD, DRY, DDD)

1. **TDD para toda mudança backend:** Escrever teste → ver falhar → implementar → ver passar → refatorar
2. **DRY:** Nenhuma "magic string" em queries SQL — usar `config.py` e `settings` centralizado
3. **DI Wiring (`main.js`):** Todo módulo instanciado via factory pattern, nunca singletons
4. **API Layer (`api.js`):** Toda chamada HTTP passa por `api.request()`
5. **Cache Strategy:** Decorator `@cache_result` em `cache_utils.py`, TTL 24h para BI, 1h para stats
6. **Testes no demo:** Testar módulos via `AutoSINAPITests.runAll()`

---

## 📋 Fases

### Fase 1 — Correções Rápidas na API (~30min)

Prioridade máxima — bugs concretos que afetam segurança e estabilidade.

| # | Descrição | Arquivos | Critério de Aceite |
|---|---|---|---|
| 1.1 | CORS restrito: `["*"]` → lido de `ALLOWED_ORIGINS` env var | `api/main.py` | GET sem origin header falha, GET com origin autorizada passa |
| 1.2 | Limite de recursão ABC: adicionar `AND rec.nivel < 10` na CTE | `api/crud.py` | Query com dados circulares não estoura stack |
| 1.3 | Limite de recursão Man-Hours: idem | `api/crud.py` | Query com dados circulares não estoura stack |
| 1.4 | Trends: `timedelta(days=30*meses)` → `relativedelta(months=meses)` | `api/crud.py` | Datas de início/fim precisas por mês calendário |
| 1.5 | Filtros `classificacao`/`grupo` movidos do Python para o SQL | `api/main.py` | Busca com filtro não carrega todos os resultados em memória |

### Fase 2 — Profissionalização da API (~5h)

Melhorias estruturais para escalabilidade e observabilidade.

| # | Descrição | Arquivos | Critério de Aceite |
|---|---|---|---|
| 2.1 | Cache nos CRUDs básicos: aplicar `@cache_result` a `get_insumo_by_codigo`, `search_insumos_by_descricao`, `get_composicao_by_codigo`, `search_composicoes_by_descricao` | `api/crud.py` | Segunda chamada não executa SQL (cache hit) |
| 2.2 | Invalidação de cache: função `invalidate_cache(pattern)` que limpa chaves Redis por padrão | `api/cache_utils.py` | Após invalidate, chamada executa SQL fresco |
| 2.3 | Structured Logging (JSON): formatador com `timestamp`, `level`, `message`, `endpoint`, `duration` | `api/main.py` | Logs no stdout em formato JSON válido |
| 2.4 | Endpoint `/health`: retorna `{status, db, redis, uptime, version}` | `api/main.py` | `curl /health` retorna JSON com todos os campos |
| 2.5 | Cache tests: mock Redis com `fakeredis` ou fixture adequada | `tests/test_cache.py` | Testes passam sem Redis real |
| 2.6 | Alembic migrations: setup inicial + migration do schema atual | `api/` (alembic/) | `alembic upgrade head` cria tabelas corretas |

### Fase 3 — Novos Endpoints de BI (~4h)

| # | Descrição | Arquivos | Critério de Aceite |
|---|---|---|---|
| 3.1 | Produtividade: `GET /bi/composicao/{codigo}/produtividade` — classifica BOM em MO/Material/Equipamento, calcula custo/hh | `api/crud.py`, `api/schemas.py`, `api/main.py` | Endpoint retorna `{total_custo, mao_de_obra, material, equipamento, custo_por_hh}` |
| 3.2 | Where-Used: `GET /bi/insumo/{codigo}/onde-usado` — query reversa para todas as composições que usam um insumo | `api/crud.py`, `api/schemas.py`, `api/main.py` | Endpoint retorna lista de composições com código, descrição, coeficiente |

### Fase 4 — Mapa Leaflet no Demo (~3.5h)

| # | Descrição | Arquivos | Critério de Aceite |
|---|---|---|---|
| 4.1 | Leaflet CDN + container `#heatmapMap` no HTML | `demo/index.html` | Leaflet carrega sem erros de rede |
| 4.2 | GeoJSON do Brasil: 27 UFs simplificado em `demo/data/` | `demo/data/brazil-ufs.json` | Arquivo válido, cada feature tem `properties.uf` |
| 4.3 | `renderMap()`: mapa coroplético com cores, tooltip, legenda | `demo/js/modules/heatmap.js` | UF colorida por preço, tooltip ao hover, legenda visível |
| 4.4 | Cleanup no modal: `map.remove()` ao fechar | `demo/js/modules/modal.js` | Nenhum leak de memória após 10 aberturas/fechamentos |
| 4.5 | Fallback: bar chart se Leaflet não carregar | `demo/js/modules/heatmap.js` | Com Leaflet bloqueado, bar chart aparece |
| 4.6 | CSS responsivo: mapa se ajusta a mobile/desktop | `demo/css/12-utilities.css` | Mapa ocupa 100% da largura, altura proporcional |

### Fase 5 — Melhorias Finais no Demo (~1.5h)

| # | Descrição | Arquivos | Critério de Aceite |
|---|---|---|---|
| 5.1 | Comparison chart: agrupar por Material/MO/Equipamento em vez de INSUMO/COMPOSICAO | `demo/js/modules/comparison.js` | Gráfico mostra 3 barras agrupadas por composição |
| 5.2 | Quality checklist: verificar 8 itens para Sprint 1c | Manual | Todos os 8 itens OK |

---

## 📊 Resumo de Esforço

| Fase | Itens | Esforço | Complexidade |
|---|---|---|---|
| 1 — Correções rápidas | 5 | ~30min | 🔵 Baixa |
| 2 — Profissionalização | 6 | ~5h | 🟡 Média |
| 3 — Novos BI endpoints | 2 | ~4h | 🟡 Média |
| 4 — Mapa Leaflet | 6 | ~3.5h | 🟡 Média |
| 5 — Melhorias finais | 2 | ~1.5h | 🟢 Baixa |
| **Total** | **21** | **~14.5h** | |

---

## Dependências

```
Fase 1 (nenhuma) → Fase 2 (cache nos CRUDs precisa de cache_utils existente)
Fase 3 (nenhuma) → Fase 4 (leaflet, nenhuma)
Fase 5 (nenhuma)

Todas as fases são independentes do ETL (AutoSINAPI/).
```