# Padrões de Contribuição do Projeto AutoSINAPI

Este documento define as convenções de contribuição e nomenclatura a serem seguidas no desenvolvimento do projeto **AutoSINAPI**, garantindo consistência, legibilidade e manutenibilidade do código.

---

## 1. Versionamento Semântico (SemVer)

O versionamento do projeto segue o padrão Semantic Versioning 2.0.0. O formato da versão é `MAJOR.MINOR.PATCH`.

-   **MAJOR**: Incrementado para mudanças incompatíveis com versões anteriores (breaking changes).
-   **MINOR**: Incrementado para adição de novas funcionalidades de forma retrocompatível.
-   **PATCH**: Incrementado para correções de bugs de forma retrocompatível.

### Regra Especial para Versões Iniciais (0.x.y)

Enquanto o projeto estiver na versão Major `0`, a API é considerada instável. Neste estágio:
-   Mudanças que quebram a compatibilidade (`breaking changes`) incrementam a versão **MINOR** (ex: de `v0.1.0` para `v0.2.0`).
-   Novas funcionalidades ou correções de bugs que **não** quebram a compatibilidade incrementam a **PATCH** (ex: de `v0.1.0` para `v0.1.1`).

A transição para a versão `1.0.0` marcará o primeiro lançamento estável do projeto.

### Versões de Pré-lançamento (Alpha/Beta)

Para versões que não estão prontas para produção, como fases de teste alfa e beta, utilizamos identificadores de pré-lançamento. O versionamento **não** recomeça após o identificador.

-   **Formato**: `MAJOR.MINOR.PATCH-identificador.N` (ex: `0.2.0-alpha.1`).
-   **Alpha**: Versão em desenvolvimento inicial, potencialmente instável e para testes internos. Formato: `MAJOR.MINOR.PATCH-alpha.N` (ex: `1.2.0-alpha.1` ou `0.0.1-alpha.1`).
-   **Beta**: Versão com funcionalidades completas, em fase de testes para um público restrito. Formato: `MAJOR.MINOR.PATCH-beta.N` (ex: `1.2.0-beta.1` ou `0.0.1-beta.1`).

O `N` é um número sequencial que se inicia em `1` para cada nova build de pré-lançamento.

**Exemplos:**
-   `v0.1.0-alpha.1`: Primeira build de testes para a versão `0.1.0`.
-   `v0.1.0-alpha.2`: Segunda build de testes para a versão `0.1.0`.
-   `v0.2.0-alpha.1`: Primeira build de testes para a versão `0.2.0`, que inclui breaking changes em relação à `v0.1.x`.
-   `v0.1.0-beta.1`: Pré-lançamento de testes para comunidade.
-   `v1.0.0`: O primeiro lançamento estável.
-   `v1.1.0`: Adição de suporte para um novo formato de planilha SINAPI (funcionalidade nova).
-   `v1.1.1`: Correção de um bug no processamento de dados de insumos (correção de bug).
-   `v2.0.0`: Mudança na estrutura do banco de dados que exige migração manual (breaking change).

---

## 2. Nomenclatura de Branches (Git)

Adotamos um fluxo de trabalho baseado no Git Flow simplificado para organizar o desenvolvimento.

- **`main`**: Contém o código estável e de produção. Apenas merges de `release` ou `hotfix` são permitidos.

- **`develop`**: Branch principal de desenvolvimento. Contém as últimas funcionalidades e correções que serão incluídas na próxima versão.

- **`feature/<nome-da-feature>`**: Para o desenvolvimento de novas funcionalidades.
  - Criada a partir de `develop`.
  - Exemplo: `feature/processar-planilha-insumos` ou `postgres_data-define` para features mais complexas.
  - Após a conclusão, deve ser mesclada em `develop`.

- **`fix/<nome-da-correcao>`**: Para correções de bugs não críticos.
  - Criada a partir de `develop`.
  - Exemplo: `fix/ajuste-parser-valor-monetario`
  - Após a conclusão, deve ser mesclada em `develop`.

- **`hotfix/<descricao-curta>`**: Para correções críticas em produção.
  - Criada a partir de `main`.
  - Após a conclusão, deve ser mesclada em `main` e `develop`.
  - Exemplo: `hotfix/permissao-acesso-negada`

- **`release/<versao>`**: Para preparar uma nova versão de produção (testes finais, atualização de documentação).
  - Criada a partir de `develop`.
  - Exemplo: `release/v1.2.0`
  - Após a conclusão, deve ser mesclada em `main` e `develop`.

---

## 3. Mensagens de Commit

Utilizamos o padrão Conventional Commits para padronizar as mensagens de commit.

**Formato:** `<tipo>(<escopo>): <descrição>`

- **`<tipo>`**:
  - `feat`: Uma nova funcionalidade.
  - `fix`: Uma correção de bug.
  - `docs`: Alterações na documentação.
  - `style`: Alterações de formatação de código (espaços, ponto e vírgula, etc.).
  - `refactor`: Refatoração de código que não altera a funcionalidade externa.
  - `test`: Adição ou correção de testes.
  - `chore`: Manutenção de build, ferramentas auxiliares, etc.

- **`<escopo>` (opcional)**: Onde a mudança ocorreu (ex: `import`, `settings`, `charts`).

**Exemplos:**

- `feat(parser): adiciona processamento de planilhas de composições`
- `fix(database): corrige tipo de dado da coluna de preço unitário`
- `docs(readme): atualiza instruções de instalação`
- `refactor(services): otimiza consulta de insumos no banco de dados`

---

## 4. Fluxo de Desenvolvimento

Para garantir um desenvolvimento organizado, eficiente e com alta qualidade, seguimos um fluxo de trabalho bem definido, que integra as convenções de nomenclatura de branches e commits já estabelecidas.

### 4.1. Ciclo de Vida de uma Funcionalidade/Correção

1.  **Criação da Branch:**
    *   Para novas funcionalidades: Crie uma branch `feature/<nome-da-feature>` a partir de `develop`.
    *   Para correções de bugs não críticos: Crie uma branch `fix/<nome-da-correcao>` a partir de `develop`.
    *   Para correções críticas em produção: Crie uma branch `hotfix/<descricao-curta>` a partir de `main`.

2.  **Desenvolvimento e Commits:**
    *   Desenvolva a funcionalidade ou correção na sua branch dedicada.
    *   Realize commits frequentes e atômicos, seguindo o padrão de [Mensagens de Commit](#3-mensagens-de-commit). Cada commit deve representar uma mudança lógica única e completa.

3.  **Testes Locais:**
    *   Antes de abrir um Pull Request, certifique-se de que todos os testes locais (unitários e de integração) estão passando.
    *   Execute os linters e formatadores de código para garantir a conformidade com os padrões do projeto.

4.  **Pull Request (PR):**
    *   Quando a funcionalidade ou correção estiver completa e testada localmente, abra um Pull Request da sua branch (`feature`, `fix`, `hotfix`) para a branch `develop` (ou `main` para `hotfix`).
    *   Utilize o template de Pull Request (`.github/pull_request_template.md`) para fornecer todas as informações necessárias, facilitando a revisão do código.
    *   Descreva claramente as mudanças, o problema que resolve (se for um bug) e como testar.

5.  **Revisão de Código e Merge:**
    *   Aguarde a revisão do código por outro(s) membro(s) da equipe.
    *   Enderece quaisquer comentários ou solicitações de alteração.
    *   Após a aprovação, a PR será mesclada na branch de destino (`develop` ou `main`).

### 4.2. Gerenciamento de Releases (Novo Fluxo)

O processo de release é **semi-automatizado** para combinar a eficiência da automação com o controle manual da comunicação. Um rascunho de release é atualizado continuamente e a publicação final é feita manualmente.

1.  **Desenvolvimento e Atualização Automática do Rascunho:**
    * Durante o ciclo de desenvolvimento, cada vez que um Pull Request é mesclado na branch `develop`, a automação (`.github/workflows/draft-release.yml`) atualiza um **rascunho de release** na página de "Releases" do GitHub, categorizando as mudanças (`feat`, `fix`, etc.) automaticamente.

2.  **Preparação para Lançamento (Branch `release`):**
    * Quando um conjunto de funcionalidades em `develop` está pronto para ser lançado, crie uma branch `release/<versao>` (ex: `release/v0.2.0-alpha.1`).
    * Nesta branch, realize apenas ajustes finais, como atualização do `CHANGELOG.md` e da documentação. Após a conclusão, mescle-a em `main` e `develop`.

3.  **Edição e Publicação da Release (Passo Manual Crucial):**
    * Com o código final em `main`, navegue até a seção **"Releases"** do repositório no GitHub.
    * Encontre o rascunho que foi preparado automaticamente (ele terá o título "Draft").
    * Clique em "Edit". No formulário de edição:
        * **Crie a tag:** No campo "Choose a tag", digite a nova tag de versão (ex: `v0.2.0-alpha.1`).
        * **Escreva a "Copy":** Edite o título e o corpo da release, adicionando a sua comunicação, explicando o valor das mudanças e orientando os usuários.
        * **Publique:** Clique em **"Publish release"**.

4.  **Construção e Upload Automatizados:**
    * O ato de publicar a release no passo anterior **cria e envia a tag** para o repositório.
    * Este push da tag dispara o segundo workflow (`.github/workflows/release.yml`), que irá construir os pacotes Python (`.whl` e `.tar.gz`) e anexá-los à release que você acabou de publicar. A publicação no PyPI permanece desativada por padrão.

---

## 5. Ferramentas de Automação e Templates

Para otimizar o fluxo de trabalho e garantir a padronização, utilizamos as seguintes ferramentas e templates no diretório `.github/` do projeto.

### 5.1. `release-drafter.yml` e `workflows/draft-release.yml`

-   **Finalidade:** Gerenciamento automático do rascunho de release.
-   **O que faz:**
    * A cada merge na branch `develop`, a action `Release Drafter` é executada.
    * Ela analisa os commits do Pull Request mesclado.
    * Atualiza um único rascunho de release ("Draft") na página de "Releases", organizando as mudanças em categorias (`Novas Funcionalidades`, `Correções de Bugs`, etc.) com base nos padrões de Conventional Commits.
-   **Benefícios:**
    * Automatiza a coleta e organização do changelog, garantindo que nenhuma mudança seja esquecida.
    * Prepara 90% do trabalho da release antes mesmo da decisão de lançar, economizando tempo e esforço manual.
    * Mantém um panorama sempre atualizado do que entrará na próxima versão.

### 5.2. `workflows/release.yml`

-   **Finalidade:** Construção e publicação dos pacotes (artefatos) da release.
-   **O que faz:**
    * É disparado **apenas quando uma nova tag de versão** (ex: `v0.2.0-alpha.1`) é criada e enviada ao repositório.
    * Constrói os pacotes Python distribuíveis (`.whl` e `.tar.gz`).
    * Anexa esses pacotes como artefatos à release do GitHub correspondente à tag.
-   **Benefícios:**
    * Garante que toda release publicada tenha os pacotes corretos e construídos de forma consistente.
    * Reduz erros manuais no processo de build e upload.

### 5.3. `pull_request_template.md`

-   **Finalidade:** Template padrão para a abertura de Pull Requests (PRs).
-   **O que faz:**
    * Preenche automaticamente a descrição de uma nova PR com seções pré-definidas.
    * Guia o contribuidor a fornecer informações essenciais, como a descrição das mudanças, como testar e um checklist de verificação.
-   **Benefícios:**
    * Padroniza a comunicação em todas as PRs.
    * Agiliza o processo de revisão de código, pois os revisores recebem todas as informações de forma clara e estruturada.
    * Melhora a qualidade geral das contribuições.

---

## 6. Nomenclatura no Código

As nomenclaturas devem ser claras e descritivas, refletindo a funcionalidade e o propósito do código.

### 6.1 Python (FastAPI)

- **Módulos e Classes**: `PascalCase` (ex: `SinapiParser`, `DatabaseManager`).
- **Variáveis e Funções**: `snake_case` (ex: `file_data`, `process_spreadsheet`).
- **Constantes**: `UPPER_SNAKE_CASE` (ex: `API_VERSION`, `DB_CONNECTION_STRING`).
- **Arquivos**: `snake_case` (ex: `sinapi_parser.py`, `main.py`).
- **Pacotes**: O código deve ser organizado em pacotes e módulos lógicos (ex: `app.services`, `app.models`, `app.routers`).
