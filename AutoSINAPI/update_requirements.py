"""
Script para atualizar automaticamente o arquivo requirements.txt baseado nas importações dos scripts Python.
"""
import os
import re
from pathlib import Path

def extract_imports(file_content):
    """Extrai todas as importações de um arquivo Python."""
    # Padrão para encontrar importações
    import_patterns = [
        r'^import\s+(\w+)',  # import numpy
        r'^from\s+(\w+)\s+import',  # from numpy import array
        r'^import\s+(\w+)\s+as',  # import numpy as np
    ]
    
    imports = set()
    lines = file_content.split('\n')
    
    for line in lines:
        line = line.strip()
        for pattern in import_patterns:
            match = re.match(pattern, line)
            if match:
                imports.add(match.group(1))
    for pack in imports:
        pack.strip()
        pack.replace(' ', '')
    return imports

def get_py_files(directory):
    """Retorna todos os arquivos .py no diretório. excluindo diretórios específicos"""
    py_files = []
    for root, dirs, files in os.walk(directory):
        # Excluir diretórios específicos
        dirs[:] = [d for d in dirs if d not in ['.git', '__pycache__','venv','env','node_modules','docs','tests']]
        for file in files:
            if file.endswith('.py'):
                py_files.append(Path(root) / file)
    return py_files #list(Path(directory).glob('**/*.py'))

    return 

def get_package_name(import_name):
    """Converte nome de importação para nome do pacote."""
    package_mapping = {
        'pandas': 'pandas',
        'numpy': 'numpy',
        'requests': 'requests',
        'openpyxl': 'openpyxl',
        'tqdm': 'tqdm',
        'sqlalchemy': 'sqlalchemy',
        'psycopg2': 'psycopg2-binary',
        'json': None,  # módulo built-in
        'os': None,  # módulo built-in
        're': None,  # módulo built-in
        'datetime': None,  # módulo built-in
        'pathlib': None,  # módulo built-in
        'time': None,  # módulo built-in
        'zipfile': None,  # módulo built-in
        'logging': None,  # módulo built-in
        'Random': None,  # módulo built-in
        'sinapi_utils':None, #módulo interno
    }
    return package_mapping.get(import_name, import_name)

def main():
    # Diretório atual
    current_dir = os.path.dirname(os.path.abspath(__file__))
    print(f'Atualizando requirements.txt no diretório: {current_dir}')
    
    # Encontrar todos os arquivos Python
    py_files = get_py_files(current_dir)
    print(f'Encontrados {len(py_files)} arquivos Python para análise:\n' + '\n'.join(str(file) for file in py_files))
    if not py_files:
        print('Nenhum arquivo Python encontrado. Encerrando o script.')
        return
        
    # Coletar todas as importações
    all_imports = set()
    for py_file in py_files:
        with open(py_file, 'r', encoding='utf-8') as f:
            content = f.read()
            imports = extract_imports(content)
            all_imports.update(imports)
    print(f'Importações encontradas: {len(all_imports)}\n ' + '\n'.join(sorted(all_imports)))
    if not all_imports:
        print('Nenhuma importação encontrada. Encerrando o script.')
        return
    
    # Converter para nomes de pacotes e filtrar built-ins
    packages = set()
    for imp in all_imports:
        package = get_package_name(imp)
        if package:
            packages.add(package)
    print(f'Pacotes identificados: {len(packages)}\n ' + '\n'.join(sorted(packages)))
    if not packages:
        print('Nenhum pacote identificado. Encerrando o script.')
        return
    
    # Escrever requirements.txt
    with open('requirements.txt', 'w', encoding='utf-8') as f:
        for package in sorted(packages):
            f.write(f'{package}\n')
    
    print(f'Arquivo requirements.txt atualizado com {len(packages)} pacotes.')

if __name__ == '__main__':
    main()
