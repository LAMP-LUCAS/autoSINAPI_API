import pandas as pd
import calendar
import decimal
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Optional
from datetime import datetime, date

# Importa a instância única de configurações
from .config import settings
from .cache_utils import cache_result

def _get_date_range(data_referencia: str):
    """
    Converte 'AAAA-MM' em um range de início e fim de mês para query indexada.
    """
    try:
        ref_date = datetime.strptime(data_referencia, "%Y-%m")
        start_date = ref_date.replace(day=1).date()
        last_day = calendar.monthrange(start_date.year, start_date.month)[1]
        end_date = start_date.replace(day=last_day)
        return start_date, end_date
    except (ValueError, TypeError):
        return None, None

@cache_result(ttl=3600)
def get_global_stats(db: Session) -> dict:
    """
    Retorna a volumetria global do banco de dados.
    """
    queries = {
        "insumos": text(f"SELECT count(*) FROM {settings.TABLE_INSUMOS}"),
        "composicoes": text(f"SELECT count(*) FROM {settings.TABLE_COMPOSICOES}"),
        "precos": text(f"SELECT count(*) FROM {settings.TABLE_PRECOS_INSUMOS}"),
        "custos": text(f"SELECT count(*) FROM {settings.TABLE_CUSTOS_COMPOSICOES}")
    }
    stats = {}
    for key, q in queries.items():
        stats[key] = db.execute(q).scalar()
    return stats

@cache_result(ttl=86400)
def get_available_filters(db: Session) -> dict:
    """
    Retorna os UFs, Regimes e Datas de Referência disponíveis no banco de dados.
    """
    ufs = db.execute(text(f"SELECT DISTINCT uf FROM {settings.TABLE_PRECOS_INSUMOS} ORDER BY uf")).scalars().all()
    datas = db.execute(text(f"SELECT DISTINCT TO_CHAR(data_referencia, 'YYYY-MM') FROM {settings.TABLE_PRECOS_INSUMOS} ORDER BY 1 DESC")).scalars().all()
    regimes = db.execute(text(f"SELECT DISTINCT regime FROM {settings.TABLE_PRECOS_INSUMOS} ORDER BY regime")).scalars().all()
    classificacoes = db.execute(text(f"SELECT DISTINCT classificacao FROM {settings.TABLE_INSUMOS} WHERE classificacao IS NOT NULL AND classificacao != '' AND status = :status ORDER BY classificacao"), {"status": settings.DEFAULT_ITEM_STATUS}).scalars().all()
    grupos = db.execute(text(f"SELECT DISTINCT grupo FROM {settings.TABLE_COMPOSICOES} WHERE grupo IS NOT NULL AND grupo != '' AND status = :status ORDER BY grupo"), {"status": settings.DEFAULT_ITEM_STATUS}).scalars().all()
    return {"ufs": ufs, "datas": datas, "regimes": regimes, "classificacoes": classificacoes, "grupos": grupos}

# --- Seção 1: Funções de Busca Direta (CRUD) ---

@cache_result(ttl=3600)
def get_insumo_by_codigo(
    db: Session, codigo: int, uf: str, data_referencia: str, regime: str
) -> Optional[dict]:
    start_date, end_date = _get_date_range(data_referencia)
    query = text(f"""
        SELECT i.codigo, i.descricao, i.unidade, i.classificacao, i.status, 
               p.preco_mediano, p.origem_preco,
               i.created_at, i.updated_at, i.sinapi_versao
        FROM {settings.TABLE_INSUMOS} AS i
        JOIN {settings.TABLE_PRECOS_INSUMOS} AS p ON i.codigo = p.insumo_codigo
        WHERE i.codigo = :codigo AND i.status = :status AND p.uf = :uf
          AND p.data_referencia >= :start_date AND p.data_referencia <= :end_date
          AND p.regime = :regime
    """)
    result = db.execute(query, {
        "codigo": codigo, "uf": uf.upper(), "start_date": start_date, "end_date": end_date,
        "regime": regime.upper(), "status": settings.DEFAULT_ITEM_STATUS
    }).first()
    return result._mapping if result else None

def _normalize_search_q(q: str):
    """Retorna (termo_limpo, codigo_int). Se q for puramente numérico,
    trata-o como busca por código exato (ADR-007 busca por código)."""
    term = (q or "").strip()
    return (term, int(term)) if term.isdigit() else (term, None)


def _tokenize_query(q: str) -> List[str]:
    """Divide a query em tokens (palavras) para busca multi-termo estilo Google.

    Espaços repetidos e termo vazio são tolerados (não geram tokens)."""
    return [tok for tok in (q or "").split() if tok]


def _build_token_match(desc_expr: str, tokens: List[str], trigram: bool,
                       combine: str = "AND") -> tuple[str, dict, str]:
    """Monta cláusula de correspondência por token (Google-style multi-termo).

    Args:
        desc_expr: expressão da coluna de descrição (ex.: "t.descricao").
        tokens: termos da query já tokenizados.
        trigram: True se pg_trgm/unaccent disponíveis (ranking por similaridade).
        combine: "AND" (todos os tokens — precisão) ou "OR" (qualquer token —
            fallback parcial quando AND não encontra itens).

    Returns:
        (match_clause, params, score_expr): cláusula WHERE por token, bind params
        (`:t_N` para ILIKE, `:q_N` para similaridade) e expressão de score.

    Score = soma por token de `GREATEST(similarity, word_similarity * 1.1)` quando
    trigram ativo e token >= 3 chars; caso contrário `NULL::float` (fallback ILIKE).
    """
    joiner = " AND " if combine == "AND" else " OR "
    clauses, params, score_parts = [], {}, []
    for i, tok in enumerate(tokens):
        tkey, qkey = f"t_{i}", f"q_{i}"
        params[tkey] = f"%{tok}%"
        if trigram and len(tok) >= 3:
            params[qkey] = tok
            clauses.append(f"f_unaccent({desc_expr}) ILIKE f_unaccent(:{tkey})")
            score_parts.append(
                f"GREATEST(similarity(f_unaccent({desc_expr}), f_unaccent(:{qkey})), "
                f"word_similarity(f_unaccent(:{qkey}), f_unaccent({desc_expr})) * 1.1)",
            )
        else:
            clauses.append(f"{desc_expr} ILIKE :{tkey}")
    match_clause = "(" + joiner.join(clauses) + ")"
    if score_parts:
        score_expr = "(" + " + ".join(score_parts) + ") AS score"
    else:
        score_expr = "NULL::float AS score"
    return match_clause, params, score_expr


# ── SIN-094 · SSOT de normalização de tipo_item e folhas do BOM ──────────────
# O ETL grava `manutencoes_historico.tipo_item` como 'COMPOSICAO'/'COMPOSIÇÃO'
# (maiúsculo, com variante acentuada), enquanto o path da API chega minúsculo.
# Sem normalização, o filtro não casa → 404 para qualquer item.

_ACCENT_TRANSLATION = str.maketrans({
    "Á": "A", "À": "A", "Â": "A", "Ã": "A", "Ä": "A",
    "É": "E", "È": "E", "Ê": "E",
    "Í": "I", "Ï": "I",
    "Ó": "O", "Ô": "O", "Õ": "O", "Ö": "O",
    "Ú": "U", "Ü": "U",
    "Ç": "C",
})


def _normalize_tipo_item(tipo) -> str:
    """Normaliza tipo_item para comparação case/acento-insensível ('Composição' → 'COMPOSICAO')."""
    return str(tipo or "").strip().upper().translate(_ACCENT_TRANSLATION)


# Expressão SQL equivalente a _normalize_tipo_item aplicada à coluna (Postgres).
_SQL_TIPO_NORM = "UPPER(TRANSLATE({col}, 'ÁÀÂÃÄÉÈÊÍÏÓÔÕÖÚÜÇ', 'AAAAAEEEIIOOOOUUC'))"


def _filter_bom_leaves(rows: List[dict]) -> List[dict]:
    """Retorna apenas as FOLHAS do BOM hierárquico (ADR-040 / SIN-094).

    Uma linha COMPOSICAO cujo nível tenha linhas mais profundas abaixo é PAI:
    seu custo consolidado duplicaria os filhos no somatório. Linha COMP sem
    nada mais profundo é folha legítima (custo sem explosão disponível).
    BOM sem níveis utilizáveis → lista integral (retrocompatível)."""
    if not rows:
        return []

    def _nivel(r: dict) -> int:
        try:
            return int(r.get("nivel") or 1)
        except (TypeError, ValueError):
            return 1

    max_nivel = max(_nivel(r) for r in rows)
    if max_nivel <= 1:
        return list(rows)

    leaves = [
        r for r in rows
        if not (
            _normalize_tipo_item(r.get("tipo_item")).startswith("COMPOSICAO")
            and any(_nivel(x) > _nivel(r) for x in rows)
        )
    ]
    return leaves or list(rows)


def _trigram_enabled(db: Session) -> bool:
    """Detecta pg_trgm + unaccent + f_unaccent (migration 006). Nunca levanta
    exceção: em fallback (sem extensões) a busca usa ILIKE simples."""
    try:
        row = db.execute(text(
            "SELECT count(*) FROM pg_extension WHERE extname IN ('pg_trgm', 'unaccent')"
        )).scalar()
        if not (row and int(row) >= 2):
            return False
        fn = db.execute(text(
            "SELECT count(*) FROM pg_proc WHERE proname = 'f_unaccent'"
        )).scalar()
        return bool(fn and int(fn) >= 1)
    except Exception:
        return False


def _run_search(db: Session, query, params: dict) -> dict:
    """Executa uma busca paginada e devolve {items, total}.

    `total` vem de COUNT(*) OVER() (janela) para evitar query dupla e
    garantir consistência com a página corrente (SPEC-RULE-SEARCH S3)."""
    rows = db.execute(query, params).fetchall()
    total = 0
    items = []
    for r in rows:
        m = dict(r._mapping)
        total = m.pop("total_count", 0)
        items.append(_json_safe(m))
    return {"items": items, "total": int(total) if rows else 0}


def _json_safe(mapping: dict) -> dict:
    """Normaliza tipos não-JSON (Decimal/date) para serialização direta."""
    out = {}
    for k, v in mapping.items():
        if isinstance(v, decimal.Decimal):
            out[k] = float(v)
        elif isinstance(v, (datetime, date)):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out


def _search_where(
    db: Session, q: str, table_item: str, table_preco: str, item_alias: str,
    join_col: str, select_cols: str, uf: str, data_referencia: str, regime: str,
    skip: int, limit: int, extra_where: str = "", extra_params: Optional[dict] = None,
    combine: str = "AND",
) -> dict:
    """Builder compartilhado das buscas (insumos/composições).

    Ranking (ADR-006) + multi-termo (EPIC-search-engine-google-powerbi):
      - pg_trgm + unaccent disponíveis e token >= 3 chars → ranking por
        `similarity`/`word_similarity` (score exposto no item).
      - Caso contrário → fallback ILIKE (ordem alfabética), score NULL.
      - Query com 2+ tokens → AND por token (todos presentes, ordem tolerada).
        Se AND não retornar itens, relaxa para OR (resultados parciais) e marca
        `relaxed=True` no resultado.
      - Token único → caminho legado preservado (zero breaking change).
    Busca por código (ADR-007): termo numérico casa `codigo = :codigo`.
    """
    start_date, end_date = _get_date_range(data_referencia)
    term, codigo = _normalize_search_q(q)
    tokens = _tokenize_query(term)
    if not tokens:
        return {"items": [], "total": 0}
    trigram = _trigram_enabled(db)
    desc_col = f"{item_alias}.descricao"
    use_trigram_score = trigram and any(len(t) >= 3 for t in tokens)

    token_params: dict = {}
    if len(tokens) >= 2:
        match_clause, token_params, score_expr = _build_token_match(
            desc_col, tokens, trigram, combine,
        )
    else:
        tok = tokens[0]
        if trigram and len(tok) >= 3:
            match_clause = f"f_unaccent({desc_col}) ILIKE f_unaccent(:query)"
            score_expr = (
                f"GREATEST(similarity(f_unaccent({desc_col}), f_unaccent(:q)), "
                f"word_similarity(f_unaccent(:q), f_unaccent({desc_col})) * 1.1) AS score"
            )
        else:
            match_clause = f"{desc_col} ILIKE :query"
            score_expr = "NULL::float AS score"

    code_clause = f" OR {item_alias}.codigo = :codigo" if codigo is not None else ""
    order_clause = "score DESC," if use_trigram_score else ""
    params = {
        "uf": uf.upper(), "start_date": start_date, "end_date": end_date,
        "regime": regime.upper(), "status": settings.DEFAULT_ITEM_STATUS,
        "skip": skip, "limit": limit,
    }
    if len(tokens) == 1:
        params["query"] = f"%{tokens[0]}%"
        if trigram and len(tokens[0]) >= 3:
            params["q"] = tokens[0]
    if codigo is not None:
        params["codigo"] = codigo
    if extra_params:
        params.update(extra_params)
    params.update(token_params)

    query = text(f"""
        SELECT {select_cols}, {score_expr}, COUNT(*) OVER() AS total_count
        FROM {table_item} AS {item_alias}
        JOIN {table_preco} AS p ON {item_alias}.codigo = p.{join_col}
        WHERE ({match_clause}{code_clause}) AND {item_alias}.status = :status
          AND p.uf = :uf AND p.data_referencia >= :start_date
          AND p.data_referencia <= :end_date AND p.regime = :regime
        {extra_where}
        ORDER BY {order_clause}{item_alias}.descricao OFFSET :skip LIMIT :limit
    """)
    result = _run_search(db, query, params)
    if result["total"] == 0 and len(tokens) >= 2 and combine == "AND":
        result = _search_where(
            db, q, table_item=table_item, table_preco=table_preco, item_alias=item_alias,
            join_col=join_col, select_cols=select_cols, uf=uf,
            data_referencia=data_referencia, regime=regime, skip=skip, limit=limit,
            extra_where=extra_where, extra_params=extra_params, combine="OR",
        )
        result["relaxed"] = True
    return result


@cache_result(ttl=3600)
def search_insumos_by_descricao(
    db: Session, q: str, uf: str, data_referencia: str, regime: str, skip: int, limit: int,
    classificacao: str = None
) -> dict:
    extra_where = ""
    extra_params = None
    if classificacao:
        extra_where = "AND UPPER(i.classificacao) = UPPER(:classificacao)"
        extra_params = {"classificacao": classificacao}
    return _search_where(
        db, q,
        table_item=settings.TABLE_INSUMOS, table_preco=settings.TABLE_PRECOS_INSUMOS,
        item_alias="i", join_col="insumo_codigo",
        select_cols=("i.codigo, i.descricao, i.unidade, i.classificacao, "
                     "i.status, p.preco_mediano, p.origem_preco"),
        uf=uf, data_referencia=data_referencia, regime=regime,
        skip=skip, limit=limit, extra_where=extra_where, extra_params=extra_params,
    )

@cache_result(ttl=3600)
def get_composicao_by_codigo(
    db: Session, codigo: int, uf: str, data_referencia: str, regime: str
) -> Optional[dict]:
    start_date, end_date = _get_date_range(data_referencia)
    query = text(f"""
        SELECT c.codigo, c.descricao, c.unidade, c.grupo, c.status, 
               p.custo_total, p.percentual_mo,
               c.created_at, c.updated_at, c.sinapi_versao
        FROM {settings.TABLE_COMPOSICOES} AS c
        JOIN {settings.TABLE_CUSTOS_COMPOSICOES} AS p ON c.codigo = p.composicao_codigo
        WHERE c.codigo = :codigo AND c.status = :status AND p.uf = :uf
          AND p.data_referencia >= :start_date AND p.data_referencia <= :end_date
          AND p.regime = :regime
    """)
    result = db.execute(query, {
        "codigo": codigo, "uf": uf.upper(), "start_date": start_date, "end_date": end_date,
        "regime": regime.upper(), "status": settings.DEFAULT_ITEM_STATUS
    }).first()
    return result._mapping if result else None

@cache_result(ttl=3600)
def search_composicoes_by_descricao(
    db: Session, q: str, uf: str, data_referencia: str, regime: str, skip: int, limit: int,
    grupo: str = None
) -> dict:
    extra_where = ""
    extra_params = None
    if grupo:
        extra_where = "AND UPPER(c.grupo) = UPPER(:grupo)"
        extra_params = {"grupo": grupo}
    return _search_where(
        db, q,
        table_item=settings.TABLE_COMPOSICOES, table_preco=settings.TABLE_CUSTOS_COMPOSICOES,
        item_alias="c", join_col="composicao_codigo",
        select_cols=("c.codigo, c.descricao, c.unidade, c.grupo, "
                     "c.status, p.custo_total, p.percentual_mo"),
        uf=uf, data_referencia=data_referencia, regime=regime,
        skip=skip, limit=limit, extra_where=extra_where, extra_params=extra_params,
    )


# --- Seção 1b: Busca unificada, suggest, did-you-mean, related (STORY-SRC-002) ---

def search_suggest(db: Session, q: str, limit: int = 8) -> List[dict]:
    """Autocomplete cross-type (insumo+composição) por prefixo + trigrama.

    Ranking: `word_similarity` (prefixo) + `similarity` (tolerante a erros).
    Sem `pg_trgm` → fallback ILIKE simples. Sem contexto de preço (rápido)."""
    term, _ = _normalize_search_q(q)
    trigram = _trigram_enabled(db) and len(term) >= 2
    ins, comp = settings.TABLE_INSUMOS, settings.TABLE_COMPOSICOES

    if trigram:
        score_expr = (
            "GREATEST(similarity(f_unaccent(descricao), f_unaccent(:q)), "
            "word_similarity(f_unaccent(:q), f_unaccent(descricao)) * 1.2) AS score"
        )
        match_clause = "f_unaccent(descricao) ILIKE f_unaccent(:like_q)"
        params = {"q": term, "like_q": f"%{term}%", "limit": limit,
                  "status": settings.DEFAULT_ITEM_STATUS}
    else:
        score_expr = "0.0 AS score"
        match_clause = "descricao ILIKE :like_q"
        params = {"like_q": f"%{term}%", "limit": limit,
                  "status": settings.DEFAULT_ITEM_STATUS}

    query = text(f"""
        SELECT codigo, descricao, unidade, 'insumo' AS tipo, {score_expr}
        FROM {ins} WHERE {match_clause} AND status = :status
        UNION ALL
        SELECT codigo, descricao, unidade, 'composicao' AS tipo, {score_expr}
        FROM {comp} WHERE {match_clause} AND status = :status
        ORDER BY score DESC, descricao
        LIMIT :limit
    """)
    rows = db.execute(query, params).fetchall()
    return [dict(r._mapping) for r in rows]


_SORT_ORDERS = {
    "relevance": "score DESC NULLS LAST, descricao",
    "price_asc": "valor ASC NULLS LAST, descricao",
    "price_desc": "valor DESC NULLS LAST, descricao",
    "name": "descricao",
    "name_asc": "descricao",
    "name_desc": "descricao DESC",
}


def search_unified(
    db: Session, q: str, uf: str, data_referencia: str, regime: str,
    tipo: str = "all", sort: str = "relevance", skip: int = 0, limit: int = 100,
    grupo: Optional[str] = None, classificacao: Optional[str] = None,
    combine: str = "AND",
) -> dict:
    """Busca unificada insumo+composição (STORY-SRC-002 / "Google do SINAPI").

    UNION ALL dos dois tipos com coluna `tipo` e `valor` unificado
    (preco_mediano p/ insumo; custo_total p/ composição). Dedupe por
    (codigo, tipo) via ROW_NUMBER (a janela de data pode repetir o item em
    vários meses). Sort e paginação server-side; total via COUNT(*) OVER().

    Multi-termo: 2+ tokens → AND por token (todos presentes, ordem tolerada);
    se AND não encontrar itens, relaxa para OR (`relaxed=True`). Token único →
    caminho legado preservado (zero breaking change)."""
    start_date, end_date = _get_date_range(data_referencia)
    term, codigo = _normalize_search_q(q)
    tokens = _tokenize_query(term)
    if not tokens:
        return {"items": [], "total": 0}
    trigram = _trigram_enabled(db)

    token_params: dict = {}
    if len(tokens) >= 2:
        match_expr, token_params, score_expr = _build_token_match(
            "t.descricao", tokens, trigram, combine,
        )
    else:
        tok = tokens[0]
        if trigram and len(tok) >= 3:
            match_expr = "f_unaccent(t.descricao) ILIKE f_unaccent(:query)"
            score_expr = (
                "GREATEST(similarity(f_unaccent(t.descricao), f_unaccent(:q)), "
                "word_similarity(f_unaccent(:q), f_unaccent(t.descricao)) * 1.1) AS score"
            )
        else:
            match_expr = "t.descricao ILIKE :query"
            score_expr = "NULL::float AS score"

    code_clause = f" OR t.codigo = :codigo" if codigo is not None else ""
    params = {
        "uf": uf.upper(),
        "start_date": start_date, "end_date": end_date,
        "regime": regime.upper(), "status": settings.DEFAULT_ITEM_STATUS,
        "skip": skip, "limit": limit,
    }
    if len(tokens) == 1:
        params["query"] = f"%{tokens[0]}%"
        if trigram and len(tokens[0]) >= 3:
            params["q"] = tokens[0]
    if codigo is not None:
        params["codigo"] = codigo
    params.update(token_params)

    # Condições de faceta aplicadas apenas ao branch correspondente.
    filtro_insumo = ""
    filtro_composicao = ""
    if classificacao:
        filtro_insumo = " AND UPPER(t.classificacao) = UPPER(:classificacao)"
        params["classificacao"] = classificacao
    if grupo:
        filtro_composicao = " AND UPPER(t.grupo) = UPPER(:grupo)"
        params["grupo"] = grupo

    def _branch(item_table, price_table, join_col, tipo_label, val_col, categoria, filtro):
        # STORY-SRC-002 fix: cada branch emite apenas as colunas que existem na
        # tabela-fonte; a coluna do outro tipo vira literal NULL (o CASE com
        # coluna inexistente causa UndefinedColumn mesmo em branch falso).
        if tipo_label == 'insumo':
            col_classif = 't.classificacao AS classificacao'
            col_grupo = 'null::text AS grupo'
        else:
            col_classif = 'null::text AS classificacao'
            col_grupo = 't.grupo AS grupo'
        return f"""
        SELECT t.codigo, t.descricao, t.unidade, '{tipo_label}' AS tipo,
               {col_classif},
               {col_grupo},
               p.{val_col} AS valor, {score_expr},
               ROW_NUMBER() OVER (PARTITION BY t.codigo ORDER BY p.data_referencia DESC) AS rn
        FROM {item_table} AS t
        JOIN {price_table} AS p ON t.codigo = p.{join_col}
        WHERE ({match_expr}{code_clause}) AND t.status = :status
          AND p.uf = :uf AND p.data_referencia >= :start_date
          AND p.data_referencia <= :end_date AND p.regime = :regime{filtro}
        """

    include_insumo = tipo.lower() in ("all", "insumo")
    include_composicao = tipo.lower() in ("all", "composicao")
    branches = []
    if include_insumo:
        branches.append(_branch(settings.TABLE_INSUMOS, settings.TABLE_PRECOS_INSUMOS,
                                "insumo_codigo", "insumo", "preco_mediano",
                                "classificacao", filtro_insumo))
    if include_composicao:
        branches.append(_branch(settings.TABLE_COMPOSICOES, settings.TABLE_CUSTOS_COMPOSICOES,
                                "composicao_codigo", "composicao", "custo_total",
                                "grupo", filtro_composicao))
    if not branches:
        return {"items": [], "total": 0}

    uniao = " UNION ALL ".join(branches)
    order_clause = _SORT_ORDERS.get((sort or "relevance").lower(), _SORT_ORDERS["relevance"])
    query = text(f"""
        SELECT u.codigo, u.descricao, u.unidade, u.tipo, u.classificacao, u.grupo,
               u.valor, u.score, COUNT(*) OVER() AS total_count
        FROM ({uniao}) AS u
        WHERE u.rn = 1
        ORDER BY {order_clause} OFFSET :skip LIMIT :limit
    """)
    result = _run_search(db, query, params)
    if result["total"] == 0 and len(tokens) >= 2 and combine == "AND":
        result = search_unified(
            db, q, uf=uf, data_referencia=data_referencia, regime=regime,
            tipo=tipo, sort=sort, skip=skip, limit=limit,
            grupo=grupo, classificacao=classificacao, combine="OR",
        )
        result["relaxed"] = True
    return result


def did_you_mean(db: Session, q: str, threshold: float = 0.3) -> Optional[str]:
    """Termo da base mais próximo de `q` via similarity trigram (limiar).

    Usa o operador `%` (pg_trgm) para restringir candidatos pelo índice GIN.
    Retorna None se `pg_trgm` ausente, termo curto/numérico ou sem similar (>0).
    """
    term, codigo = _normalize_search_q(q)
    if codigo is not None or not term or len(term) < 3 or not _trigram_enabled(db):
        return None
    ins, comp = settings.TABLE_INSUMOS, settings.TABLE_COMPOSICOES
    query = text(f"""
        SELECT descricao, MAX(sim) AS sim FROM (
            SELECT descricao, similarity(f_unaccent(descricao), f_unaccent(:q)) AS sim
            FROM {ins} WHERE f_unaccent(descricao) % f_unaccent(:q) AND status = :status
            UNION ALL
            SELECT descricao, similarity(f_unaccent(descricao), f_unaccent(:q)) AS sim
            FROM {comp} WHERE f_unaccent(descricao) % f_unaccent(:q) AND status = :status
        ) AS t GROUP BY descricao ORDER BY sim DESC LIMIT 1
    """)
    row = db.execute(query, {"q": term, "status": settings.DEFAULT_ITEM_STATUS}).first()
    if not row:
        return None
    best = dict(row._mapping)
    sim = best.get("sim")
    if sim is None or float(sim) < threshold or float(sim) >= 1.0:
        return None
    return best["descricao"]


def get_related_composicoes(
    db: Session, codigo: int, limit: int = 5
) -> List[dict]:
    """Composições relacionadas por similaridade Jaccard do BOM (camada 3).

    Jaccard = |A∩B| / |A∪B| sobre o conjunto de itens de cada composição,
    ignorando a própria. Estrutural (independente de UF/data) e barato com
    cache 24h — comportamento de `ComposicaoDetail.related`."""
    view = settings.VIEW_COMPOSICAO_ITENS
    query = text(f"""
        WITH alvo AS (
            SELECT DISTINCT item_codigo, tipo_item
            FROM {view} WHERE composicao_pai_codigo = :codigo
        ),
        cand AS (
            SELECT v.composicao_pai_codigo, COUNT(DISTINCT v.item_codigo) AS sobreposicao
            FROM {view} AS v
            JOIN alvo AS a ON a.item_codigo = v.item_codigo AND a.tipo_item = v.tipo_item
            WHERE v.composicao_pai_codigo <> :codigo
            GROUP BY v.composicao_pai_codigo
        ),
        tam AS (
            SELECT composicao_pai_codigo, COUNT(DISTINCT item_codigo) AS total_itens
            FROM {view} GROUP BY composicao_pai_codigo
        )
        SELECT c.codigo, c.descricao, c.unidade, cand.sobreposicao,
               (SELECT COUNT(*) FROM alvo) AS alvo_itens,
               ROUND(cand.sobreposicao::numeric /
                     ((SELECT COUNT(*) FROM alvo) + tam.total_itens - cand.sobreposicao), 4) AS jaccard
        FROM cand
        JOIN tam ON tam.composicao_pai_codigo = cand.composicao_pai_codigo
        JOIN {settings.TABLE_COMPOSICOES} AS c ON c.codigo = cand.composicao_pai_codigo
        WHERE c.status = :status
        ORDER BY jaccard DESC, sobreposicao DESC, c.descricao
        LIMIT :limit
    """)
    rows = db.execute(query, {
        "codigo": codigo, "limit": limit, "status": settings.DEFAULT_ITEM_STATUS,
    }).fetchall()
    return [dict(r._mapping) for r in rows]


@cache_result(ttl=86400)
def get_usado_em_summary(db: Session, codigo: int, top: int = 5) -> dict:
    """Resumo 'usado em' de um insumo (camada 3) — reusa `get_onde_usado` (cache 24h)."""
    onde = get_onde_usado(db, codigo, "insumo")
    items = [
        {
            "composicao_codigo": int(o.get("composicao_codigo") or 0),
            "composicao_descricao": o.get("composicao_descricao"),
            "nivel": o.get("nivel"),
        }
        for o in onde
    ]
    return {"total": len(onde), "items": items[:top]}

# --- Seção 2: Funções de BI ---

@cache_result(ttl=86400)
def get_composicao_bom(
    db: Session, codigo: int, uf: str, data_referencia: str, regime: str
) -> List[dict]:
    start_date, end_date = _get_date_range(data_referencia)
    query = text(f"""
    WITH RECURSIVE composicao_completa (item_codigo, tipo_item, coeficiente_total, nivel) AS (
        SELECT item_codigo, tipo_item, coeficiente, 1 FROM {settings.VIEW_COMPOSICAO_ITENS}
        WHERE composicao_pai_codigo = :codigo
        UNION ALL
        SELECT vis.item_codigo, vis.tipo_item, rec.coeficiente_total * vis.coeficiente, rec.nivel + 1
        FROM {settings.VIEW_COMPOSICAO_ITENS} AS vis
        JOIN composicao_completa AS rec ON vis.composicao_pai_codigo = rec.item_codigo
        WHERE rec.tipo_item = 'COMPOSICAO' AND rec.nivel < 10
    )
    SELECT cc.item_codigo, cc.tipo_item, MIN(cc.nivel) as nivel, COALESCE(i.descricao, c.descricao) AS descricao,
           COALESCE(i.unidade, c.unidade) AS unidade, SUM(cc.coeficiente_total) as coeficiente_total,
           COALESCE(pi.preco_mediano, pc.custo_total) AS custo_unitario,
           SUM(cc.coeficiente_total * COALESCE(pi.preco_mediano, pc.custo_total)) AS custo_impacto_total
    FROM composicao_completa cc
    LEFT JOIN {settings.TABLE_INSUMOS} i ON cc.item_codigo = i.codigo AND cc.tipo_item = 'INSUMO'
    LEFT JOIN {settings.TABLE_COMPOSICOES} c ON cc.item_codigo = c.codigo AND cc.tipo_item = 'COMPOSICAO'
    LEFT JOIN {settings.TABLE_PRECOS_INSUMOS} pi ON cc.item_codigo = pi.insumo_codigo AND pi.uf = :uf 
      AND pi.data_referencia >= :start_date AND pi.data_referencia <= :end_date AND pi.regime = :regime
    LEFT JOIN {settings.TABLE_CUSTOS_COMPOSICOES} pc ON cc.item_codigo = pc.composicao_codigo AND pc.uf = :uf 
      AND pc.data_referencia >= :start_date AND pc.data_referencia <= :end_date AND pc.regime = :regime
    GROUP BY 1, 2, 4, 5, 7 ORDER BY nivel, descricao;
    """)
    result = db.execute(query, {"codigo": codigo, "uf": uf.upper(), "start_date": start_date, "end_date": end_date, "regime": regime.upper()}).fetchall()
    return [dict(r._mapping) for r in result]

@cache_result(ttl=86400)
def get_abc_curve_for_composicoes(
    db: Session, codigos: List[int], uf: str, data_referencia: str, regime: str, top_n: int = 50
) -> List[dict]:
    start_date, end_date = _get_date_range(data_referencia)
    query = text(f"""
WITH RECURSIVE composicao_completa (item_codigo, tipo_item, coeficiente_total, nivel) AS (
        SELECT codigo, 'COMPOSICAO', 1.0, 1 FROM {settings.TABLE_COMPOSICOES} WHERE codigo IN :codigos
        UNION ALL
        SELECT vis.item_codigo, vis.tipo_item, rec.coeficiente_total * vis.coeficiente, rec.nivel + 1
        FROM {settings.VIEW_COMPOSICAO_ITENS} AS vis
        JOIN composicao_completa AS rec ON vis.composicao_pai_codigo = rec.item_codigo
        WHERE rec.tipo_item = 'COMPOSICAO' AND rec.nivel < 10
    )
    SELECT i.codigo, i.descricao, i.unidade, SUM(cc.coeficiente_total * p.preco_mediano) AS custo_impacto_total
    FROM composicao_completa cc
    JOIN {settings.TABLE_INSUMOS} i ON cc.item_codigo = i.codigo
    JOIN {settings.TABLE_PRECOS_INSUMOS} p ON i.codigo = p.insumo_codigo
    WHERE cc.tipo_item = 'INSUMO' AND p.uf = :uf AND p.data_referencia >= :start_date AND p.data_referencia <= :end_date AND p.regime = :regime
    GROUP BY i.codigo, i.descricao, i.unidade
    HAVING SUM(cc.coeficiente_total * p.preco_mediano) > 0
    ORDER BY custo_impacto_total DESC
    """)
    result = db.execute(query, {"codigos": tuple(codigos), "uf": uf.upper(), "start_date": start_date, "end_date": end_date, "regime": regime.upper()}).fetchall()
    insumos = [dict(r._mapping) for r in result]
    total_geral = sum(float(x['custo_impacto_total'] or 0) for x in insumos)
    acumulado = 0.0
    for item in insumos:
        impacto = float(item['custo_impacto_total'] or 0)
        acumulado += impacto
        item['custo_total_agregado'] = impacto
        item['percentual_individual'] = (impacto / total_geral * 100) if total_geral > 0 else 0
        item['percentual_acumulado'] = (acumulado / total_geral * 100) if total_geral > 0 else 0
        item['classe_abc'] = 'A' if item['percentual_acumulado'] <= 80 else ('B' if item['percentual_acumulado'] <= 95 else 'C')
    return insumos[:top_n]

def _compute_variacao(serie, value_key: str = 'valor'):
    """
    Enriquece uma série de pontos {data_referencia, <value_key>} com variação mês a mês.

    - `value_key`: chave numérica do ponto — 'valor' nas séries de histórico de
      custos; 'preco_medio' nas séries de tendência do BI (STORY-SIN-095/§3.7:
      ler a chave errada zerava a série inteira em silêncio).
    - 1º ponto: variacao_mensal e variacao_pct como None.
    - demais: variacao_mensal = valor_atual - valor_anterior;
      variacao_pct = variacao_mensal / valor_anterior * 100 (None se anterior == 0).
    - Ponto sem `value_key` → ValueError: nunca assumir 0 silencioso (zero
      silencioso era exatamente o defeito da auditoria §3.7).
    """
    out = []
    prev = None
    for point in serie:
        item = dict(point)
        if value_key not in item:
            raise ValueError(
                f"_compute_variacao: ponto sem a chave {value_key!r} "
                f"(chaves presentes: {sorted(item)}) — recusado para não zerar a série"
            )
        valor = float(item.get(value_key) or 0)
        if prev is None:
            item['variacao_mensal'] = None
            item['variacao_pct'] = None
        else:
            diff = valor - prev
            item['variacao_mensal'] = round(diff, 2)
            item['variacao_pct'] = round(diff / prev * 100, 4) if prev else None
        out.append(item)
        prev = valor
    return out


def _regional_stats(points):
    """
    Calcula estatísticas regionais básicas de uma lista {uf, valor}.
    """
    import statistics
    if not points:
        return {
            "media": 0.0, "mediana": 0.0, "min": 0.0, "max": 0.0,
            "desvio_padrao": 0.0, "amplitude": 0.0,
            "uf_mais_barato": None, "uf_mais_cara": None,
        }
    valores = [float(p.get('valor') or 0) for p in points]
    vals = [v for v in valores if v > 0]
    mediana = statistics.median(valores)
    min_, max_ = min(valores), max(valores)
    uf_cara = min(points, key=lambda p: -float(p.get('valor') or 0))
    uf_barato = min(points, key=lambda p: float(p.get('valor') or 0))
    if uf_barato.get('valor') is None:
        uf_mais_barato = None
    else:
        uf_mais_barato = uf_barato.get('uf')
    return {
        "media": round((sum(valores) / len(valores)) if valores else 0.0, 4),
        "mediana": round(mediana, 4),
        "min": round(min_, 4),
        "max": round(max_, 4),
        "desvio_padrao": round(statistics.pstdev(valores), 4) if len(valores) > 1 else 0.0,
        "amplitude": round(max_ - min_, 4),
        "uf_mais_barato": uf_mais_barato,
        "uf_mais_cara": uf_cara.get('uf'),
    }


@cache_result(ttl=86400)
def get_custo_historico(
    db: Session, tipo_item: str, codigo: int, uf: str, regime: str, data_inicio: str, data_fim: str
) -> List[dict]:
    table = settings.TABLE_PRECOS_INSUMOS if tipo_item == 'insumo' else settings.TABLE_CUSTOS_COMPOSICOES
    col = 'insumo_codigo' if tipo_item == 'insumo' else 'composicao_codigo'
    val = 'preco_mediano' if tipo_item == 'insumo' else 'custo_total'
    s_date, _ = _get_date_range(data_inicio)
    _, e_date = _get_date_range(data_fim)
    query = text(f"SELECT TO_CHAR(data_referencia, 'YYYY-MM') as data_referencia, {val} as valor FROM {table} WHERE {col} = :c AND uf = :uf AND regime = :r AND data_referencia >= :s AND data_referencia <= :e ORDER BY data_referencia")
    result = db.execute(query, {"c": codigo, "uf": uf.upper(), "r": regime.upper(), "s": s_date, "e": e_date}).fetchall()
    serie = [dict(r._mapping) for r in result]
    return _compute_variacao(serie)

@cache_result(ttl=86400)
def get_composicao_man_hours(db: Session, codigo: int):
    """
    Calcula o total de Hora/Homem para uma composição, somando os coeficientes
    de todos os insumos de mão de obra (unidade 'H') em todos os níveis.
    """
    query = text(f"""
    WITH RECURSIVE composicao_completa (item_codigo, tipo_item, coeficiente_total, nivel) AS (
        SELECT item_codigo, tipo_item, coeficiente, 1 FROM {settings.VIEW_COMPOSICAO_ITENS}
        WHERE composicao_pai_codigo = :codigo
        UNION ALL
        SELECT vis.item_codigo, vis.tipo_item, rec.coeficiente_total * vis.coeficiente, rec.nivel + 1
        FROM {settings.VIEW_COMPOSICAO_ITENS} AS vis
        JOIN composicao_completa AS rec ON vis.composicao_pai_codigo = rec.item_codigo
        WHERE rec.tipo_item = 'COMPOSICAO' AND rec.nivel < 10
    )
    SELECT SUM(cc.coeficiente_total) as total_hora_homem
    FROM composicao_completa cc
    JOIN {settings.TABLE_INSUMOS} i ON cc.item_codigo = i.codigo
    WHERE cc.tipo_item = 'INSUMO' AND UPPER(i.unidade) = 'H';
    """)
    result = db.execute(query, {"codigo": codigo}).first()
    if result is None or result.total_hora_homem is None:
        return {'total_hora_homem': 0.0}
    return dict(result._mapping)

@cache_result(ttl=86400)
def get_candidatos_otimizacao(
    db: Session, codigo: int, uf: str, data_referencia: str, regime: str, top_n: int = 5
) -> List[dict]:
    """
    Retorna os N insumos de maior impacto financeiro em uma composição.
    Reutiliza a lógica do BOM filtrando apenas insumos e ordenando por impacto.
    """
    bom_data = get_composicao_bom(db, codigo, uf, data_referencia, regime)
    insumos = [item for item in bom_data if item.get('tipo_item') == 'INSUMO']
    insumos.sort(key=lambda x: float(x.get('custo_impacto_total') or 0), reverse=True)
    return insumos[:top_n]

@cache_result(ttl=86400)
def get_manutencoes_historico(db: Session, codigo: int, tipo_item: str) -> List[dict]:
    """
    Retorna o histórico de manutenção (ativações/desativações) de um item.
    """
    # SIN-094: comparação case/acento-insensível — o ETL grava
    # 'COMPOSICAO'/'COMPOSIÇÃO' e o path chega 'composicao'.
    tipo_norm = _normalize_tipo_item(tipo_item)
    query = text(f"""
        SELECT item_codigo, tipo_item,
               TO_CHAR(data_referencia, 'YYYY-MM') as data_referencia,
               tipo_manutencao, descricao_item
        FROM {settings.TABLE_MANUTENCOES_HISTORICO}
        WHERE item_codigo = :codigo
          AND {_SQL_TIPO_NORM.format(col='tipo_item')} = :tipo_norm
        ORDER BY data_referencia DESC
    """)
    result = db.execute(query, {"codigo": codigo, "tipo_norm": tipo_norm}).fetchall()
    return [dict(r._mapping) for r in result]

@cache_result(ttl=86400)
def get_abc_by_classificacao(
    db: Session, codigos: List[int], uf: str, data_referencia: str, regime: str
) -> List[dict]:
    """
    Calcula a Curva ABC agrupada por classificação de insumo,
    agregando todos os insumos de mesma categoria.
    """
    start_date, end_date = _get_date_range(data_referencia)
    query = text(f"""
    WITH RECURSIVE composicao_completa (item_codigo, tipo_item, coeficiente_total, nivel) AS (
        SELECT codigo, 'COMPOSICAO', 1.0, 1 FROM {settings.TABLE_COMPOSICOES} WHERE codigo IN :codigos
        UNION ALL
        SELECT vis.item_codigo, vis.tipo_item, rec.coeficiente_total * vis.coeficiente, rec.nivel + 1
        FROM {settings.VIEW_COMPOSICAO_ITENS} as vis
        JOIN composicao_completa as rec ON vis.composicao_pai_codigo = rec.item_codigo
        WHERE rec.tipo_item = 'COMPOSICAO' AND rec.nivel < 10
    )
    SELECT i.classificacao,
           SUM(cc.coeficiente_total * p.preco_mediano) as custo_total,
           COUNT(DISTINCT i.codigo) as total_insumos
    FROM composicao_completa cc
    JOIN {settings.TABLE_INSUMOS} i ON cc.item_codigo = i.codigo
    JOIN {settings.TABLE_PRECOS_INSUMOS} p ON i.codigo = p.insumo_codigo
    WHERE cc.tipo_item = 'INSUMO' AND p.uf = :uf
      AND p.data_referencia >= :start_date AND p.data_referencia <= :end_date AND p.regime = :regime
      AND i.classificacao IS NOT NULL AND i.classificacao != ''
    GROUP BY i.classificacao
    HAVING SUM(cc.coeficiente_total * p.preco_mediano) > 0
    ORDER BY custo_total DESC;
    """)
    result = db.execute(query, {"codigos": tuple(codigos), "uf": uf.upper(), "start_date": start_date, "end_date": end_date, "regime": regime.upper()}).fetchall()
    categorias = [dict(r._mapping) for r in result]
    total_geral = sum(float(x['custo_total'] or 0) for x in categorias)
    for item in categorias:
        item['percentual'] = (float(item['custo_total'] or 0) / total_geral * 100) if total_geral > 0 else 0
    return categorias

@cache_result(ttl=86400)
def get_tendencias(
    db: Session, uf: str, regime: str, data_referencia: str, agrupar_por: str = 'classificacao', meses: int = 12, codigos: List[int] = None
) -> List[dict]:
    """
    Retorna a evolução mensal do preço/custo médio agrupado por classificação, grupo ou item individual.
    """
    s_date, e_date = _get_date_range(data_referencia)
    from dateutil.relativedelta import relativedelta
    end_date = e_date
    start_date = s_date - relativedelta(months=meses)
    
    if agrupar_por == 'grupo':
        table_val = settings.TABLE_CUSTOS_COMPOSICOES
        table_item = settings.TABLE_COMPOSICOES
        col_item = 'composicao_codigo'
        col_group = 'grupo'
        val_name = 'custo_total'
    elif agrupar_por == 'item':
        # Para itens individuais, podemos usar insumos ou composições.
        # Por padrão, vamos focar em insumos se não houver codigos, ou tentar detectar.
        # Mas para simplificar, se 'item', vamos usar codigos obrigatoriamente.
        table_val = settings.TABLE_PRECOS_INSUMOS
        table_item = settings.TABLE_INSUMOS
        col_item = 'insumo_codigo'
        col_group = 'descricao' # Group by desc to show name
        val_name = 'preco_mediano'
    else:
        table_val = settings.TABLE_PRECOS_INSUMOS
        table_item = settings.TABLE_INSUMOS
        col_item = 'insumo_codigo'
        col_group = 'classificacao'
        val_name = 'preco_mediano'

    where_clause = "WHERE p.uf = :uf AND p.regime = :regime AND p.data_referencia >= :start_date AND p.data_referencia <= :end_date"
    params = {
        "uf": uf.upper(), "regime": regime.upper(),
        "start_date": start_date, "end_date": end_date
    }

    if codigos:
        where_clause += " AND i.codigo IN :codigos"
        params["codigos"] = tuple(codigos)

    group_cols = "1, 2"
    if agrupar_por == 'item':
        group_cols = "i.codigo, i.descricao, 2"
        select_group = "i.codigo || ' - ' || i.descricao"
    else:
        select_group = f"""
               CASE 
                   WHEN i.{col_group} IS NULL OR TRIM(i.{col_group}) = '' OR UPPER(TRIM(i.{col_group})) = 'NAO_CLASSIFICADO' THEN 'GERAL'
                   ELSE UPPER(TRIM(i.{col_group})) 
               END"""

    query = text(f"""
        SELECT {select_group} as classificacao,
               TO_CHAR(p.data_referencia, 'YYYY-MM') as mes,
               AVG(p.{val_name}) as preco_medio,
               COUNT(DISTINCT i.codigo) as qtd_insumos
        FROM {table_val} p
        JOIN {table_item} i ON i.codigo = p.{col_item}
        {where_clause}
        GROUP BY {group_cols}
        ORDER BY 1, mes
    """)
    result = db.execute(query, params).fetchall()
    rows = [dict(r._mapping) for r in result]

    from itertools import groupby
    enriched = []
    for _, group in groupby(rows, key=lambda r: r['classificacao']):
        series = list(group)
        # Linhas do BI trazem `preco_medio` (não `valor`) — STORY-SIN-095/§3.7
        with_var = _compute_variacao(series, value_key='preco_medio')
        values = [float(r.get('preco_medio') or 0) for r in series]
        variacao_periodo = None
        inflacao_acumulada = None
        if values and values[0] > 0 and len(values) > 1:
            variacao_periodo = round((values[-1] - values[0]) / values[0] * 100, 4)
            acum = 1.0
            for prev, cur in zip(values, values[1:]):
                acum *= (1 + (cur - prev) / prev) if prev > 0 else 1.0
            inflacao_acumulada = round((acum - 1) * 100, 4)
        for i, row in enumerate(with_var):
            window = values[max(0, i - 2): i + 1]
            media_movel = (sum(window) / len(window)) if window else None
            row['media_movel'] = round(media_movel, 4) if media_movel is not None else None
            row['variacao_periodo'] = variacao_periodo
            row['inflacao_acumulada'] = inflacao_acumulada
            enriched.append(row)
    return enriched

@cache_result(ttl=3600)
def get_precos_all_ufs(
    db: Session, tipo_item: str, codigo: int, data_referencia: str, regime: str
) -> List[dict]:
    """
    Retorna o preço de um item em TODAS as UFs disponíveis.
    """
    start_date, end_date = _get_date_range(data_referencia)
    table = settings.TABLE_PRECOS_INSUMOS if tipo_item == 'insumo' else settings.TABLE_CUSTOS_COMPOSICOES
    col = 'insumo_codigo' if tipo_item == 'insumo' else 'composicao_codigo'
    val = 'preco_mediano' if tipo_item == 'insumo' else 'custo_total'
    query = text(f"""
        SELECT uf, {val} as valor
        FROM {table}
        WHERE {col} = :codigo
          AND data_referencia >= :start_date AND data_referencia <= :end_date
          AND regime = :regime
        ORDER BY uf
    """)
    result = db.execute(query, {
        "codigo": codigo, "start_date": start_date, "end_date": end_date,
        "regime": regime.upper()
    }).fetchall()
    return [dict(r._mapping) for r in result]

@cache_result(ttl=86400)
def get_composicao_produtividade(
    db: Session, codigo: int, uf: str, data_referencia: str, regime: str
) -> dict:
    """
    Classifica os itens do BOM de uma composição em Mão de Obra, Material e Equipamento,
    retornando o total de Horas-Homem, custo total e custo por HH.
    """
    bom_data = get_composicao_bom(db, codigo, uf, data_referencia, regime)
    if not bom_data:
        return None

    total_hh = 0.0
    mao_de_obra = 0.0
    equipamento = 0.0
    material = 0.0

    # SIN-094: total por FOLHAS — pais COMPOSICAO com custo consolidado
    # duplicariam os filhos explodidos (caso 87328: 533,41 → 407,62).
    for item in _filter_bom_leaves(bom_data):
        impacto = float(item.get('custo_impacto_total') or 0)
        unidade = (item.get('unidade') or '').upper()

        if unidade == 'H':
            mao_de_obra += impacto
            total_hh += float(item.get('coeficiente_total') or 0)
        elif unidade in ('CHP', 'CHI', 'EQ'):
            equipamento += impacto
        else:
            material += impacto

    total = mao_de_obra + material + equipamento
    custo_por_hh = total / total_hh if total_hh > 0 else None

    return {
        "total_custo": round(total, 2),
        "mao_de_obra": round(mao_de_obra, 2),
        "material": round(material, 2),
        "equipamento": round(equipamento, 2),
        "total_hh": round(total_hh, 4),
        "custo_por_hh": round(custo_por_hh, 2) if custo_por_hh is not None else None,
    }

@cache_result(ttl=86400)
def get_onde_usado(
    db: Session, codigo: int, tipo_item: str = 'insumo'
) -> List[dict]:
    """
    Query reversa recursiva: encontra todas as composições que usam um insumo
    (ou subcomposição) em qualquer nível hierárquico.
    """
    item_type = 'INSUMO' if tipo_item == 'insumo' else 'COMPOSICAO'
    query = text(f"""
        WITH RECURSIVE parents AS (
            SELECT composicao_pai_codigo, coeficiente, 1 as nivel
            FROM {settings.VIEW_COMPOSICAO_ITENS}
            WHERE item_codigo = :codigo AND tipo_item = :item_type
            UNION ALL
            SELECT ci.composicao_pai_codigo, p.coeficiente * ci.coeficiente, p.nivel + 1
            FROM {settings.VIEW_COMPOSICAO_ITENS} ci
            JOIN parents p ON ci.item_codigo = p.composicao_pai_codigo
            WHERE ci.tipo_item = 'COMPOSICAO' AND p.nivel < 10
        )
        SELECT DISTINCT c.codigo as composicao_codigo, c.descricao as composicao_descricao,
               'COMPOSICAO' as tipo_item, p.coeficiente, p.nivel
        FROM parents p
        JOIN {settings.TABLE_COMPOSICOES} c ON c.codigo = p.composicao_pai_codigo
        ORDER BY p.nivel, c.descricao
    """)
    result = db.execute(query, {"codigo": codigo, "item_type": item_type}).fetchall()
    return [dict(r._mapping) for r in result]


@cache_result(ttl=3600)
def get_audit_events(
    db: Session, tipo_item: str, codigo: int, data_referencia: str = None
) -> List[dict]:
    """
    Retorna a trilha de auditoria (histórico de manutenções/retificacoes) de um
    item. A tabela de auditoria por item é `manutencoes_historico`, que registra
    ativacoes/desativacoes e retificacoes por data de referencia.
    """
    tipo = (tipo_item or "").upper()
    if tipo not in ("INSUMO", "COMPOSICAO"):
        tipo = tipo_item  # mantém o valor original; o filtro simplesmente não casará

    query_str = f"""
        SELECT
            ROW_NUMBER() OVER (ORDER BY data_referencia DESC) AS id,
            'manutencoes_historico' AS table_name,
            jsonb_build_object(
                'item_codigo', item_codigo,
                'tipo_item', tipo_item,
                'data_referencia', TO_CHAR(data_referencia, 'YYYY-MM')
            ) AS record_pk,
            tipo_manutencao AS operation,
            NULL AS old_values,
            NULL AS new_values,
            sinapi_versao,
            descricao_item AS motivo_manutencao,
            created_at
        FROM {settings.TABLE_MANUTENCOES_HISTORICO}
        WHERE item_codigo = :codigo AND tipo_item = :tipo
    """
    params = {"codigo": codigo, "tipo": tipo}

    if data_referencia:
        query_str += " AND TO_CHAR(data_referencia, 'YYYY-MM') = :data_ref"
        params["data_ref"] = data_referencia

    query_str += " ORDER BY data_referencia DESC LIMIT 100"

    query = text(query_str)
    result = db.execute(query, params).fetchall()
    return [dict(r._mapping) for r in result]

def get_cenario_spread(
    db: Session, codigos: List[int], uf: str, data_referencia: str, regime: str
) -> dict:
    """
    Calcula o spread regional do custo total do cenário: estatísticas do custo
    agregado (todas as composições) em todas as UFs disponíveis na referência.
    """
    start_date, end_date = _get_date_range(data_referencia)
    query = text(f"""
        SELECT uf, SUM(custo_total) as valor
        FROM {settings.TABLE_CUSTOS_COMPOSICOES}
        WHERE composicao_codigo IN :codigos
          AND data_referencia >= :start_date AND data_referencia <= :end_date
          AND regime = :regime
        GROUP BY uf
        ORDER BY uf
    """)
    result = db.execute(query, {
        "codigos": tuple(codigos),
        "start_date": start_date, "end_date": end_date, "regime": regime.upper()
    }).fetchall()
    points = [dict(r._mapping) for r in result]
    return _regional_stats(points)


def get_cenario_tendencias(
    db: Session, codigos: List[int], uf: str, data_referencia: str, regime: str,
    meses: int = 12
) -> List[dict]:
    """
    Evolução mensal do custo total de um grupo de composições no cenário.
    """
    from dateutil.relativedelta import relativedelta
    _, e_date = _get_date_range(data_referencia)
    s_date = e_date - relativedelta(months=meses)
    query = text(f"""
        SELECT TO_CHAR(data_referencia, 'YYYY-MM') as data_referencia, SUM(custo_total) as valor
        FROM {settings.TABLE_CUSTOS_COMPOSICOES}
        WHERE composicao_codigo IN :codigos AND uf = :uf AND regime = :regime
          AND data_referencia >= :s_date AND data_referencia <= :e_date
        GROUP BY 1
        ORDER BY 1
    """)
    result = db.execute(query, {
        "codigos": tuple(codigos), "uf": uf.upper(), "regime": regime.upper(),
        "s_date": s_date, "e_date": e_date
    }).fetchall()
    serie = [dict(r._mapping) for r in result]
    return _compute_variacao(serie)


def get_cenario(
    db: Session, codigos: List[int], uf: str, data_referencia: str, regime: str, meses: int = 12
) -> dict:
    """
    Consolida um cenário orçamentário 'PowerBI do SINAPI':
    composições, total do BOM, Curva ABC, spread regional e tendências.
    """
    composicoes = []
    for codigo in codigos:
        comp = get_composicao_by_codigo(db, codigo, uf, data_referencia, regime) or {}
        bom = get_composicao_bom(db, codigo, uf, data_referencia, regime)
        custo_total = sum(float(i.get('custo_impacto_total') or 0) for i in (bom or []))
        composicoes.append({
            "codigo": codigo,
            "descricao": comp.get('descricao') or str(codigo),
            "custo_total": round(custo_total, 4),
        })

    total_bom = round(sum(float(c['custo_total']) for c in composicoes), 4)
    abc = get_abc_curve_for_composicoes(db, codigos=codigos, uf=uf,
                                        data_referencia=data_referencia, regime=regime) or []

    return {
        "uf": uf.upper(),
        "data_referencia": data_referencia,
        "regime": regime.upper(),
        "composicoes": composicoes,
        "total_bom": total_bom,
        "abc": abc,
        "spread_regional": get_cenario_spread(db, codigos, uf, data_referencia, regime),
        "tendencias": get_cenario_tendencias(db, codigos, uf, data_referencia, regime, meses=meses),
    }
