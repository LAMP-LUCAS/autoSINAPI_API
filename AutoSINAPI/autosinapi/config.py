"""
Módulo de configuração do AutoSINAPI.

Este módulo define a classe `Config`, responsável por centralizar, validar e gerenciar
todas as configurações necessárias para a execução do pipeline de ETL.
"""

from typing import Any, Dict

from .exceptions import ConfigurationError


class Config:
    """Gerenciador de configurações do AutoSINAPI."""

    # --- Seção de Constantes Padrão ---
    # Usado como fallback se não for fornecida uma configuração customizada.
    # Permite que o comportamento do pipeline seja extensivamente personalizado.
    DEFAULT_CONSTANTS = {
        # --- Constantes do Downloader ---
        "BASE_URL": "https://www.caixa.gov.br/Downloads/sinapi-a-vista-composicoes",
        "VALID_TYPES": ["REFERENCIA", "DESONERADO"],
        "TIMEOUT": 30,
        "ALLOWED_LOCAL_FILE_EXTENSIONS": [".xlsx", ".xls"],
        "DOWNLOAD_FILENAME_TEMPLATE": "SINAPI_{type}_{month}_{year}",
        "DOWNLOAD_FILE_EXTENSION": ".zip",

        # --- Constantes do ETL Pipeline ---
        "REFERENCE_FILE_KEYWORD": "Referência",
        "MAINTENANCE_FILE_KEYWORD": "Manuten",
        "FAMILIES_FILE_KEYWORD": "familias",
        "LABOR_FILE_KEYWORD": "mao_de_obra",
        "MAINTENANCE_DEACTIVATION_KEYWORD": "%DESATIVAÇÃO%",

        "TEMP_CSV_DIR": "csv_temp",
        "ZIP_FILENAME_TEMPLATE": "SINAPI-{year}-{month}-formato-xlsx.zip",
        "DB_POLICY_APPEND": "append",
        "DB_POLICY_UPSERT": "upsert",
        "DEFAULT_PLACEHOLDER_UNIT": "UN",
        "PLACEHOLDER_INSUMO_DESC_TEMPLATE": "INSUMO_DESCONHECIDO_{code}",
        "PLACEHOLDER_COMPOSICAO_DESC_TEMPLATE": "COMPOSICAO_DESCONHECIDA_{code}",
        "STATUS_SUCCESS": "SUCESSO",
        "STATUS_SUCCESS_NO_DATA": "SUCESSO (SEM DADOS)",
        "STATUS_FAILURE": "FALHA",

        # --- Constantes do Pre-Processor ---
        "SHEETS_TO_CONVERT": ['CSD', 'CCD', 'CSE'],
        "PREPROCESSOR_CSV_SEPARATOR": ";",

        # --- Constantes do Processor ---
        "COMPOSICAO_ITENS_SHEET_KEYWORD": "Analítico",
        "COMPOSICAO_ITENS_SHEET_EXCLUDE_KEYWORD": "Custo",
        "MANUTENCOES_HEADER_KEYWORDS": ["REFERENCIA", "TIPO", "CODIGO", "DESCRICAO", "MANUTENCAO"],
        "CUSTOS_HEADER_KEYWORDS": ["Código da Composição", "Descrição", "Unidade"],
        "SHEET_MAP": {
            "ISD": ("precos", "NAO_DESONERADO"), "ICD": ("precos", "DESONERADO"),
            "ISE": ("precos", "SEM_ENCARGOS"), "CSD": ("custos", "NAO_DESONERADO"),
            "CCD": ("custos", "DESONERADO"), "CSE": ("custos", "SEM_ENCARGOS"),
        },
        "ID_COL_STANDARDIZE_MAP": {
            "CODIGO_DO_INSUMO": "CODIGO", "DESCRICAO_DO_INSUMO": "DESCRICAO",
            "CODIGO_DA_COMPOSICAO": "CODIGO", "DESCRICAO_DA_COMPOSICAO": "DESCRICAO",
        },
        "MANUTENCOES_COL_MAP": {
            "REFERENCIA": "data_referencia", "TIPO": "tipo_item", "CODIGO": "item_codigo",
            "DESCRICAO": "descricao_item", "MANUTENCAO": "tipo_manutencao",
        },
        "ORIGINAL_COLS": {
            "TIPO_ITEM": "TIPO_ITEM", "CODIGO_COMPOSICAO": "CODIGO_DA_COMPOSICAO",
            "CODIGO_ITEM": "CODIGO_DO_ITEM", "COEFICIENTE": "COEFICIENTE",
            "DESCRICAO_ITEM": "DESCRICAO", "UNIDADE_ITEM": "UNIDADE",
        },

        "HEADER_SEARCH_LIMIT": 20,
        "MANUTENCOES_SHEET_INDEX": 0,
        "MANUTENCOES_DATE_FORMAT": "%m/%Y",
        "COMPOSICAO_ITENS_HEADER_ROW": 9,
        "PRECOS_HEADER_ROW": 9,
        "CUSTOS_CODIGO_REGEX": r",(\d+)\)$",
        "UNPIVOT_VALUE_PRECO": "preco_mediano",
        "UNPIVOT_VALUE_CUSTO": "custo_total",
        "FINAL_CATALOG_COLUMNS": {
            "CODIGO": "codigo", "DESCRICAO": "descricao", "UNIDADE": "unidade",
            "CLASSIFICACAO": "classificacao", "GRUPO": "grupo"
        },

        # --- Constantes do Database ---
        "DB_TABLE_INSUMOS": "insumos",
        "DB_TABLE_COMPOSICOES": "composicoes",
        "DB_TABLE_MANUTENCOES": "manutencoes_historico",
        "DB_TABLE_COMPOSICAO_INSUMOS": "composicao_insumos",
        "DB_TABLE_COMPOSICAO_SUBCOMPOSICOES": "composicao_subcomposicoes",
        "DB_TABLE_PRECOS_INSUMOS": "precos_insumos_mensal",
        "DB_TABLE_CUSTOS_COMPOSICOES": "custos_composicoes_mensal",
        "DB_TABLE_INSUMOS_FAMILIAS": "insumos_familias",
        "DB_TABLE_COEFICIENTES_FAMILIA": "coeficientes_familia_mensal",
        "DB_TABLE_COMPOSICOES_MIX_MO": "composicoes_mix_mao_de_obra",
        "DB_TABLE_AUDIT_LOG": "sinapi_audit_log",
        "ITEM_TYPE_INSUMO": "INSUMO",
        "ITEM_TYPE_COMPOSICAO": "COMPOSICAO",
        "DB_DIALECT": "postgresql",
        "DB_TEMP_TABLE_PREFIX": "temp_",
        "DB_DEFAULT_ITEM_STATUS": "ATIVO",
        "DB_POLICY_REPLACE": "substituir",
    }

    REQUIRED_DB_KEYS = {"host", "port", "database", "user", "password"}
    REQUIRED_SINAPI_KEYS = {"state", "month", "year", "type"}

    def __init__(
        self, db_config: Dict[str, Any], sinapi_config: Dict[str, Any], mode: str, custom_constants: Dict[str, Any] = None
    ):
        """
        Inicializa e valida todas as configurações do AutoSINAPI.
        
        Args:
            db_config: Dicionário com as configurações do banco de dados.
            sinapi_config: Dicionário com os parâmetros da extração SINAPI.
            mode: Modo de operação ('server' ou 'local').
            custom_constants: Dicionário opcional para sobrescrever as constantes padrão.
        """
        # Valida e armazena configurações brutas
        self._validate_db_config(db_config)
        self._validate_sinapi_config(sinapi_config)
        self.db_config = db_config
        self.sinapi_config = sinapi_config
        
        # Valida e define o modo de operação
        self.mode = self._validate_mode(mode)
        
        # --- Expõe as configurações como atributos de alto nível ---
        self.DOWNLOAD_DIR = "./downloads"
        self.YEAR = sinapi_config["year"]
        self.MONTH = sinapi_config["month"]
        self.STATE = sinapi_config["state"]
        self.TYPE = sinapi_config["type"]
        self.DB_HOST = db_config["host"]
        self.DB_PORT = db_config["port"]
        self.DB_NAME = db_config["database"]
        self.DB_USER = db_config["user"]
        self.DB_PASSWORD = db_config["password"]
        
        # --- Carrega as constantes (customizadas ou padrão) ---
        # Isso permite que o usuário personalize nomes de tabelas, arquivos, etc.
        constants = self.DEFAULT_CONSTANTS.copy()
        if custom_constants:
            constants.update(custom_constants)
        
        # Sandbox mode: prefix table names
        self._sandbox_prefix = ""
        if self.mode == "sandbox":
            self._sandbox_prefix = "sandbox_"
        
        for key, value in constants.items():
            # Add sandbox prefix to table names
            if key.startswith("DB_TABLE_"):
                value = f"{self._sandbox_prefix}{value}"
            setattr(self, key, value)

    def _validate_mode(self, mode: str) -> str:
        if mode not in ("server", "local", "sandbox"):
            raise ConfigurationError(f"Modo inválido: {mode}. Use 'server', 'local' ou 'sandbox'")
        return mode

    def _validate_db_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        missing = self.REQUIRED_DB_KEYS - set(config.keys())
        if missing:
            raise ConfigurationError(f"Configurações de banco ausentes: {missing}")
        return config

    def _validate_sinapi_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        missing = self.REQUIRED_SINAPI_KEYS - set(config.keys())
        if missing:
            raise ConfigurationError(f"Configurações do SINAPI ausentes: {missing}")
        return config

    @property
    def is_server_mode(self) -> bool:
        return self.mode == "server"

    @property
    def is_local_mode(self) -> bool:
        return self.mode == "local"
