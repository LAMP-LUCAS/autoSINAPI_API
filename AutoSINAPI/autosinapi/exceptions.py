"""
Módulo de exceções customizadas para o AutoSINAPI.

Este arquivo define uma hierarquia de exceções customizadas para o projeto.
O uso de exceções específicas para cada tipo de erro (Configuração, Download,
Processamento, Banco de Dados) permite um tratamento de erros mais granular
e robusto por parte das aplicações que consomem este toolkit.

A exceção base `AutoSinapiError` garante que todos os erros gerados pela
biblioteca possam ser capturados de forma unificada, se necessário.
"""


class AutoSinapiError(Exception):
    """Exceção base para todos os erros do AutoSINAPI."""

    pass


class ConfigurationError(AutoSinapiError):
    """Erro relacionado a configurações inválidas."""

    pass


class DownloadError(AutoSinapiError):
    """Erro durante o download de arquivos."""

    pass


class ProcessingError(AutoSinapiError):
    """Erro durante o processamento dos dados."""

    pass


class DatabaseError(AutoSinapiError):
    """Erro relacionado a operações de banco de dados."""

    pass
