"""Add traceability columns and audit log table.

Revision ID: 002
Revises: 001
Create Date: 2026-05-22
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    # 1. Add traceability columns to existing tables
    tables = [
        "insumos",
        "composicoes",
        "precos_insumos_mensal",
        "custos_composicoes_mensal",
        "composicao_insumos",
        "composicao_subcomposicoes",
        "manutencoes_historico",
    ]

    for table in tables:
        op.add_column(table, sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()))
        op.add_column(table, sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()))
        op.add_column(table, sa.Column("sinapi_versao", sa.String(20), nullable=True))
        op.add_column(table, sa.Column("etl_run_id", postgresql.UUID(), nullable=True))

    # 2. Create missing tables (insumos_familias, coeficientes_familia_mensal, composicoes_mix_mao_de_obra)
    # These tables were in database.py DDL but missing from migration 001
    
    op.create_table(
        "insumos_familias",
        sa.Column("codigo_familia", sa.Integer(), nullable=False),
        sa.Column("insumo_codigo", sa.Integer(), nullable=False),
        sa.Column("categoria", sa.String(50), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.Column("sinapi_versao", sa.String(20), nullable=True),
        sa.Column("etl_run_id", postgresql.UUID(), nullable=True),
        sa.PrimaryKeyConstraint("codigo_familia", "insumo_codigo"),
        sa.ForeignKeyConstraint(["insumo_codigo"], ["insumos.codigo"], ondelete="CASCADE"),
    )

    op.create_table(
        "coeficientes_familia_mensal",
        sa.Column("insumo_codigo", sa.Integer(), nullable=False),
        sa.Column("uf", sa.CHAR(2), nullable=False),
        sa.Column("data_referencia", sa.Date(), nullable=False),
        sa.Column("coeficiente", sa.Numeric(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.Column("sinapi_versao", sa.String(20), nullable=True),
        sa.Column("etl_run_id", postgresql.UUID(), nullable=True),
        sa.PrimaryKeyConstraint("insumo_codigo", "uf", "data_referencia"),
        sa.ForeignKeyConstraint(["insumo_codigo"], ["insumos.codigo"], ondelete="CASCADE"),
    )

    op.create_table(
        "composicoes_mix_mao_de_obra",
        sa.Column("composicao_codigo", sa.Integer(), nullable=False),
        sa.Column("uf", sa.CHAR(2), nullable=False),
        sa.Column("data_referencia", sa.Date(), nullable=False),
        sa.Column("porcentagem_mo", sa.Numeric(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.Column("sinapi_versao", sa.String(20), nullable=True),
        sa.Column("etl_run_id", postgresql.UUID(), nullable=True),
        sa.PrimaryKeyConstraint("composicao_codigo", "uf", "data_referencia"),
        sa.ForeignKeyConstraint(["composicao_codigo"], ["composicoes.codigo"], ondelete="CASCADE"),
    )

    # 3. Create sinapi_audit_log table
    op.create_table(
        "sinapi_audit_log",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("table_name", sa.String(100), nullable=False),
        sa.Column("record_pk", postgresql.JSONB(), nullable=False),
        sa.Column("operation", sa.String(10), nullable=False),
        sa.Column("old_values", postgresql.JSONB(), nullable=True),
        sa.Column("new_values", postgresql.JSONB(), nullable=True),
        sa.Column("sinapi_versao", sa.String(20), nullable=True),
        sa.Column("etl_run_id", postgresql.UUID(), nullable=True),
        sa.Column("motivo_manutencao", sa.String(200), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
    )

    # 4. Create indexes
    op.create_index("idx_audit_table_name", "sinapi_audit_log", ["table_name"])
    op.create_index("idx_audit_created_at", "sinapi_audit_log", ["created_at"])
    op.create_index("idx_audit_etl_run", "sinapi_audit_log", ["etl_run_id"])

    op.create_index("idx_insumos_updated_at", "insumos", ["updated_at"])
    op.create_index("idx_composicoes_updated_at", "composicoes", ["updated_at"])
    op.create_index("idx_precos_updated_at", "precos_insumos_mensal", ["updated_at"])
    op.create_index("idx_custos_updated_at", "custos_composicoes_mensal", ["updated_at"])
    op.create_index("idx_manutencoes_data", "manutencoes_historico", ["data_referencia"])


def downgrade() -> None:
    # Drop indexes
    op.drop_index("idx_manutencoes_data", table_name="manutencoes_historico")
    op.drop_index("idx_custos_updated_at", table_name="custos_composicoes_mensal")
    op.drop_index("idx_precos_updated_at", table_name="precos_insumos_mensal")
    op.drop_index("idx_composicoes_updated_at", table_name="composicoes")
    op.drop_index("idx_insumos_updated_at", table_name="insumos")
    op.drop_index("idx_audit_etl_run", table_name="sinapi_audit_log")
    op.drop_index("idx_audit_created_at", table_name="sinapi_audit_log")
    op.drop_index("idx_audit_table_name", table_name="sinapi_audit_log")

    # Drop sinapi_audit_log
    op.drop_table("sinapi_audit_log")

    # Drop newly created tables
    op.drop_table("composicoes_mix_mao_de_obra")
    op.drop_table("coeficientes_familia_mensal")
    op.drop_table("insumos_familias")

    # Remove traceability columns from existing tables
    tables = [
        "manutencoes_historico",
        "composicao_subcomposicoes",
        "composicao_insumos",
        "custos_composicoes_mensal",
        "precos_insumos_mensal",
        "composicoes",
        "insumos",
    ]

    for table in tables:
        op.drop_column(table, "etl_run_id")
        op.drop_column(table, "sinapi_versao")
        op.drop_column(table, "updated_at")
        op.drop_column(table, "created_at")
