# autosinapi/core/pre_processor.py

"""
pre_processor.py: Módulo de Pré-processamento de Arquivos.

Este módulo oferece funcionalidades para otimizar a leitura de grandes arquivos
Excel antes da etapa principal de transformação. Sua principal função é converter
planilhas específicas e de alto volume de um arquivo `.xlsx` em arquivos `.csv`
separados. Isso melhora significativamente o desempenho da leitura de dados no
módulo `processor`, que pode ler CSVs de forma muito mais eficiente que
planilhas Excel complexas.

**Função `convert_excel_sheets_to_csv`:**

- **Entradas:**
    - `xlsx_full_path (Path)`: O caminho completo para o arquivo Excel de
      origem (ex: `SINAPI_Referência_AAAA_MM.xlsx`).
    - `sheets_to_convert (list[str])`: Uma lista de nomes das planilhas que
      devem ser convertidas (ex: `['CSD', 'CCD', 'CSE']`).
    - `output_dir (Path)`: O diretório onde os arquivos CSV resultantes serão
      salvos.
    - `config (Config)`: O objeto de configuração do pipeline, do qual extrai
      parâmetros como o separador do CSV (`PREPROCESSOR_CSV_SEPARATOR`).

- **Transformações/Processos:**
    - Itera sobre a lista de planilhas a serem convertidas.
    - Para cada nome de planilha, lê os dados brutos do arquivo Excel
      utilizando `pandas.read_excel`.
    - Salva o conteúdo da planilha em um novo arquivo `.csv` no diretório de
      saída especificado. O nome do arquivo CSV será o mesmo da planilha
      (ex: `CSD.csv`).
    - Utiliza o separador definido no objeto `config` ao criar o arquivo CSV,
      garantindo consistência.

- **Saídas:**
    - A função não possui um valor de retorno explícito (`None`).
    - Seu resultado são os arquivos `.csv` criados no `output_dir`, que
      serão consumidos posteriormente pela classe `Processor`.
"""

import pandas as pd
import os
import logging
from pathlib import Path

from autosinapi.config import Config
from autosinapi.exceptions import ProcessingError

logger = logging.getLogger(__name__)

def convert_excel_sheets_to_csv(
    xlsx_full_path: Path,
    sheets_to_convert: list[str],
    output_dir: Path,
    config: Config
):
    """
    Converts specific sheets from an XLSX file to CSV, using settings from the config object.
    """
    logger.info(f"Iniciando pré-processamento do arquivo: {xlsx_full_path}")

    if not xlsx_full_path.exists():
        raise ProcessingError(f"Arquivo XLSX não encontrado: {xlsx_full_path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Diretório de saída para CSVs: {output_dir}")

    for sheet in sheets_to_convert:
        try:
            logger.info(f"Processando planilha: '{sheet}'...")
            df = pd.read_excel(
                xlsx_full_path,
                sheet_name=sheet,
                header=None,
                engine='openpyxl',
                engine_kwargs={'data_only': False}
            )

            csv_output_path = output_dir / f"{sheet}.csv"
            df.to_csv(csv_output_path, index=False, header=False, sep=config.PREPROCESSOR_CSV_SEPARATOR)
            logger.info(f"Planilha '{sheet}' convertida com sucesso para '{csv_output_path}' (separador: {config.PREPROCESSOR_CSV_SEPARATOR})")

        except Exception as e:
            raise ProcessingError(f"Falha ao processar a planilha '{sheet}'. Erro: {e}") from e

if __name__ == "__main__":
    # This part is for testing the module directly
    # Example usage (will not be used by etl_pipeline.py directly)
    # You would need to set up a dummy Excel file and output directory for this to run.
    DUMMY_BASE_PATH = Path("./downloads/2025_07/SINAPI-2025-07-formato-xlsx")
    DUMMY_XLSX_FILENAME = "SINAPI_Referência_2025_07.xlsx"
    DUMMY_SHEETS_TO_CONVERT = ['CSD', 'CCD', 'CSE']
    DUMMY_OUTPUT_DIR = DUMMY_BASE_PATH / ".." / "csv_temp"

    # Create dummy files/dirs for testing if needed
    # DUMMY_BASE_PATH.mkdir(parents=True, exist_ok=True)
    # (Create a dummy SINAPI_Referência_2025_07.xlsx here for testing)

    try:
        convert_excel_sheets_to_csv(
            DUMMY_BASE_PATH / DUMMY_XLSX_FILENAME,
            DUMMY_SHEETS_TO_CONVERT,
            DUMMY_OUTPUT_DIR
        )
        print("Pré-processamento de teste concluído com sucesso.")
    except ProcessingError as e:
        print(f"Erro durante o pré-processamento de teste: {e}")
