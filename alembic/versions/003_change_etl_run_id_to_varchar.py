"""Change etl_run_id from UUID to VARCHAR(36).

Revision ID: 003
Revises: 002
Create Date: 2026-05-22
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.alter_column("insumos", "etl_run_id", type_=sa.String(36))
    op.alter_column("composicoes", "etl_run_id", type_=sa.String(36))
    op.alter_column("precos_insumos_mensal", "etl_run_id", type_=sa.String(36))
    op.alter_column("custos_composicoes_mensal", "etl_run_id", type_=sa.String(36))
    op.alter_column("composicao_insumos", "etl_run_id", type_=sa.String(36))
    op.alter_column("composicao_subcomposicoes", "etl_run_id", type_=sa.String(36))
    op.alter_column("manutencoes_historico", "etl_run_id", type_=sa.String(36))
    op.alter_column("insumos_familias", "etl_run_id", type_=sa.String(36))
    op.alter_column("coeficientes_familia_mensal", "etl_run_id", type_=sa.String(36))
    op.alter_column("composicoes_mix_mao_de_obra", "etl_run_id", type_=sa.String(36))
    op.alter_column("sinapi_audit_log", "etl_run_id", type_=sa.String(36))


def downgrade() -> None:
    op.alter_column("sinapi_audit_log", "etl_run_id", type_=sa.UUID())
    op.alter_column("composicoes_mix_mao_de_obra", "etl_run_id", type_=sa.UUID())
    op.alter_column("coeficientes_familia_mensal", "etl_run_id", type_=sa.UUID())
    op.alter_column("insumos_familias", "etl_run_id", type_=sa.UUID())
    op.alter_column("manutencoes_historico", "etl_run_id", type_=sa.UUID())
    op.alter_column("composicao_subcomposicoes", "etl_run_id", type_=sa.UUID())
    op.alter_column("composicao_insumos", "etl_run_id", type_=sa.UUID())
    op.alter_column("custos_composicoes_mensal", "etl_run_id", type_=sa.UUID())
    op.alter_column("precos_insumos_mensal", "etl_run_id", type_=sa.UUID())
    op.alter_column("composicoes", "etl_run_id", type_=sa.UUID())
    op.alter_column("insumos", "etl_run_id", type_=sa.UUID())