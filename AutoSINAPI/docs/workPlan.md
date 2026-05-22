# Plano de Trabalho e Roadmap do Módulo AutoSINAPI

Este documento serve como um guia central para o desenvolvimento, acompanhamento e verificação das entregas do módulo `AutoSINAPI`. Ele define a arquitetura, a interface pública e o caminho a ser seguido.

## 1. Objetivos e Entregas Principais

O objetivo final é transformar o `AutoSINAPI` em uma biblioteca Python (`toolkit`) robusta, testável e desacoplada, pronta para ser consumida por outras aplicações, como uma API REST ou uma CLI.

As entregas incluem:
- **Pipeline ETL**: Processamento completo de arquivos do SINAPI, aderente ao `DataModel.md`.
- **Cobertura de Testes**: Testes unitários e de integração automatizados.
- **Interface Pública**: Uma função `run_etl()` clara e padronizada.
- **Arquitetura Modular**: Código organizado em módulos com responsabilidades únicas (`downloader`, `processor`, `database`).
- **Documentação**: Manuais de uso, arquitetura e contribuição.

## 2. Status Geral (Visão Macro)

Use esta seção para um acompanhamento rápido do progresso geral.

- [x] **Fase 1**: Refatoração do Módulo para Toolkit
- [x] **Fase 2**: Cobertura de Testes Unitários e de Integração
- [x] **Fase 3**: Documentação Profunda e Detalhada
- [ ] **Fase 4**: Empacotamento e Release Final
- [ ] **Fase 5**: Implementação da API e CLI (Pós-Toolkit)

---

## 3. Visão Geral da Arquitetura

A nossa arquitetura será baseada em **desacoplamento**. A API não executará o pesado processo de ETL diretamente. Em vez disso, ela atuará como um **controlador**, delegando a tarefa para um **trabalhador (worker)** em segundo plano. O módulo `AutoSINAPI` será o **toolkit** que o trabalhador utilizará.

**Diagrama da Arquitetura:**

```
+-----------+     +----------------+     +----------------+     +---------------------+
|           |     |                |     |                |     |  API FastAPI        |
| Usuário   |---->| Kong Gateway   |---->|  (Controller)  |---->| (Fila de Tarefas)   |
| (Admin)   |     | (Auth & Proxy) |     |  POST /populate|     |  Ex: Redis          |
+-----------+     +----------------+     +----------------+     +----------+----------+
                                                                             |
                                                                    (Nova Tarefa)
                                                                             |
                                                                             v
+-------------------------------------------------+     +--------------------+----------+
|  AutoSINAPI Toolkit                             |<----|                               |
| (Biblioteca Python instalada via pip)           |     |  Trabalhador (Celery Worker)  |
| - Lógica de Download (em memória/disco)         |     |  - Pega tarefa da fila        |
| - Lógica de Processamento (pandas)              |     |  - Executa a lógica do        |
| - Lógica de Banco de Dados (SQLAlchemy)         |     |    AutoSINAPI Toolkit         |
+-------------------------------------------------+     +--------------------+----------+
                                                                             |
                                                                 (Escreve os dados)
                                                                             |
                                                                             v
                                                                 +--------------------+
                                                                 |                    |
                                                                 |  Banco de Dados    |
                                                                 |  (PostgreSQL)      |
                                                                 +--------------------+
```

-----

## 4. O Contrato do Toolkit (Interface Pública)

Para que o `AutoSINAPI` seja consumível por outras aplicações, ele deve expor uma interface clara e previsível.

#### **Requisito 1: A Interface Pública do Módulo**

O `AutoSINAPI` deverá expor, no mínimo, uma função principal, clara e bem definida.

**Função Principal Exigida:**
`autosinapi.run_etl(db_config: dict, sinapi_config: dict, mode: str)`

  * **`db_config (dict)`**: Um dicionário contendo **toda** a informação de conexão com o banco de dados. A API irá montar este dicionário a partir das suas próprias variáveis de ambiente (`.env`).
    ```python
    # Exemplo de db_config que a API irá passar
    db_config = {
        "user": "admin",
        "password": "senha_super_secreta",
        "host": "db",
        "port": 5432,
        "dbname": "sinapi"
    }
    ```
  * **`sinapi_config (dict)`**: Um dicionário com os parâmetros da operação. A API também montará este dicionário.
    ```python
    # Exemplo de sinapi_config que a API irá passar
    sinapi_config = {
        "year": 2025,
        "month": 8,
        "workbook_type": "REFERENCIA",
        "duplicate_policy": "substituir" 
    }
    ```
  * **`mode (str)`**: O seletor de modo de operação.
      * `'server'`: Ativa o modo de alta performance, com todas as operações em memória (bypass de disco).
      * `'local'`: Usa o modo padrão, salvando arquivos em disco, para uso pela comunidade.

#### **Requisito 2: Lógica de Configuração Inteligente (Sem Leitura de Arquivos)**

Quando usado como biblioteca (`mode='server'`), o módulo `AutoSINAPI`:

  * **NÃO PODE** ler `sql_access.secrets` ou `CONFIG.json`.
  * **DEVE** usar exclusivamente os dicionários `db_config` e `sinapi_config` passados como argumentos.
  * Quando usado em modo `local`, ele pode manter a lógica de ler arquivos `CONFIG.json` para facilitar a vida do usuário final que o clona do GitHub.

#### **Requisito 3: Retorno e Tratamento de Erros**

A função `run_etl` deve retornar um dicionário com o status da operação e levantar exceções específicas para que a API possa tratar os erros de forma inteligente.

  * **Retorno em caso de sucesso:**
    ```python
    {"status": "success", "message": "Dados de 08/2025 populados.", "tables_updated": ["insumos_isd", "composicoes_csd"]}
    ```
  * **Exceções:** O módulo deve definir e levantar exceções customizadas, como `autosinapi.exceptions.DownloadError` ou `autosinapi.exceptions.DatabaseError`.

-----

## 5. Roadmap de Desenvolvimento (Etapas Detalhadas)

Este é o plano de ação detalhado, dividido em fases e tarefas.

### Fase 1: Evolução do `AutoSINAPI` para um Toolkit

Esta fase é sobre preparar o módulo para ser consumido pela nossa API.

  * **Etapa 1.1: Refatoração Estrutural:** Quebrar o `sinapi_utils.py` em módulos menores (`downloader.py`, `processor.py`, `database.py`) dentro de uma estrutura de pacote Python, como planejamos anteriormente.
  * **Etapa 1.2: Implementar a Lógica de Configuração Centralizada:** Remover toda a leitura de arquivos de configuração de dentro das classes e fazer com que elas recebam suas configurações via construtor (`__init__`).
  * **Etapa 1.3: Criar a Interface Pública:** Criar a função `run_etl(db_config, sinapi_config, mode)` que orquestra as chamadas para as classes internas.

    * **Etapa 1.3.1: Desacoplar as Classes (Injeção de Dependência):** Em vez de uma classe criar outra (ex: `self.downloader = SinapiDownloader()`), ela deve recebê-la como um parâmetro em seu construtor (`__init__(self, downloader)`). Isso torna o código muito mais flexível e testável.
  * **Etapa 1.4: Implementar o Modo Duplo:** Dentro das classes `downloader` e `processor`, adicionar a lógica `if mode == 'server': ... else: ...` para lidar com operações em memória vs. em disco.
  * **Etapa 1.5: Empacotamento:** Garantir que o módulo seja instalável via `pip` com um `setup.py` ou `pyproject.toml`.


### Fase 2: Criação e desenvolvimento dos testes unitários

...

### Fase 3: Documentação Profunda e Detalhada

**Objetivo:** Realizar a documentação e registro de todos os elementos do módulo, adicionando "headers" de descrição em cada arquivo crucial para detalhar seu propósito, o fluxo de dados (como a informação é inserida, trabalhada e entregue) e como ele se integra aos objetivos gerais do AutoSINAPI.

**Importância:** Contextualizar contribuidores, agentes de IA e ferramentas de automação para que possam utilizar e dar manutenção ao módulo da maneira mais eficiente possível.

**Tarefas Principais:**

- [ ] **Adicionar Cabeçalhos de Documentação:** Inserir um bloco de comentário no topo de cada arquivo `.py` do módulo `autosinapi` e `tools`, explicando o propósito do arquivo.
- [ ] **Revisar e Detalhar Docstrings:** Garantir que todas as classes e funções públicas tenham docstrings claras, explicando o que fazem, seus parâmetros e o que retornam.
- [ ] **Criar Documento de Fluxo de Dados:** Elaborar um novo documento no diretório `docs/` que mapeie o fluxo de dados de ponta a ponta, desde o download até a inserção no banco de dados.
- [ ] **Atualizar README.md:** Adicionar uma seção de "Arquitetura Detalhada" ao `README.md`, explicando como os componentes se conectam.

---

## 6. Atualização e Correção dos Testes (Setembro 2025)

**Objetivo:** Atualizar a suíte de testes para refletir a nova arquitetura do pipeline AutoSINAPI, garantindo que todos os testes passem e que a cobertura do código seja mantida ou ampliada.

...