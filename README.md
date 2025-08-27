# AutoSINAPI API

[](https://opensource.org/licenses/MIT)
[](https://www.docker.com/)
[](https://www.python.org/)

Um ecossistema open-source completo para transformar os dados públicos do SINAPI (Sistema Nacional de Pesquisa de Custos e Índices da Construção Civil) em uma API de alta performance, robusta, escalável e pronta para monetização através de um sistema de planos (tiers).

Este projeto automatiza a coleta, armazenamento e, principalmente, o consumo dos dados de insumos e composições do SINAPI, oferecendo um ponto de acesso centralizado e fácil de integrar para desenvolvedores, engenheiros e empresas do setor de construção.

## Por que usar esta API?

O acesso aos dados do SINAPI geralmente envolve baixar planilhas pesadas, tratá-las manualmente e importá-las para um sistema. Este projeto elimina todo esse trabalho, oferecendo:

  - **🚀 Economia de Tempo:** Tenha acesso a preços atualizados sem nenhum trabalho manual.
  - **⚡ Alta Performance:** Respostas rápidas e eficientes, ideal para sistemas que precisam de agilidade.
  - **🔧 API Developer-Friendly:** Documentação interativa automática (via FastAPI/Swagger) para facilitar a integração.
  - **📈 Escalabilidade e Controle:** O API Gateway (Kong) gerencia autenticação, segurança e limites de uso, permitindo desde um uso gratuito e limitado até planos empresariais de alto volume.
  - **📦 Conteinerizado com Docker:** Todo o ambiente (banco de dados, API, gateway) sobe com um único comando, garantindo consistência e facilidade de implantação.
  - **🌐 100% Open-Source:** Liberdade para usar, modificar e contribuir.

## Arquitetura do Ecossistema

O projeto utiliza uma arquitetura moderna baseada em microserviços, orquestrada pelo Docker Compose:

```
+----------------+      +---------------------------+      +--------------------+      +-------------------------+
|                |      |                           |      |                    |      |                         |
|  Usuário Final |----->|     Kong API Gateway      |----->|   API FastAPI      |----->|   Banco de Dados        |
|  (Aplicação)   |      |   (Porta 8000)            |      |   (Python)         |      |   PostgreSQL            |
|                |      | - Autenticação (API Key)  |      | - Lógica de negócio|      | - Dados SINAPI          |
|                |      | - Rate Limiting (Planos)  |      | - Endpoints        |      | - Dados Kong            |
|                |      |                           |      |                    |      | - Dados de Usuários     |
+----------------+      +---------------------------+      +--------------------+      +-------------------------+
                             ^
                             | (Admin via Porta 8001)
                             |
                      +----------------+
                      | Administrador  |
                      | (Criação de    |
                      |  chaves/planos)|
                      +----------------+
```

## Tecnologias Utilizadas

  - **Backend:** Python 3.10+ com [FastAPI](https://fastapi.tiangolo.com/)
  - **Banco de Dados:** [PostgreSQL](https://www.postgresql.org/)
  - **API Gateway:** [Kong](https://konghq.com/kong/)
  - **Servidor ASGI:** [Uvicorn](https://www.uvicorn.org/)
  - **Conteinerização:** [Docker](https://www.docker.com/) e [Docker Compose](https://docs.docker.com/compose/)

## Estrutura de Diretórios

```
/AutoSINAPI/
├── auto_sinapi/          # Script original para popular o banco de dados
├── api/                    # Código-fonte da API em FastAPI
│   ├── main.py
│   ├── crud.py
│   ├── schemas.py
│   └── database.py
├── kong/                   # Configuração declarativa do Kong
│   └── kong.yml
├── .env                    # Arquivo local com suas variáveis de ambiente
├── .env.example            # Arquivo de exemplo para as variáveis de ambiente
├── .gitignore
├── docker-compose.yml      # Orquestrador de todos os serviços
├── Dockerfile              # Receita para construir a imagem da API
└── README.md               # Este arquivo
```

-----

## Guia de Implementação Rápida

Siga estes passos para ter todo o ecossistema rodando em sua máquina local ou servidor.

### 1\. Pré-requisitos

Certifique-se de ter os seguintes softwares instalados:

  - [Git](https://git-scm.com/)
  - [Docker](https://docs.docker.com/engine/install/)
  - [Docker Compose](https://docs.docker.com/compose/install/) (geralmente já vem com o Docker Desktop)

### 2\. Clone o Repositório

```bash
git clone https://github.com/LAMP-LUCAS/AutoSINAPI.git
cd AutoSINAPI
```

### 3\. Configure o Ambiente

Crie um arquivo `.env` a partir do exemplo. Este arquivo conterá todas as senhas e configurações sensíveis.

```bash
cp .env.example .env
```

Agora, **edite o arquivo `.env`** e ajuste as senhas e configurações conforme sua necessidade. Ele será parecido com isto:

```env
# .env

# === Configs do PostgreSQL ===
POSTGRES_DB=sinapi
POSTGRES_USER=admin
POSTGRES_PASSWORD=sua_senha_forte_aqui

# === Configs do Kong (Gateway) ===
KONG_DB_USER=kong
KONG_DB_PASSWORD=outra_senha_forte_aqui
KONG_PG_HOST=db

# === Configs da API (FastAPI) ===
# URL de conexão que a API usará para se conectar ao banco de dados.
# O host 'db' é o nome do serviço do postgres no docker-compose.
DATABASE_URL=postgresql://admin:sua_senha_forte_aqui@db:5432/sinapi
```

### 4\. Construa e Inicie os Serviços

O comando a seguir irá construir a imagem da API, baixar as imagens do PostgreSQL e Kong, e iniciar todos os contêineres em segundo plano.

```bash
docker-compose up --build -d
```

Aguarde alguns instantes para que todos os serviços iniciem e o banco de dados do Kong seja preparado. Para verificar se tudo está rodando, use `docker-compose ps`.

### 5\. Popule o Banco de Dados (Primeira Vez)

Com os serviços no ar, você precisa rodar seu script original para baixar os dados do SINAPI e inseri-los no banco de dados. Você pode fazer isso executando o script dentro de um contêiner temporário que se conecta à mesma rede.

*(Nota: Este passo depende de como seu script `auto_sinapi` funciona. Adapte o comando abaixo se necessário.)*

```bash
# Exemplo de como rodar o script (pode precisar de adaptação)
docker-compose run --rm api python -m auto_sinapi.seu_script_principal
```

### 6\. Configure o API Gateway (Kong)

Agora, vamos configurar o Kong para proteger e gerenciar nossa API. Já existe um arquivo `kong/kong.yml` com a configuração básica. Para aplicá-lo, você pode usar uma ferramenta como o [deck](https://docs.konghq.com/deck/).

*Para simplificar, por enquanto faremos a configuração via `curl` na API Admin do Kong.*

**a) Registre o serviço da API no Kong:**

```bash
curl -i -X POST http://localhost:8001/services/ \
  --data name=sinapi-api \
  --data url=http://api:8000
```

**b) Crie uma rota para o serviço:**

```bash
curl -i -X POST http://localhost:8001/services/sinapi-api/routes \
  --data 'paths[]=/' \
  --data name=sinapi-route
```

**c) Habilite o plugin de autenticação por chave (key-auth):**

```bash
curl -i -X POST http://localhost:8001/services/sinapi-api/plugins \
  --data name=key-auth \
  --data config.key_names=X-API-KEY
```

**d) Habilite o plugin de limite de requisições (rate-limiting) para o Plano FREE:**
Isso define um limite padrão para todos os usuários de 250 chamadas por dia e 30 por minuto.

```bash
curl -i -X POST http://localhost:8001/services/sinapi-api/plugins \
  --data name=rate-limiting \
  --data "config.day=250" \
  --data "config.minute=30" \
  --data "config.policy=local"
```

### 7\. Crie seu Primeiro Consumidor e Chave de API

Agora você pode simular a criação de um "usuário" (chamado de `consumer` no Kong) e gerar uma chave para ele.

**a) Crie um consumidor (ex: "dev\_joao"):**

```bash
curl -i -X POST http://localhost:8001/consumers/ \
  --data username=dev_joao
```

**b) Gere uma chave de API para o `dev_joao`:**

```bash
curl -i -X POST http://localhost:8001/consumers/dev_joao/key-auth/
```

Copie a `key` retornada no JSON. Será algo como `k_...`. **Essa é a chave que seu usuário usará.**

### 8\. Teste a API\!

Sua API agora está protegida e disponível na porta `8000`. As requisições devem incluir a chave no cabeçalho `X-API-KEY`.

```bash
# Substitua SUA_CHAVE_AQUI pela chave que você gerou no passo anterior
curl -i -X GET http://localhost:8000/insumos/search/?q=CIMENTO \
  -H "X-API-KEY: SUA_CHAVE_AQUI"
```

Se você remover o cabeçalho `-H "X-API-KEY: ..."` ou usar uma chave inválida, receberá um erro `401 Unauthorized`. Se exceder o limite, receberá um `429 Too Many Requests`.

## Modelo de Planos (Open Source)

Este setup já implementa um sistema de planos. Para criar um usuário com um plano diferente (ex: **Individual** com 10.000 chamadas/dia), você pode aplicar uma configuração de `rate-limiting` específica para aquele consumidor:

```bash
# 1. Crie um novo consumidor "cliente_premium"
curl -i -X POST http://localhost:8001/consumers/ --data username=cliente_premium

# 2. Gere a chave para ele (guarde a chave retornada)
curl -i -X POST http://localhost:8001/consumers/cliente_premium/key-auth/

# 3. Aplique um limite de requisições customizado para ele
curl -i -X POST http://localhost:8001/consumers/cliente_premium/plugins \
  --data name=rate-limiting \
  --data "config.day=10000" \
  --data "config.minute=120" \
  --data "config.policy=local"
```

Agora, a chave do `cliente_premium` terá limites maiores que a do `dev_joao`.

## Como Contribuir

Contribuições são muito bem-vindas\! Se você tem ideias para novas funcionalidades, melhorias na performance ou correção de bugs, siga estes passos:

1.  Faça um Fork do projeto.
2.  Crie uma nova Branch (`git checkout -b feature/sua-feature`).
3.  Faça suas alterações e realize o Commit (`git commit -m 'Adiciona nova feature'`).
4.  Envie para a sua Branch (`git push origin feature/sua-feature`).
5.  Abra um Pull Request.

## Licença

Este projeto está licenciado sob a Licença MIT. Veja o arquivo `LICENSE` para mais detalhes.
