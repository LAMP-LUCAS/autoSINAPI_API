# Guia de Administração da AutoSINAPI API

Este guia detalha as principais tarefas de administração da AutoSINAPI API.

## 1. População do Banco de Dados

A população do banco de dados com os dados do SINAPI pode ser realizada de duas formas: via linha de comando (CLI) ou através de um endpoint da API.

### 1.1. Via Linha de Comando (CLI)

Esta é a forma mais direta de iniciar o processo de população do banco de dados, ideal para ambientes de desenvolvimento ou para execução manual.

1.  Certifique-se de que os containers Docker da aplicação estão em execução:
    ```bash
    make up
    ```
2.  Execute o comando `populate-db` do `Makefile`:
    ```bash
    make populate-db
    ```
    Este comando executa uma tarefa assíncrona no container `api` que irá baixar, processar e carregar os dados do SINAPI para o banco de dados. Por padrão, ele tentará popular para o mês e ano definidos no `Makefile` (atualmente, Setembro de 2025).

### 1.2. Via Endpoint da API

A API expõe um endpoint administrativo para disparar a tarefa de população do banco de dados de forma assíncrona. Esta abordagem é útil para integração com outras ferramentas ou para automação.

*   **Endpoint:** `POST /admin/populate-database`
*   **Descrição:** Dispara a tarefa de download e população da base SINAPI para um mês/ano específico. A tarefa roda em segundo plano.
*   **Parâmetros (no corpo da requisição - JSON):**
    *   `year` (inteiro, obrigatório): O ano para o qual os dados do SINAPI devem ser populados (ex: `2025`).
    *   `month` (inteiro, obrigatório): O mês para o qual os dados do SINAPI devem ser populados (ex: `9`).

**Exemplo de Requisição (usando `curl`):**

```bash
curl -X POST "http://localhost:8000/admin/populate-database" \
-H "Content-Type: application/json" \
-d '{
  "year": 2025,
  "month": 9
}'
```

Após a execução, a API retornará uma mensagem de sucesso e um `task_id` para a tarefa assíncrona.

## 2. Gerenciamento de Usuários e Chaves de API

O gerenciamento de usuários (Consumers) e suas chaves de API é realizado através do Kong Gateway, que atua como a camada de autenticação e gerenciamento de tráfego para a AutoSINAPI API.

Para criar Consumers e associar chaves de API (como `X-API-KEY`), você precisará interagir com a [Admin API do Kong](https://docs.konghq.com/gateway/latest/admin-api/):

*   **Criação de Consumer:** Utilize o endpoint `/consumers` da Admin API do Kong.
*   **Associação de Chave de API:** Após criar um Consumer, utilize o endpoint `/consumers/{consumer_id}/key-auth` para provisionar uma chave de API para ele.

Consulte a documentação oficial do Kong para obter instruções detalhadas e exemplos de como usar a Admin API para essas operações.

## 3. Outras Tarefas de Gerenciamento

Além da população do banco de dados, a principal tarefa de gerenciamento exposta diretamente pela AutoSINAPI API é a que foi detalhada na Seção 1.2. Outras tarefas de gerenciamento de API, como controle de acesso, limitação de taxa e monitoramento, são configuradas e gerenciadas através do Kong Gateway.

---

Para explorar todos os endpoints disponíveis na API, incluindo os de consulta de dados, acesse a documentação interativa (Swagger UI) em `http://localhost:8000/docs` (assumindo que a API esteja rodando localmente na porta 8000).