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

O gerenciamento de usuários (Consumers) e suas chaves de API é realizado através da Admin API do Kong Gateway, que atua como a camada de autenticação.

Abaixo estão os comandos `curl` para as operações mais comuns.

### 2.1. Criar um Novo Usuário (Consumer)

```bash
curl -X POST http://localhost:8001/consumers/ --data "username=meu-usuario"
```
*Substitua `meu-usuario` pelo nome de usuário desejado.*

### 2.2. Gerar uma Chave de API para um Usuário

```bash
curl -X POST http://localhost:8001/consumers/meu-usuario/key-auth/
```
*Este comando irá retornar a chave de API (`key`) que deverá ser usada no cabeçalho `X-API-KEY` das requisições.*

### 2.3. Listar Chaves de um Usuário

```bash
curl -X GET http://localhost:8001/consumers/meu-usuario/key-auth/
```

### 2.4. Deletar uma Chave de API

```bash
curl -X DELETE http://localhost:8001/consumers/meu-usuario/key-auth/{key_id}
```
*Substitua `{key_id}` pelo ID da chave que você deseja remover.*

Para mais detalhes e outras operações, consulte a [documentação oficial da Admin API do Kong](https://docs.konghq.com/gateway/latest/admin-api/).

## 3. Outras Tarefas de Gerenciamento

Além da população do banco de dados, a principal tarefa de gerenciamento exposta diretamente pela AutoSINAPI API é a que foi detalhada na Seção 1.2. Outras tarefas de gerenciamento de API, como controle de acesso, limitação de taxa e monitoramento, são configuradas e gerenciadas através do Kong Gateway.

---

Para explorar todos os endpoints disponíveis na API, incluindo os de consulta de dados, acesse a documentação interativa (Swagger UI) em `http://localhost:8000/docs` (assumindo que a API esteja rodando localmente na porta 8000).