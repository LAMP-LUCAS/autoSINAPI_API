"""
Pipeline de busca unificada — Fase 2-4 (STORY-SRC-002 / ADR-006).

Composição de camadas do EPIC-search-engine-google-powerbi:
  Camada 1/2 — ILIKE/trigrama (crud) — sempre ativa.
  Camada 3   — relacional: `usado_em` (insumo) via `crud.get_usado_em_summary`.
  Camada 4   — vetorial (Fase 4): embeddings cosine + RRF sobre o resultado
    trigrama quando `vector` é solicitado e a extensão/embeddings existem.
    Degrada graciosamente (meta.degraded) quando a infra vetorial está fora
    (SPEC-RULE-search-pipeline-graceful-degradation).
  `did_you_mean` quando a busca não retorna resultados.
"""
from typing import List, Optional

import logging

from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout

from sqlalchemy.orm import Session

from . import crud

logger = logging.getLogger("autosinapi.search")


def build_meta(
    providers: List[str],
    degraded: Optional[List[str]] = None,
    did_you_mean: Optional[str] = None,
    page: Optional[int] = None,
    page_size: Optional[int] = None,
    total: Optional[int] = None,
    relaxed: bool = False,
) -> dict:
    return {
        "providers": list(providers),
        "degraded": list(degraded or []),
        "did_you_mean": did_you_mean,
        "page": page,
        "page_size": page_size,
        "total": total,
        "relaxed": relaxed,
    }


def _rrf_merge(trigram_items: List[dict], vector_hits: List[dict], k: int = 60) -> List[dict]:
    """Fusão Recíproca de Ranking (RRF) entre trigrama e vetorial.

    Re-ranking híbrido deterministic: itens presentes nas duas listas ganham
    ranking recíproco somado (1/(k+pos)), os exclusivos mantêm 1/(k+pos).
    Itens só da busca vetorial são DESCARTADOS (camada 4 refina o conjunto
    textual; não expande sem matching lexical) — evita ruído semântico.
    Saída: lista reordenada, mantendo dicts originais.
    """
    if not vector_hits or not trigram_items:
        return trigram_items

    def key(it) -> tuple:
        tipo = it.get("tipo") or it.get("tipo_item") or ""
        return (int(it.get("codigo", 0)), str(tipo))

    tri_scores = {key(it): 1.0 / (k + i + 1) for i, it in enumerate(trigram_items)}
    vec_scores = {key(h): 1.0 / (k + i + 1) for i, h in enumerate(vector_hits)}

    by_id = {key(it): it for it in trigram_items}
    merged = sorted(
        trigram_items,
        key=lambda it: tri_scores.get(key(it), 0.0) + vec_scores.get(key(it), 0.0),
        reverse=True,
    )
    return merged


def unified_search(
    db: Session, q: str, uf: str, data_referencia: str, regime: str,
    tipo: str = "all", sort: str = "relevance", vector: Optional[str] = None,
    skip: int = 0, limit: int = 100, grupo: Optional[str] = None,
    classificacao: Optional[str] = None,
) -> dict:
    """Busca unificada com meta de enriquecimento e degradação graciosa."""
    trigram = crud._trigram_enabled(db)
    providers = ["trigram" if trigram else "ilike"]
    degraded = []

    result = crud.search_unified(
        db, q, uf, data_referencia, regime,
        tipo=tipo, sort=sort, skip=skip, limit=limit,
        grupo=grupo, classificacao=classificacao,
    )
    items, total = result["items"], int(result.get("total") or 0)

    # Camada 4 opt-in: vetor ativo → tenta enriquecer/rerankar por RRF.
    # Contrato: só entra em `providers` se funcionar; falha OU lentidão →
    # `degraded` (SPEC-RULE-search-pipeline-graceful-degradation).
    # STORY-SIN-095/§3.3: o passo vetorial roda sob orçamento
    # (`SEARCH_VECTOR_TIMEOUT`) — o primary pendurado (EMBEDDING_TIMEOUT=120s)
    # não pode estourar o timeout do cliente (MCP: 30s → virava erro).
    if vector not in (None, "off"):
        from .config import settings

        budget = float(getattr(settings, "SEARCH_VECTOR_TIMEOUT", 8.0))

        def _vector_step():
            from . import vector_store  # import opcional: dentro do orçamento

            meta_model = vector_store.VECTOR_MODELS[settings.SEARCH_VECTOR_MODEL]
            tname = vector_store.table_name(meta_model["dims"],
                                             settings.SEARCH_VECTOR_MODEL)
            # timeout/2 por endpoint: primary + fallback somam o orçamento.
            query_vec = (vector_store.EmbeddingProvider(timeout=budget / 2).embed([q])
                         if items else [])
            if not query_vec:
                return []
            # Sessão própria: falha SQL da camada 4 não envenena a transação
            # da request (§3.3: erro vetorial derrubava o enriquecimento
            # seguinte com InFailedSqlTransaction → 5xx em vez de degraded).
            vdb = Session(db.get_bind())
            try:
                return vector_store.cosine_search(
                    vdb, tname, tipo if tipo in ("insumo", "composicao") else "all",
                    query_vec[0], limit=max(limit, 40),
                )
            finally:
                vdb.close()

        executor = ThreadPoolExecutor(max_workers=1,
                                      thread_name_prefix="search-vector")
        try:
            hits = executor.submit(_vector_step).result(timeout=budget)
            if not hits:
                degraded.append("vector")
            else:
                items = _rrf_merge(items, hits)[:limit]
                providers.append("vector")
        except FuturesTimeout:
            degraded.append("vector")
            logger.warning(
                "camada vetorial estourou o orçamento de %.1fs — degradada",
                budget,
            )
        except Exception as exc:  # noqa: BLE001 - degradação graciosa
            degraded.append("vector")
            logger.warning("camada vetorial degradada: %s", exc)
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    for it in items:
        if it.get("tipo") == "insumo":
            it["usado_em"] = crud.get_usado_em_summary(db, int(it["codigo"]))

    dym = None
    if total == 0 and crud._normalize_search_q(q)[1] is None:
        try:
            dym = crud.did_you_mean(db, q)
        except Exception:
            dym = None

    page_no = (skip // limit) + 1 if limit else 1
    meta = build_meta(providers, degraded, did_you_mean=dym,
                      page=page_no, page_size=limit, total=total,
                      relaxed=bool(result.get("relaxed", False)))
    # total é o total textual; o RRF apenas reordena dentro da página →
    # mantém contrato (total >= len(items)).
    return {"items": items, "total": total, "meta": meta}
