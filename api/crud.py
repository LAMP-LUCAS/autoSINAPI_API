import pandas as pd
import calendar
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

def get_insumo_by_codigo(
    db: Session, codigo: int, uf: str, data_referencia: str, regime: str
) -> Optional[dict]:
    start_date, end_date = _get_date_range(data_referencia)
    query = text(f"""
        SELECT i.codigo, i.descricao, i.unidade, i.classificacao, i.status, p.preco_mediano
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
    return result

def search_insumos_by_descricao(
    db: Session, q: str, uf: str, data_referencia: str, regime: str, skip: int, limit: int
) -> List[dict]:
    start_date, end_date = _get_date_range(data_referencia)
    query = text(f"""
        SELECT i.codigo, i.descricao, i.unidade, i.classificacao, i.status, p.preco_mediano
        FROM {settings.TABLE_INSUMOS} AS i
        JOIN {settings.TABLE_PRECOS_INSUMOS} AS p ON i.codigo = p.insumo_codigo
        WHERE i.descricao ILIKE :query AND i.status = :status AND p.uf = :uf
          AND p.data_referencia >= :start_date AND p.data_referencia <= :end_date
          AND p.regime = :regime
        ORDER BY i.descricao OFFSET :skip LIMIT :limit
    """)
    result = db.execute(query, {
        "query": f"%{q}%", "uf": uf.upper(), "start_date": start_date, "end_date": end_date,
        "regime": regime.upper(), "status": settings.DEFAULT_ITEM_STATUS,
        "skip": skip, "limit": limit
    }).fetchall()
    return result

def get_composicao_by_codigo(
    db: Session, codigo: int, uf: str, data_referencia: str, regime: str
) -> Optional[dict]:
    start_date, end_date = _get_date_range(data_referencia)
    query = text(f"""
        SELECT c.codigo, c.descricao, c.unidade, c.grupo, c.status, p.custo_total
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
    return result

def search_composicoes_by_descricao(
    db: Session, q: str, uf: str, data_referencia: str, regime: str, skip: int, limit: int
) -> List[dict]:
    start_date, end_date = _get_date_range(data_referencia)
    query = text(f"""
        SELECT c.codigo, c.descricao, c.unidade, c.grupo, c.status, p.custo_total
        FROM {settings.TABLE_COMPOSICOES} AS c
        JOIN {settings.TABLE_CUSTOS_COMPOSICOES} AS p ON c.codigo = p.composicao_codigo
        WHERE c.descricao ILIKE :query AND c.status = :status AND p.uf = :uf
          AND p.data_referencia >= :start_date AND p.data_referencia <= :end_date
          AND p.regime = :regime
        ORDER BY c.descricao OFFSET :skip LIMIT :limit
    """)
    result = db.execute(query, {
        "query": f"%{q}%", "uf": uf.upper(), "start_date": start_date, "end_date": end_date,
        "regime": regime.upper(), "status": settings.DEFAULT_ITEM_STATUS,
        "skip": skip, "limit": limit
    }).fetchall()
    return result

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
    WITH RECURSIVE composicao_completa (item_codigo, tipo_item, coeficiente_total) AS (
        SELECT codigo, 'COMPOSICAO', 1.0 FROM {settings.TABLE_COMPOSICOES} WHERE codigo IN :codigos
        UNION ALL
        SELECT vis.item_codigo, vis.tipo_item, rec.coeficiente_total * vis.coeficiente
        FROM {settings.VIEW_COMPOSICAO_ITENS} as vis
        JOIN composicao_completa as rec ON vis.composicao_pai_codigo = rec.item_codigo
        WHERE rec.tipo_item = 'COMPOSICAO'
    )
    SELECT i.codigo, i.descricao, i.unidade, SUM(cc.coeficiente_total * p.preco_mediano) AS custo_impacto_total
    FROM composicao_completa cc
    JOIN {settings.TABLE_INSUMOS} i ON cc.item_codigo = i.codigo
    JOIN {settings.TABLE_PRECOS_INSUMOS} p ON i.codigo = p.insumo_codigo
    WHERE cc.tipo_item = 'INSUMO' AND p.uf = :uf
      AND p.data_referencia >= :start_date AND p.data_referencia <= :end_date AND p.regime = :regime
    GROUP BY i.codigo, i.descricao, i.unidade
    HAVING SUM(cc.coeficiente_total * p.preco_mediano) > 0
    ORDER BY custo_impacto_total DESC;
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
    return [dict(r._mapping) for r in result]

@cache_result(ttl=86400)
def get_composicao_man_hours(db: Session, codigo: int):
    """
    Calcula o total de Hora/Homem para uma composição, somando os coeficientes
    de todos os insumos de mão de obra (unidade 'H') em todos os níveis.
    """
    query = text(f"""
    WITH RECURSIVE composicao_completa (item_codigo, tipo_item, coeficiente_total) AS (
        SELECT item_codigo, tipo_item, coeficiente FROM {settings.VIEW_COMPOSICAO_ITENS}
        WHERE composicao_pai_codigo = :codigo
        UNION ALL
        SELECT vis.item_codigo, vis.tipo_item, rec.coeficiente_total * vis.coeficiente
        FROM {settings.VIEW_COMPOSICAO_ITENS} AS vis
        JOIN composicao_completa AS rec ON vis.composicao_pai_codigo = rec.item_codigo
        WHERE rec.tipo_item = 'COMPOSICAO'
    )
    SELECT SUM(cc.coeficiente_total) as total_hora_homem
    FROM composicao_completa cc
    JOIN {settings.TABLE_INSUMOS} i ON cc.item_codigo = i.codigo
    WHERE cc.tipo_item = 'INSUMO' AND UPPER(i.unidade) = 'H';
    """)
    result = db.execute(query, {"codigo": codigo}).first()
    if result is None or result.total_hora_homem is None:
        return type('ManHoursResult', (), {'total_hora_homem': 0.0})()
    return result

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
    query = text(f"""
        SELECT item_codigo, tipo_item,
               TO_CHAR(data_referencia, 'YYYY-MM') as data_referencia,
               tipo_manutencao, descricao_item
        FROM {settings.TABLE_MANUTENCOES_HISTORICO}
        WHERE item_codigo = :codigo AND tipo_item = :tipo_item
        ORDER BY data_referencia DESC
    """)
    result = db.execute(query, {"codigo": codigo, "tipo_item": tipo_item}).fetchall()
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
    WITH RECURSIVE composicao_completa (item_codigo, tipo_item, coeficiente_total) AS (
        SELECT codigo, 'COMPOSICAO', 1.0 FROM {settings.TABLE_COMPOSICOES} WHERE codigo IN :codigos
        UNION ALL
        SELECT vis.item_codigo, vis.tipo_item, rec.coeficiente_total * vis.coeficiente
        FROM {settings.VIEW_COMPOSICAO_ITENS} as vis
        JOIN composicao_completa as rec ON vis.composicao_pai_codigo = rec.item_codigo
        WHERE rec.tipo_item = 'COMPOSICAO'
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
