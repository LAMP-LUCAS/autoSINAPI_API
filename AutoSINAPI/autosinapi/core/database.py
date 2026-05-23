# autosinapi/core/database.py (versão refatorada)

"""
database.py: Módulo de Interação com o Banco de Dados.

Este módulo encapsula toda a lógica de comunicação com o banco de dados
PostgreSQL. Ele é responsável por criar o engine de conexão, gerenciar
transações e executar as operações de salvamento de dados (DML).
"""

import logging
import json
import uuid
from typing import Any, Dict

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from autosinapi.exceptions import DatabaseError


class Database:
    def __init__(self, config):
        self.logger = logging.getLogger("autosinapi.database")
        self.config = config
        self._engine = self._create_engine()

    def _create_engine(self) -> Engine:
        try:
            url = (
                f"{self.config.DB_DIALECT}://{self.config.DB_USER}:{self.config.DB_PASSWORD}@"
                f"{self.config.DB_HOST}:{self.config.DB_PORT}/{self.config.DB_NAME}"
            )
            self.logger.info(
                f"Conectando ao banco de dados: "
                f"{self.config.DB_DIALECT}://{self.config.DB_USER}:***@"
                f"{self.config.DB_HOST}:{self.config.DB_PORT}/{self.config.DB_NAME}"
            )
            return create_engine(url)
        except Exception as e:
            self.logger.error(f"Falha ao criar conexão com o banco de dados: {e}", exc_info=True)
            raise DatabaseError(f"Erro ao conectar com o banco de dados: {e}") from e

    def check_tables(self):
        """Verifica se as tabelas principais existem."""
        query = text("""
            SELECT count(*) FROM information_schema.tables 
            WHERE table_schema = 'public' AND table_name = :t
        """)
        main_tables = [self.config.DB_TABLE_INSUMOS, self.config.DB_TABLE_COMPOSICOES]
        with self._engine.connect() as conn:
            for t in main_tables:
                res = conn.execute(query, {"t": t}).scalar()
                if res == 0:
                    self.logger.warning(f"Tabela {t} não encontrada. Criando estrutura...")
                    self.create_tables()
                    break

    def create_tables(self):
        """Cria as tabelas do modelo de dados do SINAPI no banco."""
        drop_statements = f"""
        DROP VIEW IF EXISTS vw_composicao_itens_unificados;
        DROP TABLE IF EXISTS {self.config.DB_TABLE_AUDIT_LOG} CASCADE;
        DROP TABLE IF EXISTS {self.config.DB_TABLE_COMPOSICAO_SUBCOMPOSICOES} CASCADE;
        DROP TABLE IF EXISTS {self.config.DB_TABLE_COMPOSICAO_INSUMOS} CASCADE;
        DROP TABLE IF EXISTS {self.config.DB_TABLE_CUSTOS_COMPOSICOES} CASCADE;
        DROP TABLE IF EXISTS {self.config.DB_TABLE_PRECOS_INSUMOS} CASCADE;
        DROP TABLE IF EXISTS {self.config.DB_TABLE_MANUTENCOES} CASCADE;
        DROP TABLE IF EXISTS {self.config.DB_TABLE_COMPOSICOES} CASCADE;
        DROP TABLE IF EXISTS {self.config.DB_TABLE_INSUMOS} CASCADE;
        DROP TABLE IF EXISTS {self.config.DB_TABLE_INSUMOS_FAMILIAS} CASCADE;
        DROP TABLE IF EXISTS {self.config.DB_TABLE_COEFICIENTES_FAMILIA} CASCADE;
        DROP TABLE IF EXISTS {self.config.DB_TABLE_COMPOSICOES_MIX_MO} CASCADE;
        """

        ddl = f"""
        CREATE TABLE {self.config.DB_TABLE_INSUMOS} (
            codigo INTEGER PRIMARY KEY, descricao TEXT NOT NULL, unidade VARCHAR, classificacao TEXT, status VARCHAR DEFAULT '{self.config.DB_DEFAULT_ITEM_STATUS}',
            created_at TIMESTAMPTZ DEFAULT NOW(), updated_at TIMESTAMPTZ DEFAULT NOW(), sinapi_versao VARCHAR(20), etl_run_id VARCHAR(36)
        );
        CREATE TABLE {self.config.DB_TABLE_COMPOSICOES} (
            codigo INTEGER PRIMARY KEY, descricao TEXT NOT NULL, unidade VARCHAR, grupo VARCHAR, status VARCHAR DEFAULT '{self.config.DB_DEFAULT_ITEM_STATUS}',
            created_at TIMESTAMPTZ DEFAULT NOW(), updated_at TIMESTAMPTZ DEFAULT NOW(), sinapi_versao VARCHAR(20), etl_run_id VARCHAR(36)
        );
        CREATE TABLE {self.config.DB_TABLE_INSUMOS_FAMILIAS} (
            codigo_familia INTEGER NOT NULL, insumo_codigo INTEGER NOT NULL, categoria VARCHAR(50),
            created_at TIMESTAMPTZ DEFAULT NOW(), updated_at TIMESTAMPTZ DEFAULT NOW(), sinapi_versao VARCHAR(20), etl_run_id VARCHAR(36),
            PRIMARY KEY (codigo_familia, insumo_codigo),
            FOREIGN KEY (insumo_codigo) REFERENCES {self.config.DB_TABLE_INSUMOS}(codigo) ON DELETE CASCADE
        );
        CREATE TABLE {self.config.DB_TABLE_COEFICIENTES_FAMILIA} (
            insumo_codigo INTEGER NOT NULL, uf CHAR(2) NOT NULL, data_referencia DATE NOT NULL, coeficiente NUMERIC,
            created_at TIMESTAMPTZ DEFAULT NOW(), updated_at TIMESTAMPTZ DEFAULT NOW(), sinapi_versao VARCHAR(20), etl_run_id VARCHAR(36),
            PRIMARY KEY (insumo_codigo, uf, data_referencia),
            FOREIGN KEY (insumo_codigo) REFERENCES {self.config.DB_TABLE_INSUMOS}(codigo) ON DELETE CASCADE
        );
        CREATE TABLE {self.config.DB_TABLE_COMPOSICOES_MIX_MO} (
            composicao_codigo INTEGER NOT NULL, uf CHAR(2) NOT NULL, data_referencia DATE NOT NULL, porcentagem_mo NUMERIC,
            created_at TIMESTAMPTZ DEFAULT NOW(), updated_at TIMESTAMPTZ DEFAULT NOW(), sinapi_versao VARCHAR(20), etl_run_id VARCHAR(36),
            PRIMARY KEY (composicao_codigo, uf, data_referencia),
            FOREIGN KEY (composicao_codigo) REFERENCES {self.config.DB_TABLE_COMPOSICOES}(codigo) ON DELETE CASCADE
        );
        CREATE TABLE {self.config.DB_TABLE_PRECOS_INSUMOS} (
            insumo_codigo INTEGER NOT NULL, uf CHAR(2) NOT NULL, data_referencia DATE NOT NULL, regime VARCHAR NOT NULL, preco_mediano NUMERIC, origem_preco VARCHAR(10),
            created_at TIMESTAMPTZ DEFAULT NOW(), updated_at TIMESTAMPTZ DEFAULT NOW(), sinapi_versao VARCHAR(20), etl_run_id VARCHAR(36),
            PRIMARY KEY (insumo_codigo, uf, data_referencia, regime),
            FOREIGN KEY (insumo_codigo) REFERENCES {self.config.DB_TABLE_INSUMOS}(codigo) ON DELETE CASCADE
        );
        CREATE TABLE {self.config.DB_TABLE_CUSTOS_COMPOSICOES} (
            composicao_codigo INTEGER NOT NULL, uf CHAR(2) NOT NULL, data_referencia DATE NOT NULL, regime VARCHAR NOT NULL, custo_total NUMERIC,
            created_at TIMESTAMPTZ DEFAULT NOW(), updated_at TIMESTAMPTZ DEFAULT NOW(), sinapi_versao VARCHAR(20), etl_run_id VARCHAR(36),
            PRIMARY KEY (composicao_codigo, uf, data_referencia, regime),
            FOREIGN KEY (composicao_codigo) REFERENCES {self.config.DB_TABLE_COMPOSICOES}(codigo) ON DELETE CASCADE
        );
        CREATE TABLE {self.config.DB_TABLE_COMPOSICAO_INSUMOS} (
            composicao_pai_codigo INTEGER NOT NULL, insumo_filho_codigo INTEGER NOT NULL, coeficiente NUMERIC,
            created_at TIMESTAMPTZ DEFAULT NOW(), updated_at TIMESTAMPTZ DEFAULT NOW(), sinapi_versao VARCHAR(20), etl_run_id VARCHAR(36),
            PRIMARY KEY (composicao_pai_codigo, insumo_filho_codigo),
            FOREIGN KEY (composicao_pai_codigo) REFERENCES {self.config.DB_TABLE_COMPOSICOES}(codigo) ON DELETE CASCADE,
            FOREIGN KEY (insumo_filho_codigo) REFERENCES {self.config.DB_TABLE_INSUMOS}(codigo) ON DELETE CASCADE
        );
        CREATE TABLE {self.config.DB_TABLE_COMPOSICAO_SUBCOMPOSICOES} (
            composicao_pai_codigo INTEGER NOT NULL, composicao_filho_codigo INTEGER NOT NULL, coeficiente NUMERIC,
            created_at TIMESTAMPTZ DEFAULT NOW(), updated_at TIMESTAMPTZ DEFAULT NOW(), sinapi_versao VARCHAR(20), etl_run_id VARCHAR(36),
            PRIMARY KEY (composicao_pai_codigo, composicao_filho_codigo),
            FOREIGN KEY (composicao_pai_codigo) REFERENCES {self.config.DB_TABLE_COMPOSICOES}(codigo) ON DELETE CASCADE,
            FOREIGN KEY (composicao_filho_codigo) REFERENCES {self.config.DB_TABLE_COMPOSICOES}(codigo) ON DELETE CASCADE
        );
        CREATE TABLE {self.config.DB_TABLE_MANUTENCOES} (
            item_codigo INTEGER NOT NULL, tipo_item VARCHAR(20) NOT NULL, data_referencia DATE NOT NULL, tipo_manutencao VARCHAR(20) NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW(), updated_at TIMESTAMPTZ DEFAULT NOW(), sinapi_versao VARCHAR(20), etl_run_id VARCHAR(36),
            PRIMARY KEY (item_codigo, tipo_item, data_referencia, tipo_manutencao)
        );
        CREATE TABLE {self.config.DB_TABLE_AUDIT_LOG} (
            run_id VARCHAR(36) PRIMARY KEY, data_referencia VARCHAR(20), records_inserted INTEGER, tables_updated TEXT, created_at TIMESTAMPTZ DEFAULT NOW()
        );

        CREATE VIEW vw_composicao_itens_unificados AS 
        SELECT composicao_pai_codigo, insumo_filho_codigo AS item_codigo, 'INSUMO' AS tipo_item, coeficiente FROM {self.config.DB_TABLE_COMPOSICAO_INSUMOS}
        UNION ALL 
        SELECT composicao_pai_codigo, composicao_filho_codigo AS item_codigo, 'COMPOSICAO' AS tipo_item, coeficiente FROM {self.config.DB_TABLE_COMPOSICAO_SUBCOMPOSICOES};
        """

        try:
            with self._engine.connect() as conn:
                trans = conn.begin()
                conn.execute(text(drop_statements))
                conn.execute(text(ddl))
                trans.commit()
            self.logger.info("Tabelas do SINAPI criadas com sucesso.")
        except Exception as e:
            self.logger.error(f"Erro ao criar tabelas: {e}", exc_info=True)
            raise DatabaseError(f"Erro ao criar estrutura do banco: {e}") from e

    def save_data(self, data: pd.DataFrame, table_name: str, policy: str, **kwargs):
        if data.empty:
            self.logger.warning(f"DataFrame para a tabela '{table_name}' está vazio. Nenhum dado será salvo.")
            return

        self.logger.info(f"Salvando dados na tabela '{table_name}' com política '{policy.upper()}'.")
        
        # Propagar traceability fields de forma segura
        sinapi_versao = kwargs.get("sinapi_versao")
        etl_run_id = kwargs.get("etl_run_id")
        
        if sinapi_versao:
            data.loc[:, "sinapi_versao"] = sinapi_versao
        if etl_run_id:
            try:
                run_uuid = uuid.UUID(str(etl_run_id))
            except (ValueError, AttributeError):
                run_uuid = uuid.uuid5(uuid.NAMESPACE_DNS, str(etl_run_id))
            data.loc[:, "etl_run_id"] = str(run_uuid)
        
        if policy.lower() == self.config.DB_POLICY_REPLACE:
            year = kwargs.get("year")
            month = kwargs.get("month")
            if not year or not month:
                raise DatabaseError("Política 'substituir' requer 'year' e 'month'.")
            self._replace_data(data, table_name, year, month)
        elif policy.lower() == self.config.DB_POLICY_APPEND:
            self._append_data(data, table_name, **kwargs)
        elif policy.lower() == self.config.DB_POLICY_UPSERT:
            pk_columns = kwargs.get("pk_columns")
            if not pk_columns:
                raise DatabaseError("Política 'upsert' requer 'pk_columns'.")
            self._upsert_data(data, table_name, pk_columns)

    def _append_data(self, data: pd.DataFrame, table_name: str, **kwargs):
        self.logger.info(f"Inserindo {len(data)} registros em '{table_name}' (política: append).")
        try:
            with self._engine.connect() as conn:
                data.to_sql(name=table_name, con=conn, if_exists="append", index=False)
        except Exception as e:
            self.logger.error(f"Erro ao inserir dados em {table_name}: {e}", exc_info=True)
            raise DatabaseError(f"Erro ao inserir dados: {str(e)}") from e

    def _upsert_data(self, data: pd.DataFrame, table_name: str, pk_columns: list):
        self.logger.info(f"Executando UPSERT de {len(data)} registros em '{table_name}'.")
        temp_table_name = f"{self.config.DB_TEMP_TABLE_PREFIX}{table_name}"
        with self._engine.connect() as conn:
            # Garante que as colunas existam no banco antes do UPSERT
            data.to_sql(name=temp_table_name, con=conn, if_exists="replace", index=False)
            
            cols = ", ".join([f'"{c}"' for c in data.columns])
            pk_cols_str = ", ".join([f'"{c}"' for c in pk_columns])
            update_cols = ", ".join([f'"{c}" = EXCLUDED."{c}"' for c in data.columns if c not in pk_columns and c != 'created_at'])

            query = f'''
                INSERT INTO "{table_name}" ({cols})
                SELECT {cols} FROM "{temp_table_name}"
                ON CONFLICT ({pk_cols_str}) DO UPDATE SET {update_cols}, "updated_at" = NOW();
            '''
            trans = conn.begin()
            try:
                conn.execute(text(query))
                conn.execute(text(f'DROP TABLE "{temp_table_name}" CASCADE'))
                trans.commit()
            except Exception as e:
                trans.rollback()
                self.logger.error(f"Erro no UPSERT para {table_name}: {e}", exc_info=True)
                raise DatabaseError(f"Erro no UPSERT: {str(e)}") from e

    def _replace_data(self, data: pd.DataFrame, table_name: str, year: str, month: str):
        ref = f"{year}-{month:02d}"
        self.logger.info(f"Substituindo dados em '{table_name}' para o período {ref}.")
        delete_query = text(f"DELETE FROM \"{table_name}\" WHERE TO_CHAR(data_referencia, 'YYYY-MM') = :ref")
        with self._engine.connect() as conn:
            trans = conn.begin()
            try:
                conn.execute(delete_query, {"ref": ref})
                data.to_sql(name=table_name, con=conn, if_exists="append", index=False)
                trans.commit()
            except Exception as e:
                trans.rollback()
                self.logger.error(f"Erro ao substituir dados: {e}", exc_info=True)
                raise DatabaseError(f"Erro ao substituir dados: {str(e)}") from e

    def register_audit_log(self, run_id, data_ref, records, tables):
        query = text(f"INSERT INTO {self.config.DB_TABLE_AUDIT_LOG} (run_id, data_referencia, records_inserted, tables_updated) VALUES (:id, :ref, :rec, :tabs)")
        try:
            with self._engine.connect() as conn:
                trans = conn.begin()
                conn.execute(query, {"id": run_id, "ref": data_ref, "rec": records, "tabs": str(tables)})
                trans.commit()
        except Exception as e:
            self.logger.error(f"Erro ao registrar audit log: {e}")

    def __enter__(self): return self
    def __exit__(self, exc_type, exc_val, exc_tb): self._engine.dispose()
