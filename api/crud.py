# api/crud.py
from sqlalchemy.orm import Session
from sqlalchemy import text

# NOTA IMPORTANTE: Substitua 'sua_tabela_de_insumos' e 'sua_tabela_de_composicoes'
# pelos nomes reais das suas tabelas no banco de dados.

def get_insumo_by_codigo(db: Session, codigo: str):
    query = text("""
        SELECT codigo, descricao, unidade, preco_mediano 
        FROM sua_tabela_de_insumos WHERE codigo = :codigo
    """)
    result = db.execute(query, {"codigo": codigo}).first()
    return result

def search_insumos_by_descricao(db: Session, q: str, skip: int, limit: int):
    query = text("""
        SELECT codigo, descricao, unidade, preco_mediano 
        FROM sua_tabela_de_insumos 
        WHERE descricao ILIKE :query 
        ORDER BY codigo OFFSET :skip LIMIT :limit
    """)
    result = db.execute(query, {"query": f"%{q}%", "skip": skip, "limit": limit}).fetchall()
    return result

def get_composicao_by_codigo(db: Session, codigo: str):
    # Nota: o campo de custo pode ter um nome diferente, ex: 'custo_total_material_mo'
    query = text("""
        SELECT codigo, descricao, unidade, custo_total AS custo_total
        FROM sua_tabela_de_composicoes WHERE codigo = :codigo
    """)
    result = db.execute(query, {"codigo": codigo}).first()
    return result

def search_composicoes_by_descricao(db: Session, q: str, skip: int, limit: int):
    query = text("""
        SELECT codigo, descricao, unidade, custo_total AS custo_total
        FROM sua_tabela_de_composicoes
        WHERE descricao ILIKE :query
        ORDER BY codigo OFFSET :skip LIMIT :limit
    """)
    result = db.execute(query, {"query": f"%{q}%", "skip": skip, "limit": limit}).fetchall()
    return result
