# Ajuste de ambiente para execução dos testes pytest
#
# Este arquivo garante que o diretório raiz do projeto esteja no sys.path
# para que o pacote 'autosinapi' seja encontrado corretamente durante os testes.

import os
import sys

# Adiciona a raiz do projeto ao sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))
