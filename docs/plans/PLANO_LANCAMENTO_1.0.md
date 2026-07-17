# Plano de Lançamento: API v1.0.0 (AutoSINAPI)

## Objetivo
Elevar a AutoSINAPI API do status **beta** (última release `v0.3.0-beta.0`) para uma release **estável `v1.0.0`**, consolidando robustez de erros, observabilidade, defesa em profundidade de autenticação, cobertura de testes em CI e fixação do toolkit como dependência estável. O contrato `/api/v1` deve ser congelado: nenhuma *breaking change* sem um bump para `/api/v2`.

---

## Decisões de Escopo (confirmadas)
1. **Dados SINAPI permanecem públicos (demo).** Os endpoints `/api/v1/public/insumos`, `/api/v1/public/composicoes` e `/api/v1/public/bi/*` continuam sem `key-auth` no Kong, protegidos apenas por *rate-limiting*. Abuso é mitigado por limites de taxa, não por autenticação. Esta é uma decisão de produto, documentada em `docs/` e no `README.md`.
2. **Escopo de hardening = completo.** Inclui handler global de exceções, auth app-level nos endpoints admin, suíte de integração em CI com DB semeado, pin do submodule toolkit em tag de release, separação `/health` vs `/ready` e política de versionamento documentada.

---

## Definition of Done (v1.0.0)
- [ ] CI verde executando **suíte completa** (contract + integração) contra um DB de testes semeado, com threshold de cobertura (`pytest --cov`).
- [ ] Handler global de erro com **envelope único**; nenhum traceback exposto em respostas `500`.
- [ ] Endpoints `/api/v1/public/health` (liveness) e `/api/v1/public/ready` (readiness) distintos.
- [ ] Endpoints admin (`/api/v1/admin/*`) com **auth app-level** (defesa em profundidade), além do `key-auth` do Kong.
- [ ] Submodule `AutoSINAPI` fixado em uma **tag de release estável** (não em `develop`).
- [ ] Política de versionamento/estabilidade documentada (`docs/`).
- [ ] `version="1.0.0"` em `api/main.py`, `/health` e `/ready`; release `v1.0.0` publicada no GitHub.

---

## Convenções deste plano
- Cada fase vira 1+ commits no padrão do repositório: `tipo(escopo): STORY-XXX — descrição` (ex.: `feat(api): STORY-API-007 — ...`, `fix(sec): STORY-SEC-001 — ...`).
- Histórico de mudanças é gerado automaticamente pelo `release-drafter` (`.github/release-drafter.yml`) a partir dos commits.
- O release é disparado por tag `v*` (`.github/workflows/release.yml`).

---

## Fase 1 — Robustez de erros & observabilidade — `STORY-API-007`
**Arquivos-alvo:** `api/main.py`, `api/schemas.py`.

### 1.1 Handler global de exceções
- Registrar `@app.exception_handler(Exception)` que captura qualquer erro não tratado e retorna `500` **sanitizado**, sem traceback:
  ```json
  { "error": { "code": "internal_error", "message": "Erro interno. Consulte o request_id.", "request_id": "<uuid>" } }
  ```
- Registrar handler para `RequestValidationError` → `422` com o mesmo envelope (hoje o FastAPI devolve formato próprio).
- Normalizar `HTTPException` para o envelope único (já usa `detail`; padronizar para `{ "error": { "code": "<status>", "message": "<detail>" } }`).

### 1.2 `request_id` e correlação
- Injetar um `request_id` (UUID) no middleware de log existente (`api/main.py`, middleware `log_requests`) e propagá-lo no envelope de erro e no header de resposta `X-Request-ID`.

### 1.3 Liveness vs Readiness
- Manter `GET /api/v1/public/health` como **liveness** (DB/Redis degraded → `503`), conforme `api/main.py:176`.
- Adicionar `GET /api/v1/public/ready` como **readiness**, que além de DB/Redis valida também a disponibilidade do lock Redis de ETL (`redis_client` em `api/main.py:267`). Retorna `503` se qualquer dependência crítica indisponível.

**Critérios de aceitação:** nenhum `500` expõe stack trace; respostas de erro seguem o envelope; `/ready` distingue degradação de ETL de degradação de DB.

---

## Fase 2 — Defesa em profundidade de autenticação — `STORY-SEC-001`
**Arquivos-alvo:** `api/main.py`, `api/portal.py` (padrão de referência).

### 2.1 Auth app-level nos endpoints admin
- Rotas públicas (`/api/v1/public/*`) continuam sem auth (decisão demo da Fase de Escopo).
- `/api/v1/admin/populate-database` (`api/main.py:227`) e `/api/v1/admin/tasks/{task_id}` (`api/main.py:263`) já estão sob `key-auth` no Kong (`kong/kong.yml`, rota `sinapi-route`). Adicionar **verificação app-level** reusando o padrão de `api/portal.py:21`:
  ```python
  x_api_key: str = Header(..., alias="X-API-KEY")
  # validar contra saas.api_keys; 401 se inválido
  ```
- Assim, se a rede expuser o container `api` (hoje só na rede interna `sinapi-net`), o dano é limitado.

**Critérios de aceitação:** chamada aos endpoints admin sem `X-API-KEY` válido → `401` mesmo ignorando o Kong; rotas públicas continuam abertas.

---

## Fase 3 — Cobertura de testes & CI de integração — `STORY-QA-001`
**Arquivos-alvo:** `tests/conftest.py` (novo), `tests/fixtures/` (seed), `.github/workflows/ci.yml`.

### 3.1 Fixture de DB de testes + seed
- Criar `tests/conftest.py` com fixture de session/DB isolado (role/credentials de teste) e `tests/fixtures/` com um seed mínimo (SQL/CSV enxuto) cobrindo insumos, composições, BOM e auditoria para os testes de BI/traceability/cache.

### 3.2 CI executa a suíte completa
- Em `.github/workflows/ci.yml`, adicionar passo `docker compose exec -T api alembic upgrade head` (padrão já usado em `scripts/deploy_orchestrator.py:71`) antes dos testes.
- Rodar a **suíte inteira** no container `api` (já montado em `cfc8620`): contract + `test_cache.py`, `test_traceability_api.py`, `test_sandbox_integration.py`, `test_etl_integration.py`, `test_deploy_orchestrator.py` — contra o DB semeado.
- Gate de cobertura: `pytest --cov=api --cov-fail-under=<NN>` (limiar definido nesta fase).

**Critérios de aceitação:** CI verde com integração; cobertura mínima atingida; novos cenários de erro (Fase 1) cobertos por testes.

---

## Fase 4 — Pin do submodule toolkit — `STORY-INFRA-001`
**Arquivos-alvo:** `AutoSINAPI` (submodule), `.gitmodules`.

### 4.1 Release estável do toolkit
- Coordenar um release estável do toolkit AutoSINAPI (atualmente `v0.5.0-beta.0` no commit `b9deb00`). Ex.: `v0.5.0`.

### 4.2 Fixar o ponteiro
- Atualizar o submodule para a **tag de release** (hoje aponta para `develop`/`b9deb00`) e commitar:
  `chore(submodule): pin AutoSINAPI to v0.5.0`.
- Garantir que o checkout de release usa `submodules: recursive` (já presente em `release.yml` e `ci.yml`).

**Critérios de aceitação:** `git submodule status` aponta para um commit com tag; build de release reprodutível.

---

## Fase 5 — Documentação & política de versionamento
**Arquivos-alvo:** `docs/` (novo ou `docs/README.md`), `README.md`, `ROADMAP.md`.

### 5.1 Política de versionamento/estabilidade
- Documentar em `docs/`: sem *breaking change* no `v1` sem bump para `v2`; *deprecation policy* (mínimo de 1 minor de aviso); changelog contínuo via release-drafter.
- Atualizar `README.md` e `ROADMAP.md` com o status 1.0 e o aviso de que os dados são públicos por design (Fase de Escopo).

### 5.2 Artefato OpenAPI
- Gerar `openapi.json` via `scripts/generate_openapi.sh` e anexar como artefato da release (já validado por `test_openapi_generation.py`).

---

## Fase 6 — Release `v1.0.0`
**Arquivos-alvo:** `api/main.py`, `docs/`.

### 6.1 Bump de versão
- `fix(api): version 1.0.0` — `version="1.0.0"` em `api/main.py:116`, no `checks["version"]` de `/health` e em `/ready`.

### 6.2 Merge, tag e publicação
1. Merge `develop` → `main` (`chore(release): merge develop into main for v1.0.0`).
2. `git tag -a v1.0.0 -m "Release v1.0.0 — ..."`.
3. Push de `main`, `develop` e da tag → `release.yml` cria a GitHub Release com notas automáticas.
4. Validar inclusão do submodule pinned (checkout recursivo).
- Opcional: lançar `v1.0.0-rc.1` antes de `v1.0.0` para validação em staging.

---

## Ordem de execução sugerida
Fases **1 → 2 → 3** (qualidade) → **4** (infra) → **5** (docs) → **6** (release). Cada fase entrega valor incremental e pode ser mergeada em `develop` independentemente, mantendo o trunk sempre passível de release beta.

## Referências
- Gateway/rotas: `kong/kong.yml` (rota `sinapi-route` com `key-auth`; `public-demo-route` sem auth).
- Padrão de auth app-level: `api/portal.py:21`.
- CI atual: `.github/workflows/ci.yml` (passo de contract tests em `cfc8620`).
- Release: `.github/workflows/release.yml`, `.github/release-drafter.yml`.
- Migrations: `scripts/deploy_orchestrator.py:71` (`alembic upgrade head`).
