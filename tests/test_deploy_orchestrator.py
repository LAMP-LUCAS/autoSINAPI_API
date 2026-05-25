import os
import sys
import tempfile
import pytest
from unittest.mock import patch, MagicMock

# Ajusta o PYTHONPATH para importar o script
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__line__ if '__line__' in locals() else __file__), '../scripts')))
from deploy_orchestrator import DeployOrchestrator

@pytest.fixture
def isolated_env():
    """
    Cria um diretório temporário isolado para atuar como ROOT_DIR.
    Nenhum arquivo real do repositório será tocado.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        # Cria a pasta do Toolkit fake
        os.makedirs(os.path.join(temp_dir, "AutoSINAPI"))
        yield temp_dir

def test_load_config_defaults(isolated_env):
    """Teste Unitário: Garante que os valores padrão são carregados sem um arquivo .config"""
    orchestrator = DeployOrchestrator(isolated_env)
    assert orchestrator.config["OPERATOR_CMD"] == "docker compose up -d --remove-orphans"
    assert orchestrator.config["FORCE_TESTS"] == "true"

def test_load_custom_config(isolated_env):
    """Teste Unitário: Garante que o deploy.config sobrescreve os defaults sem usar regex sujas"""
    config_path = os.path.join(isolated_env, "deploy.config")
    with open(config_path, "w") as f:
        f.write('OPERATOR_CMD="bash dummy_script.sh"\n')
        f.write('FORCE_TESTS=false\n')
    
    orchestrator = DeployOrchestrator(isolated_env)
    assert orchestrator.config["OPERATOR_CMD"] == "bash dummy_script.sh"
    assert orchestrator.config["FORCE_TESTS"] == "false"

@patch('deploy_orchestrator.subprocess.run')
def test_execution_flow_isolation(mock_run, isolated_env):
    """
    Teste de Integração (Isolado): 
    Moca as chamadas de subprocesso para garantir que 'pytest', 'docker compose' 
    e comandos git NÃO sejam executados na máquina real.
    """
    orchestrator = DeployOrchestrator(isolated_env)
    
    # Força modo não interativo
    with patch('sys.stdout.isatty', return_value=False):
        orchestrator.execute()
    
    # Verifica se os passos cruciais foram chamados na ordem correta
    # sem disparar ações reais.
    called_commands = [call.args[0] for call in mock_run.call_args_list]
    
    assert "pytest" in called_commands[0]
    assert "python -m build" in called_commands[1]
    assert orchestrator.config["OPERATOR_CMD"] in called_commands[2]
    assert "alembic upgrade head" in called_commands[3]
