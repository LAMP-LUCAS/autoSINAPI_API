# 📐 Arquitetura da API — Híbrida MVC-Hexagonal

Este documento descreve a arquitetura da aplicação **autoSINAPI API**, estruturada sob um padrão híbrido que combina o fluxo MVC (Model-View-Controller) tradicional de rotas HTTP com a arquitetura de **Portas e Adaptadores (Hexagonal)** para a isolação do domínio de negócios.

---

## 1. Visão Arquitetural

A aplicação separa as preocupações em camadas concêntricas. O Core do Domínio está no centro, blindado de dependências tecnológicas externas (como o framework FastAPI ou drivers específicos de banco de dados).

```mermaid
C4Container
    title C4 Container - autoSINAPI API (MVC-Hexagonal)

    Person(client, "Cliente / Desenvolvedor", "Consome os endpoints via HTTP")
    
    Container_Boundary(api, "autoSINAPI API") {
        Component(inbound_adapter, "FastAPI Controllers (Adapters)", "Python/FastAPI", "Recebe HTTP, sanitiza inputs, gerencia injeção de dependência")
        Component(inbound_port, "Pydantic Schemas (Ports)", "Python", "Valida payloads e serializa respostas")
        Component(core, "Core Domain (Services)", "Python", "Regras de negócio puro: BOM recursiva, Otimização ABC")
        Component(outbound_port, "Repository Interfaces (Ports)", "Python", "Assinaturas abstratas de persistência")
        Component(outbound_adapter_db, "SQLAlchemy + asyncpg (Adapter)", "Python", "Implementa persistência no PostgreSQL")
        Component(outbound_adapter_cache, "Redis Decorator (Adapter)", "Python", "Gerencia fallback no cache")
    }

    SystemDb(postgres, "PostgreSQL Database", "Dados do SINAPI com índices GIN")
    SystemDb(redis, "Redis Cache", "Armazenamento em memória (Buscas Textuais)")

    Rel(client, inbound_adapter, "Requisições RESTful", "HTTPS/JSON")
    Rel(inbound_adapter, inbound_port, "Valida e desserializa", "DTOs")
    Rel(inbound_port, core, "Invoca lógica de negócio")
    Rel(core, outbound_port, "Delega requisição de dados")
    Rel(outbound_port, outbound_adapter_db, "Invocado via Injeção de Dependência")
    Rel(outbound_port, outbound_adapter_cache, "Invocado via Injeção de Dependência")
    Rel(outbound_adapter_db, postgres, "Queries assíncronas", "TCP/asyncpg")
    Rel(outbound_adapter_cache, redis, "Leitura/Escrita de Cache", "TCP/redis-py")
```

---

## 2. Detalhamento das Camadas e Componentes

### 2.1. Camada Core Domain
Contém as entidades puras e a lógica analítica do SINAPI. Não faz importação de nenhum framework web.
*   **Serviços de Domínio:** Lógica recursiva da CTE de explosão da BOM, cálculo de produtividade (mão de obra vs. equipamento) e o ranqueamento financeiro para a Curva ABC.

### 2.2. Camada Application (Ports)
Define os contratos que permitem a comunicação com o mundo externo.
*   **Inbound Ports:** Schemas Pydantic (`schemas.py`) que validam os dados recebidos na requisição e determinam o formato de serialização do JSON de saída.
*   **Outbound Ports:** Contratos lógicos de persistência. A lógica do `crud.py` consome a interface de sessão do banco de dados (SQLAlchemy Session) fornecida na injeção de dependências.

### 2.3. Camada Infrastructure (Adapters)
Implementações concretas de I/O.
*   **Inbound Adapters (Controllers):** Os arquivos [api/main.py](file:///z:/repos/autosinapi_api/api/main.py) que contêm as rotas FastAPI. Recebem as requisições HTTP, executam a sanitização e invocam a camada de aplicação/serviço.
*   **Outbound Adapters:**
    *   **Postgres Adapter:** Gerenciado por [api/database.py](file:///z:/repos/autosinapi_api/api/database.py). Conecta a aplicação ao PostgreSQL.
    *   **Cache Adapter:** Gerenciado por [api/cache_utils.py](file:///z:/repos/autosinapi_api/api/cache_utils.py). Implementa o cliente Redis e o decorator `@cache_result` para encapsular a lógica de cache transparente.
    *   **Event Adapter (opt-in):** Gerenciado por [api/etl_events.py](file:///z:/repos/autosinapi_api/api/etl_events.py). Publica o evento de domínio `etl.completed` via webhook quando `ETL_EVENT_WEBHOOK_URL` está configurada. **Best-effort**: falha do consumidor nunca comprometa o ETL. Ver §4.

---

## 4. Evento de Integração `etl.completed` (Adapter de Eventos)

Contrato opcional para que consumidores externos reajam à conclusão de uma
execução de ETL **sem que este repositório saiba quem são** — o consumidor é
definido exclusivamente por configuração de deploy, nunca por código.

### 4.1. Regras de domínio

| Regra | Significado |
|-------|-------------|
| **Opt-in** | Sem `ETL_EVENT_WEBHOOK_URL`, o módulo é *no-op* (nenhuma saída de rede nova). Padrão do open source inalterado. |
| **Payload neutro** | Somente vocabulário do contexto do ETL (competência, status, task, registros). Vocabulário de outros domínios (campanha, leads, clientes, entrega de mensagens, templates, tópicos) é **proibido** — assegurado por teste (`tests/test_etl_events.py`), atuando como *anti-corruption layer*. |
| **Best-effort** | Timeout curto (`ETL_EVENT_TIMEOUT`, 5s) e erros engolidos com log. Publicar evento **nunca** altera o resultado da task nem a liberação do lock do ETL. |
| **Best-effort ≠ sem retentativa** | Falha **de uma** tentativa não é o fim: até `ETL_EVENT_TENTATIVAS` (padrão 3) tentativas, com backoff `ETL_EVENT_BACKOFF` exponencial (1s, 4s) e jitter de 25% — a janela comum de indisponibilidade do consumidor (restart, deploy) é atravessada. `ETL_EVENT_TENTATIVAS=1` volta ao comportamento de 1x. O **payload é idêntico** em todas as tentativas (o contrato não muda por causa de uma retentativa) e o timeout por tentativa não cresce. Pior caso: `3 × timeout + 1s + 4s` de espera. |
| **O ETL não decide** | Publica o status terminal real (`success` \| `failure` \| `no_data`); a regra de negócio de reagir a ele é de quem consome. |

### 4.2. Contrato do payload

```json
{
  "event": "etl.completed",
  "source": "autosinapi",
  "year": 2026,
  "month": 8,
  "status": "success",
  "task_id": "50339024-2986-41ec-b401-4043d1305c34",
  "records_inserted": 1619900,
  "published_at": "2026-09-30T14:02:31.120000+00:00"
}
```

| Campo | Tipo | Observação |
|-------|------|-----------|
| `event` | str | Sempre `etl.completed` (nome canônico do evento). |
| `source` | str | Origem: `autosinapi`. |
| `year` / `month` | int | Competência processada. |
| `status` | str | `success` \| `failure` \| `no_data` (ou `unknown`). |
| `task_id` | str\|null | ID da task orquestradora, quando houver. |
| `records_inserted` | int\|null | Total de registros informado pelo ETL. |
| `published_at` | str | Timestamp ISO-8601 UTC do disparo. |

### 4.3. Configuração

```bash
# .env (opcional)
ETL_EVENT_WEBHOOK_URL=http://consumidor.local:5678/webhook/etl-event
ETL_EVENT_TIMEOUT=5.0
```

---

## 3. Direção de Dependência (Regra de Ouro)

Nenhuma classe, função ou variável declarada nas camadas mais internas (Core Domain) pode fazer referência ou importar componentes das camadas mais externas (FastAPI, Redis ou SQLAlchemy). Isso assegura a manutenibilidade e permite que a API Mínima (código livre) possa ser facilmente reutilizada ou portada para outros frameworks ou bancos de dados sem quebrar a lógica de negócio.
