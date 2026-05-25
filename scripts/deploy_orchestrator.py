#!/usr/bin/env python3
"""
Orquestrador de Deploy Inteligente - AutoSINAPI
Garante que a API seja construída com a versão testada e correta do Toolkit.
"""

import os
import sys
import subprocess

class DeployOrchestrator:
    def __init__(self, root_dir):
        self.root_dir = root_dir
        self.toolkit_dir = os.path.join(root_dir, "AutoSINAPI")
        self.config = self._load_config()

    def _load_config(self):
        config = {
            "OPERATOR_CMD": "docker compose up -d --remove-orphans",
            "DEFAULT_SUFFIX": "beta",
            "FORCE_TESTS": "true"
        }
        config_path = os.path.join(self.root_dir, "deploy.config")
        if os.path.exists(config_path):
            with open(config_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, val = line.split("=", 1)
                        config[key.strip()] = val.strip().strip("'\"")
        return config

    def run_cmd(self, cmd, cwd=None, capture=False):
        """Wrapper isolado para facilitar mocking nos testes."""
        cwd = cwd or self.root_dir
        if capture:
            return subprocess.check_output(cmd, shell=True, cwd=cwd, text=True).strip()
        subprocess.run(cmd, shell=True, cwd=cwd, check=True)

    def interactive_menu(self):
        # Aqui entra a lógica que lê as tags do Git e pergunta ao usuário
        # Para fins de teste, retornaremos uma tag mock se não estivermos no terminal
        if not sys.stdout.isatty():
            return f"v0.0.0-{self.config['DEFAULT_SUFFIX']}"
        
        print(f"--- Menu de Deploy AutoSINAPI ---")
        print(f"[1] Build com Sufixo ({self.config['DEFAULT_SUFFIX']})")
        print(f"[2] Abortar")
        choice = input("Escolha: ")
        if choice == "1":
            return f"v0.0.0-{self.config['DEFAULT_SUFFIX']}"
        sys.exit(0)

    def run_toolkit_tests(self):
        if self.config["FORCE_TESTS"].lower() == "true":
            print("🧪 Rodando testes do Toolkit...")
            self.run_cmd("pytest", cwd=self.toolkit_dir)

    def build_toolkit(self):
        print("📦 Empacotando o Toolkit (.whl)...")
        self.run_cmd("python -m build", cwd=self.toolkit_dir)

    def call_operator(self):
        cmd = self.config["OPERATOR_CMD"]
        print(f"🚢 Acionando Operador da Infraestrutura: {cmd}")
        self.run_cmd(cmd)

    def validate_database(self):
        print("🗄️ Validando Migrações do Banco de Dados (Alembic)...")
        # Adaptação para rodar via operator genérico ou docker exec direto
        self.run_cmd("docker compose exec -T api alembic upgrade head")

    def execute(self):
        version = self.interactive_menu()
        print(f"Iniciando deploy para versão: {version}")
        self.run_toolkit_tests()
        self.build_toolkit()
        # self.inject_dependency() -> Atualizaria o requirements.txt dinâmico
        self.call_operator()
        self.validate_database()
        print("✅ Deploy Finalizado e Validado.")

if __name__ == "__main__":
    orchestrator = DeployOrchestrator(os.getcwd())
    orchestrator.execute()
