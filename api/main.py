# api/main.py (versão refatorada e com endpoints de BI)
"""
Ponto de entrada principal da AutoSINAPI API.

Este módulo define todos os endpoints da API utilizando FastAPI,
orquestrando as chamadas para as funções do módulo `crud` e utilizando os
`schemas` para validação e serialização de dados.
"""

import os
import json
import time
import secrets
import logging
import redis
from celery.result import AsyncResult
from .sandbox_utils import is_sandbox_mode
from typing import List, Optional
from contextlib import asynccontextmanager
try:
    import sentry_sdk
except ImportError:
    sentry_sdk = None
try:
    from prometheus_fastapi_instrumentator import Instrumentator
except ImportError:
    Instrumentator = None
try:
    from prometheus_client import Gauge
except ImportError:
    Gauge = None
from fastapi import FastAPI, Depends, HTTPException, Query, Path, Request, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.orm import Session
from datetime import date, datetime
from dateutil.relativedelta import relativedelta

from . import crud, schemas, config, populate_utils
from . import search as search_pipeline
from .database import get_db
from .tasks import populate_sinapi_task
from .cache_utils import redis_client as cache_redis
from .portal import router as portal_router
from .legal_service import get_legal_document
import threading

# Carrega as configurações uma vez
settings = config.settings

# Structured Logging
class JSONLogFormatter(logging.Formatter):
    def format(self, record):
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "endpoint"):
            log_entry["endpoint"] = record.endpoint
        if hasattr(record, "duration"):
            log_entry["duration_ms"] = round(record.duration * 1000, 2)
        if record.exc_info and record.exc_info[0]:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry, ensure_ascii=False)

# Configure root logger with JSON format
json_handler = logging.StreamHandler()
json_handler.setFormatter(JSONLogFormatter())
root_logger = logging.getLogger()
root_logger.handlers = [json_handler]
root_logger.setLevel(logging.INFO)

logger = logging.getLogger("autosinapi.api")

# ── Documentação consolidada de autenticação, rate limits e erros ──
# Contrato do gateway Kong (não do FastAPI). Os números de rate limit espelham
# kong/plans.yaml (SSOT canônico dos planos). A API NÃO importa de `stacks/`
# (GUIDE-development.md 1.2); apenas documenta o contrato exposto pelo Kong.
_AUTH_SECTION = (
    "## Autenticação\n"
    "Endpoints em `/api/v1/public/*` são públicos (sem chave) com rate limit de demonstração "
    "(15 req/min, 300 req/hour). Envie o header `X-API-KEY` para elevar o limite conforme o plano:\n"
    "- **Starter**: 600 req/min (fila compartilhada, insumos + composições)\n"
    "- **Pro**: 3.000 req/min (fila prioritária, + BOM e Análise BI)\n"
    "- **Business**: 10.000 req/min (fila dedicada, + endpoints exclusivos)\n\n"
)
_ERROR_SECTION = (
    "## Códigos de Erro (retornados pelo gateway Kong)\n"
    "- `401` API key ausente/inválida\n"
    "- `402` assinatura inativa/expirada\n"
    "- `429` rate limit excedido\n\n"
)
_TIER_SECTION = (
    "## Tiers de Endpoint (disponibilidade por plano)\n"
    "- `tier_1` (leve): health, stats, filters, insumos, composições — Starter/Pro/Business\n"
    "- `tier_2` (pesado/BI): BOM, curva-abc, tendências, precos-uf — Pro/Business\n"
    "- `tier_3` (exclusivo): Business\n\n"
)
_MCP_SECTION = (
    "## Integração com Agentes de IA (Model Context Protocol)\n\n"
    "O AutoSINAPI expõe suas tools via MCP (Model Context Protocol). "
    "Conecte seus agentes de IA (Claude, Cursor, VSCode, OpenCode, Hermes, OpenClaw) "
    "diretamente ao motor de dados do SINAPI.\n\n"
    "### Endpoint SSE\n"
    "`https://mcp.autosinapi.mundoaec.com/sse`\n\n"
    "### Autenticação\n"
    "Header `X-API-KEY`. Sem chave → modo demonstração (15 req/min). "
    "Com chave válida → rate limit do plano.\n\n"
    "### Tools disponíveis\n"
    "- **Tier 1** (todas os planos): sinapi_health, sinapi_portal_me, sinapi_stats, sinapi_filters, "
    "sinapi_search_insumos, sinapi_get_insumo, sinapi_search_composicoes, sinapi_get_composicao\n"
    "- **Tier 2** (Pro+): sinapi_get_bom, sinapi_get_hora_homem, sinapi_get_curva_abc, "
    "sinapi_get_curva_abc_classificacao, sinapi_get_tendencias, sinapi_get_precos_uf, "
    "sinapi_get_produtividade, sinapi_get_onde_usado, sinapi_get_historico, sinapi_get_manutencoes, sinapi_get_audit\n\n"
    "### Clientes suportados\n"
    "Consulte o [Developer Portal](https://mundoaec.com/dev/api#mcp-agents) para snippets de configuração "
    "de cada cliente (Claude Desktop, Cursor, OpenCode, VSCode, OpenAI Codex, Hermes, OpenClaw).\n\n"
    "### Exemplo de conexão (curl)\n"
    "```bash\n"
    "curl -N https://mcp.autosinapi.mundoaec.com/sse \\\n"
    "  -H \"X-API-KEY: SUA_CHAVE_AQUI\"\n"
    "```\n"
)
# SSOT da documentação de auth/erros/rate-limits exibida no Swagger (consolidada).
_AUTH_DOCS = _AUTH_SECTION + _ERROR_SECTION + _TIER_SECTION + _MCP_SECTION

# Respostas de erro retornadas pelo gateway Kong + plugin ssl-mp-adapter.
# SSOT do contrato de erro reutilizada por todos os endpoints (coesão/DRY).
# Definidas em schemas.py para evitar import circular com portal.py.
from .schemas import (
    _AUTH_RESPONSES,
    _RATE_LIMIT_RESPONSE,
    _NOT_FOUND_404,
    _BAD_REQUEST_400,
    _CONFLICT_409,
    _SERVER_ERROR_500,
    _SERVICE_UNAVAILABLE_503,
)

# Monitoramento da base disponível × consumida (ADR-034 / SPEC-RULE B3-B4):
# funções puras do módulo compartilhado (DRY — também usado pelo kong watcher).
from .sinapi_disponibilidade import (
    expected_latest_competence,
    discover_available_base,
    resolve_status,
)

# Composições de `responses` reutilizando a SSOT de contrato de erro em
# schemas.py (coesão/DRY, STORY-API-006). Aplicadas apenas nos endpoints que de
# fato levantam cada código no código FastAPI.
_PUBLIC_NOT_FOUND = {**_RATE_LIMIT_RESPONSE, "404": _NOT_FOUND_404}
_PUBLIC_VALIDATED = {**_RATE_LIMIT_RESPONSE, "404": _NOT_FOUND_404, "400": _BAD_REQUEST_400}
_POPULATE_RESPONSES = {**_AUTH_RESPONSES, "409": _CONFLICT_409, "500": _SERVER_ERROR_500}
_HEALTH_RESPONSES = {**_RATE_LIMIT_RESPONSE, "503": _SERVICE_UNAVAILABLE_503}

app = FastAPI(
    title="AutoSINAPI API",
    description=(
        "API para consulta de preços, custos, estruturas e análises da base de dados SINAPI.\n\n"
        + _AUTH_DOCS
    ),
    version="0.4.0-beta.0",
)

# Injeta o securityScheme ApiKeyAuth (X-API-KEY) no schema OpenAPI para o
# botão "Authorize" do Swagger UI, sem impor autenticação no FastAPI.
from fastapi.openapi.utils import get_openapi

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    schema.setdefault("components", {}).setdefault("securitySchemes", {})["ApiKeyAuth"] = {
        "type": "apiKey",
        "in": "header",
        "name": "X-API-KEY",
        "description": (
            "Chave de API da assinatura (Starter / Pro / Business). Opcional: "
            "endpoints /api/v1/public/* são acessíveis sem chave (rate limit de "
            "demonstração: 15 req/min, 300 req/hour). Com X-API-KEY válido os limites "
            "sobem conforme o plano onde aplicável."
        ),
    }
    app.openapi_schema = schema
    return app.openapi_schema

app.openapi = custom_openapi


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS.split(",") if settings.ALLOWED_ORIGINS != "*" else ["*"],
    allow_credentials=settings.ALLOWED_ORIGINS != "*",
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static GeoJSON data
import os
_data_dir = os.path.join(os.path.dirname(__file__), "..", "demo", "data")
if os.path.isdir(_data_dir):
    app.mount("/api/v1/public/data/geo", StaticFiles(directory=_data_dir), name="data")

app.include_router(portal_router)

# ── Métricas Prometheus (consumido pelo Netdata go.d prometheus collector) ──
if Instrumentator is not None:
    instrumentator = Instrumentator(
        should_group_status_codes=False,
        should_ignore_untemplated=True,
        excluded_handlers=["/metrics"],
    ).instrument(app)
else:
    instrumentator = None
    logger.warning("prometheus-fastapi-instrumentator not installed; /metrics disabled")

# ── Gauge de quota utilizada por assinatura (STORY-GOLIVE-03 / REGRA 8) ──
if Gauge is not None:
    QUOTA_GAUGE = Gauge(
        "autosinapi_quota_usage_ratio",
        "Uso percentual da cota mensal por assinatura ativa",
        ["client", "plan"],
    )
else:
    QUOTA_GAUGE = None
    logger.warning("prometheus_client not installed; quota gauge disabled")


def _init_sentry():
    if settings.SENTRY_DSN and sentry_sdk is not None:
        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            environment=settings.SENTRY_ENV,
            traces_sample_rate=0.1,
        )
        logger.info("Sentry initialized (env=%s)", settings.SENTRY_ENV)


def _update_quota_gauges(stop_event: threading.Event):
    from sqlalchemy import text as sa_text
    from .database import SessionLocal

    while not stop_event.is_set():
        try:
            db = SessionLocal()
            rows = db.execute(
                sa_text(
                    """
                    SELECT
                        c.name AS client_name,
                        p.slug AS plan_slug,
                        COALESCE(
                            SUM(CASE WHEN ul.requested_at >= s.current_period_start
                                THEN 1 ELSE 0 END), 0
                        ) AS total_usage,
                        CAST(p.max_requests AS BIGINT) * 60 * 24 * p.duration_days AS monthly_quota
                    FROM saas.subscriptions s
                    JOIN saas.clients c ON s.client_id = c.id
                    JOIN saas.plans p ON s.plan_id = p.id
                    LEFT JOIN saas.api_keys ak ON s.id = ak.subscription_id
                    LEFT JOIN saas.usage_logs ul ON ak.id = ul.api_key_id
                    WHERE s.status = 'active'
                    GROUP BY c.name, p.slug, p.max_requests, p.duration_days
                    """
                )
            ).fetchall()

            if QUOTA_GAUGE is not None:
                QUOTA_GAUGE.clear()
                for row in rows:
                    pct = (row.total_usage / row.monthly_quota * 100) if row.monthly_quota > 0 else 0.0
                    QUOTA_GAUGE.labels(client=row.client_name, plan=row.plan_slug).set(pct)
        except Exception:
            logger.warning("Quota gauge update failed (DB likely unavailable)", exc_info=True)
        finally:
            db.close()
        stop_event.wait(60)


# ── Startup event (Sentry, metrics, background gauge) ──
@app.on_event("startup")
async def _on_startup():
    if instrumentator is not None:
        instrumentator.expose(app)
    _init_sentry()
    if QUOTA_GAUGE is not None:
        stop_ev = threading.Event()
        thr = threading.Thread(target=_update_quota_gauges, args=(stop_ev,), daemon=True)
        thr.start()
        logger.info("Gauge updater thread started")


# ── Admin auth dependency (STORY-GOLIVE-03) ──
def verify_admin_token(authorization: str = Header(None)):
    """FastAPI dependency: verify Bearer ADMIN_API_TOKEN."""
    if not settings.ADMIN_API_TOKEN:
        raise HTTPException(status_code=500, detail="ADMIN_API_TOKEN not configured")
    token_prefix = "Bearer "
    if not authorization or not authorization.startswith(token_prefix):
        raise HTTPException(
            status_code=401, detail="Missing or invalid Authorization header"
        )
    token = authorization[len(token_prefix):]
    if not secrets.compare_digest(token, settings.ADMIN_API_TOKEN or ""):
        raise HTTPException(status_code=401, detail="Invalid admin token")


# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration = time.time() - start
    extra = {"endpoint": request.url.path, "duration": duration}
    logger.info(f"{request.method} {request.url.path} {response.status_code}", extra=extra)
    return response

@app.get("/api/v1/public/health", tags=["tier_1", "Health"], summary="Verificar health check da API", response_description="Status do serviço, banco e Redis.", responses=_HEALTH_RESPONSES)
@app.get("/api/v1/sinapi/health", tags=["tier_1", "Health"], include_in_schema=False)
def health_check(db: Session = Depends(get_db)):
    """
    Health check endpoint. Retorna status do banco, Redis e versão da API.

    Contrato canônico do ecossistema Mundoaec: `GET /api/v1/sinapi/health`
    (alias do legado `/api/v1/public/health`).

    Latência: `max_data_referencia` faz full scan (~400 ms) na tabela de preços
    e dominava o tempo de resposta. Aqui ele é memoizado por `_HEALTH_TTL_S`
    (janela curta), mantendo o health barato (< 300 ms) sem alterar o contrato
    observável — o valor é exatamente o que `_get_max_data_referencia` retorna.
    """
    checks = {"status": "healthy",         "version": "0.4.0-beta.0", "timestamp": datetime.utcnow().isoformat() + "Z"}

    try:
        db.execute(text("SELECT 1"))
        checks["database"] = "connected"
    except Exception as e:
        checks["database"] = f"error: {str(e)}"
        checks["status"] = "degraded"

    try:
        cache_redis.ping()
        checks["redis"] = "connected"
    except Exception as e:
        checks["redis"] = f"error: {str(e)}"
        checks["status"] = "degraded"

    # B4.2: expõe a competência máxima consumida (YYYY-MM) para comparabilidade
    # direta com a base disponível (ADR-034). Memoizado (TTL curto).
    checks["max_data_referencia"] = _get_max_data_referencia_cached(db)

    status_code = 200 if checks["status"] == "healthy" else 503
    return JSONResponse(content=checks, status_code=status_code)


_HEALTH_TTL_S = 30


def _is_production_session(db: Session) -> bool:
    """True quando a sessão pertence ao engine de produção (SessionLocal).

    Testes injetam sessões fake via `dependency_overrides[get_db]`; para elas o
    health NUNCA usa cache, garantindo que o valor reflita o DB do teste
    (contrato observável de `max_data_referencia`).
    """
    try:
        from .database import engine
        return db.get_bind() is engine
    except Exception:
        return False


def _get_max_data_referencia_cached(db: Session) -> Optional[str]:
    """`_get_max_data_referencia` com memoização curta (evita full scan por request).

    O cache só vale para o engine de produção; sessões de teste sempre consultam
    o banco, preservando o contrato observável.
    """
    if not _is_production_session(db):
        return _get_max_data_referencia(db)

    now = time.time()
    cached = _max_ref_cache["value"]
    if cached is not None and (now - _max_ref_cache["at"]) < _HEALTH_TTL_S:
        return cached["v"]

    value = _get_max_data_referencia(db)
    if value is not None:
        _max_ref_cache["at"] = now
        _max_ref_cache["value"] = {"v": value}
    return value


_max_ref_cache: dict = {"at": 0.0, "value": None}


def _get_max_data_referencia(db: Session) -> Optional[str]:
    """Competência máxima consumida (max data_referencia em precos_insumos_mensal).

    Retorna no formato 'YYYY-MM' (ex.: '2026-06') ou None se a base estiver
    vazia/indisponível. Nunca levanta: health/base não podem quebrar por erro
    de consulta (resiliência, ADR-034).
    """
    try:
        row = db.execute(text("SELECT max(data_referencia) FROM precos_insumos_mensal")).first()
        if row is None or row[0] is None:
            return None
        max_data = row[0]
        if hasattr(max_data, "isoformat"):
            return max_data.isoformat()[:7]
        return str(max_data)[:7]
    except Exception:
        return None


@app.get("/api/v1/public/base", tags=["tier_1", "Health"], summary="Verificar base disponível vs consumida", response_description="Compara a competência disponível (calendário/probe) com a consumida (max da base).", responses=_HEALTH_RESPONSES)
def base_availability(db: Session = Depends(get_db)):
    """
    Compara a base disponível × consumida (ADR-034 B4.1).

    - `available_base`: competência disponível (calendário de publicação,
      confirmada por probe quando possível — B2.2/B4.3);
    - `consumed_base`: `max(data_referencia)` da tabela de preços (YYYY-MM);
    - `status`: `current` | `new-base-available` | `unknown`;
    - `sources`: cadeia de fontes consultadas (calendar, portal, ...);
    - `as_of`: timestamp da resposta.
    """
    consumed_base = _get_max_data_referencia(db)
    # O endpoint é síncrono e público: usar o calendário como fonte (B2.1) sem
    # probe de rede por requisição (latência + risco de 429; o probe é feito
    # pelo kong watcher com cache TTL — DRY, ADR-034 R2.4).
    available_base, source, sources = discover_available_base(
        probe_fn=lambda c: False
    )
    status = resolve_status(available_base, consumed_base)

    return JSONResponse(content={
        "available_base": available_base,
        "consumed_base": consumed_base,
        "status": status,
        "source": source,
        "sources": sources,
        "as_of": datetime.utcnow().isoformat() + "Z",
    })

# Conexão direta com Redis para lock de tarefas (idempotência)
redis_client = redis.Redis(host=os.getenv("REDIS_HOST", "autosinapi_redis"), port=6379, db=0)

@app.get("/api/v1/public/stats", tags=["tier_1", "Public"], summary="Obter estatísticas do banco de dados", response_description="Volumetria geral do banco de dados SINAPI.", responses=_RATE_LIMIT_RESPONSE)
def get_database_stats(db: Session = Depends(get_db)):
    """
    Retorna estatísticas de volumetria do banco de dados.
    """
    return crud.get_global_stats(db)

@app.get("/api/v1/public/filters", tags=["tier_1", "Public"], summary="Obter filtros dinâmicos disponíveis", response_description="Filtros dinâmicos (UFs, datas, regimes, classificações, grupos).", responses=_RATE_LIMIT_RESPONSE)
def get_filters(
    tipo: str = Query(None, description="Filtrar por tipo: 'insumo' (retorna classificacoes) ou 'composicao' (retorna grupos)."),
    db: Session = Depends(get_db)
):
    """
    Retorna os filtros dinâmicos disponíveis no banco.
    Opcionalmente filtra por tipo para retornar classificações ou grupos.
    """
    result = crud.get_available_filters(db)
    if tipo == 'insumo':
        result.pop('grupos', None)
    elif tipo == 'composicao':
        result.pop('classificacoes', None)
    return result

@app.get("/api/v1/public/legal/{doc_name}", tags=["tier_1", "Public"], summary="Obter documento legal preenchido (SSOT)", response_description="Documento legal (LGPD, TOS, Reembolso, SINAPI) populado com dados corporativos.", responses=_RATE_LIMIT_RESPONSE)
def get_legal_doc(doc_name: str):
    """
    Retorna o documento legal solicitado (privacidade, tos, reembolso, sinapi)
    populado dinamicamente com os dados do SSOT (CNPJ, Razão Social, DPO, etc.).
    """
    try:
        return get_legal_document(doc_name)
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=404, detail=str(e))

# --- Endpoints de Administração ---

@app.post("/api/v1/admin/populate-database", status_code=202, tags=["tier_1", "Admin"], summary="Disparar população da base de dados", response_description="Tarefa de ETL enfileirada para processamento assíncrono.", responses=_POPULATE_RESPONSES)
def trigger_database_population(
    payload: schemas.PopulateDatabaseRequest,
    _auth=Depends(verify_admin_token),
):
    """Dispara ETL para um mês/ano/UF. Lock via Redis (idempotente)."""
    result = populate_utils.dispatch_populate(payload.year, payload.month, payload.state)
    if result is None:
        raise HTTPException(
            status_code=409,
            detail=f"Já existe uma tarefa em andamento para {payload.state.upper()} {payload.month:02d}/{payload.year}."
        )
    return result

@app.get("/api/v1/admin/tasks/{task_id}", tags=["tier_1", "Admin"], summary="Verificar status de tarefa Celery", response_description="Status e resultado da tarefa Celery.", responses=_AUTH_RESPONSES)
def get_task_status(task_id: str, _auth=Depends(verify_admin_token)):
    """Verifica o status e resultado de uma tarefa Celery."""
    result = AsyncResult(task_id, app=populate_sinapi_task.app)
    return {
        "task_id": task_id,
        "status": result.status,
        "ready": result.ready(),
        "result": str(result.result) if result.ready() else None
    }



@app.get("/", tags=["tier_1", "Root"], summary="Exibir mensagem de boas-vindas", response_description="Mensagem de boas-vindas da API.", responses=_AUTH_RESPONSES)
def read_root():
    return {"message": "Bem-vindo à API AutoSINAPI. Acesse /docs para a documentação interativa."}


# --- Endpoints de Insumos ---

@app.get("/api/v1/public/insumos/{codigo}", response_model=schemas.Insumo, tags=["tier_1", "Insumos"], summary="Consultar insumo por código e contexto", response_description="Insumo e seu preço no contexto (UF, data, regime).", responses=_PUBLIC_NOT_FOUND)
def read_insumo_by_codigo(
    codigo: int,
    uf: str = Query(..., description="Unidade Federativa (UF). Ex: SP", min_length=2, max_length=2, examples={"exemplo": {"value": "SP"}}),
    data_referencia: str = Query(..., description="Data de referência no formato AAAA-MM. Ex: 2025-09", examples={"exemplo": {"value": "2025-09"}}),
    regime: str = Query("NAO_DESONERADO", description="Regime de preço.", examples={"exemplo": {"value": "NAO_DESONERADO"}}),
    db: Session = Depends(get_db)
):
    """
    Obtém um insumo específico e seu preço para um determinado contexto.
    """
    db_insumo = crud.get_insumo_by_codigo(db, codigo=codigo, uf=uf, data_referencia=data_referencia, regime=regime)
    if db_insumo is None:
        raise HTTPException(status_code=404, detail="Insumo não encontrado para os filtros especificados.")
    return db_insumo

def _search_response(result: dict, meta: bool) -> JSONResponse:
    """Empacota o resultado de busca.

    SPEC-RULE-SEARCH: sem `meta` → lista simples (retrocompatível) + header
    `X-Total-Count`; com `meta=true` → envelope `{items, total}`.
    """
    items, total = result.get("items", []), result.get("total", 0)
    payload = result if meta else items
    resp = JSONResponse(content=payload)
    resp.headers["X-Total-Count"] = str(total)
    return resp

@app.get("/api/v1/public/insumos", response_model=schemas.InsumoSearchResult, tags=["tier_1", "Insumos"], summary="Buscar insumos por descrição ou código", response_description="Lista paginada de insumos. `?meta=true` retorna envelope `{items, total}`; sem meta retorna lista simples e `X-Total-Count` no header.", responses=_RATE_LIMIT_RESPONSE)
def search_insumos(
    q: str = Query(..., min_length=3, description="Termo para buscar na descrição do insumo, ou código numérico exato."),
    uf: str = Query(..., description="Unidade Federativa (UF). Ex: SP", min_length=2, max_length=2, examples={"exemplo": {"value": "SP"}}),
    data_referencia: str = Query(..., description="Data de referência no formato AAAA-MM. Ex: 2025-09", examples={"exemplo": {"value": "2025-09"}}),
    regime: str = Query("NAO_DESONERADO", description="Regime de preço.", examples={"exemplo": {"value": "NAO_DESONERADO"}}),
    classificacao: str = Query(None, description="Filtrar por classificação do insumo. Ex: AGREGADOS, ACO, CONCRETO"),
    meta: bool = Query(False, description="true → envelope `{items, total}`; false → lista simples."),
    skip: int = 0, limit: int = 100, db: Session = Depends(get_db)
):
    """
    Busca insumos pela descrição (ranking trigram) ou código exato e retorna
    seus preços para um determinado contexto. Opcionalmente filtra por
    classificação.
    """
    result = crud.search_insumos_by_descricao(db, q=q, uf=uf, data_referencia=data_referencia, regime=regime, skip=skip, limit=limit, classificacao=classificacao)
    return _search_response(result, meta)


# --- Endpoints de Composições ---

@app.get("/api/v1/public/composicoes/{codigo}", response_model=schemas.Composicao, tags=["tier_1", "Composições"], summary="Consultar composição por código e contexto", response_description="Composição e seu custo no contexto informado.", responses=_PUBLIC_NOT_FOUND)
def read_composicao_by_codigo(
    codigo: int,
    uf: str = Query(..., description="Unidade Federativa (UF). Ex: SP", min_length=2, max_length=2, examples={"exemplo": {"value": "SP"}}),
    data_referencia: str = Query(..., description="Data de referência no formato AAAA-MM. Ex: 2025-09", examples={"exemplo": {"value": "2025-09"}}),
    regime: str = Query("NAO_DESONERADO", description="Regime de custo.", examples={"exemplo": {"value": "NAO_DESONERADO"}}),
    db: Session = Depends(get_db)
):
    """
    Obtém uma composição específica e seu custo para um determinado contexto.
    """
    db_composicao = crud.get_composicao_by_codigo(db, codigo=codigo, uf=uf, data_referencia=data_referencia, regime=regime)
    if db_composicao is None:
        raise HTTPException(status_code=404, detail="Composição não encontrada para os filtros especificados.")
    return db_composicao

@app.get("/api/v1/public/composicoes", response_model=schemas.ComposicaoSearchResult, tags=["tier_1", "Composições"], summary="Buscar composições por descrição ou código", response_description="Lista paginada de composições. `?meta=true` retorna envelope `{items, total}`; sem meta retorna lista simples e `X-Total-Count` no header.", responses=_RATE_LIMIT_RESPONSE)
def search_composicoes(
    q: str = Query(..., min_length=3, description="Termo para buscar na descrição da composição, ou código numérico exato."),
    uf: str = Query(..., description="Unidade Federativa (UF). Ex: SP", min_length=2, max_length=2, examples={"exemplo": {"value": "SP"}}),
    data_referencia: str = Query(..., description="Data de referência no formato AAAA-MM. Ex: 2025-09", examples={"exemplo": {"value": "2025-09"}}),
    regime: str = Query("NAO_DESONERADO", description="Regime de custo.", examples={"exemplo": {"value": "NAO_DESONERADO"}}),
    grupo: str = Query(None, description="Filtrar por grupo da composição. Ex: SERVICOS, ESTRUTURA, INSTALACOES"),
    meta: bool = Query(False, description="true → envelope `{items, total}`; false → lista simples."),
    skip: int = 0, limit: int = 100, db: Session = Depends(get_db)
):
    """
    Busca composições pela descrição (ranking trigram) ou código exato e retorna
    seus custos para um determinado contexto. Opcionalmente filtra por grupo.
    """
    result = crud.search_composicoes_by_descricao(db, q=q, uf=uf, data_referencia=data_referencia, regime=regime, skip=skip, limit=limit, grupo=grupo)
    return _search_response(result, meta)


# --- Endpoints de Busca Unificada (STORY-SRC-002 / "Google do SINAPI") ---

@app.get("/api/v1/public/search", response_model=schemas.UnifiedSearchResult, tags=["tier_1", "Search"], summary="Buscar insumos e composições", response_description="Busca unificada (insumo+composição) com ranking, sort e paginação server-side; `meta.providers`/`meta.degraded` expõem as camadas ativas e degradações.", responses=_RATE_LIMIT_RESPONSE)
def search_unified(
    q: str = Query(..., min_length=1, description="Termo para buscar em descrições de insumos e composições, ou código numérico exato."),
    uf: str = Query(..., description="Unidade Federativa (UF). Ex: SP", min_length=2, max_length=2, examples={"exemplo": {"value": "SP"}}),
    data_referencia: str = Query(..., description="Data de referência no formato AAAA-MM. Ex: 2025-09", examples={"exemplo": {"value": "2025-09"}}),
    regime: str = Query("NAO_DESONERADO", description="Regime de preço/custo.", examples={"exemplo": {"value": "NAO_DESONERADO"}}),
    tipo: str = Query("all", description="Filtrar tipo: `all`, `insumo` ou `composicao`.", examples={"exemplo": {"value": "all"}}),
    sort: str = Query("relevance", description="Ordenação: `relevance`, `price_asc`, `price_desc`, `name`.", examples={"exemplo": {"value": "relevance"}}),
    vector: str = Query("off", description="Camada vetorial: `auto`, `off` ou `<model_slug>`. Nesta fase é degradada (Fase 4).", examples={"exemplo": {"value": "off"}}),
    grupo: str = Query(None, description="Filtrar composições por grupo. Ex: ESTRUTURA"),
    classificacao: str = Query(None, description="Filtrar insumos por classificação. Ex: CONCRETO"),
    skip: int = 0, limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)
):
    """
    Busca unificada de insumos e composições (camadas ILIKE/trigrama + relacional).
    O envelope expõe `meta.providers` (camadas ativas) e `meta.degraded`
    (camadas solicitadas indisponíveis — ex.: `vector`), além de
    `meta.did_you_mean` quando não há resultados. Itens de insumo incluem
    `usado_em` (top 5 composições que o utilizam).
    """
    return search_pipeline.unified_search(
        db, q=q, uf=uf, data_referencia=data_referencia, regime=regime,
        tipo=tipo, sort=sort, vector=vector, skip=skip, limit=limit,
        grupo=grupo, classificacao=classificacao,
    )

@app.get("/api/v1/public/search/suggest", response_model=schemas.SearchSuggestResult, tags=["tier_1", "Search"], summary="Sugerir autocompletar", response_description="Top 8 sugestões cross-type (insumo+composição) por prefixo/trigrama.", responses=_RATE_LIMIT_RESPONSE)
def search_suggest(
    q: str = Query(..., min_length=1, description="Prefixo/termo para sugestões de autocomplete."),
    limit: int = Query(8, ge=1, le=20), db: Session = Depends(get_db)
):
    """
    Autocomplete cross-type: retorna até `limit` sugestões (padrão 8)
    combinando insumos e composições, ranqueadas por prefixo + trigrama.
    """
    return {"items": crud.search_suggest(db, q=q, limit=limit)}

@app.get("/api/v1/public/search/related", response_model=schemas.SearchRelatedResult, tags=["tier_2", "Search"], summary="Listar composições relacionadas", response_description="Top 5 composições relacionadas via Jaccard do Bill of Materials.", responses=_RATE_LIMIT_RESPONSE)
def search_related(
    codigo: int = Query(..., description="Código da composição de referência.", examples={"exemplo": {"value": 88247}}),
    uf: str = Query(..., description="Unidade Federativa (UF). Ex: SP", min_length=2, max_length=2, examples={"exemplo": {"value": "SP"}}),
    data_referencia: str = Query(..., description="Data de referência no formato AAAA-MM. Ex: 2025-09", examples={"exemplo": {"value": "2025-09"}}),
    regime: str = Query("NAO_DESONERADO", description="Regime de custo.", examples={"exemplo": {"value": "NAO_DESONERADO"}}),
    limit: int = Query(5, ge=1, le=20), db: Session = Depends(get_db)
):
    """
    Composições relacionadas à composição `codigo` por similaridade Jaccard
    do BOM estrutural (camada 3 relacional). Para uso na seção
    "Composições relacionadas" do detalhe da composição.
    """
    return {"items": crud.get_related_composicoes(db, codigo=codigo, limit=limit)}


# --- Endpoints de Business Intelligence (BI) ---

@app.get("/api/v1/public/bi/composicao/{codigo}/bom", response_model=List[schemas.ComposicaoBOMItem], tags=["tier_2", "Business Intelligence"], summary="Obter Bill of Materials da composição", response_description="Árvore completa de Bill of Materials (BOM) com impacto de custo.", responses=_PUBLIC_NOT_FOUND)
def get_composition_bom(
    codigo: int,
    uf: str = Query(..., description="Unidade Federativa (UF). Ex: SP", min_length=2, max_length=2, examples={"exemplo": {"value": "SP"}}),
    data_referencia: str = Query(..., description="Data de referência no formato AAAA-MM. Ex: 2025-09", examples={"exemplo": {"value": "2025-09"}}),
    regime: str = Query("NAO_DESONERADO", description="Regime de custo/preço.", examples={"exemplo": {"value": "NAO_DESONERADO"}}),
    db: Session = Depends(get_db)
):
    """
    Retorna o Bill of Materials (BOM) completo de uma composição,
    explodindo todos os níveis e calculando o impacto de custo de cada item.
    """
    bom_items = crud.get_composicao_bom(db, codigo=codigo, uf=uf, data_referencia=data_referencia, regime=regime)
    if not bom_items:
        raise HTTPException(status_code=404, detail="Composição não encontrada ou sem estrutura para os filtros especificados.")
    return bom_items

@app.get("/api/v1/public/bi/composicao/{codigo}/hora-homem", response_model=schemas.ComposicaoManHours, tags=["tier_2", "Business Intelligence"], summary="Calcular hora-homem da composição", response_description="Total de hora-homem da composição (todas as mãos de obra).", responses=_RATE_LIMIT_RESPONSE)
def get_composition_man_hours(codigo: int, db: Session = Depends(get_db)):
    """
    Calcula o total de Hora/Homem para uma composição, somando os coeficientes
    de todos os insumos de mão de obra (unidade 'H') em todos os níveis.
    """
    result = crud.get_composicao_man_hours(db, codigo=codigo)
    total_hh = 0.0
    if result is not None:
        if isinstance(result, dict):
            total_hh = result.get('total_hora_homem') or 0.0
        else:
            total_hh = getattr(result, 'total_hora_homem', None) or 0.0
    return schemas.ComposicaoManHours(total_hora_homem=total_hh)

@app.post("/api/v1/public/bi/curva-abc", response_model=List[schemas.CurvaABCItem], tags=["tier_2", "Business Intelligence"], summary="Calcular curva ABC de insumos", response_description="Curva ABC de insumos das composições informadas.", responses=_PUBLIC_NOT_FOUND)
def get_abc_curve(
    payload: schemas.CurvaABCRequest,
    uf: str = Query(..., description="Unidade Federativa (UF). Ex: SP", min_length=2, max_length=2, examples={"exemplo": {"value": "SP"}}),
    data_referencia: str = Query(..., description="Data de referência no formato AAAA-MM. Ex: 2025-09", examples={"exemplo": {"value": "2025-09"}}),
    regime: str = Query("NAO_DESONERADO", description="Regime de preço.", examples={"exemplo": {"value": "NAO_DESONERADO"}}),
    db: Session = Depends(get_db)
):
    """
    Calcula a Curva ABC de insumos para um grupo de composições,
    identificando os itens de maior impacto financeiro.
    """
    abc_curve = crud.get_abc_curve_for_composicoes(db, codigos=payload.codigos, uf=uf, data_referencia=data_referencia, regime=regime)
    if not abc_curve:
        raise HTTPException(status_code=404, detail="Nenhum insumo encontrado para as composições e filtros especificados.")
    return abc_curve

@app.get("/api/v1/public/bi/composicao/{codigo}/otimizar", response_model=List[schemas.ComposicaoBOMItem], tags=["tier_2", "Business Intelligence"], summary="Obter candidatos para otimização", response_description="Top-N insumos de maior impacto financeiro (foco de otimização).", responses=_PUBLIC_NOT_FOUND)
def get_optimization_candidates(
    codigo: int,
    uf: str = Query(..., description="Unidade Federativa (UF). Ex: SP", min_length=2, max_length=2, examples={"exemplo": {"value": "SP"}}),
    data_referencia: str = Query(..., description="Data de referência no formato AAAA-MM. Ex: 2025-09", examples={"exemplo": {"value": "2025-09"}}),
    regime: str = Query("NAO_DESONERADO", description="Regime de custo/preço.", examples={"exemplo": {"value": "NAO_DESONERADO"}}),
    top_n: int = Query(5, description="Número de principais insumos a serem retornados."),
    db: Session = Depends(get_db)
):
    """
    Retorna os N insumos de maior impacto financeiro em uma composição (Curva ABC - Foco).
    """
    candidates = crud.get_candidatos_otimizacao(db, codigo=codigo, uf=uf, data_referencia=data_referencia, regime=regime, top_n=top_n)
    if not candidates:
        raise HTTPException(status_code=404, detail="Não foi possível calcular os candidatos para otimização.")
    return candidates

@app.get("/api/v1/public/bi/item/{tipo_item}/{codigo}/historico", response_model=List[schemas.HistoricoCusto], tags=["tier_2", "Business Intelligence"], summary="Obter histórico de custo do item", response_description="Série histórica de custo/preço do item por mês.", responses=_PUBLIC_VALIDATED)
def get_item_cost_history(
    tipo_item: str = Path(..., description="Tipo do item: 'insumo' ou 'composicao'"),
    codigo: int = Path(..., description="Código do item."),
    uf: str = Query(..., description="Unidade Federativa (UF). Ex: SP", min_length=2, max_length=2, examples={"exemplo": {"value": "SP"}}),
    regime: str = Query("NAO_DESONERADO", description="Regime de custo/preço.", examples={"exemplo": {"value": "NAO_DESONERADO"}}),
    data_fim: str = Query(f"{date.today():%Y-%m}", description="Data final (AAAA-MM) da análise.", examples={"exemplo": {"value": "2025-09"}}),
    meses: int = Query(12, description="Número de meses a serem analisados para trás."),
    db: Session = Depends(get_db)
):
    """
    Retorna o histórico de custo/preço de um item para um período.
    """
    try:
        end_date = datetime.strptime(data_fim, "%Y-%m")
    except ValueError:
        raise HTTPException(status_code=400, detail="Formato de data_fim inválido. Use AAAA-MM.")

    start_date = end_date - relativedelta(months=meses - 1)
    data_inicio_str = start_date.strftime("%Y-%m")

    if tipo_item not in ['insumo', 'composicao']:
        raise HTTPException(status_code=400, detail="Tipo de item inválido. Use 'insumo' ou 'composicao'.")

    history = crud.get_custo_historico(
        db, tipo_item=tipo_item, codigo=codigo, uf=uf, regime=regime,
        data_inicio=data_inicio_str, data_fim=data_fim
    )
    if not history:
        raise HTTPException(status_code=404, detail="Não foram encontrados dados históricos para o item e filtros especificados.")
    return history

@app.get("/api/v1/public/bi/item/{tipo_item}/{codigo}/manutencoes", response_model=List[schemas.HistoricoManutencao], tags=["tier_2", "Business Intelligence"], summary="Obter histórico de manutenções do item", response_description="Histórico de manutenções (ativações/desativações) do item.", responses=_PUBLIC_VALIDATED)
def get_item_maintenance_history(
    tipo_item: str = Path(..., description="Tipo do item: 'insumo' ou 'composicao'"),
    codigo: int = Path(..., description="Código do item."),
    db: Session = Depends(get_db)
):
    """
    Retorna o histórico de manutenção (ativações/desativações) de um item.
    """
    if tipo_item not in ['insumo', 'composicao']:
        raise HTTPException(status_code=400, detail="Tipo de item inválido. Use 'insumo' ou 'composicao'.")
    manutencoes = crud.get_manutencoes_historico(db, codigo=codigo, tipo_item=tipo_item)
    if not manutencoes:
        raise HTTPException(status_code=404, detail="Nenhum histórico de manutenção encontrado para este item.")
    return manutencoes


@app.get("/api/v1/public/bi/audit/{tipo_item}/{codigo}", response_model=List[schemas.AuditEvent], tags=["tier_2", "Business Intelligence"], summary="Obter trilha de auditoria do item", response_description="Trilha de auditoria completa do item (retificações, status, estrutura).", responses=_PUBLIC_VALIDATED)
def get_audit_trail(
    tipo_item: str = Path(..., description="Tipo do item: 'insumo' ou 'composicao'"),
    codigo: int = Path(..., description="Código do item."),
    data_referencia: str = Query(None, description="Filtrar por data de referência (AAAA-MM).", examples={"exemplo": {"value": "2025-09"}}),
    db: Session = Depends(get_db)
):
    """
    Retorna o histórico completo de auditoria para um item.
    Inclui retificações de preços, mudanças de status e modificações de estrutura.
    """
    if tipo_item not in ['insumo', 'composicao']:
        raise HTTPException(status_code=400, detail="Tipo de item inválido. Use 'insumo' ou 'composicao'.")
    audit_events = crud.get_audit_events(db, tipo_item=tipo_item, codigo=codigo, data_referencia=data_referencia)
    if not audit_events:
        raise HTTPException(status_code=404, detail="Nenhum evento de auditoria encontrado para este item.")
    return audit_events

@app.post("/api/v1/public/bi/curva-abc/por-classificacao", response_model=List[schemas.AbcPorClassificacao], tags=["tier_2", "Business Intelligence"], summary="Calcular curva ABC por classificação", response_description="Curva ABC agregada por classificação de insumo.", responses=_PUBLIC_NOT_FOUND)
def get_abc_by_classificacao(
    payload: schemas.CurvaABCRequest,
    uf: str = Query(..., description="Unidade Federativa (UF). Ex: SP", min_length=2, max_length=2, examples={"exemplo": {"value": "SP"}}),
    data_referencia: str = Query(..., description="Data de referência no formato AAAA-MM. Ex: 2025-09", examples={"exemplo": {"value": "2025-09"}}),
    regime: str = Query("NAO_DESONERADO", description="Regime de preço.", examples={"exemplo": {"value": "NAO_DESONERADO"}}),
    db: Session = Depends(get_db)
):
    """
    Calcula a Curva ABC agrupada por classificação de insumo,
    agregando todos os insumos de mesma categoria para mostrar
    quais classes de materiais dominam o custo.
    """
    result = crud.get_abc_by_classificacao(db, codigos=payload.codigos, uf=uf, data_referencia=data_referencia, regime=regime)
    if not result:
        raise HTTPException(status_code=404, detail="Nenhuma classificação encontrada para as composições e filtros especificados.")
    return result

@app.get("/api/v1/public/bi/tendencias/por-classificacao", response_model=List[schemas.TendenciaClassificacao], tags=["tier_2", "Business Intelligence"], summary="Obter tendências por classificação", response_description="Evolução mensal de preço/custo agrupada por classificação/grupo/item.", responses=_PUBLIC_VALIDATED)
def get_tendencias_classificacao(
    uf: str = Query(..., description="Unidade Federativa (UF). Ex: SP", min_length=2, max_length=2, examples={"exemplo": {"value": "SP"}}),
    data_referencia: str = Query(..., description="Data de referência final no formato AAAA-MM. Ex: 2025-09", examples={"exemplo": {"value": "2025-09"}}),
    regime: str = Query("NAO_DESONERADO", description="Regime de preço.", examples={"exemplo": {"value": "NAO_DESONERADO"}}),
    agrupar_por: str = Query("classificacao", description="Campo para agrupamento: 'classificacao' (Insumos), 'grupo' (Composições) ou 'item' (Itens individuais)."),
    codigos: Optional[str] = Query(None, description="Lista de códigos separados por vírgula para filtrar itens específicos."),
    meses: int = Query(12, description="Número de meses a serem analisados para trás."),
    db: Session = Depends(get_db)
):
    """
    Retorna a evolução mensal do preço/custo médio agrupado por classificação de insumo,
    grupo de composição ou item individual para análise de tendências e volatilidade.
    """
    code_list = None
    if codigos:
        try:
            code_list = [int(c.strip()) for c in codigos.split(",") if c.strip()]
        except ValueError:
            raise HTTPException(status_code=400, detail="O parâmetro 'codigos' deve conter apenas números separados por vírgula.")

    result = crud.get_tendencias(db, uf=uf, regime=regime, data_referencia=data_referencia, agrupar_por=agrupar_por, meses=meses, codigos=code_list)
    if not result:
        raise HTTPException(status_code=404, detail="Nenhum dado de tendência encontrado para os filtros especificados.")
    return result

@app.get("/api/v1/public/bi/item/{tipo_item}/{codigo}/precos-uf", response_model=List[schemas.PrecoPorUF], tags=["tier_2", "Business Intelligence"], summary="Obter preços do item em todas UFs", response_description="Preço do item em todas as UFs (mapa de calor regional). `?meta=true` retorna envelope `{items, stats}` com estatísticas regionais.", responses=_PUBLIC_VALIDATED)
def get_item_prices_all_ufs(
    tipo_item: str = Path(..., description="Tipo do item: 'insumo' ou 'composicao'"),
    codigo: int = Path(..., description="Código do item."),
    data_referencia: str = Query(..., description="Data de referência no formato AAAA-MM. Ex: 2025-09", examples={"exemplo": {"value": "2025-09"}}),
    regime: str = Query("NAO_DESONERADO", description="Regime de custo/preço.", examples={"exemplo": {"value": "NAO_DESONERADO"}}),
    meta: bool = Query(False, description="Se true, retorna envelope `{items, stats}` com estatísticas regionais."),
    db: Session = Depends(get_db)
):
    """
    Retorna o preço de um item em TODAS as UFs disponíveis para
    comparação regional completa e mapa de calor.
    """
    if tipo_item not in ['insumo', 'composicao']:
        raise HTTPException(status_code=400, detail="Tipo de item inválido. Use 'insumo' ou 'composicao'.")
    precos = crud.get_precos_all_ufs(db, tipo_item=tipo_item, codigo=codigo, data_referencia=data_referencia, regime=regime)
    if not precos:
        raise HTTPException(status_code=404, detail="Nenhum dado encontrado para o item e filtros especificados.")
    if meta:
        safe_items = [{"uf": p["uf"], "valor": float(p["valor"])} for p in precos]
        return _search_response({"items": safe_items, "total": len(safe_items), "stats": crud._regional_stats(safe_items)}, meta=True)
    return precos

@app.get("/api/v1/public/bi/composicao/{codigo}/produtividade", response_model=schemas.ComposicaoProdutividade, tags=["tier_2", "Business Intelligence"], summary="Obter análise de produtividade", response_description="Análise de produtividade (Mão de Obra / Material / Equipamento).", responses=_PUBLIC_NOT_FOUND)
def get_composition_productivity(
    codigo: int,
    uf: str = Query(..., description="Unidade Federativa (UF). Ex: SP", min_length=2, max_length=2, examples={"exemplo": {"value": "SP"}}),
    data_referencia: str = Query(..., description="Data de referência no formato AAAA-MM. Ex: 2025-09", examples={"exemplo": {"value": "2025-09"}}),
    regime: str = Query("NAO_DESONERADO", description="Regime de custo/preço.", examples={"exemplo": {"value": "NAO_DESONERADO"}}),
    db: Session = Depends(get_db)
):
    """
    Classifica os itens do BOM de uma composição em Mão de Obra, Material e Equipamento,
    retornando o total de Horas-Homem e o custo por HH como métrica de produtividade.
    """
    result = crud.get_composicao_produtividade(db, codigo=codigo, uf=uf, data_referencia=data_referencia, regime=regime)
    if not result:
        raise HTTPException(status_code=404, detail="Não foi possível calcular a produtividade para esta composição.")
    return result

@app.get("/api/v1/public/bi/insumo/{codigo}/onde-usado", response_model=List[schemas.InsumoOndeUsado], tags=["tier_2", "Business Intelligence"], summary="Obter composições que usam o insumo", response_description="Query reversa: composições que utilizam o item (em qualquer nível).", responses=_PUBLIC_VALIDATED)
def get_insumo_where_used(
    codigo: int,
    tipo_item: str = Query("insumo", description="Tipo do item: 'insumo' ou 'composicao'"),
    db: Session = Depends(get_db)
):
    """
    Query reversa: encontra todas as composições (em qualquer nível) que utilizam
    um determinado insumo ou subcomposição. Útil para análise de impacto.
    """
    if tipo_item not in ['insumo', 'composicao']:
        raise HTTPException(status_code=400, detail="Tipo de item inválido. Use 'insumo' ou 'composicao'.")
    result = crud.get_onde_usado(db, codigo=codigo, tipo_item=tipo_item)
    if not result:
        raise HTTPException(status_code=404, detail="Nenhuma composição encontrada que utilize este item.")
    return result

@app.get("/api/v1/public/bi/cenario", response_model=schemas.CenarioResponse, tags=["tier_2", "Business Intelligence"], summary="Calcular cenário orçamentário consolidado", response_description="Cenário 'PowerBI do SINAPI': composições, total do BOM, Curva ABC, spread regional e tendências.", responses=_PUBLIC_VALIDATED)
def get_cenario(
    codigos: str = Query(..., description="Lista de códigos de composição separados por vírgula. Ex: 92711,88307"),
    uf: str = Query(..., description="Unidade Federativa (UF). Ex: SP", min_length=2, max_length=2, examples={"exemplo": {"value": "SP"}}),
    data_referencia: str = Query(..., description="Data de referência no formato AAAA-MM. Ex: 2025-09", examples={"exemplo": {"value": "2025-09"}}),
    regime: str = Query("NAO_DESONERADO", description="Regime de custo/preço.", examples={"exemplo": {"value": "NAO_DESONERADO"}}),
    meses: int = Query(12, description="Número de meses de tendências a analisar."),
    db: Session = Depends(get_db)
):
    """
    Consolida o cenário orçamentário de um grupo de composições:
    total do BOM, Curva ABC, spread regional entre UFs e tendência mensal.
    """
    try:
        code_list = [int(c.strip()) for c in codigos.split(",") if c.strip()]
    except ValueError:
        raise HTTPException(status_code=400, detail="O parâmetro 'codigos' deve conter apenas números separados por vírgula.")
    if not code_list:
        raise HTTPException(status_code=400, detail="Informe ao menos um código de composição em 'codigos'.")

    cenario = crud.get_cenario(db, codigos=code_list, uf=uf, data_referencia=data_referencia, regime=regime, meses=meses)
    if not cenario["composicoes"]:
        raise HTTPException(status_code=404, detail="Nenhuma composição encontrada para os códigos informados.")
    return cenario
