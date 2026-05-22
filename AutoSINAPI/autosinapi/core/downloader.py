# autosinapi/core/downloader.py

"""
downloader.py: Módulo de Obtenção de Dados do AutoSINAPI.

Este módulo é responsável por abstrair a origem dos arquivos de dados do SINAPI.
Ele fornece uma interface unificada para obter os dados, que podem vir de um
download direto do site da Caixa Econômica Federal ou de um arquivo local
fornecido pelo usuário.

**Classe `Downloader`:**

- **Inicialização:** Recebe um objeto `Config` que contém todos os parâmetros
  necessários para a operação, como a URL base, templates de nome de arquivo,
  tipos de planilha válidos e configurações de timeout.

- **Entradas:**
    - O método principal `get_sinapi_data` pode receber um `file_path`
      opcional. Se fornecido, o módulo lê o arquivo local. Caso contrário,
      ele constrói a URL de download com base nos parâmetros `YEAR`, `MONTH` e
      `TYPE` presentes no objeto `Config`.

- **Transformações/Processos:**
    - **Construção de URL:** Monta a URL completa para o download do arquivo
      `.zip` do SINAPI, utilizando o template e os parâmetros definidos no
      `Config`.
    - **Requisição HTTP:** Gerencia uma sessão `requests` para realizar o
      download do arquivo, tratando exceções de rede (como timeouts ou erros de
      HTTP) de forma robusta.
    - **Leitura Local:** Valida se o arquivo local fornecido existe e se possui
      uma extensão permitida (definida no `Config`).

- **Saídas:**
    - O método `get_sinapi_data` retorna um objeto `BinaryIO` (especificamente
      `io.BytesIO`), que é um stream de bytes do conteúdo do arquivo (seja ele
      baixado ou lido localmente). Este formato é ideal para ser
      consumido pelos próximos estágios do pipeline (como o `unzip` no
      `etl_pipeline.py`) sem a necessidade de salvar arquivos intermediários
      em disco, embora também suporte salvar o arquivo baixado se configurado.
"""

import logging
from io import BytesIO
from pathlib import Path
from typing import BinaryIO, Optional, Union

import requests

from ..config import Config
from ..exceptions import DownloadError


class Downloader:
    """
    Classe responsável por obter os arquivos SINAPI, seja por download ou input direto.
    """

    def __init__(self, config: Config):
        """
        Inicializa o downloader.
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        self._session = requests.Session()
        self.logger.info("Downloader inicializado.")

    def get_sinapi_data(
        self,
        file_path: Optional[Union[str, Path]] = None,
        save_path: Optional[Path] = None,
    ) -> BinaryIO:
        """
        Obtém os dados do SINAPI, seja por download ou arquivo local.
        """
        if file_path:
            self.logger.info("Modo de obtenção: Leitura de arquivo local.")
            return self._read_local_file(file_path)
        
        self.logger.info("Modo de obtenção: Download do servidor SINAPI.")
        return self._download_file(save_path)

    def _read_local_file(self, file_path: Union[str, Path]) -> BinaryIO:
        """Lê um arquivo XLSX local."""
        self.logger.debug(f"Lendo arquivo local em: {file_path}")
        try:
            path = Path(file_path)
            if not path.exists():
                raise FileNotFoundError(f"Arquivo não encontrado: {path}")
            # MODIFICADO: Usa constante do config para as extensões permitidas
            if path.suffix.lower() not in self.config.ALLOWED_LOCAL_FILE_EXTENSIONS:
                raise ValueError(f"Formato inválido. Use arquivos dos tipos: {self.config.ALLOWED_LOCAL_FILE_EXTENSIONS}")
            
            content = BytesIO(path.read_bytes())
            self.logger.info(f"Arquivo local '{path.name}' lido com sucesso.")
            return content
        except Exception as e:
            self.logger.error(f"Erro ao ler o arquivo local '{file_path}': {e}", exc_info=True)
            raise DownloadError(f"Erro ao ler arquivo local: {str(e)}")

    def _download_file(self, save_path: Optional[Path] = None) -> BinaryIO:
        """
        Realiza o download do arquivo SINAPI.
        """
        try:
            url = self._build_url()
            self.logger.info(f"Realizando download de: {url}")
            response = self._session.get(url, timeout=self.config.TIMEOUT)
            response.raise_for_status()

            content = BytesIO(response.content)
            self.logger.info(f"Download de {url} concluído com sucesso ({len(content.getvalue())} bytes).")

            if self.config.is_local_mode and save_path:
                self.logger.debug(f"Salvando arquivo baixado em: {save_path}")
                save_path.write_bytes(response.content)

            return content

        except requests.RequestException as e:
            self.logger.error(f"Falha no download de {url}: {e}", exc_info=True)
            raise DownloadError(f"Erro no download: {str(e)}")

    def _build_url(self) -> str:
        """
        Constrói a URL do arquivo SINAPI com base nas configurações.
        """
        ano = str(self.config.YEAR).zfill(4)
        mes = str(self.config.MONTH).zfill(2)

        tipo = self.config.TYPE.upper()
        if tipo not in self.config.VALID_TYPES:
            raise ValueError(f"Tipo de planilha inválido: {tipo}")

        # MODIFICADO: Usa template do config para o nome do arquivo e extensão
        file_name = self.config.DOWNLOAD_FILENAME_TEMPLATE.format(type=tipo, month=mes, year=ano)
        url = f"{self.config.BASE_URL}/{file_name}{self.config.DOWNLOAD_FILE_EXTENSION}"
        
        self.logger.debug(f"URL construída: {url}")

        return url

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.logger.debug("Fechando sessão HTTP do Downloader.")
        self._session.close()