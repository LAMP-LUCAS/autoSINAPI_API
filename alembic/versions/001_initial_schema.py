"""Initial schema: create all AutoSINAPI tables.

Revision ID: 001
Revises: 
Create Date: 2026-05-21
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None

def upgrade() -> None:
    op.create_table(
        "insumos",
        sa.Column("codigo", sa.Integer(), nullable=False),
        sa.Column("descricao", sa.Text(), nullable=False),
        sa.Column("unidade", sa.String(length=10), nullable=True),
        sa.Column("classificacao", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=True, server_default="ATIVO"),
        sa.PrimaryKeyConstraint("codigo"),
    )
    op.create_table(
        "composicoes",
        sa.Column("codigo", sa.Integer(), nullable=False),
        sa.Column("descricao", sa.Text(), nullable=False),
        sa.Column("unidade", sa.String(length=10), nullable=True),
        sa.Column("grupo", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=True, server_default="ATIVO"),
        sa.PrimaryKeyConstraint("codigo"),
    )
    op.create_table(
        "precos_insumos_mensal",
        sa.Column("insumo_codigo", sa.Integer(), nullable=False),
        sa.Column("uf", sa.CHAR(length=2), nullable=False),
        sa.Column("data_referencia", sa.Date(), nullable=False),
        sa.Column("regime", sa.String(length=50), nullable=False),
        sa.Column("preco_mediano", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.PrimaryKeyConstraint("insumo_codigo", "uf", "data_referencia", "regime"),
    )
    op.create_table(
        "custos_composicoes_mensal",
        sa.Column("composicao_codigo", sa.Integer(), nullable=False),
        sa.Column("uf", sa.CHAR(length=2), nullable=False),
        sa.Column("data_referencia", sa.Date(), nullable=False),
        sa.Column("regime", sa.String(length=50), nullable=False),
        sa.Column("custo_total", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.PrimaryKeyConstraint("composicao_codigo", "uf", "data_referencia", "regime"),
    )
    op.create_table(
        "composicao_insumos",
        sa.Column("composicao_pai_codigo", sa.Integer(), nullable=False),
        sa.Column("insumo_filho_codigo", sa.Integer(), nullable=False),
        sa.Column("coeficiente", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.PrimaryKeyConstraint("composicao_pai_codigo", "insumo_filho_codigo"),
    )
    op.create_table(
        "composicao_subcomposicoes",
        sa.Column("composicao_pai_codigo", sa.Integer(), nullable=False),
        sa.Column("composicao_filho_codigo", sa.Integer(), nullable=False),
        sa.Column("coeficiente", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.PrimaryKeyConstraint("composicao_pai_codigo", "composicao_filho_codigo"),
    )
    op.create_table(
        "manutencoes_historico",
        sa.Column("item_codigo", sa.Integer(), nullable=False),
        sa.Column("tipo_item", sa.String(length=20), nullable=False),
        sa.Column("data_referencia", sa.Date(), nullable=False),
        sa.Column("tipo_manutencao", sa.Text(), nullable=False),
        sa.Column("descricao_item", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("item_codigo", "tipo_item", "data_referencia", "tipo_manutencao"),
    )
    op.execute("""
        CREATE OR REPLACE VIEW vw_composicao_itens_unificados AS
        SELECT
            composicao_pai_codigo,
            insumo_filho_codigo AS item_codigo,
            'INSUMO' AS tipo_item,
            coeficiente
        FROM composicao_insumos
        UNION ALL
        SELECT
            composicao_pai_codigo,
            composicao_filho_codigo AS item_codigo,
            'COMPOSICAO' AS tipo_item,
            coeficiente
        FROM composicao_subcomposicoes;
    """)

def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS vw_composicao_itens_unificados")
    op.drop_table("manutencoes_historico")
    op.drop_table("composicao_subcomposicoes")
    op.drop_table("composicao_insumos")
    op.drop_table("custos_composicoes_mensal")
    op.drop_table("precos_insumos_mensal")
    op.drop_table("composicoes")
    op.drop_table("insumos")