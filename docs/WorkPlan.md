# Plano de Trabalho da AutoSINAPI API — Status Atual

> **Data:** 22/05/2026
> **Repositório:** `repos/autosinapi_api`

---

## ✅ Funcionalidades Implementadas

### Básicas (CRUD)
| Endpoint | Descrição | Status |
|---|---|---|
| `GET /stats` | Volumetria do banco | ✅ Cache 1h |
| `GET /filters` | Filtros dinâmicos (UF, datas, regimes, classificações, grupos) | ✅ Cache 24h |
| `GET /insumos?q=&uf=&data_referencia=&regime=` | Busca insumos por descrição | ✅ Cache 1h, filtro `classificacao` no SQL |
| `GET /insumos/{codigo}` | Detalhe de insumo com preço contextual | ✅ Cache 1h |
| `GET /composicoes?q=&uf=&data_referencia=&regime=` | Busca composições por descrição | ✅ Cache 1h, filtro `grupo` no SQL |
| `GET /composicoes/{codigo}` | Detalhe de composição com custo contextual | ✅ Cache 1h |

### Business Intelligence (BI)
| Endpoint | Descrição | Status |
|---|---|---|
| `GET /bi/composicao/{codigo}/bom` | Bill of Materials recursivo | ✅ Cache 24h, limite `nivel < 10` |
| `GET /bi/composicao/{codigo}/hora-homem` | Total de Horas-Homem | ✅ Cache 24h, limite `nivel < 10` |
| `POST /bi/curva-abc` | Curva ABC (insumos por impacto) | ✅ Cache 24h, limite `nivel < 10` |
| `GET /bi/composicao/{codigo}/otimizar` | Top N insumos de maior impacto | ✅ Reusa BOM |
| `GET /bi/item/{tipo}/{codigo}/historico` | Histórico de preços/custos (12 meses) | ✅ Cache 24h |
| `GET /bi/item/{tipo}/{codigo}/manutencoes` | Histórico de manutenção | ✅ Cache 24h |
| `POST /bi/curva-abc/por-classificacao` | ABC agrupada por classificação | ✅ Cache 24h |
| `GET /bi/tendencias/por-classificacao` | Tendências por classificação | ✅ Cache 24h, `relativedelta` preciso |
| `GET /bi/item/{tipo}/{codigo}/precos-uf` | Preço em todas as 27 UFs | ✅ Cache 24h |
| **`GET /bi/composicao/{codigo}/produtividade`** | **Classifica BOM em MO/Material/Equipamento** | **✅ NOVO** |
| **`GET /bi/insumo/{codigo}/onde-usado`** | **Query reversa — composições que usam um insumo** | **✅ NOVO** |

### Administração
| Endpoint | Descrição | Status |
|---|---|---|
| `POST /admin/populate-database` | Dispara ETL (com lock via Redis) | ✅ |
| `GET /admin/tasks/{task_id}` | Status da tarefa Celery | ✅ |

### Infraestrutura
| Item | Descrição | Status |
|---|---|---|
| `GET /api/v1/public/health` | Health check (DB + Redis) | ✅ NOVO |
| Structured Logging (JSON) | Logs em JSON com `timestamp, endpoint, duration_ms` | ✅ NOVO |
| CORS configurável | `ALLOWED_ORIGINS` via env var | ✅ CORRIGIDO |
| Cache decorator | `@cache_result` com TTL configurável | ✅ |
| Invalidação de cache | `invalidate_cache(pattern)` com scan+cursor | ✅ NOVO |
| Alembic | `alembic/` — migrations com schema inicial + view | ✅ NOVO |

---

## 📋 Schemas Pydantic

| Schema | Campos |
|---|---|
| `Insumo` | codigo, descricao, unidade, preco_mediano, classificacao, status |
| `Composicao` | codigo, descricao, unidade, custo_total, grupo, status |
| `ComposicaoBOMItem` | item_codigo, tipo_item, nivel, descricao, unidade, coeficiente_total, custo_unitario, custo_impacto_total |
| `ComposicaoManHours` | total_hora_homem |
| `CurvaABCItem` | codigo, descricao, unidade, custo_total_agregado, percentual_individual, percentual_acumulado, classe_abc |
| `HistoricoCusto` | data_referencia, valor |
| `HistoricoManutencao` | item_codigo, tipo_item, data_referencia, tipo_manutencao, descricao_item |
| `AbcPorClassificacao` | classificacao, custo_total, percentual, total_insumos |
| `TendenciaClassificacao` | classificacao, mes, preco_medio, qtd_insumos |
| `PrecoPorUF` | uf, valor |
| **`ComposicaoProdutividade`** | **total_custo, mao_de_obra, material, equipamento, total_hh, custo_por_hh** |
| **`InsumoOndeUsado`** | **composicao_codigo, composicao_descricao, tipo_item, coeficiente, nivel** |

---

## 🔧 Arquitetura da API

### Dependências
- **Framework:** FastAPI + Uvicorn
- **ORM:** SQLAlchemy (raw SQL + text queries)
- **Cache:** Redis (decorator `@cache_result`)
- **Tarefas:** Celery + Redis (lock de ETL)
- **Migrations:** Alembic (`alembic/versions/001_initial_schema.py`)
- **Database:** PostgreSQL 14+

### Logging
Todos os logs em formato JSON:
```json
{"timestamp": "2026-05-21T22:27:38Z", "level": "INFO", "logger": "autosinapi.api", "message": "GET /api/v1/public/health 200", "endpoint": "/api/v1/public/health", "duration_ms": 4.21}
```

### Cache
- TTL padrão: 24h (86400s)
- TTL para CRUD de busca: 1h (3600s)
- Cache key: `cache:{func_name}:{sandbox}:{args}:{kwargs}`
- Invalidação: `invalidate_cache("cache:get_composicao_bom:*")`

### Segurança
- CORS configurável via env `ALLOWED_ORIGINS` (padrão `*`)
- Rate limiting via Kong Gateway externo (não implementado na API)

---

## 🔍 Health Check

```
GET /api/v1/public/health
```

Resposta (200 OK):
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "timestamp": "2026-05-21T22:27:38Z",
  "database": "connected",
  "redis": "connected"
}
```

Resposta (503 Degraded):
```json
{
  "status": "degraded",
  "version": "1.0.0",
  "timestamp": "2026-05-21T22:27:38Z",
  "database": "connected",
  "redis": "error: Connection refused"
}
```

---

## 📁 Estrutura de Arquivos

```
api/
├── main.py          # Endpoints + Structured Logging + Health + Static GeoJSON
├── crud.py          # Funções CRUD + BI (com @cache_result)
├── schemas.py       # Schemas Pydantic (12 schemas)
├── config.py        # Settings (env vars + constantes)
├── cache_utils.py   # @cache_result decorator + invalidate_cache()
├── database.py      # Conexão PostgreSQL (SessionLocal)
├── tasks.py         # Tarefas Celery (populate_sinapi_task)
├── celery_config.py # Config da fila Celery
└── sandbox_utils.py # Modo sandbox para tabelas isoladas
tests/
├── test_cache.py    # 4 testes de cache com mock
└── test_etl_integration.py  # 1 teste de integração ETL
alembic/
├── alembic.ini
├── env.py
├── script.py.mako
└── versions/
    └── 001_initial_schema.py  # Schema inicial (7 tabelas + view)
demo/
├── index.html       # Página demo (com Leaflet CDN)
├── data/
│   └── brazil-ufs.json  # GeoJSON IBGE (27 UFs, 1.1MB)
├── js/
│   ├── main.js      # Entry Point — DI Wiring
│   ├── state.js     # Estado centralizado
│   ├── dom.js       # Cache de elementos DOM
│   ├── api.js       # API Layer (fetch + error handling)
│   ├── events.js    # Event listeners
│   ├── utils.js     # Utilitários (escapeHtml, formatCurrency)
│   └── modules/
│       ├── search.js      # Pesquisa (Grid/List)
│       ├── abc.js          # Curva ABC (Chart.js)
│       ├── compare.js      # Comparativo Regional (Chart.js)
│       ├── modal.js        # Modal (BOM, histórico, heatmap)
│       ├── admin.js        # Admin UI (populate database)
│       ├── trends.js       # Tendências (Chart.js)
│       ├── heatmap.js      # Mapa Leaflet + bar chart fallback
│       └── comparison.js   # Comparação Cruzada (Chart.js)
├── css/
│   └── ... (11 arquivos CSS em @layer)
└── tests.js          # Testes de interface (console)
```

---

## 📄 Documentos Relacionados

| Documento | Conteúdo |
|---|---|
| `docs/SPRINT_ENRIQUECIMENTO.md` | Plano original das sprints 1a, 1b, 1c |
| `docs/workplans/SPRINT_202605_API_DEMO_ENHANCEMENT.md` | Plano de trabalho desta sessão (Fases 1-5) |
| `docs/workplans/SPRINT_202605_AUTOSINAPI_PROFESSIONALIZATION.md` | Sprint de profissionalização da API |
| `docs/plans/SPRINT_HEATMAP_LEAFLET.md` | Plano do mapa Leaflet |
| `AutoSINAPI/docs/SPRINT_ETL_ENRICHMENT.md` | **Sprint do ETL — pendente (outra sessão)** |
| `AutoSINAPI/docs/DataModel.md` | Modelo de dados do toolkit |