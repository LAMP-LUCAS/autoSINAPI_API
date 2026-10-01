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

## 4. Leitura do Funil: Aquisição, Receita e Retenção (2026-10-01)

Três endpoints acrescentados em `api/admin_crm.py`. Todos exigem o token admin
e **excluem tráfego de teste** (`is_test`), como o resto do painel.

### 4.1. `GET /api/v1/admin/leads/attribution?days=90`

De onde vêm os leads. O portal grava `utm_*`, `referrer` e `landing_path` em
`saas.leads.metadata.attribution` no momento da captura; sem isso o traffic
source é irrecuperável depois do contato.

```json
{
  "days": 90,
  "totals": { "leads": 10, "com_atribuicao": 2, "cobertura_pct": 20.0 },
  "by_utm_source":    [{ "origem": "(direct)", "leads": 8, "convertidos": 3, "taxa_conversao_pct": 37.5 }],
  "by_source":        [ ... ],
  "by_landing_path":  [ ... ]
}
```

Leads sem atribuição — porque não consentiram com marketing, ou porque são
anteriores à coleta — contam como **`(direct)`**. Ausência não é zero: sem
isso, 8 de 10 leads sem UTM apareceriam como "origem desconhecida".

`cobertura_pct` é a métrica a vigiar: com 20% de cobertura, o relatório ainda
não sustenta decisão de canal.

### 4.2. `GET /api/v1/admin/dashboard` → `revenue`

```json
{ "mrr_brl": 1035.07, "mrr_paid_brl": 0, "arr_brl": 6340.0,
  "subs_pagas": 4, "subs_com_cobranca": 0, "expira_7d": 0, "expira_30d": 1 }
```

Dois cuidados, ambos verificados com dados:

- **MRR normaliza por `duration_days`**: `business_anual` a R$ 2.890,00 não é
  R$ 2.890/mês. Sem `price_cents * (30 / duration_days)` o MRR mente por um
  fator de 12.
- **`mrr_paid_brl` só conta assinatura com `mp_payment_id`**. As duas colunas
  hoje divergem de propósito: as 4 assinaturas pagas ativas vieram de
  concessão/E2E, sem cobrança. `mrr_paid_brl = 0` é o estado honesto do funil —
  e é o número que o primeiro pagamento real precisa mover.

### 4.3. `GET /api/v1/admin/retention?days=90`

```json
{ "ativacao": { "assinaturas": 15, "ativadas": 10, "taxa_ativacao_pct": 66.7 },
  "churn":    { "canceladas": 0, "base_periodo": 0, "churn_pct": null },
  "renovacao": { "renovadas": 0, "vencidas_no_periodo": 4, "taxa_renovacao_pct": 0.0 },
  "dunning_30d": [ { "email": "...", "plano": "...", "current_period_end": "..." } ] }
```

- **Ativação** = assinatura com ≥10 chamadas em 7 dias. Abaixo disso é onboarding
  abandonado, não cliente.
- **Denominador zero devolve `null`, nunca `0%`** — `churn_pct: null` com
  `base_periodo: 0` significa "ainda não há base para medir", não "churn zero"
  (SR-DATA-01 / ADR-060).
- **Renovação** conta no numerador apenas quem já venceu no período. Contar quem
  ainda não venceu dava 275% — o numerador tem de ser subconjunto do
  denominador.
- **`dunning_30d`** é a fila que a automação de cobrança vai consumir quando
  existir base pagante. Hoje ela não dispara nada (ver
  `repos/saas-gateway/emails/registry.yaml`, templates marcados "sem gatilho").

### Por que isto está preparado e não ativo

NPS, dunning, win-back e open/click foram deliberadamente **não**
implementados como disparo. Não há `mp_payment_id` em assinatura alguma: mandar
"atualize seu cartão" ou "seu plano renova" para quem nunca foi cobrado seria
ameaça de cobrança sem cliente. As métricas acima é o que se pode medir com
honestidade hoje; o resto depende do primeiro pagamento real.

---

Para explorar todos os endpoints disponíveis na API, incluindo os de consulta de dados, acesse a documentação interativa (Swagger UI) em `http://localhost:8000/docs` (assumindo que a API esteja rodando localmente na porta 8000).