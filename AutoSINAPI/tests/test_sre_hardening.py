
import pandas as pd
import pytest
import logging
from autosinapi.config import Config
from autosinapi.core.processor import Processor
from autosinapi.etl_pipeline import PipelineETL
from unittest.mock import MagicMock, patch

@pytest.fixture
def config():
    db_config = {"host": "h", "port": 5432, "database": "d", "user": "u", "password": "p"}
    sinapi_config = {"state": "SP", "month": 8, "year": 2025, "type": "REFERENCIA"}
    return Config(db_config, sinapi_config, mode="local")

@pytest.fixture
def processor(config):
    return Processor(config)

def test_processor_extracts_group_for_compositions(processor, tmp_path):
    """Reproduction Task 1: Verify if processor extracts 'Grupo' from Analítico sheet."""
    test_file = tmp_path / "test_sinapi_analitico.xlsx"
    
    # Simulating the 'Analítico' sheet structure as found in the audit
    # Row 9 is the header (index 9)
    df = pd.DataFrame([
        ['Grupo', 'Código da\nComposição', 'Tipo Item', 'Código do\nItem', 'Descrição', 'Unidade', 'Coeficiente', 'Situação'],
        ['Acessibilidade', 104658, None, None, 'PISO PODOTÁTIL...', 'M2', None, 'COM CUSTO'],
        ['Acessibilidade', 104658, 'COMPOSICAO', 88316, 'SERVENTE...', 'H', 1.279, 'COM CUSTO'],
    ])
    
    writer = pd.ExcelWriter(test_file, engine="xlsxwriter")
    df.to_excel(writer, index=False, header=False, sheet_name="Analítico")
    writer.close()

    # We need to adjust COMPOSICAO_ITENS_HEADER_ROW to 0 for this test
    processor.config.COMPOSICAO_ITENS_HEADER_ROW = 0
    
    result = processor.process_composicao_itens(str(test_file))
    
    parent_details = result.get("parent_composicoes_details")
    assert parent_details is not None
    assert "grupo" in parent_details.columns, "Coluna 'grupo' deve estar presente no retorno"
    assert parent_details.iloc[0]["grupo"] == 'Acessibilidade'

def test_processor_aggregates_catalog_prioritizing_data(processor):
    """Reproduction Task 2: Verify if processor preserves classification during aggregation."""
    # Simulate two sheets: one with classification, one without (e.g. if ISE missed it)
    df1 = pd.DataFrame({
        'CODIGO': [1, 2],
        'DESCRICAO': ['A', 'B'],
        'UNIDADE': ['UN', 'UN'],
        'CLASSIFICACAO': ['MAT', 'SER']
    })
    df2 = pd.DataFrame({
        'CODIGO': [1, 2],
        'DESCRICAO': ['A', 'B'],
        'UNIDADE': ['UN', 'UN']
        # CLASSIFICACAO missing here
    })
    
    # Simulate aggregation logic
    all_dfs = {}
    temp_insumos = [df1, df2]
    
    result = processor._aggregate_final_dataframes(all_dfs, temp_insumos, [])
    insumos = result['insumos']
    
    # If df2 was concatenated last and drop_duplicates kept first, it might be OK
    # but we want to ensure non-nulls are prioritized.
    # Currently drop_duplicates(subset=['CODIGO']) keeps the FIRST occurrence.
    # If temp_insumos = [df2, df1], it would keep NaN.
    
    temp_insumos_rev = [df2, df1]
    result_rev = processor._aggregate_final_dataframes({}, temp_insumos_rev, [])
    insumos_rev = result_rev['insumos']
    
    assert insumos_rev.iloc[0]['classificacao'] == 'MAT', "Deve priorizar classificação preenchida"

def test_pipeline_protects_insumo_classification(config, mocker):
    """Reproduction Task 2: Verify if pipeline avoids overwriting classifications with placeholders."""
    dummy_db = {"host": "h", "port": 5432, "database": "d", "user": "u", "password": "p"}
    dummy_sinapi = {"state": "SP", "month": 8, "year": 2025, "type": "REFERENCIA"}
    
    mocker.patch("autosinapi.etl_pipeline.PipelineETL._get_db_config", return_value=dummy_db)
    mocker.patch("autosinapi.etl_pipeline.PipelineETL._get_sinapi_config", return_value=dummy_sinapi)
    mocker.patch("autosinapi.etl_pipeline.PipelineETL._load_base_config", return_value={})
    mocker.patch("autosinapi.etl_pipeline.Database")
    
    pipeline = PipelineETL(custom_constants=config.DEFAULT_CONSTANTS)
    
    # Existing data with classification
    processed_data = {
        'insumos': pd.DataFrame({
            'codigo': [45333],
            'descricao': ['REAL DESC'],
            'unidade': ['UN'],
            'classificacao': ['SERVIÇOS']
        })
    }
    
    # Structure referencing the same item but without classification details
    structure_dfs = {
        'child_item_details': pd.DataFrame({
            'codigo': [45333, 999],
            'tipo': ['INSUMO', 'INSUMO'],
            'descricao': ['DESC FROM STRUCTURE', 'NEW ITEM'],
            'unidade': ['UN', 'KG']
        }),
        config.DB_TABLE_COMPOSICAO_INSUMOS: pd.DataFrame({
            'composicao_pai_codigo': [104658, 104658],
            'insumo_filho_codigo': [45333, 999]
        }),
        config.DB_TABLE_COMPOSICAO_SUBCOMPOSICOES: pd.DataFrame(columns=['composicao_pai_codigo', 'composicao_filho_codigo']),
        'parent_composicoes_details': pd.DataFrame({'codigo': []})
    }
    
    updated_data = pipeline._handle_missing_items_placeholders(processed_data, structure_dfs)
    
    # Check existing item
    target_row = updated_data['insumos'][updated_data['insumos']['codigo'] == 45333]
    assert len(target_row) == 1
    assert target_row.iloc[0]['classificacao'] == 'SERVIÇOS', f"Classificação original deve ser preservada, got {target_row.iloc[0]['classificacao']}"
    
    # Check new item placeholder
    new_item = updated_data['insumos'][updated_data['insumos']['codigo'] == 999]
    assert len(new_item) == 1
    assert new_item.iloc[0]['classificacao'] == 'NAO_CLASSIFICADO'

def test_database_traceability_propagation_complex(config, mocker):
    """Reproduction Task 3: Verify if save_data propagates etl_run_id even when data is a slice/view."""
    from autosinapi.core.database import Database
    import uuid
    
    mocker.patch("autosinapi.core.database.create_engine")
    db = Database(config)
    
    # Create a DataFrame and take a slice (view)
    full_df = pd.DataFrame({
        'codigo': [1, 2, 3],
        'descricao': ['a', 'b', 'c'],
        'extra': [10, 20, 30]
    })
    sample_df = full_df[['codigo', 'descricao']] # This is a slice
    
    run_id = "550e8400-e29b-41d4-a716-446655440000"
    sinapi_versao = "2025.07"
    
    mock_upsert = mocker.patch.object(db, "_upsert_data")
    
    # This might raise SettingWithCopyWarning if not handled correctly in database.py
    db.save_data(sample_df, "test_table", policy="upsert", 
                 pk_columns=['codigo'], etl_run_id=run_id, sinapi_versao=sinapi_versao)
    
    args, _ = mock_upsert.call_args
    final_df = args[0]
    
    assert "etl_run_id" in final_df.columns
    assert "sinapi_versao" in final_df.columns
