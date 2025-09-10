# Como Contribuir com o autoSINAPI_API

Ficamos muito felizes com seu interesse em contribuir! Este documento fornece as diretrizes para garantir que o processo seja o mais simples e consistente possível.

## Como Começar

1.  **Faça um Fork** do repositório para a sua própria conta do GitHub.
2.  **Clone** o seu fork para a sua máquina local.
3.  **Siga as instruções de setup** no arquivo `README.md` para configurar o ambiente de desenvolvimento com Docker. É rápido e garante que todos usem a mesma base.

---

## Padrão de Desenvolvimento

Para manter o projeto organizado e consistente, seguimos algumas convenções.

### 1. Nomenclatura de Branches (Git)

Adotamos um fluxo de trabalho baseado no Git Flow simplificado.

-   **`main`**: Contém o código estável e de produção.
-   **`develop`**: Branch principal de desenvolvimento. Onde novas funcionalidades são integradas.
-   **`feature/<nome-da-feature>`**: Para o desenvolvimento de novas funcionalidades (ex: `feature/analise-de-impacto`).
-   **`fix/<nome-da-correcao>`**: Para correções de bugs não críticos (ex: `fix/query-performance-insumos`).
-   **`hotfix/<descricao-curta>`**: Para correções críticas em produção.
-   **`docs/<descricao-curta>`**: Para adicionar ou melhorar a documentação (ex: `docs/ajustar-readme`).

### 2. Mensagens de Commit (Conventional Commits)

Utilizamos o padrão [Conventional Commits](https://www.conventionalcommits.org/) para padronizar as mensagens.

**Formato:** `<tipo>(<escopo>): <descrição>`

-   **`<tipo>`**: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`.
-   **`<escopo>` (opcional)**: Onde a mudança ocorreu. Escopos sugeridos:
    -   `project`: Mudanças que afetam a estrutura geral ou múltiplos locais.
    -   `api`: Lógica da API FastAPI (`main.py`, `schemas.py`).
    -   `bi`: Lógica de Business Intelligence (`crud.py`).
    -   `infra`: Arquivos de infraestrutura (`docker-compose.yml`, `Dockerfile`).
    -   `deps`: Atualização de dependências (`requirements.txt`).

### 3. Padrões de Código e Infraestrutura

-   **Python (API e Worker)**: O código segue o padrão **PEP 8**. Usamos `snake_case` para variáveis e funções e `PascalCase` para classes.
-   **Infraestrutura (Docker & Kong)**: Nomes de serviços e contêineres devem ser em `snake_case` e descritivos (ex: `celery_worker`, `sinapi_gateway`).

---

## Submetendo Alterações

1.  Após implementar sua funcionalidade ou correção, faça o commit das suas alterações seguindo o padrão acima.
2.  Envie as alterações para o seu fork (`git push origin feature/<nome-da-feature>`).
3.  Abra um **Pull Request (PR)** do seu fork para a branch `develop` do repositório principal.
4.  No PR, descreva claramente o que foi feito e por quê.

Obrigado por sua contribuição!
