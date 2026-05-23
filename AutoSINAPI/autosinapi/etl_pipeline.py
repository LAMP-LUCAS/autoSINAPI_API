# autosinapi/etl_pipeline.py

"""
etl_pipeline.py: Orquestrador Principal do Pipeline ETL do AutoSINAPI.
"""

import argparse
import json
import logging
import os
import re
import shutil
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from io import BytesIO

import pandas as pd

from autosinapi.config import Config
from autosinapi.core.database import Database
from autosinapi.core.downloader import Downloader
from autosinapi.core.pre_processor import convert_excel_sheets_to_csv
from autosinapi.core.processor import Processor
from autosinapi.exceptions import AutoSinapiError, ConfigurationError, DownloadError, ProcessingError, DatabaseError

# --- CONFIGURAÇÃO DE LOGGING ---
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
    def __init__(self, run_id: str = None, config_path: str = None, custom_constants: dict = None, debug_mode: bool = False):
        self.run_id = run_id or str(uuid.uuid4())[:8]
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
            except Exception as e:
                self.logger.error(f"Erro ao carregar arquivo de configuração: {e}")
        return {
            'default_month': None,
            'default_year': None,
            'duplicate_policy': 'substituir',
            'secrets_path': 'tools/sql_access.secrets'
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
            'month': os.getenv("SINAPI_MONTH", base_config.get('default_month')),
            'year': os.getenv("SINAPI_YEAR", base_config.get('default_year')),
            'state': os.getenv("SINAPI_STATE", "SP"),
            'type': os.getenv("SINAPI_TYPE", "REFERENCIA")
        }

    def run(self, input_file_path: str = None) -> Dict:
        self.logger.info("=" * 50)
        self.logger.info(f"Iniciando Processamento ETL - Versão {self.config.VERSION}")
        self.logger.info(f"Referência: {self.config.YEAR}/{self.config.MONTH:02d} - UF: {self.config.STATE}")
        self.logger.info("=" * 50)

        status = self.config.STATUS_SUCCESS
        message = "Pipeline executado com sucesso."
        tables_updated = []
        records_inserted = 0

        try:
            with Database(self.config) as db:
                self.logger.info("[FASE 0] Verificando existência de tabelas...")
                db.check_tables()

                self.logger.info("[FASE 1] Extraindo arquivos...")
                downloader = Downloader(self.config)
                referencia_file_path, extra_files = downloader.get_sinapi_data(input_file_path)

                if not referencia_file_path:
                    status = self.config.STATUS_SUCCESS_NO_DATA
                    message = "Pipeline finalizado sem dados para processar."
                else:
                    extraction_path = Path(referencia_file_path).parent
                    self._run_pre_processing(referencia_file_path, extraction_path)
                    
                    data_referencia = self.extract_sinapi_version(referencia_file_path)
                    self.logger.info(f"Versão SINAPI extraída do arquivo: {data_referencia}")

                    self.logger.info("[FASE 2] Transformando dados...")
                    processor = Processor(self.config)
                    processed_data = processor.process_catalogo_e_precos(referencia_file_path)
                    structure_dfs = processor.process_composicao_itens(referencia_file_path)
                    
                    if extra_files.get("manutencoes"):
                        manut_df = processor.process_manutencoes(extra_files["manutencoes"])
                        processed_data["manutencoes_historico"] = manut_df
                    
                    if extra_files.get("familias"):
                        fam_data = processor.process_familias_e_coeficientes(extra_files["familias"])
                        processed_data.update(fam_data)

                    if extra_files.get("mao_de_obra"):
                        mo_df = processor.process_mao_de_obra(extra_files["mao_de_obra"])
                        processed_data["composicoes_mix_mao_de_obra"] = mo_df

                    processed_data = self._handle_missing_items_placeholders(processed_data, structure_dfs)

                    self.logger.info("[FASE 3] Carregando dados no Postgres...")
                    records_inserted, tables_updated = self._execute_phase_3_load_data(
                        db, processed_data, structure_dfs, data_referencia
                    )

        except AutoSinapiError as e:
            self.logger.error(f"Erro no pipeline: {e}")
            status = self.config.STATUS_FAILURE
            message = str(e)
        except Exception as e:
            self.logger.critical(f"Ocorreu um erro inesperado e fatal no pipeline: {e}", exc_info=True)
            status = self.config.STATUS_FAILURE
            message = f"Erro inesperado: {e}"

        self.logger.info("=" * 50)
        self.logger.info(f"=========   PIPELINE FINALIZADO (Run ID: {self.run_id})   =========")
        self.logger.info(f"Status Final: {status}")
        self.logger.info(f"Total de Registros Inseridos: {records_inserted}")
        self.logger.info(f"Tabelas Atualizadas: {tables_updated}")
        self.logger.info("=" * 50)

        return {
            "status": status,
            "message": message,
            "tables_updated": list(set(tables_updated)),
            "records_inserted": records_inserted,
        }

    def _run_pre_processing(self, referencia_file_path, extraction_path):
        self.logger.info("Iniciando pré-processamento (Excel -> CSV)...")
        output_dir = extraction_path / self.config.TEMP_CSV_DIR
        convert_excel_sheets_to_csv(
            xlsx_full_path=referencia_file_path,
            sheets_to_convert=self.config.SHEETS_TO_CONVERT,
            output_dir=output_dir,
            config=self.config 
        )

    def extract_sinapi_version(self, filename: str) -> str:
        """Extrai versão SINAPI do nome do arquivo."""
        if not filename: return "DESCONHECIDA"
        fname = Path(filename).name
        match = re.search(r'(\d{4})[_-](\d{2})', fname)
        if match:
            return f"{match.group(1)}.{match.group(2)}"
        return f"{self.config.YEAR}.{self.config.MONTH:02d}"

    def _handle_missing_items_placeholders(self, processed_data: Dict, structure_dfs: Dict) -> Dict:
        """
        Verifica inconsistências de dados e cria placeholders para itens ausentes.
        """
        # 1. Tratamento para insumos ausentes
        existing_insumos_df = processed_data.get('insumos', pd.DataFrame(columns=['codigo', 'descricao', 'unidade', 'classificacao']))
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
            missing_insumos_df['codigo'] = missing_insumos_df['codigo'].astype('Int64')
            processed_data['insumos'] = pd.concat([existing_insumos_df, missing_insumos_df], ignore_index=True)

        # 2. Tratamento para composições ausentes
        existing_composicoes_df = processed_data.get('composicoes', pd.DataFrame(columns=['codigo', 'descricao', 'unidade', 'grupo']))
        
        parent_codes = structure_dfs.get('parent_composicoes_details', pd.DataFrame(columns=['codigo', 'descricao', 'unidade', 'grupo'])).set_index('codigo')
        child_codes = structure_dfs['child_item_details'][
            structure_dfs['child_item_details']['tipo'] == self.config.ITEM_TYPE_COMPOSICAO
        ].drop_duplicates(subset=['codigo']).set_index('codigo')

        all_comp_codes_in_structure = set(parent_codes.index) | set(child_codes.index)
        all_comp_codes_in_structure |= set(structure_dfs[self.config.DB_TABLE_COMPOSICAO_INSUMOS]['composicao_pai_codigo'].unique())
        if self.config.DB_TABLE_COMPOSICAO_SUBCOMPOSICOES in structure_dfs:
             all_comp_codes_in_structure |= set(structure_dfs[self.config.DB_TABLE_COMPOSICAO_SUBCOMPOSICOES]['composicao_pai_codigo'].unique())
             all_comp_codes_in_structure |= set(structure_dfs[self.config.DB_TABLE_COMPOSICAO_SUBCOMPOSICOES]['composicao_filho_codigo'].unique())

        existing_composicao_codes_set = set(existing_composicoes_df['codigo'].values)
        missing_composicao_codes = list(all_comp_codes_in_structure - existing_composicao_codes_set)

        if missing_composicao_codes:
            self.logger.warning(f"Encontradas {len(missing_composicao_codes)} composições na estrutura que não estão no catálogo. Criando placeholders...")
            def get_detail(code, column):
                if code in parent_codes.index and column in parent_codes.columns:
                    val = parent_codes.loc[code, column]
                    if pd.notna(val): return val
                if code in child_codes.index and column in child_codes.columns:
                    val = child_codes.loc[code, column]
                    if pd.notna(val): return val
                
                if column == 'descricao': return self.config.PLACEHOLDER_COMPOSICAO_DESC_TEMPLATE.format(code=code)
                if column == 'unidade': return self.config.DEFAULT_PLACEHOLDER_UNIT
                if column == 'grupo': return 'NAO_CLASSIFICADO'
                return None

            missing_comp_data = {
                'codigo': missing_composicao_codes,
                'descricao': [get_detail(code, 'descricao') for code in missing_composicao_codes],
                'unidade': [get_detail(code, 'unidade') for code in missing_composicao_codes],
                'grupo': [get_detail(code, 'grupo') for code in missing_composicao_codes]
            }
            missing_comp_df = pd.DataFrame(missing_comp_data)
            missing_comp_df['codigo'] = missing_comp_df['codigo'].astype('Int64')
            processed_data['composicoes'] = pd.concat([existing_composicoes_df, missing_comp_df], ignore_index=True)

        return processed_data

    def _execute_phase_3_load_data(self, db: Database, processed_data: Dict, structure_dfs: Dict, data_referencia: str) -> Tuple[int, List[str]]:
        tables_updated = []
        records_inserted = 0

        # Ordem de carga respeitando FKS
        load_order = [
            ("insumos", "insumos", self.config.DB_POLICY_UPSERT, ["codigo"]),
            ("composicoes", "composicoes", self.config.DB_POLICY_UPSERT, ["codigo"]),
            (self.config.DB_TABLE_COMPOSICAO_INSUMOS, "composicao_insumos", self.config.DB_POLICY_APPEND, ["composicao_pai_codigo", "insumo_filho_codigo"]),
            (self.config.DB_TABLE_COMPOSICAO_SUBCOMPOSICOES, "composicao_subcomposicoes", self.config.DB_POLICY_APPEND, ["composicao_pai_codigo", "composicao_filho_codigo"]),
            ("precos_insumos_mensal", "precos_insumos_mensal", self.config.DB_POLICY_APPEND, ["insumo_codigo", "uf", "data_referencia", "regime"]),
            ("custos_composicoes_mensal", "custos_composicoes_mensal", self.config.DB_POLICY_APPEND, ["composicao_codigo", "uf", "data_referencia", "regime"]),
            ("manutencoes_historico", "manutencoes_historico", self.config.DB_POLICY_UPSERT, ["item_codigo", "tipo_item", "data_referencia", "tipo_manutencao"]),
            ("insumos_familias", "insumos_familias", self.config.DB_POLICY_UPSERT, ["insumo_codigo"]),
            ("coeficientes_familia_mensal", "coeficientes_familia_mensal", self.config.DB_POLICY_APPEND, ["insumo_codigo", "uf"]),
            ("composicoes_mix_mao_de_obra", "composicoes_mix_mao_de_obra", self.config.DB_POLICY_APPEND, ["composicao_codigo", "uf"])
        ]

        for data_key, table_name, policy, pk in load_order:
            df = processed_data.get(data_key) if data_key in processed_data else structure_dfs.get(data_key)
            if df is not None and not df.empty:
                db.save_data(df, table_name, policy=policy, pk_columns=pk, 
                             etl_run_id=self.run_id, sinapi_versao=data_referencia)
                tables_updated.append(table_name)
                records_inserted += len(df)

        # Fase Final: Auditoria
        db.register_audit_log(self.run_id, data_referencia, records_inserted, tables_updated)
        
        return records_inserted, tables_updated
