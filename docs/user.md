# Guia de Uso da AutoSINAPI API

Este guia detalha como interagir com os endpoints da AutoSINAPI API, incluindo os parâmetros de entrada e os formatos de retorno esperados.

## Autenticação

Todas as requisições para a AutoSINAPI API devem incluir uma chave de API válida no cabeçalho `X-API-KEY`. Esta chave é gerenciada através do Kong Gateway.

**Exemplo de Cabeçalho:**

```
X-API-KEY: sua_chave_de_api_aqui
```

## Endpoints Disponíveis

### 1. Raiz da API

*   **GET /**
    *   **Descrição:** Retorna uma mensagem de boas-vindas e informações sobre a documentação.
    *   **Parâmetros:** Nenhum.
    *   **Exemplo de `curl`:**
        ```bash
        curl -X GET "http://localhost:8000/" -H "X-API-KEY: sua_chave_de_api_aqui"
        ```
    *   **Retorno Esperado:**
        ```json
        {
          "message": "Bem-vindo à API AutoSINAPI. Acesse /docs para a documentação interativa."
        }
        ```

### 2. Endpoints de Insumos

*   **GET /insumos/{codigo}**
    *   **Descrição:** Obtém um insumo específico e seu preço para um determinado contexto.
    *   **Parâmetros de Caminho:**
        *   `codigo` (inteiro, obrigatório): O código do insumo.
    *   **Parâmetros de Query:**
        *   `uf` (string, obrigatório): Unidade Federativa (UF). Ex: `SP`.
        *   `data_referencia` (string, obrigatório): Data de referência no formato `AAAA-MM`. Ex: `2025-09`.
        *   `regime` (string, opcional): Regime de preço. Padrão: `NAO_DESONERADO`.
    *   **Exemplo de `curl`:**
        ```bash
        curl -X GET "http://localhost:8000/insumos/43430?uf=SP&data_referencia=2025-09" -H "X-API-KEY: sua_chave_de_api_aqui"
        ```
    *   **Retorno Esperado:** Um objeto `Insumo`.

*   **GET /insumos/**
    *   **Descrição:** Busca insumos pela descrição e retorna seus preços para um determinado contexto.
    *   **Parâmetros de Query:**
        *   `q` (string, obrigatório): Termo para buscar na descrição do insumo (mínimo 3 caracteres).
        *   `uf` (string, obrigatório): Unidade Federativa (UF). Ex: `SP`.
        *   `data_referencia` (string, obrigatório): Data de referência no formato `AAAA-MM`. Ex: `2025-09`.
        *   `regime` (string, opcional): Regime de preço. Padrão: `NAO_DESONERADO`.
        *   `skip` (inteiro, opcional): Número de itens a serem pulados (para paginação). Padrão: `0`.
        *   `limit` (inteiro, opcional): Número máximo de itens a serem retornados. Padrão: `100`.
    *   **Exemplo de `curl`:**
        ```bash
        curl -X GET "http://localhost:8000/insumos/?q=ACO%20CA-50&uf=SP&data_referencia=2025-09&limit=5" -H "X-API-KEY: sua_chave_de_api_aqui"
        ```
    *   **Retorno Esperado:** Uma lista de objetos `Insumo`.

### 3. Endpoints de Composições

*   **GET /composicoes/{codigo}**
    *   **Descrição:** Obtém uma composição específica e seu custo para um determinado contexto.
    *   **Parâmetros de Caminho:**
        *   `codigo` (inteiro, obrigatório): O código da composição.
    *   **Parâmetros de Query:**
        *   `uf` (string, obrigatório): Unidade Federativa (UF). Ex: `SP`.
        *   `data_referencia` (string, obrigatório): Data de referência no formato `AAAA-MM`. Ex: `2025-09`.
        *   `regime` (string, opcional): Regime de custo. Padrão: `NAO_DESONERADO`.
    *   **Exemplo de `curl`:**
        ```bash
        curl -X GET "http://localhost:8000/composicoes/92711?uf=SP&data_referencia=2025-09" -H "X-API-KEY: sua_chave_de_api_aqui"
        ```
    *   **Retorno Esperado:** Um objeto `Composicao`.

*   **GET /composicoes/**
    *   **Descrição:** Busca composições pela descrição e retorna seus custos para um determinado contexto.
    *   **Parâmetros de Query:**
        *   `q` (string, obrigatório): Termo para buscar na descrição da composição (mínimo 3 caracteres).
        *   `uf` (string, obrigatório): Unidade Federativa (UF). Ex: `SP`.
        *   `data_referencia` (string, obrigatório): Data de referência no formato `AAAA-MM`. Ex: `2025-09`.
        *   `regime` (string, opcional): Regime de custo. Padrão: `NAO_DESONERADO`.
        *   `skip` (inteiro, opcional): Número de itens a serem pulados (para paginação). Padrão: `0`.
        *   `limit` (inteiro, opcional): Número máximo de itens a serem retornados. Padrão: `100`.
    *   **Exemplo de `curl`:**
        ```bash
        curl -X GET "http://localhost:8000/composicoes/?q=CONCRETO%20BOMBEADO&uf=SP&data_referencia=2025-09&limit=5" -H "X-API-KEY: sua_chave_de_api_aqui"
        ```
    *   **Retorno Esperado:** Uma lista de objetos `Composicao`.

### 4. Endpoints de Business Intelligence (BI)

*   **GET /bi/composicao/{codigo}/bom**
    *   **Descrição:** Retorna o Bill of Materials (BOM) completo de uma composição, explodindo todos os níveis e calculando o impacto de custo de cada item.
    *   **Parâmetros de Caminho:**
        *   `codigo` (inteiro, obrigatório): O código da composição.
    *   **Parâmetros de Query:**
        *   `uf` (string, obrigatório): Unidade Federativa (UF). Ex: `SP`.
        *   `data_referencia` (string, obrigatório): Data de referência no formato `AAAA-MM`. Ex: `2025-09`.
        *   `regime` (string, opcional): Regime de custo/preço. Padrão: `NAO_DESONERADO`.
    *   **Exemplo de `curl`:**
        ```bash
        curl -X GET "http://localhost:8000/bi/composicao/92711/bom?uf=SP&data_referencia=2025-09" -H "X-API-KEY: sua_chave_de_api_aqui"
        ```
    *   **Retorno Esperado:** Uma lista de objetos `ComposicaoBOMItem`.

*   **GET /bi/composicao/{codigo}/hora-homem**
    *   **Descrição:** Calcula o total de Hora/Homem para uma composição, somando os coeficientes de todos os insumos de mão de obra (unidade 'H') em todos os níveis.
    *   **Parâmetros de Caminho:**
        *   `codigo` (inteiro, obrigatório): O código da composição.
    *   **Exemplo de `curl`:**
        ```bash
        curl -X GET "http://localhost:8000/bi/composicao/92711/hora-homem" -H "X-API-KEY: sua_chave_de_api_aqui"
        ```
    *   **Retorno Esperado:** Um objeto `ComposicaoManHours`.

*   **POST /bi/curva-abc**
    *   **Descrição:** Calcula a Curva ABC de insumos para um grupo de composições, identificando os itens de maior impacto financeiro.
    *   **Parâmetros de Query:**
        *   `uf` (string, obrigatório): Unidade Federativa (UF). Ex: `SP`.
        *   `data_referencia` (string, obrigatório): Data de referência no formato `AAAA-MM`. Ex: `2025-09`.
        *   `regime` (string, opcional): Regime de preço. Padrão: `NAO_DESONERADO`.
    *   **Corpo da Requisição (JSON):**
        *   `codigos` (lista de inteiros, obrigatório): Lista de códigos de composições a serem analisadas. Ex: `[92711, 88307]`.
    *   **Exemplo de `curl`:**
        ```bash
        curl -X POST "http://localhost:8000/bi/curva-abc?uf=SP&data_referencia=2025-09" \
        -H "Content-Type: application/json" \
        -H "X-API-KEY: sua_chave_de_api_aqui" \
        -d '{"codigos": [92711, 88307]}'
        ```
    *   **Retorno Esperado:** Uma lista de objetos `CurvaABCItem`.

*   **GET /bi/composicao/{codigo}/otimizar**
    *   **Descrição:** Retorna os N insumos de maior impacto financeiro em uma composição (Curva ABC - Foco).
    *   **Parâmetros de Caminho:**
        *   `codigo` (inteiro, obrigatório): O código da composição.
    *   **Parâmetros de Query:**
        *   `uf` (string, obrigatório): Unidade Federativa (UF). Ex: `SP`.
        *   `data_referencia` (string, obrigatório): Data de referência no formato `AAAA-MM`. Ex: `2025-09`.
        *   `regime` (string, opcional): Regime de custo/preço. Padrão: `NAO_DESONERADO`.
        *   `top_n` (inteiro, opcional): Número de principais insumos a serem retornados. Padrão: `5`.
    *   **Exemplo de `curl`:**
        ```bash
        curl -X GET "http://localhost:8000/bi/composicao/92711/otimizar?uf=SP&data_referencia=2025-09&top_n=3" -H "X-API-KEY: sua_chave_de_api_aqui"
        ```
    *   **Retorno Esperado:** Uma lista de objetos `ComposicaoBOMItem`.

*   **GET /bi/item/{tipo_item}/{codigo}/historico**
    *   **Descrição:** Retorna o histórico de custo/preço de um item para um período.
    *   **Parâmetros de Caminho:**
        *   `tipo_item` (string, obrigatório): Tipo do item: `insumo` ou `composicao`.
        *   `codigo` (inteiro, obrigatório): O código do item.
    *   **Parâmetros de Query:**
        *   `uf` (string, obrigatório): Unidade Federativa (UF). Ex: `SP`.
        *   `regime` (string, opcional): Regime de custo/preço. Padrão: `NAO_DESONERADO`.
        *   `data_fim` (string, opcional): Data final (`AAAA-MM`) da análise. Padrão: Mês atual.
        *   `meses` (inteiro, opcional): Número de meses a serem analisados para trás. Padrão: `12`.
    *   **Exemplo de `curl` (para um insumo):**
        ```bash
        curl -X GET "http://localhost:8000/bi/item/insumo/43430/historico?uf=SP&meses=6" -H "X-API-KEY: sua_chave_de_api_aqui"
        ```
    *   **Exemplo de `curl` (para uma composição):**
        ```bash
        curl -X GET "http://localhost:8000/bi/item/composicao/92711/historico?uf=SP&meses=12&regime=DESONERADO" -H "X-API-KEY: sua_chave_de_api_aqui"
        ```
    *   **Retorno Esperado:** Uma lista de objetos `HistoricoCusto`.

### 5. Endpoints de Administração

*   **POST /admin/populate-database**
    *   **Descrição:** Dispara a tarefa de download e população da base SINAPI para um mês/ano específico. A tarefa roda em segundo plano.
    *   **Corpo da Requisição (JSON):**
        *   `year` (inteiro, obrigatório): O ano para o qual os dados do SINAPI devem ser populados (ex: `2025`).
        *   `month` (inteiro, obrigatório): O mês para o qual os dados do SINAPI devem ser populados (ex: `9`).
    *   **Exemplo de `curl`:**
        ```bash
        curl -X POST "http://localhost:8000/admin/populate-database" \
        -H "Content-Type: application/json" \
        -H "X-API-KEY: sua_chave_de_api_aqui" \
        -d '{"year": 2025, "month": 9}'
        ```
    *   **Retorno Esperado:**
        ```json
        {
          "message": "Tarefa de população da base de dados iniciada com sucesso.",
          "task_id": "a-unique-task-id"
        }
        ```

---

Para explorar todos os schemas de dados e a documentação interativa (Swagger UI), acesse `http://localhost:8000/docs` (assumindo que a API esteja rodando localmente na porta 8000).