# Plano de Implementação: Dashboard Demo (Free Tier) - AutoSINAPI

## Objetivo
Criar um dashboard de demonstração em HTML/CSS/JS (Vanilla) para a AutoSINAPI, acessível via frontend estático. A segurança será garantida no Kong Gateway, eliminando riscos de backdoors.

## 1. Configuração do Kong (Security & Free Tier)
Modificaremos o arquivo declarativo `kong/kong.yml` para criar uma rota segura, estritamente controlada para o público.

*   **Nova Rota (`/public-demo`):** Apontará para o serviço existente da API, mas sob regras restritas.
*   **Controle de Métodos:** Bloqueio de qualquer método diferente de `GET` usando o plugin `request-termination` (ou limitando a rota a `methods: ["GET"]`). Nenhuma requisição `POST` chegará ao endpoint administrativo via esta rota.
*   **Rate Limiting Severo:** Limite de 5 a 10 requisições por minuto por IP para evitar abusos e scraping.
*   **CORS (Cross-Origin Resource Sharing):** Habilitar o plugin CORS na rota pública para que a página estática possa fazer chamadas AJAX (fetch) sem ser bloqueada pelos navegadores.
*   **Bypass de Key-Auth:** Esta rota específica **não** exigirá o plugin `key-auth` (que ficará restrito à rota raiz padrão e operações de gerência).

## 2. Front-End Portátil (HTML/CSS/JS)
Criaremos um diretório `demo/` contendo arquivos estáticos que você poderá hospedar em qualquer lugar (S3, Vercel, seu site principal).

### Estrutura
*   `index.html`: Layout moderno (estilo SaaS) com campo de busca de insumos e composições.
*   `style.css`: Estilização limpa usando CSS Vanilla (variáveis, flexbox/grid), garantindo carregamento ultrarrápido sem dependências pesadas.
*   `app.js`: Lógica de requisição usando `fetch()`.

### Funcionalidades do Dashboard
1.  **Busca Rápida:** Campo unificado para buscar Insumos ou Composições pelo nome.
2.  **Visualização de Preços:** Exibição clara do Preço Mediano ou Custo Total.
3.  **Visualização de BOM (Curva ABC / Detalhes):** Para composições, exibiremos uma tabela simples com os insumos atrelados, demonstrando a capacidade analítica da API.
4.  **Feedback Visual de Limites:** Tratamento de erros de Rate Limit (HTTP 429), exibindo uma mensagem amigável ao usuário quando o limite do "Free Tier" for atingido.

## Próximos Passos
1. Obter aprovação deste plano.
2. Sair do modo Plan.
3. Atualizar o `kong/kong.yml`.
4. Desenvolver os arquivos em `repos/autosinapi_api/demo/`.