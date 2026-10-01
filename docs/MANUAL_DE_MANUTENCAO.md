# Manual de manutenção — autoSINAPI_API

> Para quem vai **mudar** este repo. O que fazer, o que não fazer, e por quê.
> O [README](../README.md) diz como usar; este diz como manter.
> Spec rules e ADRs vivem em [`docs/spec-rules/`](spec-rules/) e
> [`docs/adrs/`](adrs/) — **eles prevalecem** sobre qualquer atalho aqui.

---

## 1. A doutrina

Duas regras que explicam quase tudo o que mudou aqui nos últimos dias:

> **1. Só há sinal com FATO medido.** Achado vira claim de gate (comportamento
> contra o gateway real), não opinião em review.
>
> **2. Falhar alto e nomeado** (ADR 010): erro tem **código**, causa acionável e
> `correlation_id`. Ausência de dado **não** é erro — é resposta com envelope.

A regra 1 tem um custo que precisa ser respeitado: **um alarme sem evidência é
pior que nenhum alarme.** No AutoCUB um aviso de "dado provisório" acusava nossa
carga; a verificação na fonte provou que a série era oficial e o alarme foi
removido. A mesma disciplina vale aqui: se um detector acusar, ele carrega fato.

---

## 2. Mapa do código

```
api/
├── main.py          FastAPI (monolítico, ~1.000 linhas) — todas as rotas
├── crud.py          SQL e regras de leitura/escrita (~1.400 linhas) — o coração
├── schemas.py       Pydantic (respostas) — `Num` = Decimal→float na borda
├── search.py        pipeline de busca unificada (camadas + meta)
├── validation.py    ★ validação de entrada (BR_UFS, datas, tipo) — ADR 010
├── cache_utils.py   `cache_result` (Redis, fail-open) + serialização
└── tasks.py         tarefas Celery (ponte API → ETL)

tests/               42 arquivos (pytest). Roda no container (Postgres+Redis).
AutoSINAPI/          submódulo: o ETL (commitar em 2 repos, ver §7)
```

**Onde mexer:**

| Mudança | Arquivo |
|---|---|
| Novo endpoint | `api/main.py` (rotas por tier) + `schemas.py` |
| Regra de leitura / SQL | `api/crud.py` |
| Busca / ranqueamento | `api/search.py` + `api/crud.py` |
| Validação de entrada | `api/validation.py` |
| ETL (coleta CAIXA) | `AutoSINAPI/` (submódulo) |
| Documentação de contrato | `docs/spec-rules/`, `docs/adrs/` |

---

## 3. O contrato de resposta (invariantes)

Toda resposta de tool MCP tem **três estados** que nunca se confundem:

| Estado | HTTP | Corpo |
|---|---|---|
| **com dado** | 200 | a resposta + sinais (`versao_preco`, `preco_disponivel`…) |
| **sem dado** | 200 | envelope `{items: [], motivo, ...}` (ver MCP) |
| **erro** | 4xx/5xx | `detail` **prefixado por código** + `correlation_id` |

Invariantes com claim de gate:

1. Erro nomeado: `INVALID_UF: …`, `INVALID_DATE_REFERENCE: …`,
   `AUDIT_NOT_FOUND: … a última competência é 2021-12`. Nunca "não encontrado"
   genérico (ADR 010).
2. `valor`/`custo_total` **ausente é `null`**, nunca `0.0` (S-02). Preço
   indisponível vem com `preco_disponivel: false` + `motivo_indisponivel`.
3. `versao_preco` é a versão do **preço aplicado** (a linha consultada), com
   fallback por `data_referencia` quando o ETL não carimbou a coluna (§3.9);
   `sinapi_versao` do **cadastro** segue exposto (traceability).
4. Número é **JSON number**, nunca string (ADR 009 — `Num` nos schemas).
5. `correlation_id` em todo erro.
6. Recomendações/limites de produto **no description** da rota (o agente lê).

---

## 4. A evolução da campanha de auditoria (o que mudou e por quê)

Cada § é um achado verificado por comportamento. O **RED** foi o gate, o fix
tocou pouco código, e tudo virou claim permanente.

### 4.1 Busca e BI (os P0 — devolviam número plausível e errado)

| § | Defeito | Correção |
|---|---|---|
| **3.7** | `get_tendencias` devolvia variação **0.0 eterna** e `pct: null` | `_compute_variacao` passou a exigir `value_key` explícita; ausente → **erro**, nunca zero silencioso |
| **3.2** | ranking sem score real (tudo empatado) | score de relevância de fato: **prefixo na frente**, score em `[0,1]` |
| **3.3** | `vector=on` estourava timeout | camada vetorial sob **orçamento de tempo** + degradação graciosa (nunca timeout ao cliente) |
| **3.10** | `classificacao: null` no caminho de composição | composição espelha o `grupo` na faceta paralela (não inventa valor) |
| **3.1** | somar o BOM inteiro contava pai+filho (~4% a mais) | envelope com `custo_total_nivel1` + regra de somatório explícita (MCP) |

### 4.2 Sinalização de dado (o que protege o orçamento)

| § | Correção |
|---|---|
| **3.4** | composição sem preço sinaliza `preco_disponivel: false` (nunca "custo 0" como válido) |
| **3.5** | insumo de hora-homem devolve `1.0 HH` (o agente precisa da hora) |
| **3.6** | `percentual_mo` era `null` em 100% das linhas → calculado do BOM (split de produtividade) |
| **S-02** | preço ausente = **`null`** + motivo, envelope conta `total_itens_sem_preco` (Fase 6) |

### 4.3 ETL e frescor do dado

| § | Correção |
|---|---|
| **3.8** | lacuna 2026-01/02 fechada: **Smart Discovery sem recursão infinita** + reprocesso **com backup** |
| **3.9** | `versao_preco` = versão do preço aplicado (não a do cadastro) |

### 4.4 Fase 6 — certificação funcional (o que o laudo achou e o que era falso)

| § | Achado | Veredito medido |
|---|---|---|
| **S-01** | curva ABC devolvia só o 1º código | **parcial**: multi-código funcionava; o defeito real era **código órfão em silêncio** → agora erro nomeado |
| **S-03** | `uf:"XX"`, data futura → lista vazia | **real** → `validation.py`, erro nomeado com valor válido |
| **S-04** | `get_audit` "não encontrado" em item válido | **real** → o item tem evento em **outra data** → o 404 nomeia a última competência |
| **S-05** | rótulo dizia "insumo" para consulta de composição | **real (rótulo)** → rota com tipo no path + artigo correto |
| **S-02** | `valor: 0.0` sem aviso | **real** → ver 4.2 |

> **Lição registrada:** a "correção" pedida no laudo para o S-01 (trocar a curva
> por classificação) teria sido **regressão** — a medição desmentiu. É por isso
> que a regra 1 existe.

---

## 5. Como manter (receitas)

### 5.1 Adicionar um endpoint
1. Rota em `api/main.py` com `response_model` em `schemas.py` e `description`
   que **diga ao agente** formato, limites e o que "sem dado" significa.
2. Query em `api/crud.py` com `cache_result(ttl=…)` se for caro.
3. Valide entrada com `api/validation.py` (UF, `AAAA-MM`, tipo) — **antes** de
   tocar o banco.
4. Teste em `tests/`.
5. Spec rule correspondente em `docs/spec-rules/` se muda contrato público.

### 5.2 Adicionar/mudar um campo de resposta
- `Num` (não `Decimal`) em schemas — ADR 009.
- Ausência de dado: `Optional` + sinalizador, **nunca `0.0`** (regra 2 da §3).
- Se é dado de **preço**, versione (`versao_preco`).

### 5.3 Rodar a verificação (gate)
O gate vive na **casa** (`automation/scripts/verify_mcp_audit_claims.py`) e fala
com os 3 MCPs ao vivo:

```bash
# 1. flush das 3 camadas + Kong
for r in autosinapi_redis autocub_redis autoincc_redis; do
  docker exec $r redis-cli -n 0 FLUSHDB
done
REDIS_CONTAINER=api-gateway-redis bash stacks/autosinapi/kong/scripts/flush_cache.sh

# 2. rodar
python3 automation/scripts/verify_mcp_audit_claims.py   # exit 0 = verde
python3 automation/scripts/verify_mcp_docs_facts.py   # docs batem com o código?
```

### 5.4 Rodar os testes
```bash
docker exec autosinapi_api python -m pytest tests/ -q   # tem Postgres+Redis
```
`tests/test_post_schemas.py` (2 falhas pré-existentes sem infra) **exige** Redis e
Postgres — rode no container.

---

## 6. Armadilhas conhecidas

| Armadilha | O que fazer |
|---|---|
| **`_compute_variacao` sem `value_key`** | agora **levanta**; não reintroduza default silencioso (§3.7) |
| **`Decimal` em schema** | vira string no JSON. Use `Num` (ADR 009) |
| **`0.0` como "sem preço"** | nunca; use `null` + sinalizador (S-02) |
| **`cache_result` é fail-open** | Redis fora = **sem cache**, não erro. Ok por design |
| **ETL é submódulo** | mudança de ETL vai em `AutoSINAPI/` **e** no ponteiro deste repo (ver §7) |
| **`main.py` monolítico** | rotas por tier; mantenha a ordem e o `_MCP_SECTION` sincronizado (claim de docs) |
| **Spec rules** | `SPEC-RULE-SEARCH`, `MCP-05`… — mudá-las é decisão, não detalhe |

---

## 7. Regra do submódulo (ETL)

O núcleo de processamento vive em `AutoSINAPI/` (submódulo Git). Duas regras do
projeto:

1. **Mudança de ETL** → commita em `AutoSINAPI/` primeiro.
2. **Depois** commita o **ponteiro** do submódulo aqui.

```bash
cd AutoSINAPI && git commit -am "fix(etl): …" && cd ..
git add AutoSINAPI && git commit -m "chore(submodule): aponta para <sha>"
```

---

## 8. Referências

- **ADRs** (decisões que moldam o código): [`docs/adrs/`](adrs/) — em especial
  **004** (trigram), **005/006** (busca híbrida/vetorial), **008** (folhas do
  BOM), **009** (tipagem), **010** (fail-loud).
- **Spec rules:** [`docs/spec-rules/`](spec-rules/)
- **Story da campanha de auditoria:** [`docs/stories/STORY-SIN-095-auditoria-mcp-custo-p0.md`](stories/STORY-SIN-095-auditoria-mcp-custo-p0.md)
- **Contribuindo (badges de commit, branches):** [`CONTRIBUTING.md`](../CONTRIBUTING.md)
- **Manual equivalente do AutoCUB** (mesma doutrina, aplicada ao CUB):
  [`autocub_api/docs/MANUAL_DE_MANUTENCAO.md`](../../autocub_api/docs/MANUAL_DE_MANUTENCAO.md)