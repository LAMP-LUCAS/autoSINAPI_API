# autosinapi/core/database.py (versão refatorada)

"""
database.py: Módulo de Interação com o Banco de Dados.

Este módulo encapsula toda a lógica de comunicação com o banco de dados
PostgreSQL. Ele é responsável por criar o esquema de tabelas, inserir os dados
processados e gerenciar as transações, garantindo a integridade e a
consistência dos dados.

**Classe `Database`:**

- **Inicialização:** Recebe um objeto `Config`, do qual extrai todas as
  informações de conexão (host, port, user, password, dbname), o dialeto do
  banco (`postgresql`), e nomes de tabelas, além de outras constantes
  relacionadas ao banco.

- **Entradas:**
    - Recebe DataFrames do Pandas, que são o produto final do módulo `Processor`.
    - Recebe o nome da tabela de destino e uma `policy` (política de
      salvamento) que dita como os dados devem ser inseridos.

- **Transformações/Processos:**
    - **Gerenciamento de Conexão:** Utiliza `SQLAlchemy` para criar e gerenciar
      um pool de conexões com o banco de dados.
    - **Criação de Esquema (`create_tables`):** Executa instruções DDL (Data
      Definition Language) para apagar (DROP) e recriar (CREATE) todas as
      tabelas, views e relacionamentos necessários. O status padrão de um item
      (`ATIVO`) é definido a partir do `Config`.
    - **Políticas de Carga de Dados (`save_data`):**
        - **`append`:** Insere novos registros, ignorando conflitos de chave
          primária. Ideal para dados que não mudam, como histórico.
        - **`upsert`:** Insere novos registros ou atualiza os existentes com base
          na chave primária. Usado para atualizar catálogos de insumos e
          composições.
        - **`replace`:** Remove registros de um período específico (mês/ano)
          antes de inserir os novos dados (não implementado no código fornecido).
    - **Uso de Tabelas Temporárias:** Para operações de `append` e `upsert` em
      larga escala, os dados são primeiro carregados em uma tabela temporária
      (com prefixo definido no `Config`) e depois transferidos para a tabela
      final com uma única instrução SQL, garantindo melhor desempenho e
      atomicidade.

- **Saídas:**
    - A classe não retorna dados, mas modifica o estado do banco de dados,
      populando-o com as informações processadas do SINAPI.
    - Levanta exceções (`DatabaseError`) em caso de falhas de conexão ou
      execução de queries para que o pipeline possa tratar o erro.
"""

import logging
import json
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
            created_at TIMESTAMPTZ DEFAULT NOW(), updated_at TIMESTAMPTZ DEFAULT NOW(), sinapi_versao VARCHAR(20), etl_run_id UUID
        );
        CREATE TABLE {self.config.DB_TABLE_COMPOSICOES} (
            codigo INTEGER PRIMARY KEY, descricao TEXT NOT NULL, unidade VARCHAR, grupo VARCHAR, status VARCHAR DEFAULT '{self.config.DB_DEFAULT_ITEM_STATUS}',
            created_at TIMESTAMPTZ DEFAULT NOW(), updated_at TIMESTAMPTZ DEFAULT NOW(), sinapi_versao VARCHAR(20), etl_run_id UUID
        );
        CREATE TABLE {self.config.DB_TABLE_INSUMOS_FAMILIAS} (
            codigo_familia INTEGER NOT NULL, insumo_codigo INTEGER NOT NULL, categoria VARCHAR(50),
            created_at TIMESTAMPTZ DEFAULT NOW(), updated_at TIMESTAMPTZ DEFAULT NOW(), sinapi_versao VARCHAR(20), etl_run_id UUID,
            PRIMARY KEY (codigo_familia, insumo_codigo),
            FOREIGN KEY (insumo_codigo) REFERENCES {self.config.DB_TABLE_INSUMOS}(codigo) ON DELETE CASCADE
        );
        CREATE TABLE {self.config.DB_TABLE_COEFICIENTES_FAMILIA} (
            insumo_codigo INTEGER NOT NULL, uf CHAR(2) NOT NULL, data_referencia DATE NOT NULL, coeficiente NUMERIC,
            created_at TIMESTAMPTZ DEFAULT NOW(), updated_at TIMESTAMPTZ DEFAULT NOW(), sinapi_versao VARCHAR(20), etl_run_id UUID,
            PRIMARY KEY (insumo_codigo, uf, data_referencia),
            FOREIGN KEY (insumo_codigo) REFERENCES {self.config.DB_TABLE_INSUMOS}(codigo) ON DELETE CASCADE
        );
        CREATE TABLE {self.config.DB_TABLE_COMPOSICOES_MIX_MO} (
            composicao_codigo INTEGER NOT NULL, uf CHAR(2) NOT NULL, data_referencia DATE NOT NULL, porcentagem_mo NUMERIC,
            created_at TIMESTAMPTZ DEFAULT NOW(), updated_at TIMESTAMPTZ DEFAULT NOW(), sinapi_versao VARCHAR(20), etl_run_id UUID,
            PRIMARY KEY (composicao_codigo, uf, data_referencia),
            FOREIGN KEY (composicao_codigo) REFERENCES {self.config.DB_TABLE_COMPOSICOES}(codigo) ON DELETE CASCADE
        );
        CREATE TABLE {self.config.DB_TABLE_PRECOS_INSUMOS} (
            insumo_codigo INTEGER NOT NULL, uf CHAR(2) NOT NULL, data_referencia DATE NOT NULL, regime VARCHAR NOT NULL, preco_mediano NUMERIC, origem_preco VARCHAR(10),
            created_at TIMESTAMPTZ DEFAULT NOW(), updated_at TIMESTAMPTZ DEFAULT NOW(), sinapi_versao VARCHAR(20), etl_run_id UUID,
            PRIMARY KEY (insumo_codigo, uf, data_referencia, regime),
            FOREIGN KEY (insumo_codigo) REFERENCES {self.config.DB_TABLE_INSUMOS}(codigo) ON DELETE CASCADE
        );
        CREATE TABLE {self.config.DB_TABLE_CUSTOS_COMPOSICOES} (
            composicao_codigo INTEGER NOT NULL, uf CHAR(2) NOT NULL, data_referencia DATE NOT NULL, regime VARCHAR NOT NULL, custo_total NUMERIC, percentual_mo NUMERIC,
            created_at TIMESTAMPTZ DEFAULT NOW(), updated_at TIMESTAMPTZ DEFAULT NOW(), sinapi_versao VARCHAR(20), etl_run_id UUID,
            PRIMARY KEY (composicao_codigo, uf, data_referencia, regime),
            FOREIGN KEY (composicao_codigo) REFERENCES {self.config.DB_TABLE_COMPOSICOES}(codigo) ON DELETE CASCADE
        );
        CREATE TABLE {self.config.DB_TABLE_COMPOSICAO_INSUMOS} (
            composicao_pai_codigo INTEGER NOT NULL, insumo_filho_codigo INTEGER NOT NULL, coeficiente NUMERIC,
            created_at TIMESTAMPTZ DEFAULT NOW(), updated_at TIMESTAMPTZ DEFAULT NOW(), sinapi_versao VARCHAR(20), etl_run_id UUID,
            PRIMARY KEY (composicao_pai_codigo, insumo_filho_codigo),
            FOREIGN KEY (composicao_pai_codigo) REFERENCES {self.config.DB_TABLE_COMPOSICOES}(codigo) ON DELETE CASCADE,
            FOREIGN KEY (insumo_filho_codigo) REFERENCES {self.config.DB_TABLE_INSUMOS}(codigo) ON DELETE CASCADE
        );
        CREATE TABLE {self.config.DB_TABLE_COMPOSICAO_SUBCOMPOSICOES} (
            composicao_pai_codigo INTEGER NOT NULL, composicao_filho_codigo INTEGER NOT NULL, coeficiente NUMERIC,
            created_at TIMESTAMPTZ DEFAULT NOW(), updated_at TIMESTAMPTZ DEFAULT NOW(), sinapi_versao VARCHAR(20), etl_run_id UUID,
            PRIMARY KEY (composicao_pai_codigo, composicao_filho_codigo),
            FOREIGN KEY (composicao_pai_codigo) REFERENCES {self.config.DB_TABLE_COMPOSICOES}(codigo) ON DELETE CASCADE,
            FOREIGN KEY (composicao_filho_codigo) REFERENCES {self.config.DB_TABLE_COMPOSICOES}(codigo) ON DELETE CASCADE
        );
        CREATE TABLE {self.config.DB_TABLE_MANUTENCOES} (
            item_codigo INTEGER NOT NULL, tipo_item VARCHAR NOT NULL, data_referencia DATE NOT NULL, tipo_manutencao TEXT NOT NULL, descricao_item TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW(), updated_at TIMESTAMPTZ DEFAULT NOW(), sinapi_versao VARCHAR(20), etl_run_id UUID,
            PRIMARY KEY (item_codigo, tipo_item, data_referencia, tipo_manutencao)
        );
        CREATE TABLE {self.config.DB_TABLE_AUDIT_LOG} (
            id BIGSERIAL PRIMARY KEY, table_name VARCHAR(100) NOT NULL, record_pk JSONB NOT NULL, operation VARCHAR(10) NOT NULL,
            old_values JSONB, new_values JSONB, sinapi_versao VARCHAR(20), etl_run_id UUID, motivo_manutencao VARCHAR(200),
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
        CREATE INDEX idx_audit_table_name ON {self.config.DB_TABLE_AUDIT_LOG}(table_name);
        CREATE INDEX idx_audit_created_at ON {self.config.DB_TABLE_AUDIT_LOG}(created_at);
        CREATE INDEX idx_audit_etl_run ON {self.config.DB_TABLE_AUDIT_LOG}(etl_run_id);
        CREATE INDEX idx_insumos_updated_at ON {self.config.DB_TABLE_INSUMOS}(updated_at);
        CREATE INDEX idx_composicoes_updated_at ON {self.config.DB_TABLE_COMPOSICOES}(updated_at);
        CREATE INDEX idx_precos_updated_at ON {self.config.DB_TABLE_PRECOS_INSUMOS}(updated_at);
        CREATE INDEX idx_custos_updated_at ON {self.config.DB_TABLE_CUSTOS_COMPOSICOES}(updated_at);
        CREATE INDEX idx_manutencoes_data ON {self.config.DB_TABLE_MANUTENCOES}(data_referencia);
        CREATE OR REPLACE VIEW vw_composicao_itens_unificados AS
        SELECT composicao_pai_codigo, insumo_filho_codigo AS item_codigo, '{self.config.ITEM_TYPE_INSUMO}' AS tipo_item, coeficiente FROM {self.config.DB_TABLE_COMPOSICAO_INSUMOS}
        UNION ALL
        SELECT composicao_pai_codigo, composicao_filho_codigo AS item_codigo, '{self.config.ITEM_TYPE_COMPOSICAO}' AS tipo_item, coeficiente FROM {self.config.DB_TABLE_COMPOSICAO_SUBCOMPOSICOES};
        """
        trans = None 
        try:
            with self._engine.connect() as conn:
                trans = conn.begin()
                self.logger.info("Recriando o esquema do banco de dados...")
                for stmt in drop_statements.split(";"):
                    if stmt.strip(): conn.execute(text(stmt))
                for stmt in ddl.split(";"):
                    if stmt.strip(): conn.execute(text(stmt))
                trans.commit()
            self.logger.info("Esquema do banco de dados recriado com sucesso.")
        except Exception as e:
            if trans: 
                trans.rollback()
            self.logger.error(f"Erro ao recriar tabelas: {e}", exc_info=True)
            raise DatabaseError(f"Erro ao recriar as tabelas: {str(e)}") from e

    def save_data(self, data: pd.DataFrame, table_name: str, policy: str, **kwargs):
        if data.empty:
            self.logger.warning(f"DataFrame para a tabela '{table_name}' está vazio. Nenhum dado será salvo.")
            return

        self.logger.info(f"Salvando dados na tabela '{table_name}' com política '{policy.upper()}'.")
        
        # Propagar traceability fields
        sinapi_versao = kwargs.get("sinapi_versao")
        etl_run_id = kwargs.get("etl_run_id")
        
        # Add columns if they don't exist, always propagate values
        if sinapi_versao:
            data["sinapi_versao"] = sinapi_versao
        if etl_run_id:
            data["etl_run_id"] = etl_run_id
        if "created_at" not in data.columns:
            data["created_at"] = None
        if "updated_at" not in data.columns:
            data["updated_at"] = None
        
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
        else:
            raise DatabaseError(f"Política de duplicatas desconhecida: {policy}")

    def _append_data(self, data: pd.DataFrame, table_name: str, **kwargs):
        self.logger.info(f"Inserindo/atualizando {len(data)} registros em '{table_name}' (política: upsert-on-append).")
        temp_table_name = f"{self.config.DB_TEMP_TABLE_PREFIX}{table_name}"
        with self._engine.connect() as conn:
            data.to_sql(name=temp_table_name, con=conn, if_exists="replace", index=False)
            pk_cols_query = text(f"""
                SELECT a.attname FROM pg_index i
                JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
                WHERE i.indrelid = '{table_name}'::regclass AND i.indisprimary;
            """)
            trans = conn.begin()
            try:
                pk_cols_result = conn.execute(pk_cols_query).fetchall()
                if not pk_cols_result:
                    raise DatabaseError(f"Nenhuma chave primária encontrada para a tabela {table_name}.")
                
                pk_cols = [row[0] for row in pk_cols_result]
                pk_cols_str = ", ".join(pk_cols)
                cols = ", ".join([f'\"{c}\"' for c in data.columns])
                
                # UPSERT: Insert or Update on conflict
                update_cols = ", ".join([
                    f'\"{c}\" = EXCLUDED.\"{c}\"' 
                    for c in data.columns 
                    if c not in pk_cols
                ])
                if update_cols:
                    update_cols += f', "updated_at" = NOW()'
                
                insert_query = f'''
                    INSERT INTO \"{table_name}\" ({cols})
                    SELECT {cols} FROM \"{temp_table_name}\" 
                    ON CONFLICT ({pk_cols_str}) DO UPDATE SET {update_cols};
                '''
                conn.execute(text(insert_query))
                conn.execute(text(f'DROP TABLE "{temp_table_name}" CASCADE'))
                trans.commit()
            except Exception as e:
                trans.rollback()
                self.logger.error(f"Erro ao inserir dados em {table_name}: {e}", exc_info=True)
                raise DatabaseError(f"Erro ao inserir dados em {table_name}: {str(e)}") from e

    def _replace_data(self, data: pd.DataFrame, table_name: str, year: str, month: str):
        self.logger.info(f"Substituindo dados em '{table_name}' para o período {year}-{month}.")
        delete_query = text(f'DELETE FROM "{table_name}" WHERE TO_CHAR(data_referencia, \'YYYY-MM\') = :ref')
        with self._engine.connect() as conn:
            trans = conn.begin()
            try:
                conn.execute(delete_query, {"ref": f"{year}-{month}"})
                data.to_sql(name=table_name, con=conn, if_exists="append", index=False)
                trans.commit()
            except Exception as e:
                trans.rollback()
                self.logger.error(f"Erro ao substituir dados em {table_name}: {e}", exc_info=True)
                raise DatabaseError(f"Erro ao substituir dados: {str(e)}") from e

    def _upsert_data(self, data: pd.DataFrame, table_name: str, pk_columns: list):
        self.logger.info(f"Executando UPSERT de {len(data)} registros em '{table_name}'.")
        temp_table_name = f"{self.config.DB_TEMP_TABLE_PREFIX}{table_name}"
        with self._engine.connect() as conn:
            data.to_sql(name=temp_table_name, con=conn, if_exists="replace", index=False)
            cols = ", ".join([f'\"{c}\"' for c in data.columns])
            pk_cols_str = ", ".join(pk_columns)
            update_cols = ", ".join([f'\"{c}\" = EXCLUDED.\"{c}\"' for c in data.columns if c not in pk_columns])
            
            if not update_cols:
                self._append_data(data, table_name)
                return

            query = f'''
                INSERT INTO \"{table_name}\" ({cols})
                SELECT {cols} FROM \"{temp_table_name}\" 
                ON CONFLICT ({pk_cols_str}) DO UPDATE SET {update_cols};
            '''
            trans = conn.begin()
            try:
                conn.execute(text(query))
                conn.execute(text(f'DROP TABLE "{temp_table_name}" CASCADE'))
                trans.commit()
            except Exception as e:
                trans.rollback()
                self.logger.error(f"Erro no UPSERT para {table_name}: {e}", exc_info=True)
                raise DatabaseError(f"Erro no UPSERT para {table_name}: {str(e)}") from e

    def truncate_table(self, table_name: str):
        self.logger.info(f"Limpando tabela: {table_name}")
        query = f'TRUNCATE TABLE "{table_name}" RESTART IDENTITY CASCADE'
        try:
            with self._engine.connect() as conn:
                trans = conn.begin()
                conn.execute(text(query))
                trans.commit()
        except Exception as e:
            trans.rollback()
            self.logger.error(f"Falha ao truncar tabela {table_name}. Query: '{query}'", exc_info=True)
            raise DatabaseError(f"Erro ao truncar a tabela {table_name}: {str(e)}") from e

    def execute_query(self, query: str, params: Dict[str, Any] = None) -> pd.DataFrame:
        try:
            with self._engine.connect() as conn:
                result = conn.execute(text(query), params or {})
                return pd.DataFrame(result.fetchall(), columns=result.keys())
        except Exception as e:
            self.logger.error(f"Erro ao executar query. Query: '{query}'", exc_info=True)
            raise DatabaseError(f"Erro ao executar query: {str(e)}") from e

    def execute_non_query(self, query: str, params: Dict[str, Any] = None) -> int:
        try:
            with self._engine.connect() as conn:
                trans = conn.begin()
                result = conn.execute(text(query), params or {})
                trans.commit()
                return result.rowcount
        except Exception as e:
            trans.rollback()
            self.logger.error(f"Erro ao executar non-query. Query: '{query}'", exc_info=True)
            raise DatabaseError(f"Erro ao executar non-query: {str(e)}") from e

    def _log_audit_event(self, table_name: str, record_pk: dict, operation: str, 
                         old_values: dict = None, new_values: dict = None,
                         sinapi_versao: str = None, etl_run_id: str = None,
                         motivo_manutencao: str = None):
        """Registra evento no sinapi_audit_log."""
        audit_table = self.config.DB_TABLE_AUDIT_LOG
        query = text(f"""
            INSERT INTO {audit_table}
            (table_name, record_pk, operation, old_values, new_values, 
             sinapi_versao, etl_run_id, motivo_manutencao)
            VALUES (:table_name, :record_pk, :operation, :old_values, :new_values,
                    :sinapi_versao, :etl_run_id, :motivo_manutencao)
        """)
        params = {
            "table_name": table_name,
            "record_pk": json.dumps(record_pk),
            "operation": operation,
            "old_values": json.dumps(old_values) if old_values else None,
            "new_values": json.dumps(new_values) if new_values else None,
            "sinapi_versao": sinapi_versao,
            "etl_run_id": etl_run_id,
            "motivo_manutencao": motivo_manutencao,
        }
        try:
            with self._engine.connect() as conn:
                trans = conn.begin()
                conn.execute(query, params)
                trans.commit()
        except Exception as e:
            self.logger.error(f"Erro ao registrar audit log: {e}", exc_info=True)
            # Não levanta exceção para não quebrar o pipeline principal

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._engine.dispose()