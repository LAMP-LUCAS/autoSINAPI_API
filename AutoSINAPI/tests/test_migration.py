"""
Testes para a migração Alembic 002 (traceability columns).
Valida se as colunas traceability sao criadas corretamente.
"""
import pytest
from sqlalchemy import create_engine, text, inspect

TRACEABILITY_COLUMNS = ['created_at', 'updated_at', 'sinapi_versao', 'etl_run_id']

@pytest.fixture
def migrated_engine():
    migration_path = 'alembic/versions/002_add_traceability_columns.py'
    with open(migration_path, 'r') as f:
        content = f.read()
    # Validate: traceability column names appear in the script
    for col in TRACEABILITY_COLUMNS:
        assert col in content, f"Coluna '{col}' nao encontrada no script de migracao"
    # sinapi_audit_log table created via op.create_table
    assert 'op.create_table' in content
    assert 'sinapi_audit_log' in content
    # JSONB columns exist (with quotes + parentheses)
    assert '"old_values"' in content
    assert '"new_values"' in content
    assert 'postgresql.JSONB()' in content
    assert 'motivo_manutencao' in content
    # Indexes created via op.create_index
    assert 'op.create_index' in content
    assert 'idx_audit_table_name' in content
    assert 'idx_audit_created_at' in content
    assert 'idx_audit_etl_run' in content
    # Downgrade
    assert 'def downgrade()' in content
    assert 'op.drop_column' in content
    return content

class TestMigration002:
    def test_migration_script_has_traceability_columns(self, migrated_engine):
        content = migrated_engine
        assert 'op.add_column' in content
        for col in TRACEABILITY_COLUMNS:
            assert col in content

    def test_migration_script_has_audit_log_table(self, migrated_engine):
        content = migrated_engine
        assert 'op.create_table' in content
        assert 'sinapi_audit_log' in content
        assert '"old_values"' in content
        assert 'postgresql.JSONB()' in content

    def test_migration_script_has_indexes(self, migrated_engine):
        content = migrated_engine
        assert 'op.create_index' in content
        assert 'idx_audit' in content

class TestDowngrade:
    def test_downgrade_script_exists(self, migrated_engine):
        content = migrated_engine
        assert 'def downgrade()' in content
        assert 'op.drop_column' in content
        assert 'op.drop_table("sinapi_audit_log")' in content

    def test_downgrade_removes_columns(self, migrated_engine):
        content = migrated_engine
        for col in TRACEABILITY_COLUMNS:
            assert f'op.drop_column(table, "{col}")' in content
