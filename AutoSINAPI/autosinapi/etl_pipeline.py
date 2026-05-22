# autosinapi/etl_pipeline.py

"""
etl_pipeline.py: Orquestrador Principal do Pipeline ETL do AutoSINAPI.

Este módulo contém a classe `PipelineETL`, que atua como o ponto de entrada e
orquestrador central para todo o processo de Extração, Transformação e Carga (ETL)
dos dados do SINAPI.

**Responsabilidades:**

1.  **Inicialização e Configuração:**
    - Recebe um `run_id` único para rastrear a execução.
    - Carrega as configurações a partir de variáveis de ambiente ou de um
      arquivo de configuração JSON opcional.
    - Instancia e centraliza o objeto `Config`, que contém todas as
      constantes e parâmetros operacionais (nomes de arquivos, políticas de
      banco de dados, etc.).
    - Configura um sistema de logging detalhado, associando todas as mensagens
      ao `run_id` da execução.

2.  **Orquestração do Fluxo (ETL):**
    - **Extração (Fase 1):** Utiliza a classe `Downloader` para obter o
      arquivo de referência do SINAPI, seja fazendo o download do site da Caixa
      ou lendo um arquivo local. Gerencia a descompactação dos arquivos.
    - **Transformação (Fase 2):**
        - Invoca o `pre_processor` para converter planilhas Excel de alto
          volume em arquivos CSV, otimizando a leitura.
        - Utiliza a classe `Processor` para ler os arquivos de Manutenções e
          de Referência, transformando os dados brutos em DataFrames
          estruturados e limpos.
        - Aplica uma lógica robusta de "placeholders" para garantir a
          integridade referencial, criando registros temporários para insumos
          ou composições que são referenciados na estrutura mas não
          existem no catálogo principal.
    - **Carga (Fase 3):**
        - Utiliza a classe `Database` para carregar os DataFrames processados
          no banco de dados PostgreSQL.
        - Gerencia a ordem de inserção e as políticas de salvamento (APPEND,
          UPSERT) para cada tabela, conforme definido no objeto `Config`.
        - Sincroniza o status dos itens (ATIVO/DESATIVADO) com base nos
          dados do arquivo de manutenções.

**Retorno:**
- A execução do método `run()` retorna um dicionário contendo o sumário da
  operação, incluindo o status final (`SUCESSO` ou `FALHA`), uma mensagem
  descritiva, a lista de tabelas atualizadas e o total de registros inseridos.
"""

import argparse
import json
import logging
import os
import re
import uuid
import zipfile
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd

from autosinapi.config import Config
from autosinapi.core.database import Database
from autosinapi.core.downloader import Downloader
from autosinapi.core.pre_processor import convert_excel_sheets_to_csv
from autosinapi.core.processor import Processor
from autosinapi.exceptions import (
    AutoSinapiError,
    ConfigurationError,
    ProcessingError,
)

logger = logging.getLogger("autosinapi")


class RunIdFilter(logging.Filter):
    def __init__(self, run_id):
        super().__init__()
        self.run_id = run_id

    def filter(self, record):
        record.run_id = self.run_id
        return True


def setup_logging(run_id: str, debug_mode=False):
    level = logging.DEBUG if debug_mode else logging.INFO
    log_file_path = Path("./logs/etl_pipeline.log")
    log_file_path.parent.mkdir(parents=True, exist_ok=True)
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    run_id_filter = RunIdFilter(run_id)
    file_formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] [%(run_id)s] %(name)s: %(message)s"
    )
    stream_formatter_info = logging.Formatter("[%(levelname)s] [%(run_id)s] %(message)s")
    stream_formatter_debug = logging.Formatter(
        "%(asctime)s [%(levelname)s] [%(run_id)s] %(name)s: %(message)s"
    )
    file_handler = logging.FileHandler(log_file_path, mode="a")
    file_handler.setFormatter(file_formatter)
    file_handler.setLevel(level)
    file_handler.addFilter(run_id_filter)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(
        stream_formatter_debug if debug_mode else stream_formatter_info
    )
    stream_handler.setLevel(level)
    stream_handler.addFilter(run_id_filter)
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    logger.setLevel(level)
    if not debug_mode:
        logging.getLogger("urllib3").setLevel(logging.WARNING)

class PipelineETL:
    def __init__(self, run_id: str, config_path: str = None, custom_constants: dict = None, debug_mode: bool = False):
        self.run_id = run_id
        setup_logging(run_id=self.run_id, debug_mode=debug_mode)
        
        self.logger = logging.getLogger("autosinapi.pipeline")
        self.logger.info(f"Iniciando nova execução do pipeline. Run ID: {self.run_id}")

        try:
            base_config = self._load_base_config(config_path)
            db_cfg = self._get_db_config(base_config)
            sinapi_cfg = self._get_sinapi_config(base_config)
            
            self.config = Config(
                db_config=db_cfg,
                sinapi_config=sinapi_cfg,
                mode=os.getenv('AUTOSINAPI_MODE', 'local'),
                custom_constants=custom_constants
            )
            self.config.RUN_ID = self.run_id
        except ConfigurationError as e:
            self.logger.critical(f"Erro fatal de configuração: {e}", exc_info=True)
            raise

    def _load_base_config(self, config_path: str):
        self.logger.debug(f"Tentando carregar configuração. Caminho fornecido: {config_path}")
        if config_path:
            self.logger.info(f"Carregando configuração do arquivo: {config_path}")
            try:
                with open(config_path, 'r') as f:
                    return json.load(f)
            except FileNotFoundError as e:
                raise ConfigurationError(f"Arquivo de configuração não encontrado: {config_path}") from e
            except json.JSONDecodeError as e:
                raise ConfigurationError(f"Erro ao decodificar o arquivo JSON de configuração: {config_path}") from e
        else:
            self.logger.info("Carregando configuração a partir de variáveis de ambiente.")
            return {
                "secrets_path": os.getenv("AUTOSINAPI_SECRETS_PATH", "tools/sql_access.secrets"),
                "default_year": os.getenv("AUTOSINAPI_YEAR"),
                "default_month": os.getenv("AUTOSINAPI_MONTH"),
                "workbook_type_name": os.getenv("AUTOSINAPI_TYPE", "REFERENCIA"),
                "duplicate_policy": os.getenv("AUTOSINAPI_POLICY", "substituir"),
            }

    def _get_db_config(self, base_config):
        self.logger.debug("Extraindo configurações do banco de dados.")
        if os.getenv("DOCKER_ENV"):
            self.logger.info(
                "Modo Docker detectado. Lendo configuração do DB a partir de variáveis de ambiente."
            )
            required_vars = ["POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD"]
            missing_vars = [v for v in required_vars if not os.getenv(v)]
            if missing_vars:
                raise ConfigurationError(
                    f"Variáveis de ambiente para o banco de dados não encontradas: {missing_vars}. "
                    f"Verifique se o arquivo 'tools/docker/.env' existe e está preenchido corretamente."
                )
            return {
                'host': os.getenv("POSTGRES_HOST", "db"),
                'port': os.getenv("POSTGRES_PORT", 5432),
                'database': os.getenv("POSTGRES_DB"),
                'user': os.getenv("POSTGRES_USER"),
                'password': os.getenv("POSTGRES_PASSWORD"),
            }
        try:
            secrets_path = base_config['secrets_path']
            with open(secrets_path, 'r') as f:
                content = f.read()
            
            db_config = {}
            for line in content.splitlines():
                if '=' in line:
                    key, value = line.split('=', 1)
                    db_config[key.strip()] = value.strip().strip("'")
            
            return {
                'host': db_config['DB_HOST'],
                'port': db_config['DB_PORT'],
                'database': db_config['DB_NAME'],
                'user': db_config['DB_USER'],
                'password': db_config['DB_PASSWORD'],
            }
        except Exception as e:
            raise ConfigurationError(f"Erro ao ler ou processar o arquivo de secrets '{secrets_path}': {e}") from e

    def _get_sinapi_config(self, base_config):
        return {
            'state': base_config.get('default_state', 'BR'),
            'year': base_config['default_year'],
            'month': base_config['default_month'],
            'type': base_config.get('workbook_type_name', 'REFERENCIA'),
            'file_format': base_config.get('default_format', 'XLSX'),
            'duplicate_policy': base_config.get('duplicate_policy', 'substituir'),
            'mode': os.getenv('AUTOSINAPI_MODE', 'local')
        }

    def _find_and_normalize_zip(self, download_path: Path, standardized_name: str) -> Path:
        """
        Localiza o arquivo ZIP de dados, buscando na subpasta ou na raiz de downloads.
        Implementa Smart Discovery para identificar arquivos XLSX e ignorar PDFs.
        """
        self.logger.debug(f"Buscando arquivo ZIP em: {download_path}")
        
        # 1. Tentar busca exata na subpasta
        for file in download_path.glob('*.zip'):
            if 'xlsx' in file.name.lower():
                return file

        # 2. Smart Discovery: Buscar na raiz de downloads
        import re
        import shutil
        base_dir = Path(self.config.DOWNLOAD_DIR)
        year = str(self.config.YEAR)
        month = str(self.config.MONTH).zfill(2)
        pattern = re.compile(rf'SINAPI-{year}-{month}-formato-xlsx.*\.zip', re.IGNORECASE)

        for file in base_dir.glob('*.zip'):
            if pattern.search(file.name):
                self.logger.info(f"[SMART DISCOVERY] Identificado arquivo {file.name} na raiz. Auto-organizando...")
                download_path.mkdir(parents=True, exist_ok=True)
                target_path = download_path / file.name
                shutil.move(str(file), str(target_path))
                return target_path

        self.logger.info("Nenhum arquivo ZIP de dados encontrado localmente (incluindo Smart Discovery).")
        return None

    def _unzip_file(self, zip_path: Path) -> Path:
        extraction_path = zip_path.parent / zip_path.stem
        self.logger.info(f"Descompactando '{zip_path.name}' para: {extraction_path}")
        extraction_path.mkdir(parents=True, exist_ok=True)
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extraction_path)
            self.logger.info(f"Arquivo descompactado com sucesso em {extraction_path}")
            return extraction_path
        except zipfile.BadZipFile as e:
            raise ProcessingError(
                f"O arquivo '{zip_path.name}' não é um zip válido ou está corrompido."
                ) from e

    def _execute_phase_1_acquisition(self, downloader: Downloader) -> Path:
        """
        Executa a Fase 1: Aquisição e descompactação dos dados do SINAPI.
        Retorna o caminho para o diretório com os arquivos extraídos.
        """
        year = str(self.config.YEAR)
        month = str(self.config.MONTH).zfill(2)
        self.logger.info(f"[FASE 1] Iniciando obtenção de dados para {month}/{year}.")
        
        download_path = Path(os.path.join(self.config.DOWNLOAD_DIR, f"{year}_{month}"))
        download_path.mkdir(parents=True, exist_ok=True)
        
        standardized_name = self.config.ZIP_FILENAME_TEMPLATE.format(year=year, month=month)
        local_zip_path = self._find_and_normalize_zip(download_path, standardized_name)
        
        if not local_zip_path:
            self.logger.info("Arquivo não encontrado localmente. Iniciando download...")
            file_content = downloader.get_sinapi_data(save_path=download_path)
            local_zip_path = download_path / standardized_name
            with open(local_zip_path, 'wb') as f:
                f.write(file_content.getbuffer())
            self.logger.info(f"Download concluído e salvo em: {local_zip_path}")
        
        extraction_path = self._unzip_file(local_zip_path)
        self.logger.info("[FASE 1] Obtenção de dados concluída com sucesso.")
        return extraction_path

    def extract_sinapi_version(self, filename: str) -> str:
        """Extrai versão SINAPI do nome do arquivo."""
        match = re.search(r'(\d{4})[_-](\d{2})', filename)
        if match:
            return f"{match.group(1)}.{match.group(2)}"
        return f"{self.config.YEAR}.{str(self.config.MONTH).zfill(2)}"

    def _process_maintenance_data(self, processor: Processor, db: Database, file_path: Path) -> Tuple[int, str]:
        """
        Processa e carrega os dados de manutenção, sincronizando o status dos catálogos.
        Retorna o número de registros inseridos e o nome da tabela atualizada.
        """
        self.logger.info(f"Processando arquivo de Manutenções: {file_path.name}")
        manutencoes_df = processor.process_manutencoes(str(file_path))
        
        if not manutencoes_df.empty:
            sinapi_versao = self.extract_sinapi_version(file_path.name)
            db.save_data(manutencoes_df, self.config.DB_TABLE_MANUTENCOES, 
                        policy=self.config.DB_POLICY_APPEND,
                        sinapi_versao=sinapi_versao, etl_run_id=self.run_id)
            self.logger.info(f"{len(manutencoes_df)} registros de manutenção carregados. Sincronizando status...")
            self._sync_catalog_status(db)
            return len(manutencoes_df), self.config.DB_TABLE_MANUTENCOES
        
        self.logger.info("Nenhum dado de manutenção para processar.")
        return 0, None

    def _handle_missing_items_placeholders(self, processed_data: Dict, structure_dfs: Dict) -> Dict:
        """
        Verifica inconsistências de dados e cria placeholders para itens ausentes.
        Retorna o dicionário `processed_data` atualizado.
        """
        # Tratamento para insumos ausentes
        existing_insumos_df = processed_data.get('insumos', pd.DataFrame(columns=['codigo', 'descricao', 'unidade']))
        all_child_insumo_codes = structure_dfs[self.config.DB_TABLE_COMPOSICAO_INSUMOS]['insumo_filho_codigo'].unique()
        existing_insumo_codes_set = set(existing_insumos_df['codigo'].values)
        missing_insumo_codes = [code for code in all_child_insumo_codes if code not in existing_insumo_codes_set]
        
        if missing_insumo_codes:
            self.logger.warning(f"Encontrados {len(missing_insumo_codes)} insumos na estrutura que não estão no catálogo. Criando placeholders...")
            insumo_details_df = structure_dfs['child_item_details'][
                        (structure_dfs['child_item_details']['codigo'].isin(missing_insumo_codes)) &
                        (structure_dfs['child_item_details']['tipo'] == self.config.ITEM_TYPE_INSUMO)
                    ].drop_duplicates(subset=['codigo']).set_index('codigo')

            missing_insumos_data = {
                'codigo': missing_insumo_codes,
                'descricao': [insumo_details_df.loc[code, 'descricao'] if code in insumo_details_df.index else self.config.PLACEHOLDER_INSUMO_DESC_TEMPLATE.format(code=code) for code in missing_insumo_codes],
                'unidade': [insumo_details_df.loc[code, 'unidade'] if code in insumo_details_df.index else self.config.DEFAULT_PLACEHOLDER_UNIT for code in missing_insumo_codes],
                'classificacao': 'NAO_CLASSIFICADO'
            }
            missing_insumos_df = pd.DataFrame(missing_insumos_data)
            processed_data['insumos'] = pd.concat([existing_insumos_df, missing_insumos_df], ignore_index=True)

        # Tratamento para composições ausentes
        existing_composicoes_df = processed_data.get('composicoes', pd.DataFrame(columns=['codigo', 'descricao', 'unidade', 'grupo']))
        parent_codes = structure_dfs['parent_composicoes_details'].set_index('codigo')
        child_codes = structure_dfs['child_item_details'][
            structure_dfs['child_item_details']['tipo'] == self.config.ITEM_TYPE_COMPOSICAO
        ].drop_duplicates(subset=['codigo']).set_index('codigo')

        all_composicao_codes_in_structure = set(parent_codes.index) | set(child_codes.index)
        existing_composicao_codes_set = set(existing_composicoes_df['codigo'].values)
        missing_composicao_codes = list(all_composicao_codes_in_structure - existing_composicao_codes_set)

        if missing_composicao_codes:
            self.logger.warning(f"Encontradas {len(missing_composicao_codes)} composições na estrutura que não estão no catálogo. Criando placeholders...")
            def get_detail(code, column):
                if code in parent_codes.index: return parent_codes.loc[code, column]
                if code in child_codes.index: return child_codes.loc[code, column]
                if column == 'descricao': return self.config.PLACEHOLDER_COMPOSICAO_DESC_TEMPLATE.format(code=code)
                if column == 'unidade': return self.config.DEFAULT_PLACEHOLDER_UNIT
                if column == 'grupo': return 'NAO_CLASSIFICADO'
                return None

            missing_composicoes_df = pd.DataFrame({
                'codigo': missing_composicao_codes,
                'descricao': [get_detail(code, 'descricao') for code in missing_composicao_codes],
                'unidade': [get_detail(code, 'unidade') for code in missing_composicao_codes],
                'grupo': [get_detail(code, 'grupo') for code in missing_composicao_codes]
            })
            processed_data['composicoes'] = pd.concat([existing_composicoes_df, missing_composicoes_df], ignore_index=True)
            
        return processed_data

    def _execute_phase_3_load_data(self, db: Database, processed_data: Dict, structure_dfs: Dict, data_referencia: str) -> Tuple[int, List[str]]:
        """
        Executa a Fase 3: Carga dos dados processados no banco de dados.
        Retorna o total de registros inseridos e a lista de tabelas atualizadas nesta fase.
        """
        self.logger.info("[FASE 3] Iniciando carga de dados no banco.")
        records_loaded = 0
        tables_loaded = []
        
        # Extrair versão SINAPI do nome do arquivo
        sinapi_versao = f"{self.config.YEAR}.{str(self.config.MONTH).zfill(2)}"
        
        # Carrega catálogos
        for catalog_name in ['insumos', 'composicoes']:
            if catalog_name in processed_data and not processed_data[catalog_name].empty:
                table_name = getattr(self.config, f"DB_TABLE_{catalog_name.upper()}")
                df = processed_data[catalog_name]
                db.save_data(df, table_name, policy=self.config.DB_POLICY_UPSERT, 
                            pk_columns=['codigo'], sinapi_versao=sinapi_versao, etl_run_id=self.run_id)
                tables_loaded.append(table_name)
                records_loaded += len(df)

        # Carrega estrutura - DELETE por período em vez de TRUNCATE
        ref_date = data_referencia
        for structure_name in [self.config.DB_TABLE_COMPOSICAO_INSUMOS, self.config.DB_TABLE_COMPOSICAO_SUBCOMPOSICOES]:
            if structure_name in structure_dfs and not structure_dfs[structure_name].empty:
                # Deleta apenas registros do período
                db.execute_non_query(
                    f'DELETE FROM "{structure_name}" WHERE data_referencia = :ref',
                    {"ref": ref_date}
                )
                df = structure_dfs[structure_name]
                db.save_data(df, structure_name, policy=self.config.DB_POLICY_APPEND,
                            sinapi_versao=sinapi_versao, etl_run_id=self.run_id)
                tables_loaded.append(structure_name)
                records_loaded += len(df)
        
        # Carrega dados mensais com UPSERT (permite retificações)
        for monthly_data_key in ['precos_insumos_mensal', 'custos_composicoes_mensal']:
            if monthly_data_key in processed_data and not processed_data[monthly_data_key].empty:
                table_name = getattr(self.config, f"DB_TABLE_{monthly_data_key.upper().replace('_MENSAL', '')}")
                df = processed_data[monthly_data_key]
                df['data_referencia'] = pd.to_datetime(data_referencia)
                db.save_data(df, table_name, policy=self.config.DB_POLICY_APPEND,
                            sinapi_versao=sinapi_versao, etl_run_id=self.run_id)
                tables_loaded.append(table_name)
                records_loaded += len(df)
                
        self.logger.info("[FASE 3] Carga de dados concluída.")
        return records_loaded, tables_loaded
        
    # --- MÉTODOS DE SINCRONIZAÇÃO E PRÉ-PROCESSAMENTO (inalterados) ---
    def _run_pre_processing(self, referencia_file_path: Path, extraction_path: Path):
        # ... (código inalterado) ...
        self.logger.info("Iniciando pré-processamento de planilhas para CSV.")
        output_dir = extraction_path.parent / self.config.TEMP_CSV_DIR
        try:
            convert_excel_sheets_to_csv(
                xlsx_full_path=referencia_file_path,
                sheets_to_convert=self.config.SHEETS_TO_CONVERT,
                output_dir=output_dir,
                config=self.config 
            )
            self.logger.info("Pré-processamento de planilhas concluído com sucesso.")
        except ProcessingError as e:
            self.logger.error(f"Erro durante o pré-processamento: {e}", exc_info=True)
            raise

    def _sync_catalog_status(self, db: Database):
        # ... (código inalterado) ...
        self.logger.info("Sincronizando status dos catálogos (insumos/composições).")
        sql_update = f"""
        WITH latest_maintenance AS (
            SELECT
                item_codigo, tipo_item, tipo_manutencao,
                ROW_NUMBER() OVER(PARTITION BY item_codigo, tipo_item ORDER BY data_referencia DESC) as rn
            FROM {self.config.DB_TABLE_MANUTENCOES}
        )
        UPDATE {{table}}
        SET status = 'DESATIVADO'
        WHERE codigo IN (
            SELECT item_codigo FROM latest_maintenance
            WHERE rn = 1 AND tipo_item = '{{item_type}}' AND tipo_manutencao ILIKE '{self.config.MAINTENANCE_DEACTIVATION_KEYWORD}'
        );
        """
        try:
            num_insumos_updated = db.execute_non_query(sql_update.format(table=self.config.DB_TABLE_INSUMOS, item_type=self.config.ITEM_TYPE_INSUMO))
            self.logger.info(f"Status do catálogo de insumos sincronizado. Itens desativados: {num_insumos_updated}")
            num_composicoes_updated = db.execute_non_query(sql_update.format(table=self.config.DB_TABLE_COMPOSICOES, item_type=self.config.ITEM_TYPE_COMPOSICAO))
            self.logger.info(f"Status do catálogo de composições sincronizado. Itens desativados: {num_composicoes_updated}")
        except Exception as e:
            self.logger.error(f"Erro ao sincronizar status dos catálogos: {e}", exc_info=True)
            raise DatabaseError(f"Erro ao sincronizar status dos catálogos: {e}") from e


    def run(self):
        """
        Método principal que orquestra a execução completa do pipeline ETL.
        """
        tables_updated = []
        records_inserted = 0
        status = self.config.STATUS_FAILURE
        message = "Ocorreu um erro inesperado."

        try:
            self.logger.info("Configuração validada com sucesso.")
            downloader = Downloader(self.config)
            processor = Processor(self.config)
            db = Database(self.config)

            # Fase 0: Preparação do Banco de Dados (Inteligente)
            self.logger.info("[FASE 0] Verificando existência de tabelas...")
            with db._engine.connect() as conn:
                from sqlalchemy import text
                check_table = self.config.DB_TABLE_INSUMOS
                check = conn.execute(text(f"SELECT EXISTS (SELECT FROM pg_tables WHERE schemaname = 'public' AND tablename = '{check_table}')")).scalar()
                if not check:
                    self.logger.info(f"[FASE 0] Tabela '{check_table}' não encontrada. Criando esquema...")
                    db.create_tables()
                else:
                    self.logger.info("[FASE 0] Esquema já existente. Pulando criação.")

            # Fase 1: Aquisição de Dados
            extraction_path = self._execute_phase_1_acquisition(downloader)

            # Fase 2: Processamento de Arquivos
            self.logger.info("[FASE 2] Iniciando processamento dos arquivos.")
            all_excel_files = list(extraction_path.glob('*.xlsx'))
            if not all_excel_files:
                raise ProcessingError(f"Nenhum arquivo .xlsx encontrado em {extraction_path}")

            manutencoes_file_path = next((f for f in all_excel_files if self.config.MAINTENANCE_FILE_KEYWORD in f.name), None)
            referencia_file_path = next((f for f in all_excel_files if self.config.REFERENCE_FILE_KEYWORD in f.name), None)
            families_file_path = next((f for f in all_excel_files if self.config.FAMILIES_FILE_KEYWORD in f.name), None)
            labor_file_path = next((f for f in all_excel_files if self.config.LABOR_FILE_KEYWORD in f.name), None)

            # Processa manutenções (se existirem)
            if manutencoes_file_path:
                count, table = self._process_maintenance_data(processor, db, manutencoes_file_path)
                if table:
                    records_inserted += count
                    tables_updated.append(table)
            else:
                self.logger.warning("Arquivo de Manutenções não encontrado. Sincronização de status pulada.")

            # Processa famílias e coeficientes (se existirem)
            if families_file_path:
                families_dfs = processor.process_familias_e_coeficientes(str(families_file_path))
                sinapi_versao = self.extract_sinapi_version(families_file_path.name)
                for table_key, df in families_dfs.items():
                    if not df.empty:
                        table_name = getattr(self.config, f"DB_TABLE_{table_key.replace('_MENSAL', '').upper()}")
                        if 'mensal' in table_key:
                            df['data_referencia'] = pd.to_datetime(f"{self.config.YEAR}-{str(self.config.MONTH).zfill(2)}-01")
                            db.save_data(df, table_name, policy=self.config.DB_POLICY_APPEND,
                                        sinapi_versao=sinapi_versao, etl_run_id=self.run_id)
                        else:
                            db.save_data(df, table_name, policy=self.config.DB_POLICY_UPSERT, 
                                        pk_columns=list(df.columns[:-1]),
                                        sinapi_versao=sinapi_versao, etl_run_id=self.run_id)
                        records_inserted += len(df)
                        tables_updated.append(table_name)

            # Processa mix de mão de obra (se existir)
            if labor_file_path:
                labor_df = processor.process_mao_de_obra(str(labor_file_path))
                if not labor_df.empty:
                    table_name = self.config.DB_TABLE_COMPOSICOES_MIX_MO
                    sinapi_versao = self.extract_sinapi_version(labor_file_path.name)
                    labor_df['data_referencia'] = pd.to_datetime(f"{self.config.YEAR}-{str(self.config.MONTH).zfill(2)}-01")
                    db.save_data(labor_df, table_name, policy=self.config.DB_POLICY_APPEND,
                                sinapi_versao=sinapi_versao, etl_run_id=self.run_id)
                    records_inserted += len(labor_df)
                    tables_updated.append(table_name)

            # Processa arquivo de referência (se existir)
            if not referencia_file_path:
                self.logger.warning("Arquivo de Referência não encontrado. Finalizando pipeline.")
                status = self.config.STATUS_SUCCESS_NO_DATA
                message = "Pipeline finalizado sem dados para processar."
            else:
                self._run_pre_processing(referencia_file_path, extraction_path)
                
                processed_data = processor.process_catalogo_e_precos(str(referencia_file_path))
                structure_dfs = processor.process_composicao_itens(str(referencia_file_path))
                
                processed_data = self._handle_missing_items_placeholders(processed_data, structure_dfs)
                
                self.logger.info("[FASE 2] Processamento de arquivos concluído.")

                # Fase 3: Carga de Dados
                data_referencia = f"{self.config.YEAR}-{str(self.config.MONTH).zfill(2)}-01"
                count, tables = self._execute_phase_3_load_data(db, processed_data, structure_dfs, data_referencia)
                records_inserted += count
                tables_updated.extend(tables)
                
                status = self.config.STATUS_SUCCESS
                message = "Dados populados com sucesso."

        except AutoSinapiError as e:
            self.logger.error(f"Erro de negócio no pipeline: {e}", exc_info=True)
            message = f"Erro de negócio: {e}"
        except Exception as e:
            self.logger.critical(f"Ocorreu um erro inesperado e fatal no pipeline: {e}", exc_info=True)
            message = f"Erro inesperado: {e}"
        finally:
            # --- Sumário da Execução ---
            self.logger.info("=" * 50)
            self.logger.info(f"=========   PIPELINE FINALIZADO (Run ID: {self.run_id})   =========")
            self.logger.info(f"Status Final: {status}")
            self.logger.info(f"Total de Registros Inseridos: {records_inserted}")
            self.logger.info(f"Tabelas Atualizadas: {list(set(tables_updated))}")
            self.logger.info("=" * 50)

        return {
            "status": status,
            "message": message,
            "tables_updated": list(set(tables_updated)),
            "records_inserted": records_inserted,
        }