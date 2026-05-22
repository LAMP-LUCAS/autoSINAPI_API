# 🚀 AutoSINAPI: Acelere Suas Decisões na Construção Civil com Dados Inteligentes

[![Licença](https://img.shields.io/badge/licen%C3%A7a-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Python](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Status](https://img.shields.io/badge/status-alpha-orange.svg)](https://github.com/LAMP-LUCAS/AutoSINAPI/releases)

## 🚧 Cansado de Planilhas e Dados Desatualizados? Conheça o AutoSINAPI!

Para arquitetos, engenheiros e construtores, a gestão de custos e orçamentos é a espinha dorsal de qualquer projeto bem-sucedido. No entanto, a realidade muitas vezes envolve: 

*   **Horas Perdidas:** Coletando, organizando e atualizando manualmente dados do SINAPI.
*   **Decisões Baseadas em Achismos:** A falta de dados precisos e atualizados compromete a assertividade.
*   **Complexidade:** Lidar com a vasta e mutável base de dados do SINAPI é um desafio constante.

O **AutoSINAPI** surge como a solução definitiva para transformar essa realidade. Somos uma ferramenta open-source completa, projetada para automatizar o ciclo de vida dos dados do SINAPI, desde a coleta até a análise, entregando a você **informação precisa e atualizada na palma da mão.**

### ✨ O Que o AutoSINAPI Oferece?

*   **Automação Inteligente:** Diga adeus à tediosa coleta manual. O AutoSINAPI baixa, processa e organiza os dados do SINAPI para você.
*   **Precisão Inquestionável:** Tenha acesso a dados limpos, padronizados e prontos para uso, garantindo orçamentos mais acurados e análises confiáveis.
*   **Visão Estratégica:** Libere seu tempo para focar no que realmente importa: análises estratégicas, otimização de custos e tomadas de decisão embasadas.
*   **Histórico Completo:** Mantenha um registro detalhado das alterações do SINAPI ao longo do tempo, essencial para auditorias e comparações.
*   **Flexibilidade:** Seja você um usuário final buscando uma solução pronta ou um desenvolvedor que precisa integrar dados SINAPI em seus sistemas, o AutoSINAPI se adapta.

---

## 🛠️ Para Desenvolvedores: Robustez, Confiabilidade e Código Aberto

Construído com as melhores práticas de engenharia de software, o AutoSINAPI é mais do que uma ferramenta; é um `toolkit` Python modular, testável e desacoplado.

*   **Arquitetura Modular:** Componentes bem definidos (`downloader`, `processor`, `database`) facilitam a compreensão, manutenção e extensão.
*   **Testes Abrangentes:** Uma suíte de testes robusta garante a estabilidade e a confiabilidade do pipeline, mesmo com as constantes atualizações do SINAPI.
*   **Integração Simplificada:** Projetado para ser facilmente consumido por outras aplicações, como APIs REST (ex: [autoSINAPI_API](https://github.com/LAMP-LUCAS/autoSINAPI_API)) ou CLIs customizadas.
*   **Open Source:** Transparência total e a possibilidade de contribuir para a evolução da ferramenta.

---

## 🚀 Como Começar com o AutoSINAPI

Existem duas maneiras de rodar o pipeline, escolha a que melhor se adapta ao seu fluxo de trabalho.

### Opção 1: Ambiente Docker (Recomendado)

A forma mais simples e recomendada de usar o AutoSINAPI. Com um único comando, você sobe um ambiente completo e isolado com o banco de dados PostgreSQL e o pipeline pronto para rodar.

**Pré-requisitos:**
-   Docker e Docker Compose instalados.

**Passo a Passo:**

1.  **Clone o repositório:**
    ```bash
    git clone https://github.com/LAMP-LUCAS/AutoSINAPI.git
    cd AutoSINAPI
    ```

2.  **Configure o Ambiente:**
    -   Dentro da pasta `tools/docker/`, renomeie o arquivo `.env.example` para `.env`.
    -   Abra o arquivo `.env` e ajuste as variáveis conforme sua necessidade (ano, mês, senhas, etc.).

3.  **(Opcional) Adicione Arquivos Locais:**
    -   Se você já tiver o arquivo `.zip` do SINAPI, coloque-o dentro da pasta `tools/docker/downloads/`. O pipeline irá detectá-lo, renomeá-lo para o padrão correto (se necessário) e pulará a etapa de download.

4.  **Execute o Pipeline:**
    Ainda dentro da pasta `tools/docker/`, execute o comando:
    ```bash
    docker-compose up
    ```
    Este comando irá construir a imagem, subir o container do banco de dados e, em seguida, rodar o container da aplicação que executará o pipeline. Ao final, os containers serão finalizados.

### Opção 2: Ambiente Local (Avançado)

Para quem prefere ter controle total sobre o ambiente e não usar Docker.

**Pré-requisitos:**
-   Python 3.8+ e PostgreSQL 12+ instalados e configurados na sua máquina.

**Passo a Passo:**

1.  **Clone o repositório e instale as dependências** conforme a seção de instalação do `README.md`.
2.  **Configure o acesso ao banco de dados** no arquivo `tools/sql_access.secrets`.
3.  **Crie e ajuste um arquivo de configuração** (ex: `tools/meu_config.json`) a partir do `tools/CONFIG.example.json`.
4.  **Execute o pipeline** via linha de comando:
    ```bash
    python tools/autosinapi_pipeline.py --config tools/meu_config.json
    ```

---

## 🏗️ Arquitetura do Projeto

O **AutoSINAPI** é projetado como um `toolkit` modular e desacoplado, focado em processar dados do SINAPI de forma eficiente e robusta. Sua arquitetura é dividida em componentes principais que interagem para formar um pipeline ETL completo.

Para uma compreensão aprofundada do modelo de dados e do fluxo de execução do ETL, consulte os seguintes documentos:

*   **[Modelo de Dados Detalhado](docs/DataModel.md)**: Descreve as tabelas do banco de dados, seus relacionamentos e a estrutura dos dados.
*   **[Fluxo de Execução do ETL](docs/DataModel.md#3-processo-de-etl-fluxo-de-execucao-detalhado)**: Detalha as fases do processo de Extração, Transformação e Carga, desde a obtenção dos dados até a persistência no banco de dados.

---

## Versionamento e Estratégia de Lançamento

O versionamento deste projeto é **totalmente automatizado com base nas tags do Git**. Para mais detalhes, consulte a documentação sobre o fluxo de trabalho do Git.

## 🌐 Ecossistema AutoSINAPI

-   **[autoSINAPI_API](https://github.com/LAMP-LUCAS/autoSINAPI_API):** API para consumir os dados do banco de dados SINAPI.

## 🤝 Como Contribuir

O **AutoSINAPI** é um projeto open-source que cresce com a comunidade! Sua contribuição é fundamental, seja ela qual for. Cada ajuda nos impulsiona a construir uma ferramenta cada vez mais robusta e útil para todos.

**Como você pode ajudar?**

*   **Reporte Bugs:** Encontrou um problema? Sua observação é valiosa! Abra uma [Issue no GitHub](https://github.com/LAMP-LUCAS/AutoSINAPI/issues) descrevendo o bug. Isso nos ajuda a identificar e corrigir falhas rapidamente.
*   **Sugira Novas Funcionalidades:** Tem uma ideia para melhorar o AutoSINAPI? Compartilhe conosco abrindo uma [Issue de Feature Request](https://github.com/LAMP-LUCAS/AutoSINAPI/issues).
*   **Contribua com Código:** Se você é desenvolvedor, suas habilidades são muito bem-vindas! Contribua com novas funcionalidades, correções de bugs ou melhorias no código. Consulte nosso guia de contribuição para começar: [Como Contribuir](docs/CONTRIBUTING.md).
*   **Documentação:** Ajude a melhorar nossa documentação, tornando-a mais clara e completa.
*   **Divulgue:** Compartilhe o AutoSINAPI com sua rede! Quanto mais pessoas conhecerem, maior nossa comunidade.
*   **Apoie com um Cafezinho:** Gosta do projeto e quer nos ajudar a manter o ritmo? Considere fazer uma pequena doação para o "cafezinho" da equipe. Seu apoio financeiro, por menor que seja, faz uma grande diferença!  
🔑 Chave Pix: `a03ffaea-d46f-4dc6-a372-2b4fa8b0385f` copie e cole no seu app bancário ou \
📋 Use nosso link de pagamento pelo [MercadoPago](link.mercadopago.com.br/autosinapi)

**Junte-se a nós e faça parte desta jornada!**

Para detalhes sobre como configurar seu ambiente de desenvolvimento, padrões de código, fluxo de trabalho e muito mais, consulte nosso guia completo: [Como Contribuir](docs/CONTRIBUTING.md).

## 📝 Licença

Distribuído sob a licença **GNU General Public License v3.0**.
