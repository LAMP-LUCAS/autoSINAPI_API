"""
Testes do módulo de download com suporte a input direto de arquivo.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch
from io import BytesIO

import pandas as pd
import pytest

from autosinapi.etl_pipeline import PipelineETL


@pytest.fixture
def mock_pipeline(mocker, tmp_path):
    """Fixture para mockar o pipeline e suas dependências."""
    mocker.patch("autosinapi.etl_pipeline.setup_logging")

    # Mock do objeto Config
    mock_config = MagicMock()
    mock_config.DOWNLOAD_DIR = tmp_path / "downloads"
    mock_config.YEAR = "2023"
    mock_config.MONTH = "01"
    mock_config.STATE = "SP"
    mock_config.TYPE = "insumos"
    mock_config.DB_HOST = "localhost"
    mock_config.DB_PORT = 5432
    mock_config.DB_NAME = "test_db"
    mock_config.DB_USER = "test_user"
    mock_config.DB_PASSWORD = "test_pass"
    mock_config.REFERENCE_FILE_KEYWORD = "Referencia"
    mock_config.MAINTENANCE_FILE_KEYWORD = "Manuten"
    mock_config.MAINTENANCE_DEACTIVATION_KEYWORD = "%DESATIVAÇÃO%"
    mock_config.DB_TABLE_MANUTENCOES = "manutencoes_historico"
    mock_config.DB_TABLE_INSUMOS = "insumos"
    mock_config.DB_TABLE_COMPOSICOES = "composicoes"
    mock_config.DB_TABLE_COMPOSICAO_INSUMOS = "composicao_insumos"
    mock_config.DB_TABLE_COMPOSICAO_SUBCOMPOSICOES = "composicao_subcomposicoes"
    mock_config.DB_TABLE_PRECOS_INSUMOS = "precos_insumos_mensal"
    mock_config.DB_TABLE_CUSTOS_COMPOSICOES = "custos_composicoes_mensal"
    mock_config.ITEM_TYPE_INSUMO = "INSUMO"
    mock_config.ITEM_TYPE_COMPOSICAO = "COMPOSICAO"
    mock_config.SHEETS_TO_CONVERT = ['CSD', 'CCD', 'CSE']
    mock_config.sinapi_config = {"state": "SP", "month": "01", "year": "2023", "type": "insumos"} # Adicionado para o test_fallback_to_download

    # Patch para que PipelineETL use o mock_config
    mocker.patch("autosinapi.etl_pipeline.Config", return_value=mock_config)

    # Cria um diretório de extração falso
    extraction_path = tmp_path / "extraction"
    extraction_path.mkdir()
    # Cria um arquivo de referência falso dentro do diretório
    referencia_file_name = f"SINAPI_{mock_config.REFERENCE_FILE_KEYWORD}_20_23_01.xlsx"
    referencia_file_path = extraction_path / referencia_file_name
    # Create a dummy Excel file with required sheets
    with pd.ExcelWriter(referencia_file_path) as writer:
        for sheet_name in mock_config.SHEETS_TO_CONVERT:
            pd.DataFrame({"col1": [1, 2], "col2": [3, 4]}).to_excel(writer, sheet_name=sheet_name, index=False)
        # Add other sheets that might be processed by processor.process_catalogo_e_precos and process_composicao_itens
        pd.DataFrame({"codigo": [1,2], "descricao": ["a","b"]}).to_excel(writer, sheet_name="ISD", index=False)
        pd.DataFrame({"codigo": [1,2], "descricao": ["a","b"]}).to_excel(writer, sheet_name="Analítico", index=False)

    with patch("autosinapi.etl_pipeline.Database") as mock_db_class, patch(
        "autosinapi.etl_pipeline.Downloader"
    ) as mock_downloader_class, patch(
        "autosinapi.etl_pipeline.Processor"
    ) as mock_processor_class, patch(
        "autosinapi.core.pre_processor.convert_excel_sheets_to_csv"
    ) as mock_convert_excel_sheets_to_csv:

        mock_db_instance = MagicMock()
        mock_db_class.return_value = mock_db_instance

        mock_downloader_instance = MagicMock()
        mock_downloader_class.return_value = mock_downloader_instance
        mock_downloader_instance.get_sinapi_data.return_value = BytesIO(b"dummy zip content")

        mock_processor_instance = MagicMock()
        mock_processor_class.return_value = mock_processor_instance

        pipeline = PipelineETL(config_path=None) # config_path=None is fine as Config is mocked

        
        spy_run_pre_processing = mocker.spy(pipeline, "_run_pre_processing")
        spy_run = mocker.spy(pipeline, "run")
        mocker.patch.object(pipeline, "_sync_catalog_status")
        mocker.patch.object(
            pipeline, "_unzip_file", return_value=extraction_path
        )
        mocker.patch.object(
            pipeline, "_find_and_normalize_zip", return_value=Path("mocked.zip")
        )

        yield (
            pipeline,
            mock_db_instance,
            mock_downloader_instance,
            mock_processor_instance,
            mock_convert_excel_sheets_to_csv,
            referencia_file_path,
            mock_config, # Pass mock_config to the test
            spy_run_pre_processing, # Pass spy_run_pre_processing to the test
            spy_run # Add spy_run to the yield
        )


def test_direct_file_input(tmp_path, mock_pipeline):
    """Testa o pipeline com input direto de arquivo."""
        pipeline, mock_db, mock_downloader, mock_processor, mock_convert_excel_sheets_to_csv, referencia_file_path, mock_config, spy_run_pre_processing, spy_run = mock_pipeline

    test_file = tmp_path / "test_sinapi.xlsx"
    df = pd.DataFrame(
        {
            "codigo": [1234, 5678],
            "descricao": ["Item 1", "Item 2"],
            "unidade": ["un", "kg"],
            "preco": [10.5, 20.75],
        }
    )
    df.to_excel(test_file, index=False)

    # Set the input_file directly on the mocked sinapi_config
    mock_config.sinapi_config["input_file"] = str(test_file)

    mock_processor.process_catalogo_e_precos.return_value = {"insumos": df}
    mock_processor.process_composicao_itens.return_value = {
        "composicao_insumos": pd.DataFrame(columns=["insumo_filho_codigo"]),
        "composicao_subcomposicoes": pd.DataFrame(),
        "parent_composicoes_details": pd.DataFrame(
            columns=["codigo", "descricao", "unidade"]
        ),
        "child_item_details": pd.DataFrame(
            columns=["codigo", "tipo", "descricao", "unidade"]
        ),
    }

    result = pipeline.run() # Capture the result

    mock_processor.process_catalogo_e_precos.assert_called()
    mock_db.save_data.assert_called()
    spy_run_pre_processing.assert_called_once()
    assert result["status"] == "SUCESSO"
    assert "populados com sucesso" in result["message"]
    assert result["records_inserted"] > 0
    mock_convert_excel_sheets_to_csv.assert_called_once_with(
        xlsx_full_path=referencia_file_path,
        sheets_to_convert=mock_config.SHEETS_TO_CONVERT,
        output_dir=referencia_file_path.parent.parent / "csv_temp"
    )


def test_fallback_to_download(mock_pipeline, mocker):
    """Testa o fallback para download quando arquivo não é fornecido."""
    pipeline, _, mock_downloader, _, _, _, mock_config, spy_run_pre_processing, spy_run = mock_pipeline
    spy_find_and_normalize_zip = mocker.spy(pipeline, "_find_and_normalize_zip")

    # Ensure input_file is not set in the mocked sinapi_config
    if "input_file" in mock_config.sinapi_config:
        del mock_config.sinapi_config["input_file"]

    pipeline._find_and_normalize_zip.return_value = None

    result = pipeline.run() # Capture the result

    mock_downloader.get_sinapi_data.assert_called_once()
    spy_find_and_normalize_zip.assert_called_once()
    assert result["status"] == "SUCESSO"
    assert "populados com sucesso" in result["message"]
    assert result["records_inserted"] > 0


def test_invalid_input_file(mock_pipeline, mocker):
    """Testa erro ao fornecer arquivo inválido."""
    pipeline, _, _, _, _, _, mock_config, spy_run_pre_processing, spy_run = mock_pipeline

    # Set an invalid input_file in the mocked sinapi_config
    mock_config.sinapi_config["input_file"] = "arquivo_inexistente.xlsx"

    pipeline._unzip_file.side_effect = FileNotFoundError(
        "Arquivo não encontrado"
    )

    result = pipeline.run() # Capture the result

    assert result["status"] == "FALHA"
    assert "Arquivo não encontrado" in result["message"]
    assert result["tables_updated"] == []
    assert result["records_inserted"] == 0



