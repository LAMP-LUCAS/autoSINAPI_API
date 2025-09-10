# 🚀 autoSINAPI API: A sua ponte para os dados do SINAPI.

[![Versão](https://img.shields.io/badge/version-alpha1-blue.svg)](https://github.com/LAMP-LUCAS/autoSINAPI_API)
[![Licença](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Docker](https://img.shields.io/badge/Docker-Ready-blue?logo=docker)](https://www.docker.com/)
[![Powered by: FastAPI](https://img.shields.io/badge/Powered%20by-FastAPI-green?logo=fastapi)](https://fastapi.tiangolo.com/)

**Chega de perder horas com planilhas complexas e dados desatualizados.** A autoSINAPI API é a solução definitiva para desenvolvedores, engenheiros e orçamentistas que precisam de acesso rápido, estruturado e confiável aos custos da construção civil no Brasil.

Nós transformamos o caos de arquivos ZIP e PDFs da Caixa em uma API RESTful inteligente, pronta para alimentar seus sistemas, dashboards e inovações.

---

### 💡 O Fim da Dor de Cabeça Mensal

Se você trabalha com orçamentos de obra, sabe o quão repetitivo e frustrante é o processo de usar os dados do SINAPI. Nós também sabíamos, e por isso criamos uma solução.

| ❌ **O Jeito Antigo (e Doloroso)** | ✅ **A Solução autoSINAPI API** |
| ------------------------------------ | ----------------------------------- |
| Baixar e tratar planilhas todo mês.  | Acesso instantâneo via API RESTful. |
| Dados brutos e de difícil análise.   | Respostas em JSON, prontas para uso. |
| Processos lentos e manuais.          | Performance para seus apps e BI.    |
| Banco de dados desatualizado.        | Dados sempre atualizados.           |

---

### ⚡ Comece a Usar em 5 Minutos (Auto-Hospedado)

Tenha sua própria instância da API, com banco de dados e toda a infraestrutura, rodando localmente com apenas 5 passos.

1.  **Clone o Repositório**
    ```bash
    git clone https://github.com/LAMP-LUCAS/autoSINAPI_API.git
    cd autoSINAPI_API
    ```

2.  **Configure o Ambiente**
    Copie o arquivo de exemplo `.env.example` para um novo arquivo chamado `.env`. Nenhuma alteração é necessária para começar.
    ```bash
    cp .env.example .env
    ```

3.  **Suba a Infraestrutura com Docker**
    Este comando usa o `Makefile` para orquestrar a construção e execução de todos os serviços em segundo plano.
    ```bash
    make up
    ```

4.  **Popule o Banco de Dados**
    Execute o comando para iniciar a tarefa de ETL, que irá baixar e inserir os dados do SINAPI.
    ```bash
    make populate-db
    ```
    *Este processo pode levar alguns minutos. Você pode acompanhar o progresso com `docker-compose logs -f celery_worker`.*

5.  **(Opcional) Usando Arquivos SINAPI Locais**
    Para pular a etapa de download (ideal para usar dados históricos ou em ambientes offline), você pode usar arquivos `.zip` do SINAPI.

    1.  Crie uma subpasta dentro de `autosinapi_downloads` com o nome no formato `AAAA_MM` (ex: `2024_07`).
    2.  Coloque o arquivo `.zip` do SINAPI correspondente a essa data dentro desta subpasta.

    Quando você executar `make populate-db`, o sistema irá detectar o arquivo local e usá-lo para a carga de dados, ignorando o download.

6.  **Gere sua Chave e Faça a Primeira Consulta!**
    Sua API está no ar, protegida por um gateway. Para usá-la, basta criar um "consumidor" e gerar uma chave de acesso.

    ```bash
    # 1. Crie um consumidor (usuário) para a API
    curl -X POST http://localhost:8001/consumers/ --data "username=meu-usuario"

    # 2. Gere uma chave de acesso para ele (copie o valor de "key")
    curl -X POST http://localhost:8001/consumers/meu-usuario/key-auth/

    # 3. Faça sua primeira consulta! (substitua SUA_CHAVE_AQUI)
    curl -X GET "http://localhost:8000/api/v1/ufs/sp/municipios" \
      -H "apikey: SUA_CHAVE_AQUI"
    ```
    **Pronto!** Explore todos os outros endpoints na documentação interativa em [http://localhost:8000/docs](http://localhost:8000/docs).

---

### 🎛️ Painel de Controle via `make`

Use estes comandos para gerenciar seu ambiente facilmente.

| Comando | Descrição |
|---|---|
| `make up` | Inicia todo o ambiente Docker. |
| `make down` | Para todos os serviços e remove contêineres/volumes. |
| `make populate-db`| Dispara a tarefa de ETL para popular o banco de dados. |
| `make logs-api` | Exibe os logs da API em tempo real. |
| `make status` | Mostra o status de todos os contêineres. |

---

### 🧠 Inteligência de Negócio na Ponta dos Dedos

A autoSINAPI API vai além de simples consultas. Oferecemos endpoints de BI que entregam análises valiosas:

-   **Estrutura Analítica (BOM):** Exploda uma composição em sua árvore completa de custos.
-   **Curva ABC:** Envie seu orçamento e descubra quais insumos representam 80% do seu custo.
-   **Otimizador de Custo:** Identifique os maiores vilões de custo em qualquer serviço.
-   **Série Histórica:** Analise a "inflação" de um insumo ou composição ao longo do tempo.

---

### 💼 Do Open Source para o Profissional: Apoie o Projeto!

Manter um projeto open source desta complexidade exige tempo e recursos. A versão auto-hospedada é perfeita para estudantes, testes e entusiastas.

**Para uso comercial, aplicações críticas e para garantir a continuidade deste projeto, considere usar nossa API profissional.**

- **Zero Infraestrutura:** Esqueça Docker, servidores e atualizações. Apenas consuma a API.
- **Alta Disponibilidade e Escalabilidade:** Conte com um ambiente robusto e monitorado.
- **Suporte Prioritário:** Tenha um canal direto para tirar dúvidas e resolver problemas.

Ao se tornar um assinante, você não apenas obtém um serviço superior, mas também **investe diretamente na evolução e manutenção da ferramenta** que beneficia toda a comunidade.

**Seja um apoiador. Conheça os planos em [mundoaec.com/autosinapi](https://mundoaec.com/autosinapi).**

---

### 🤝 Faça Parte da Comunidade

Sua contribuição é a força motriz do open source.

- **Reporte Bugs:** Encontrou um problema? Abra uma *Issue*.
- **Sugira Melhorias:** Tem uma ideia para uma nova funcionalidade de BI? Vamos conversar!
- **Envie Código:** Siga nosso [**Guia de Contribuição (`CONTRIBUTING.md`)**](./CONTRIBUTING.md) e ajude a construir o futuro da análise de custos.

**Junte-se a nós na missão de modernizar o acesso a dados na construção civil!**
