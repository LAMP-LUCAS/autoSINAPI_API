# autosinapi/core/processor.py

"""
processor.py: Módulo de Transformação de Dados do AutoSINAPI.

Este módulo é o coração da lógica de transformação do pipeline. Ele é
responsável por converter os dados brutos das planilhas Excel do SINAPI,
obtidas pelo `downloader`, em um conjunto de DataFrames estruturados, limpos e
prontos para serem carregados no banco de dados.

**Classe `Processor`:**

- **Inicialização:** Recebe um objeto `Config`, que fornece acesso a todas as
  constantes de negócio necessárias para a interpretação dos arquivos, como
  palavras-chave para encontrar cabeçalhos, nomes de colunas, mapas de planilhas,
  números de linha fixos e expressões regulares.

- **Entradas:**
    - Recebe os caminhos (`xlsx_path`) para os arquivos Excel de "Manutenções"
      e "Referência" descompactados.

- **Transformações/Processos:**
    - **Busca Dinâmica de Cabeçalho:** Implementa uma função (`_find_header_row`)
      para localizar a linha inicial de uma tabela dentro de uma planilha com base
      em um conjunto de palavras-chave, tornando o processo resiliente a pequenas
      mudanças de layout.
    - **Leitura e Limpeza:** Lê as planilhas (tanto Excel quanto CSVs
      pré-processados) e aplica uma série de limpezas: normalização de nomes
      de colunas, padronização de tipos de dados e tratamento de valores
      ausentes.
    - **Unpivot:** Transforma tabelas de preços e custos, que originalmente têm
      os estados (UFs) como colunas, para um formato "longo" (tidy data), com
      uma única coluna para "uf" e outra para o valor (preço ou custo).
    - **Extração de Catálogos:** Extrai os catálogos de insumos e composições
      a partir de múltiplas planilhas de preços e custos, consolidando-os em
      DataFrames únicos e sem duplicatas.
    - **Extração de Estrutura:** Processa a complexa planilha "Analítico" para
      mapear as relações pai-filho entre composições, insumos e
      subcomposições, gerando os dados para as tabelas de relacionamento.

- **Saídas:**
    - O método `process_manutencoes` retorna um único DataFrame com o histórico
      de manutenções.
    - O método `process_catalogo_e_precos` retorna um dicionário de DataFrames
      contendo os catálogos (`insumos`, `composicoes`) e os dados mensais
      (`precos_insumos_mensal`, `custos_composicoes_mensal`).
    - O método `process_composicao_itens` retorna um dicionário de DataFrames
      com os relacionamentos (`composicao_insumos`, `composicao_subcomposicoes`)
      e detalhes extraídos da estrutura analítica.
"""

import logging
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pandas as pd

from ..config import Config
from ..exceptions import ProcessingError


class Processor:
    def __init__(self, config: Config):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.logger.info("Processador inicializado.")

    def _find_header_row(self, df: pd.DataFrame, keywords: List[str]) -> int:
        self.logger.debug(f"Procurando cabeçalho com keywords: {keywords}")

        def normalize_text(text_val):
            s = str(text_val).strip()
            s = "".join(
                c
                for c in unicodedata.normalize("NFD", s)
                if unicodedata.category(c) != "Mn"
            )
            s = re.sub(
                r"[^A-Z0-9_]", "", s.upper().replace(" ", "_").replace("\n", "_")
            )
            return s

        for i, row in df.iterrows():
            if i > self.config.HEADER_SEARCH_LIMIT:
                self.logger.warning(
                    f"Limite de busca por cabeçalho ({self.config.HEADER_SEARCH_LIMIT} linhas)"
                    f" atingido em {keywords}. Cabeçalho não encontrado."
                )
                break

            try:
                row_values = [
                    str(cell) if pd.notna(cell) else "" for cell in row.values
                ]
                normalized_row_values = [normalize_text(cell) for cell in row_values]
                row_str = " ".join(normalized_row_values)
                normalized_keywords = [normalize_text(k) for k in keywords]

                self.logger.debug(f"Linha {i} normalizada para busca: {row_str}")

                if all(nk in row_str for nk in normalized_keywords):
                    self.logger.info(f"Cabeçalho encontrado na linha {i} para {keywords}.")
                    return i
            except Exception as e:
                self.logger.error(
                    f"Erro ao processar a linha {i} para encontrar o cabeçalho: {e}",
                    exc_info=True,
                )
                continue

        self.logger.error(f"Cabeçalho com as keywords {keywords} não foi encontrado.")
        return None

    def _normalize_cols(self, df: pd.DataFrame) -> pd.DataFrame:
        self.logger.debug("Normalizando nomes das colunas...")
        new_cols = {}
        for col in df.columns:
            s = str(col).strip()
            s = "".join(
                c
                for c in unicodedata.normalize("NFD", s)
                if unicodedata.category(c) != "Mn"
            )
            s = s.upper()
            s = re.sub(r"[\s\n]+", "_", s)
            s = re.sub(r"[^A-Z0-9_]", "", s)
            new_cols[col] = s

        self.logger.debug(f"Mapeamento de colunas normalizadas: {new_cols}")
        return df.rename(columns=new_cols)

    def _unpivot_data(
        self, df: pd.DataFrame, id_vars: List[str], value_name: str
    ) -> pd.DataFrame:
        self.logger.debug(f"Iniciando unpivot para '{value_name}' com id_vars: {id_vars}")

        uf_cols = [
            col for col in df.columns if len(str(col)) == 2 and str(col).isalpha()
        ]
        if not uf_cols:
            self.logger.warning(
                f"Nenhuma coluna de UF foi identificada para o unpivot"
                f" na planilha de {value_name}. O DataFrame pode ficar vazio."
            )
            return pd.DataFrame(columns=id_vars + ["uf", value_name])

        self.logger.debug(f"Colunas de UF identificadas para unpivot: {uf_cols}")

        long_df = df.melt(
            id_vars=id_vars, value_vars=uf_cols, var_name="uf", value_name=value_name
        )
        long_df = long_df.dropna(subset=[value_name])
        long_df[value_name] = pd.to_numeric(long_df[value_name], errors="coerce")

        self.logger.debug(f"DataFrame após unpivot. Head:\n{long_df.head().to_string()}")
        return long_df

    def _standardize_id_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        self.logger.debug("Padronizando colunas de ID (CODIGO, DESCRICAO)...")
        rename_map = self.config.ID_COL_STANDARDIZE_MAP
        actual_rename_map = {k: v for k, v in rename_map.items() if k in df.columns}
        if actual_rename_map:
            self.logger.debug(f"Mapeamento de renomeação de ID aplicado: {actual_rename_map}")
        return df.rename(columns=actual_rename_map)

    def process_manutencoes(self, xlsx_path: str) -> pd.DataFrame:
        self.logger.info(f"Processando arquivo de manutenções: {xlsx_path}")
        try:
            df_raw = pd.read_excel(xlsx_path, sheet_name=self.config.MANUTENCOES_SHEET_INDEX, header=None)
            header_row = self._find_header_row(
                df_raw, self.config.MANUTENCOES_HEADER_KEYWORDS
            )
            if header_row is None:
                raise ProcessingError(
                    f"Cabeçalho não encontrado no arquivo de manutenções: {xlsx_path}"
                )
            
            df = pd.read_excel(xlsx_path, sheet_name=self.config.MANUTENCOES_SHEET_INDEX, header=header_row)
            df = self._normalize_cols(df)

            col_map = self.config.MANUTENCOES_COL_MAP
            df = df.rename(
                columns={k: v for k, v in col_map.items() if k in df.columns}
            )
            
            df["data_referencia"] = pd.to_datetime(
                df["data_referencia"], errors="coerce", format=self.config.MANUTENCOES_DATE_FORMAT
            ).dt.date
            df["item_codigo"] = pd.to_numeric(
                df["item_codigo"], errors="coerce"
            ).astype("Int64")
            df["tipo_item"] = df["tipo_item"].str.upper().str.strip()
            df["tipo_manutencao"] = df["tipo_manutencao"].str.upper().str.strip()

            self.logger.info("Processamento de manutenções concluído com sucesso.")
            return df[list(col_map.values())]
        except Exception as e:
            self.logger.error(
                f"Falha crítica ao processar arquivo de manutenções. Erro: {e}",
                exc_info=True,
            )
            raise ProcessingError(f"Erro em 'process_manutencoes': {e}") from e

    def process_composicao_itens(self, xlsx_path: str) -> Dict[str, pd.DataFrame]:
        self.logger.info(f"Processando estrutura de itens de composição de: {xlsx_path}")
        try:
            xls = pd.ExcelFile(xlsx_path)
            sheet_SINAPI_name = next((
                s for s in xls.sheet_names if self.config.COMPOSICAO_ITENS_SHEET_KEYWORD in s and self.config.COMPOSICAO_ITENS_SHEET_EXCLUDE_KEYWORD not in s
            ), None)
            if not sheet_SINAPI_name:
                raise ProcessingError(
                    f"Aba '{self.config.COMPOSICAO_ITENS_SHEET_KEYWORD}' não encontrada no arquivo: {xlsx_path}"
                )

            self.logger.info(f"Lendo aba de composição: {sheet_SINAPI_name}")
            df = pd.read_excel(xlsx_path,
                               sheet_name=sheet_SINAPI_name,
                               header=self.config.COMPOSICAO_ITENS_HEADER_ROW
                               )
            df = self._normalize_cols(df)

            cols = self.config.ORIGINAL_COLS
            subitens = df[
                df[cols["TIPO_ITEM"]].str.upper().isin([
                        self.config.ITEM_TYPE_INSUMO,
                        self.config.ITEM_TYPE_COMPOSICAO
                        ])
            ].copy()

            subitens["composicao_pai_codigo"] = pd.to_numeric(
                subitens[cols["CODIGO_COMPOSICAO"]], errors="coerce"
            ).astype("Int64")
            subitens["item_codigo"] = pd.to_numeric(
                subitens[cols["CODIGO_ITEM"]], errors="coerce"
            ).astype("Int64")
            subitens["tipo_item"] = subitens[cols["TIPO_ITEM"]].str.upper().str.strip()
            subitens["coeficiente"] = pd.to_numeric(
                subitens[cols["COEFICIENTE"]].astype(str).str.replace(",", "."),
                errors="coerce",
            )
            subitens.rename(
                columns={
                    cols["DESCRICAO_ITEM"]: "item_descricao", 
                    cols["UNIDADE_ITEM"]: "item_unidade"
                },
                inplace=True,
            )

            subitens.dropna(
                subset=["composicao_pai_codigo", "item_codigo", "tipo_item"],
                inplace=True,
            )
            subitens = subitens.drop_duplicates(
                subset=["composicao_pai_codigo", "item_codigo", "tipo_item"]
            )

            insumos_df = subitens[
                subitens["tipo_item"] == self.config.ITEM_TYPE_INSUMO
                ]
            composicoes_df = subitens[
                subitens["tipo_item"] == self.config.ITEM_TYPE_COMPOSICAO
                ]

            self.logger.info(
                f"Encontrados {len(insumos_df)} links insumo-composição"
                f" e {len(composicoes_df)} links subcomposição-composição."
            )

            composicao_insumos = insumos_df[
                ["composicao_pai_codigo", "item_codigo", "coeficiente"]
            ].rename(columns={"item_codigo": "insumo_filho_codigo"})
            composicao_subcomposicoes = composicoes_df[
                ["composicao_pai_codigo", "item_codigo", "coeficiente"]
            ].rename(columns={"item_codigo": "composicao_filho_codigo"})

            parent_composicoes_df = df[
                df[cols["CODIGO_COMPOSICAO"]].notna()
                & ~df[
                    cols["TIPO_ITEM"]].str.upper().isin([
                        self.config.ITEM_TYPE_INSUMO,
                        self.config.ITEM_TYPE_COMPOSICAO
                        ])
            ].copy()
            parent_composicoes_df = parent_composicoes_df.rename(
                columns={
                    cols["CODIGO_COMPOSICAO"]: "codigo",
                    cols["DESCRICAO_ITEM"]: "descricao",
                    cols["UNIDADE_ITEM"]: "unidade",
                    cols["GRUPO_COMPOSICAO"]: "grupo",
                }
            )
            parent_composicoes_df = parent_composicoes_df[
                ["codigo", "descricao", "unidade", "grupo"]
            ].drop_duplicates(subset=["codigo"])

            child_item_details = subitens[
                ["item_codigo", "tipo_item", "item_descricao", "item_unidade"]
            ].copy()
            child_item_details.rename(
                columns={
                    "item_codigo": "codigo",
                    "tipo_item": "tipo",
                    "item_descricao": "descricao",
                    "item_unidade": "unidade",
                },
                inplace=True,
            )
            child_item_details = child_item_details.drop_duplicates(
                subset=["codigo", "tipo"]
            )

            return {
                self.config.DB_TABLE_COMPOSICAO_INSUMOS: composicao_insumos,
                self.config.DB_TABLE_COMPOSICAO_SUBCOMPOSICOES: composicao_subcomposicoes,
                "parent_composicoes_details": parent_composicoes_df,
                "child_item_details": child_item_details,
            }
        except Exception as e:
            self.logger.error(
                f"Falha crítica ao processar estrutura de composições. Erro: {e}",
                exc_info=True,
            )
            raise ProcessingError(f"Erro em 'process_composicao_itens': {e}") from e

    def _process_precos_sheet(
        self, xls: pd.ExcelFile, sheet_name: str
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        self.logger.debug(f"Processando aba de preços: {sheet_name}")
        try:
            df = pd.read_excel(xls, sheet_name=sheet_name, header=self.config.PRECOS_HEADER_ROW)
            df = self._normalize_cols(df)
            df = self._standardize_id_columns(df)

            catalogo_df = pd.DataFrame()
            if "CODIGO" in df.columns and "DESCRICAO" in df.columns:
                cols_catalogo = ["CODIGO", "DESCRICAO", "UNIDADE"]
                if "CLASSIFICACAO" in df.columns:
                    cols_catalogo.append("CLASSIFICACAO")
                catalogo_df = df[cols_catalogo].copy()
                self.logger.debug(f"Extraídos {len(catalogo_df)} registros de catálogo da aba {sheet_name}.")
            
            id_vars = ["CODIGO"]
            if "ORIGEM_DE_PRECO" in df.columns:
                id_vars.append("ORIGEM_DE_PRECO")

            long_df = self._unpivot_data(df, id_vars, self.config.UNPIVOT_VALUE_PRECO)
            self.logger.debug(f"Extraídos {len(long_df)} registros de preços da aba {sheet_name}.")
            return long_df, catalogo_df
        except Exception as e:
            self.logger.error(f"Erro ao processar aba de preços '{sheet_name}': {e}", exc_info=True)
            raise ProcessingError(f"Erro em '_process_precos_sheet': {e}") from e

    def _process_custos_sheet(
        self, xlsx_path: str, process_key: str
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        csv_dir = Path(xlsx_path).parent.parent / self.config.TEMP_CSV_DIR
        csv_path = csv_dir / f"{process_key}.csv"
        self.logger.info(f"Lendo dados de custo do arquivo CSV pré-processado: {csv_path}")
        if not csv_path.exists():
            raise FileNotFoundError(f"Arquivo CSV de custos não encontrado: {csv_path}.")

        try:
            df_raw = pd.read_csv(csv_path, header=None, low_memory=False, sep=";")
            header_row = self._find_header_row(
                df_raw, self.config.CUSTOS_HEADER_KEYWORDS
            )
            if header_row is None:
                self.logger.warning(f"Cabeçalho não encontrado em {csv_path.name}. Pulando.")
                return pd.DataFrame(), pd.DataFrame()

            header_df = df_raw.iloc[header_row - 1 : header_row + 1].copy()

            def clean_level0(val):
                s_val = str(val)
                return s_val if len(s_val) == 2 and s_val.isalpha() else pd.NA

            header_df.iloc[0] = header_df.iloc[0].apply(clean_level0).ffill()
            new_cols = [
                f"{h0}_{h1}" if pd.notna(h0) else str(h1)
                for h0, h1 in zip(header_df.iloc[0], header_df.iloc[1])
            ]
            df = df_raw.iloc[header_row + 1 :].copy()
            df.columns = new_cols
            df.dropna(how="all", inplace=True)

            df = self._normalize_cols(df)
            df = self._standardize_id_columns(df)
            if "CODIGO" in df.columns:
                df["CODIGO"] = df["CODIGO"].astype(str).str.extract(self.config.CUSTOS_CODIGO_REGEX)[0]
                df["CODIGO"] = pd.to_numeric(df["CODIGO"], errors="coerce")
                df.dropna(subset=["CODIGO"], inplace=True)
                if not df.empty:
                    df["CODIGO"] = df["CODIGO"].astype("Int64")

            catalogo_df = pd.DataFrame()
            if "CODIGO" in df.columns and "DESCRICAO" in df.columns:
                cols_catalogo = ["CODIGO", "DESCRICAO", "UNIDADE"]
                if "GRUPO" in df.columns:
                    cols_catalogo.append("GRUPO")
                catalogo_df = df[cols_catalogo].copy()

            cost_cols = {
                col.split("_")[0]: col
                for col in df.columns
                if "CUSTO" in col and len(col.split("_")[0]) == 2
            }
            if "CODIGO" in df.columns and cost_cols:
                df_costs = df[["CODIGO"] + list(cost_cols.values())].copy()
                df_costs = df_costs.rename(
                    columns=lambda x: x.split("_")[0] if "CUSTO" in x else x
                )
                long_df = self._unpivot_data(df_costs, ["CODIGO"], self.config.UNPIVOT_VALUE_CUSTO)
                return long_df, catalogo_df

            self.logger.warning(f"Não foi possível extrair custos da aba '{process_key}'.")
            return pd.DataFrame(), pd.DataFrame()
        except Exception as e:
            self.logger.error(f"Erro ao processar aba de custos '{csv_path.name}': {e}", exc_info=True)
            raise ProcessingError(f"Erro em '_process_custos_sheet': {e}") from e

    def _aggregate_final_dataframes(
        self, all_dfs: Dict, temp_insumos: List, temp_composicoes: List
    ) -> Dict:
        self.logger.info("Agregando e finalizando DataFrames...")

        if temp_insumos:
            all_insumos = pd.concat(temp_insumos, ignore_index=True)
            
            # Priorizar linhas com CLASSIFICACAO preenchida
            if "CLASSIFICACAO" in all_insumos.columns:
                # Cria coluna temporária: 1 se tem valor, 0 se é nulo/vazio
                all_insumos["_has_class"] = all_insumos["CLASSIFICACAO"].notnull() & (all_insumos["CLASSIFICACAO"] != "")
                all_insumos.sort_values(by=["CODIGO", "_has_class"], ascending=[True, False], inplace=True)
                all_insumos.drop(columns=["_has_class"], inplace=True)

            all_insumos.drop_duplicates(subset=["CODIGO"], keep="first", inplace=True)
            all_dfs["insumos"] = all_insumos.rename(
                columns=self.config.FINAL_CATALOG_COLUMNS
            )
            self.logger.info(
                f"Catálogo de insumos finalizado com {len(all_insumos)} registros únicos."
            )

        if temp_composicoes:
            all_composicoes = pd.concat(temp_composicoes, ignore_index=True)
            
            # Priorizar linhas com GRUPO preenchido
            if "GRUPO" in all_composicoes.columns:
                all_composicoes["_has_group"] = all_composicoes["GRUPO"].notnull() & (all_composicoes["GRUPO"] != "")
                all_composicoes.sort_values(by=["CODIGO", "_has_group"], ascending=[True, False], inplace=True)
                all_composicoes.drop(columns=["_has_group"], inplace=True)

            all_composicoes.drop_duplicates(subset=["CODIGO"], keep="first", inplace=True)
            all_dfs["composicoes"] = all_composicoes.rename(
                columns=self.config.FINAL_CATALOG_COLUMNS
            )
            self.logger.info(
                f"Catálogo de composições finalizado com {len(all_composicoes)} registros únicos."
            )

        if "precos_insumos_mensal" in all_dfs:
            df_concat = pd.concat(all_dfs["precos_insumos_mensal"], ignore_index=True)
            all_dfs["precos_insumos_mensal"] = df_concat
            self.logger.info(
                f"Tabela de preços mensais finalizada com {len(df_concat)} registros."
            )
        if "custos_composicoes_mensal" in all_dfs:
            df_concat = pd.concat(all_dfs["custos_composicoes_mensal"], ignore_index=True)
            all_dfs["custos_composicoes_mensal"] = df_concat
            self.logger.info(
                f"Tabela de custos mensais finalizada com {len(df_concat)} registros."
            )
        return all_dfs

    def process_catalogo_e_precos(self, xlsx_path: str) -> Dict[str, pd.DataFrame]:
        self.logger.info(
            f"Iniciando processamento completo de catálogos e preços de: {xlsx_path}"
        )
        xls = pd.ExcelFile(xlsx_path)
        all_dfs = {}
        sheet_map = self.config.SHEET_MAP
        temp_insumos, temp_composicoes = [], []

        for sheet_name in xls.sheet_names:
            process_key = next((k for k in sheet_map if k in sheet_name), None)
            if not process_key:
                continue

            try:
                process_type, regime = sheet_map[process_key]
                self.logger.info(
                    f"Processando aba: '{sheet_name}' (tipo: {process_type}, regime: {regime})"
                )

                long_df, catalogo_df = pd.DataFrame(), pd.DataFrame()
                if process_type == "precos":
                    long_df, catalogo_df = self._process_precos_sheet(xls, sheet_name)
                    if not catalogo_df.empty:
                        temp_insumos.append(catalogo_df)
                
                elif process_type == "custos":
                    long_df, catalogo_df = self._process_custos_sheet(
                        xlsx_path, process_key
                    )
                    if not catalogo_df.empty:
                        temp_composicoes.append(catalogo_df)

                if not long_df.empty:
                    long_df["regime"] = regime
                    table, code = (
                        ("precos_insumos_mensal", "insumo_codigo")
                        if process_type == "precos"
                        else ("custos_composicoes_mensal", "composicao_codigo")
                    )
                    long_df.rename(columns={"CODIGO": code, "ORIGEM_DE_PRECO": "origem_preco"}, inplace=True)
                    all_dfs.setdefault(table, []).append(long_df)
                    self.logger.info(f"Dados da aba '{sheet_name}' adicionados à chave '{table}'.")

            except Exception as e:
                self.logger.error(
                    f"Falha CRÍTICA ao processar a aba '{sheet_name}'. Esta aba será ignorada. Erro: {e}",
                    exc_info=True,
                )
        
        return self._aggregate_final_dataframes(all_dfs, temp_insumos, temp_composicoes)

    def process_familias_e_coeficientes(self, xlsx_path: str) -> Dict[str, pd.DataFrame]:
        self.logger.info(f"Processando famílias e coeficientes: {xlsx_path}")
        try:
            df = pd.read_excel(xlsx_path, sheet_name=0, header=4)
            df = self._normalize_cols(df)
            
            # 1. Extração de Famílias
            familias_df = df[["CODIGO_DA_FAMILIA", "CODIGO_DO_INSUMO", "CATEGORIA"]].copy()
            familias_df.rename(columns={
                "CODIGO_DA_FAMILIA": "codigo_familia",
                "CODIGO_DO_INSUMO": "insumo_codigo",
                "CATEGORIA": "categoria"
            }, inplace=True)
            familias_df["insumo_codigo"] = pd.to_numeric(familias_df["insumo_codigo"], errors="coerce").astype("Int64")
            familias_df.dropna(subset=["insumo_codigo"], inplace=True)

            # 2. Extração de Coeficientes (Unpivot UFs)
            coef_df = self._unpivot_data(df, ["CODIGO_DO_INSUMO"], "coeficiente")
            coef_df.rename(columns={"CODIGO_DO_INSUMO": "insumo_codigo"}, inplace=True)
            coef_df["insumo_codigo"] = pd.to_numeric(coef_df["insumo_codigo"], errors="coerce").astype("Int64")
            coef_df.dropna(subset=["insumo_codigo"], inplace=True)

            return {
                "insumos_familias": familias_df,
                "coeficientes_familia_mensal": coef_df
            }
        except Exception as e:
            self.logger.error(f"Erro ao processar famílias e coeficientes: {e}", exc_info=True)
            return {}

    def process_mao_de_obra(self, xlsx_path: str) -> pd.DataFrame:
        self.logger.info(f"Processando porcentagem de mão de obra: {xlsx_path}")
        try:
            # Lemos a aba 'SEM Desoneração' por padrão para SSOT base
            df = pd.read_excel(xlsx_path, sheet_name=0, header=4)
            df = self._normalize_cols(df)
            
            # Unpivot UFs para obter a porcentagem de MO
            long_df = self._unpivot_data(df, ["CODIGO_DA_COMPOSICAO"], "porcentagem_mo")
            long_df.rename(columns={"CODIGO_DA_COMPOSICAO": "composicao_codigo"}, inplace=True)
            long_df["composicao_codigo"] = pd.to_numeric(long_df["composicao_codigo"], errors="coerce").astype("Int64")
            long_df.dropna(subset=["composicao_codigo"], inplace=True)
            
            return long_df
        except Exception as e:
            self.logger.error(f"Erro ao processar mix de mão de obra: {e}", exc_info=True)
            return pd.DataFrame()