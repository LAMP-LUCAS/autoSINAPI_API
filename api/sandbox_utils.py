import os

def is_sandbox_mode():
    """Verifica se a execução atual deve ocorrer em modo Sandbox."""
    return os.getenv("AUTOSINAPI_SANDBOX", "false").lower() == "true"

def get_sandbox_table_name(base_name: str):
    """Retorna o nome da tabela com sufixo sandbox se estiver no modo sandbox."""
    if is_sandbox_mode():
        return f"{base_name}_sandbox"
    return base_name
