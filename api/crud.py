# api/crud.py (versão refatorada e expandida com BI)
"""
Módulo CRUD (Create, Read, Update, Delete) e de Business Intelligence para a API.

Este módulo contém as funções de acesso ao banco de dados, abstraindo as queries
SQL. Ele é dividido em duas seções:
1. Funções de busca direta (CRUD).
2. Funções de análise e Business Intelligence (BI).

Utiliza o módulo de configuração para obter nomes de tabelas e constantes.
"""
import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Optional

# Importa a instância única de configurações
from .config import settings

# --- Seção 1: Funções de Busca Direta (CRUD) ---

def get_insumo_by_codigo(
    db: Session, codigo: int, uf: str, data_referencia: str, regime: str
) -> Optional[dict]:
    """
    Busca um único insumo pelo seu código, retornando seu preço para um
    contexto específico (UF, data e regime).
    """
    query = text(f"""
        SELECT
            i.codigo, i.descricao, i.unidade, p.preco_mediano
        FROM {settings.TABLE_INSUMOS} AS i
        JOIN {settings.TABLE_PRECOS_INSUMOS} AS p ON i.codigo = p.insumo_codigo
        WHERE i.codigo = :codigo
          AND i.status = :status
          AND p.uf = :uf
          AND TO_CHAR(p.data_referencia, 'YYYY-MM') = :data_referencia
          AND p.regime = :regime
    """)
    result = db.execute(query, {
        "codigo": codigo, "uf": uf.upper(), "data_referencia": data_referencia,
        "regime": regime.upper(), "status": settings.DEFAULT_ITEM_STATUS
    }).first()
    return result

def search_insumos_by_descricao(
    db: Session, q: str, uf: str, data_referencia: str, regime: str, skip: int, limit: int
) -> List[dict]:
    """
    Busca insumos por uma string em sua descrição, retornando os preços
    para um contexto específico.
    """
    query = text(f"""
        SELECT
            i.codigo, i.descricao, i.unidade, p.preco_mediano
        FROM {settings.TABLE_INSUMOS} AS i
        JOIN {settings.TABLE_PRECOS_INSUMOS} AS p ON i.codigo = p.insumo_codigo
        WHERE i.descricao ILIKE :query
          AND i.status = :status
          AND p.uf = :uf
          AND TO_CHAR(p.data_referencia, 'YYYY-MM') = :data_referencia
          AND p.regime = :regime
        ORDER BY i.descricao OFFSET :skip LIMIT :limit
    """)
    result = db.execute(query, {
        "query": f"%{q}%", "uf": uf.upper(), "data_referencia": data_referencia,
        "regime": regime.upper(), "status": settings.DEFAULT_ITEM_STATUS,
        "skip": skip, "limit": limit
    }).fetchall()
    return result

def get_composicao_by_codigo(
    db: Session, codigo: int, uf: str, data_referencia: str, regime: str
) -> Optional[dict]:
    """
    Busca uma única composição pelo seu código, retornando seu custo total
    para um contexto específico (UF, data e regime).
    """
    query = text(f"""
        SELECT
            c.codigo, c.descricao, c.unidade, p.custo_total
        FROM {settings.TABLE_COMPOSICOES} AS c
        JOIN {settings.TABLE_CUSTOS_COMPOSICOES} AS p ON c.codigo = p.composicao_codigo
        WHERE c.codigo = :codigo
          AND c.status = :status
          AND p.uf = :uf
          AND TO_CHAR(p.data_referencia, 'YYYY-MM') = :data_referencia
          AND p.regime = :regime
    """)
    result = db.execute(query, {
        "codigo": codigo, "uf": uf.upper(), "data_referencia": data_referencia,
        "regime": regime.upper(), "status": settings.DEFAULT_ITEM_STATUS
    }).first()
    return result

def search_composicoes_by_descricao(
    db: Session, q: str, uf: str, data_referencia: str, regime: str, skip: int, limit: int
) -> List[dict]:
    """
    Busca composições por uma string em sua descrição, retornando os custos
    para um contexto específico. A busca é feita por palavras-chave independentes.
    """
    # 1. Quebra a string de busca em palavras individuais.
    search_words = q.split()
    
    # 2. Cria uma cláusula WHERE dinâmica com um ILIKE para cada palavra.
    #    Ex: se q="CONCRETO BOMBEADO", isto cria: "c.descricao ILIKE :word0 AND c.descricao ILIKE :word1"
    conditions = [f"c.descricao ILIKE :word{i}" for i in range(len(search_words))]
    where_descricao_clause = " AND ".join(conditions)

    # 3. Monta o dicionário de parâmetros dinamicamente para as palavras de busca.
    #    Ex: {"word0": "%CONCRETO%", "word1": "%BOMBEADO%"}
    params = {f"word{i}": f"%{word}%" for i, word in enumerate(search_words)}

    # 4. Adiciona os outros parâmetros fixos ao dicionário.
    params.update({
        "uf": uf.upper(),
        "data_referencia": data_referencia,
        "regime": regime.upper(),
        "status": settings.DEFAULT_ITEM_STATUS,
        "skip": skip,
        "limit": limit
    })

    # 5. Monta a query final usando a cláusula WHERE dinâmica.
    query_sql = f"""
        SELECT
            c.codigo, c.descricao, c.unidade, p.custo_total
        FROM {settings.TABLE_COMPOSICOES} AS c
        JOIN {settings.TABLE_CUSTOS_COMPOSICOES} AS p ON c.codigo = p.composicao_codigo
        WHERE 
            {where_descricao_clause}  -- << A MUDANÇA ESTÁ AQUI
            AND c.status = :status
            AND p.uf = :uf
            AND TO_CHAR(p.data_referencia, 'YYYY-MM') = :data_referencia
            AND p.regime = :regime
        ORDER BY c.descricao 
        OFFSET :skip 
        LIMIT :limit
    """
    
    query = text(query_sql)
    result = db.execute(query, params).fetchall()
    return result
# --- Seção 2: Funções de Análise e Business Intelligence (BI) ---

def get_composicao_bom(
    db: Session, codigo: int, uf: str, data_referencia: str, regime: str
) -> List[dict]:
    """
    Retorna o Bill of Materials (BOM) completo de uma composição, explodindo
    todos os níveis de subcomposições e calculando o custo de cada item.
    """
    # Esta query recursiva (CTE) navega na árvore de composições.
    query = text(f"""
    WITH RECURSIVE composicao_completa (composicao_pai_codigo, item_codigo, tipo_item, coeficiente_total, nivel) AS (
        -- Caso base: Itens diretos da composição principal
        SELECT
            composicao_pai_codigo,
            item_codigo,
            tipo_item,
            coeficiente AS coeficiente_total,
            1 AS nivel
        FROM {settings.VIEW_COMPOSICAO_ITENS}
        WHERE composicao_pai_codigo = :codigo
        
        UNION ALL
        
        -- Passo recursivo: Itens das subcomposições
        SELECT
            rec.composicao_pai_codigo,
            vis.item_codigo,
            vis.tipo_item,
            rec.coeficiente_total * vis.coeficiente AS coeficiente_total,
            rec.nivel + 1
        FROM {settings.VIEW_COMPOSICAO_ITENS} AS vis
        JOIN composicao_completa AS rec ON vis.composicao_pai_codigo = rec.item_codigo
        WHERE rec.tipo_item = 'COMPOSICAO'
    )
    -- Seleção final, unindo com os catálogos e preços/custos
    SELECT
        cc.item_codigo,
        cc.tipo_item,
        COALESCE(i.descricao, c.descricao) AS descricao,
        COALESCE(i.unidade, c.unidade) AS unidade,
        cc.coeficiente_total,
        COALESCE(pi.preco_mediano, pc.custo_total) AS custo_unitario,
        (cc.coeficiente_total * COALESCE(pi.preco_mediano, pc.custo_total)) AS custo_impacto_total
    FROM composicao_completa cc
    LEFT JOIN {settings.TABLE_INSUMOS} i ON cc.item_codigo = i.codigo AND cc.tipo_item = 'INSUMO'
    LEFT JOIN {settings.TABLE_COMPOSICOES} c ON cc.item_codigo = c.codigo AND cc.tipo_item = 'COMPOSICAO'
    LEFT JOIN {settings.TABLE_PRECOS_INSUMOS} pi ON cc.item_codigo = pi.insumo_codigo
        AND cc.tipo_item = 'INSUMO'
        AND pi.uf = :uf AND TO_CHAR(pi.data_referencia, 'YYYY-MM') = :data_referencia AND pi.regime = :regime
    LEFT JOIN {settings.TABLE_CUSTOS_COMPOSICOES} pc ON cc.item_codigo = pc.composicao_codigo
        AND cc.tipo_item = 'COMPOSICAO'
        AND pc.uf = :uf AND TO_CHAR(pc.data_referencia, 'YYYY-MM') = :data_referencia AND pc.regime = :regime
    ORDER BY cc.nivel, descricao;
    """)

    result = db.execute(query, {
        "codigo": codigo, "uf": uf.upper(), "data_referencia": data_referencia,
        "regime": regime.upper()
    }).fetchall()
    return result

def get_composicao_man_hours(
    db: Session, codigo: int
) -> dict:
    """
    Calcula o total de Hora/Homem para uma composição, somando os coeficientes
    de todos os insumos de mão de obra (unidade 'H') em todos os níveis.
    """
    query = text(f"""
    WITH RECURSIVE composicao_insumos_base (item_codigo, coeficiente_total) AS (
        SELECT item_codigo, coeficiente AS coeficiente_total
        FROM {settings.VIEW_COMPOSICAO_ITENS}
        WHERE composicao_pai_codigo = :codigo
        
        UNION ALL
        
        SELECT vis.item_codigo, rec.coeficiente_total * vis.coeficiente
        FROM {settings.VIEW_COMPOSICAO_ITENS} AS vis
        JOIN composicao_insumos_base AS rec ON vis.composicao_pai_codigo = rec.item_codigo
    )
    SELECT
        SUM(cib.coeficiente_total) AS total_hora_homem
    FROM composicao_insumos_base cib
    JOIN {settings.TABLE_INSUMOS} i ON cib.item_codigo = i.codigo
    WHERE i.unidade = 'H';
    """)
    result = db.execute(query, {"codigo": codigo}).first()
    return result

def get_abc_curve_for_composicoes(
    db: Session, codigos: List[int], uf: str, data_referencia: str, regime: str
) -> List[dict]:
    """
    Calcula a Curva ABC de insumos para um grupo de composições, identificando
    os itens de maior impacto financeiro.
    """
    query = text(f"""
    WITH RECURSIVE composicao_completa (composicao_pai_codigo, item_codigo, tipo_item, coeficiente_total) AS (
        SELECT codigo, codigo, 'COMPOSICAO', 1.0 FROM {settings.TABLE_COMPOSICOES} WHERE codigo IN :codigos
        UNION ALL
        SELECT rec.composicao_pai_codigo, vis.item_codigo, vis.tipo_item, rec.coeficiente_total * vis.coeficiente
        FROM {settings.VIEW_COMPOSICAO_ITENS} as vis
        JOIN composicao_completa as rec ON vis.composicao_pai_codigo = rec.item_codigo
        WHERE rec.tipo_item = 'COMPOSICAO'
    )
    SELECT
        i.codigo,
        i.descricao,
        i.unidade,
        SUM(cc.coeficiente_total * p.preco_mediano) AS custo_total_agregado
    FROM composicao_completa cc
    JOIN {settings.TABLE_INSUMOS} i ON cc.item_codigo = i.codigo
    JOIN {settings.TABLE_PRECOS_INSUMOS} p ON i.codigo = p.insumo_codigo
    WHERE cc.tipo_item = 'INSUMO'
      AND p.uf = :uf
      AND TO_CHAR(p.data_referencia, 'YYYY-MM') = :data_referencia
      AND p.regime = :regime
    GROUP BY i.codigo, i.descricao, i.unidade
    HAVING SUM(cc.coeficiente_total * p.preco_mediano) > 0
    ORDER BY custo_total_agregado DESC;
    """)
    params = {
        "codigos": tuple(codigos), "uf": uf.upper(),
        "data_referencia": data_referencia, "regime": regime.upper()
    }
    insumos_custo = db.execute(query, params).fetchall()
    if not insumos_custo:
        return []
    df = pd.DataFrame(insumos_custo, columns=['codigo', 'descricao', 'unidade', 'custo_total_agregado'])
    df['custo_total_agregado'] = pd.to_numeric(df['custo_total_agregado'])
    custo_total_geral = df['custo_total_agregado'].sum()
    df = df.sort_values(by='custo_total_agregado', ascending=False)
    df['percentual_individual'] = (df['custo_total_agregado'] / custo_total_geral) * 100
    df['percentual_acumulado'] = df['percentual_individual'].cumsum()
    def classificar_abc(percentual_acumulado):
        if percentual_acumulado <= 80:
            return 'A'
        elif percentual_acumulado <= 95:
            return 'B'
        else:
            return 'C'
    df['classe_abc'] = df['percentual_acumulado'].apply(classificar_abc)
    return df.to_dict(orient='records')

def get_candidatos_otimizacao(
    db: Session, codigo: int, uf: str, data_referencia: str, regime: str, top_n: int = 5
) -> List[dict]:
    """
    Identifica os insumos de maior impacto financeiro em uma composição,
    servindo como candidatos para otimização de custos.
    """
    bom_completo = get_composicao_bom(db, codigo=codigo, uf=uf, data_referencia=data_referencia, regime=regime)
    if not bom_completo:
        return []
    
    insumos = [item for item in bom_completo if item['tipo_item'] == 'INSUMO' and item['custo_impacto_total'] is not None]
    
    insumos_sorted = sorted(insumos, key=lambda x: x['custo_impacto_total'], reverse=True)
    
    return insumos_sorted[:top_n]

def get_custo_historico(
    db: Session, tipo_item: str, codigo: int, uf: str, regime: str, data_inicio: str, data_fim: str
) -> List[dict]:
    """
    Busca o histórico de preço/custo de um item dentro de um período.
    """
    if tipo_item == 'insumo':
        table_name = settings.TABLE_PRECOS_INSUMOS
        code_column = 'insumo_codigo'
        value_column = 'preco_mediano'
    elif tipo_item == 'composicao':
        table_name = settings.TABLE_CUSTOS_COMPOSICOES
        code_column = 'composicao_codigo'
        value_column = 'custo_total'
    else:
        return []

    query = text(f"""
        SELECT TO_CHAR(data_referencia, 'YYYY-MM') as data_referencia, {value_column} as valor
        FROM {table_name}
        WHERE {code_column} = :codigo
          AND uf = :uf
          AND regime = :regime
          AND TO_CHAR(data_referencia, 'YYYY-MM') >= :data_inicio
          AND TO_CHAR(data_referencia, 'YYYY-MM') <= :data_fim
        ORDER BY data_referencia ASC
    """)
    result = db.execute(query, {
        "codigo": codigo, "uf": uf.upper(), "regime": regime.upper(),
        "data_inicio": data_inicio, "data_fim": data_fim
    }).fetchall()
    return result