# Refatoração do AutoSINAPI para Toolkit Modular

## Descrição
Esta PR implementa a primeira fase da refatoração do AutoSINAPI, transformando-o em uma biblioteca Python modular e desacoplada, seguindo os princípios SOLID e Clean Code.

## Mudanças Principais
- ✨ Implementa estrutura modular com injeção de dependências
- 🔄 Adiciona suporte para input direto de arquivos XLSX
- 🧪 Configura ambiente de testes unitários com pytest
- 📦 Atualiza empacotamento para distribuição via pip

## Estrutura de Diretórios
```
/AutoSINAPI/
├── autosinapi/             # Código principal da biblioteca
│   ├── core/              # Módulos principais
│   │   ├── database.py    # Operações com banco de dados
│   │   ├── downloader.py  # Download/input de arquivos
│   │   ├── processor.py   # Processamento de planilhas
│   │   └── file_manager.py # Utilitários de arquivo
│   ├── pipeline.py        # Orquestração do ETL
│   ├── config.py          # Gerenciamento de configurações
│   ├── exceptions.py      # Exceções customizadas
│   └── __init__.py        # Interface pública
├── tests/                 # Testes unitários
└── ...
```

## Interface Pública
```python
def run_etl(db_config: dict, sinapi_config: dict, mode: str) -> dict:
    """
    Executa o pipeline ETL do SINAPI.
    
    Args:
        db_config: Configurações do banco de dados
        sinapi_config: Configurações do SINAPI
        mode: Modo de operação ('server' ou 'local')
    
    Returns:
        Dict com status da operação
    """
```

## Testes Implementados
- ✅ Testes do módulo de configuração
- ✅ Testes do downloader com mocks
- ✅ Testes de input direto de arquivo
- 🚧 Testes do processador (pendente)
- 🚧 Testes do banco de dados (pendente)

## Breaking Changes
- Removida leitura direta de arquivos de configuração no modo 'server'
- Alterada assinatura da função principal para `run_etl`
- Migração para Python 3.8+ devido a type hints

## Checklist
- [x] Código segue os padrões de estilo do projeto
- [x] Testes unitários adicionados
- [x] Documentação atualizada
- [x] Todas as dependências listadas no setup.py/pyproject.toml
- [ ] Revisão de código necessária

## Próximos Passos
1. Implementar testes restantes
2. Atualizar README.md com instruções de uso
3. Preparar release alpha (v0.1.0-alpha.1)

## Referências
- #issue_number (se houver)
- [Documento de Arquitetura](docs/workPlan.md)
- [Padrões de Contribuição](docs/CONTRIBUTING.md)
