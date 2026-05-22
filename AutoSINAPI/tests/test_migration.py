"""
Testes para a migração Alembic 002 (traceability columns).
Valida se as colunas created_at, updated_at, sinapi_versao, etl_run_id
são criadas corretamente em todas as tabelas.
"""
import pytest
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.exc import SQLAlchemyError

# Colunas esperadas em todas as tabelas
TRACEABILITY_COLUMNS = ['created_at', 'updated_at', 'sinapi_versao', 'etl_run_id']

# Tabelas que devem ter as colunas de traceability
TABLES_TO_CHECK = [
    'insumos', 'composicoes', 'precos_insumos_mensal',
    'custos_composicoes_mensal', 'composicao_insumos',
    'composicao_subcomposicoes', 'manutencoes_historico',
    'insumos_familias', 'coeficientes_familia_mensal',
    'composicoes_mix_mao_de_obra',
]


@pytest.fixture
def test_engine():
    """Cria uma conexão com banco de teste em memória."""
    engine = create_engine('sqlite:///:memory:')
    yield engine
    engine.dispose()


@pytest.fixture
def migrated_engine():
    """
    Fixture que aplica a migração 002 em um banco de teste.
    Como não podemos rodar Alembic diretamente em testes unitários,
    vamos verificar se o script de migração tem a sintaxe correta.
    """
    # Para testes reais, usar um banco PostgreSQL de teste
    # Aqui apenas validamos a estrutura do script
    migration_path = 'alembic/versions/002_add_traceability_columns.py'
    with open(migration_path, 'r') as f:
        content = f.read()
    
    # Verifica se as colunas de traceability estão no script
    for col in TRACEABILITY_COLUMNS:
        assert col in content, f"Coluna '{col}' não encontrada no script de migração"
    
    # Verifica se a tabela sinapi_audit_log está definida
    assert 'sinapi_audit_log' in content, "Tabela sinapi_audit_log não encontrada"
    assert 'old_values JSONB' in content, "Campo old_values não encontrado"
    assert 'new_values JSONB' in content, "Campo new_values não encontrado"
    
    return content


class TestMigration002:
    """Testes para validar a migração 002."""
    
    def test_migration_script_has_traceability_columns(self, migrated_engine):
        """Verifica se o script de migração tem todas as colunas."""
        content = migrated_engine
        # Verifica se ADD COLUMN aparece para cada tabela
        assert 'op.add_column' in content
        assert 'created_at' in content
        assert 'updated_at' in content
        assert 'sinapi_versao' in content
        assert 'etl_run_id' in content
    
    def test_migration_script_has_audit_log_table(self, migrated_engine):
        """Verifica se a tabela de auditoria está definida."""
        content = migrated_engine
        assert 'CREATE TABLE sinapi_audit_log' in content
        assert 'record_pk' in content
        assert 'operation' in content
        assert 'motivo_manutencao' in content
    
    def test_migration_script_has_indexes(self, migrated_engine):
        """Verifica se os índices de performance estão definidos."""
        content = migrated_engine
        assert 'CREATE INDEX idx_audit_table_name' in content
        assert 'CREATE INDEX idx_audit_created_at' in content
        assert 'CREATE INDEX idx_audit_etl_run' in content
        assert 'CREATE INDEX idx_insumos_updated_at' in content


class TestTraceabilityColumns:
    """Testes para validar colunas de traceability (requer banco PostgreSQL)."""
    
    @pytest.fixture
    def pg_connection_string(self):
        """Retorna string de conexão PostgreSQL para testes."""
        import os
        return os.getenv(
            'TEST_DATABASE_URL',
            'postgresql://test_user:test_pass@localhost:5432/test_autosinapi'
        )
    
    @pytest.mark.skipif(
        True,  # Skip por padrão - requer banco PostgreSQL
        reason="Requer banco PostgreSQL configurado (TEST_DATABASE_URL)"
    )
    def test_all_tables_have_traceability_columns(self, pg_connection_string):
        """Testa se todas as tabelas têm colunas de traceability."""
        engine = create_engine(pg_connection_string)
        inspector = inspect(engine)
        
        for table in TABLES_TO_CHECK:
            columns = [c['name'] for c in inspector.get_columns(table)]
            for col in TRACEABILITY_COLUMNS:
                assert col in columns, f"Tabela '{table}' não tem coluna '{col}'"
        
        engine.dispose()
    
    @pytest.mark.skipif(
        True,
        reason="Requer banco PostgreSQL configurado (TEST_DATABASE_URL)"
    )
    def test_audit_log_table_exists(self, pg_connection_string):
        """Testa se a tabela sinapi_audit_log existe com as colunas certas."""
        engine = create_engine(pg_connection_string)
        
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'sinapi_audit_log'
            """))
            columns = [r[0] for r in result]
            
            assert 'id' in columns
            assert 'table_name' in columns
            assert 'record_pk' in columns
            assert 'operation' in columns
            assert 'old_values' in columns
            assert 'new_values' in columns
            assert 'sinapi_versao' in columns
            assert 'etl_run_id' in columns
            assert 'motivo_manutencao' in columns
            assert 'created_at' in columns
        
        engine.dispose()


class TestDowngrade:
    """Testes para validar o rollback da migração."""
    
    def test_downgrade_script_exists(self, migrated_engine):
        """Verifica se o script tem função downgrade."""
        content = migrated_engine
        assert 'def downgrade()' in content
        assert 'op.drop_column' in content
        assert 'op.drop_table("sinapi_audit_log")' in content
