# Padrões de Nomenclatura do Projeto autoSINAPI_API

Este documento define as convenções de nomenclatura a serem seguidas no desenvolvimento do projeto **autoSINAPI_API**, garantindo consistência, legibilidade e manutenibilidade do código e da infraestrutura.

---

## 1. Versionamento Semântico (SemVer)

O versionamento do projeto segue o padrão [Semantic Versioning 2.0.0](https://semver.org/lang/pt-BR/). O formato da versão é `MAJOR.MINOR.PATCH`.

- **MAJOR**: Incrementado para mudanças incompatíveis com a API (breaking changes).
- **MINOR**: Incrementado para adição de novas funcionalidades de forma retrocompatível.
- **PATCH**: Incrementado para correções de bugs de forma retrocompatível.

**Exemplos:**

- `0.1.0`: Lançamento inicial da API com funcionalidades básicas.
- `0.2.0`: Adição dos endpoints de `composicoes`.
- `0.2.1`: Correção de um bug na busca de `insumos`.
- `1.0.0`: Lançamento estável para produção.

---

## 2. Nomenclatura de Branches (Git)

Adotamos um fluxo de trabalho baseado no Git Flow simplificado.

- **`main`**: Contém o código estável e de produção. Apenas merges de `release` ou `hotfix` são permitidos.
- **`develop`**: Branch principal de desenvolvimento. Contém as últimas funcionalidades e correções.
- **`feature/<nome-da-feature>`**: Para o desenvolvimento de novas funcionalidades.
  - Criada a partir de `develop`.
  - Exemplo: `feature/task-status-endpoint`
- **`fix/<nome-da-correcao>`**: Para correções de bugs não críticos.
  - Criada a partir de `develop`.
  - Exemplo: `fix/query-performance-insumos`
- **`hotfix/<descricao-curta>`**: Para correções críticas em produção.
  - Criada a partir de `main` e mesclada em `main` e `develop`.
  - Exemplo: `hotfix/security-patch-auth`
- **`docs/<descricao-curta>`**: Para adicionar ou melhorar a documentação.
  - Exemplo: `docs/ajustar-readme`

---

## 3. Mensagens de Commit (Conventional Commits)

Utilizamos o padrão [Conventional Commits](https://www.conventionalcommits.org/) para padronizar as mensagens.

**Formato:** `<tipo>(<escopo>): <descrição>`

- **`<tipo>`**: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`.

- **`<escopo>` (opcional)**: Onde a mudança ocorreu. Escopos sugeridos para este projeto:
  - `api`: Lógica da API FastAPI (endpoints, schemas em `main.py`, `schemas.py`).
  - `worker`: Tarefas do Celery (`tasks.py`).
  - `db`: Modelos SQLAlchemy ou consultas em `crud.py`.
  - `infra`: Arquivos de infraestrutura (`docker-compose.yml`, `Dockerfile`, `kong.yml`).
  - `deps`: Adição, remoção ou atualização de dependências (`requirements.txt`).

**Exemplos:**

- `feat(api): adiciona endpoint para status de tarefas`
- `fix(worker): corrige tratamento de erro na tarefa de ETL`
- `docs(readme): atualiza instruções de setup do ambiente`
- `refactor(db): otimiza consulta de composições`
- `chore(infra): adiciona healthcheck ao serviço de api`
- `chore(deps): atualiza versão do fastapi`

---

## 4. Nomenclatura no Código e Infraestrutura

### 4.1. Python (API e Worker)

O código segue o padrão **PEP 8**.

- **Módulos e Classes**: `PascalCase` (ex: `Insumo`, `Composicao` em `schemas.py`).
- **Variáveis e Funções**: `snake_case` (ex: `get_db`, `populate_sinapi_task`).
- **Constantes**: `UPPER_SNAKE_CASE` (ex: `POSTGRES_USER`).
- **Arquivos**: `snake_case` (ex: `crud.py`, `tasks.py`).
- **Estrutura de Pacotes**: O código da aplicação reside no diretório `api/`.
  - `main.py`: Contém a instância do FastAPI e os endpoints.
  - `crud.py`: Contém as funções de acesso ao banco de dados (Create, Read, Update, Delete).
  - `schemas.py`: Contém os modelos Pydantic para validação de dados da API.
  - `database.py`: Contém a configuração da conexão com o banco de dados.
  - `tasks.py`: Contém as definições de tarefas do Celery.

### 4.2. Infraestrutura (Docker & Kong)

- **Nomes de Serviço (em `docker-compose.yml`)**: `snake_case` e descritivos.
  - Exemplos: `celery_worker`, `kong_migrations`.
- **Nomes de Contêiner**: Padrão `sinapi_<nome_do_serviço>`.
  - Exemplos: `sinapi_api`, `sinapi_db`, `sinapi_worker`, `sinapi_gateway`.
- **Redes**: Padrão `sinapi-net`.

### 4.3. Convenções para Consumidores (Frontend)

As seções a seguir aplicam-se a projetos que consomem esta API (ex: um aplicativo web), e não ao repositório da API em si.

#### 4.3.1. CSS

- **Prefixo**: `as-` (AutoSINAPI).
- **Metodologia**: BEM (`as-bloco__elemento--modificador`).
- **Exemplos**: `.as-table`, `.as-table__row`, `.as-table__row--selected`.

#### 4.3.2. JavaScript

- **Variáveis e Funções**: `camelCase` (ex: `fetchInsumos`).
- **Classes**: `PascalCase` (ex: `SinapiClient`).
- **Constantes**: `UPPER_SNAKE_CASE` (ex: `API_BASE_URL`).
