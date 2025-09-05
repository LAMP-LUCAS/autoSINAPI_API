# 🚀 AutoSINAPI API: Acesso Instantâneo e Estruturado aos Dados da Construção Civil

[![Versão](https://img.shields.io/badge/version-alpha1-blue.svg)](https://github.com/LAMP-LUCAS/autoSINAPI_API)
[![Licença](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Docker](https://img.shields.io/badge/Docker-Ready-blue?logo=docker)](https://www.docker.com/)
[![Powered by: FastAPI](https://img.shields.io/badge/Powered%20by-FastAPI-green?logo=fastapi)](https://fastapi.tiangolo.com/)

**Transforme horas de trabalho manual com planilhas em milissegundos de resposta de API.** O AutoSINAPI API é um ecossistema completo e open source que resolve o problema crônico de acesso aos dados do SINAPI, servindo informações de insumos e composições de forma rápida, confiável e sempre atualizada.

---

### 💡 A Dor que Curamos: O Fim das Planilhas Gigantes

Se você é desenvolvedor, orçamentista ou engenheiro no setor AEC (Arquitetura, Engenharia e Construção), você conhece a rotina:

| ❌ **O Jeito Antigo (e Doloroso)** | ✅ **A Solução AutoSINAPI API** |
| ---------------------------------------------------------------- | -------------------------------------------------------------- |
| Baixar arquivos ZIP de dezenas de megabytes todo mês.            | Acesso instantâneo aos dados via uma chamada de API.           |
| Lidar com planilhas complexas, inconsistentes e de difícil parse. | Respostas em JSON limpo, padronizado e pronto para uso.        |
| Gastar horas limpando, tratando e importando dados.              | O ETL é nosso problema, não o seu.                             |
| Manter um banco de dados próprio, complexo e desatualizado.      | Dados sempre atualizados com a última referência da Caixa.     |
| Processos lentos que travam a inovação e a agilidade.            | Performance para alimentar seus sistemas, dashboards e apps.   |

**Nosso objetivo é simples: devolver seu tempo e potenciar suas aplicações com dados de qualidade.**

---

### ⚡️ Como Usar: Escolha o Caminho Ideal para Você

Existem duas maneiras de aproveitar o poder do AutoSINAPI API, pensadas para diferentes necessidades.

#### **Opção 1: Consumir a API Pública (Para Desenvolvedores e Empresas)**

A forma mais rápida e fácil de integrar os dados do SINAPI ao seu projeto. Sem se preocupar com infraestrutura, atualizações ou manutenção. Foco total no seu negócio.

**Comece a usar em 3 passos:**
1.  **Obtenha sua Chave de API:** [Cadastre-se aqui!](https://www.mundoaec.com/autoSINAPI_API)
2.  **Consulte a Documentação Interativa:** Acesse `https://autosinapi.mundoaec.com/docs` para ver todos os endpoints e testá-los ao vivo.
3.  **Faça sua Primeira Requisição:**

    ```bash
    # Exemplo: Buscando por "CIMENTO"
    curl -X GET "[https://autosinapi.mundoaec.com/insumos/search/?q=CIMENTO](https://autosinapi.mundoaec.com/insumos/search/?q=CIMENTO)" \
      -H "X-API-KEY: SUA_CHAVE_API_AQUI"
    ```
**Pronto!** Você receberá uma resposta JSON com os dados estruturados, prontos para serem usados em seu sistema.

---

#### **Opção 2: Auto-Hospedagem (Para a Comunidade Open Source e Entusiastas)**

Tenha controle total sobre o ambiente, personalize o código e use sem limites. Ideal para quem quer aprender, contribuir ou precisa de uma solução 100% customizada. Graças ao Docker e ao `Makefile`, a instalação é surpreendentemente simples.

**Guia Rápido de Instalação:**

1.  **Clone o repositório:**
    ```bash
    git clone [https://github.com/LAMP-LUCAS/autoSINAPI_API.git](https://github.com/LAMP-LUCAS/autoSINAPI_API.git)
    cd autoSINAPI_API
    ```

2.  **Configure seu ambiente:**
    Copie o arquivo de exemplo `.env.example` para `.env` e, se necessário, ajuste as senhas. Os padrões já funcionam localmente.
    ```bash
    cp .env.example .env
    ```

3.  **Inicie todos os serviços com um único comando:**
    Este comando irá construir as imagens, baixar o que for preciso e iniciar o banco de dados, a API, o gateway e todos os componentes em segundo plano.
    ```bash
    make up
    ```

4.  **Popule seu banco de dados:**
    Execute este comando para acionar o módulo `AutoSINAPI`, que fará o download da referência mais recente da Caixa e a inserirá no seu banco de dados.
    ```bash
    make populate-db
    ```

**Pronto!** Sua API está no ar, acessível em `http://localhost:8000`. Agora você só precisa [gerar sua chave de API local](#-gerenciando-o-ambiente-com-make) e começar a usar.

---

### 🔧 Arquitetura e Tecnologias

Este projeto é um ecossistema de microserviços orquestrado com Docker Compose, garantindo isolamento, escalabilidade e robustez.

* **API Gateway (Kong):** Gerencia toda a autenticação, segurança e limites de uso (rate limiting).
* **API Backend (FastAPI):** A aplicação principal que serve os endpoints de consulta de dados.
* **Banco de Dados (PostgreSQL):** Armazena de forma otimizada todos os dados do SINAPI.
* **Fila de Tarefas (Redis):** Gerencia as tarefas de longa duração, como a população do banco.
* **Worker (Celery):** O "trabalhador" que executa as tarefas pesadas (usando o módulo `AutoSINAPI`) em segundo plano, sem travar a API.
* **Toolkit de ETL (AutoSINAPI):** O cérebro por trás da coleta e tratamento dos dados.

---

### 🎛️ Gerenciando o Ambiente com `make`

Para facilitar a vida de quem auto-hospeda, criamos um painel de controle simples via `Makefile`.

| Comando           | Descrição                                                          |
|-------------------|--------------------------------------------------------------------|
| `make up`         | Inicia todo o ambiente Docker em segundo plano.                    |
| `make down`       | Para todos os serviços e remove os contêineres e volumes.           |
| `make populate-db`| Executa o script de download e inserção dos dados do SINAPI.       |
| `make logs-api`   | Exibe os logs do contêiner da API em tempo real.                   |
| `make logs-kong`  | Exibe os logs do contêiner do Kong Gateway.                        |
| `make status`     | Mostra o status atual de todos os contêineres.                     |

**Para gerar sua chave de API localmente:**
```bash
# 1. Crie um "consumidor" (usuário)
curl -X POST http://localhost:8001/consumers/ --data username=meu-usuario-local

# 2. Gere a chave para ele (copie a "key" da resposta)
curl -X POST http://localhost:8001/consumers/meu-usuario-local/key-auth/