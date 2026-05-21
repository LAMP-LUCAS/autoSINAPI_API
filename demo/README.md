# AutoSINAPI Demo

Interface web responsiva que demonstra o potencial da **AutoSINAPI** — API RESTful para dados de custos da construção civil (SINAPI/IBGE).

## 📁 Estrutura

```
demo/
├── index.html              # HTML semântico com acessibilidade (ARIA)
├── style.css               # CSS entry point — @layer cascade system
├── tests.js                # Suíte de testes unitários + interface + E2E
├── README.md               # Este arquivo
│
├── css/                    # CSS modular — 13 arquivos em @layer
│   ├── 01-variables.css    # Custom properties (cores, spacing, typography, shadows)
│   ├── 02-reset.css        # Reset + tipografia base + reduced-motion
│   ├── 03-navbar.css       # Navegação + mobile menu
│   ├── 04-hero.css         # Hero section + estatísticas + tech stack
│   ├── 05-search.css       # Search box + filtros + state chips
│   ├── 06-results.css      # Grid/List views + skeleton (.shimmer) + loader
│   ├── 07-charts.css       # Chart containers + tables
│   ├── 08-compare.css      # Comparativo stats + state selector
│   ├── 09-modal.css        # Modal de detalhes + BOM cards/table
│   ├── 10-footer.css       # Footer com theme-awareness
│   ├── 11-toast.css        # Toast notifications
│   ├── 12-utilities.css    # .hidden, .sr-only, .shimmer, .anim-*, flex/grid utils
│   └── 13-responsive.css   # Media queries (320px → 3840px) + print + forced-colors
│
└── js/                     # JavaScript modular — ES Modules + DI
    ├── main.js             # Entry point: DI wiring + init
    ├── config.js           # Constantes congeladas (API_BASE, timeouts)
    ├── state.js            # Estado centralizado (factory function)
    ├── dom.js              # Cache DOM + $/$$ helpers (factory)
    ├── utils.js            # formatCurrency, escapeHtml, getChartTheme(),
    │                       #   hexToRgba(), downloadAsFile(), createChartConfig(),
    │                       #   createViewToggle()
    ├── api.js              # Camada HTTP + endpoints + populates filtros (factory)
    ├── toast.js            # Notificações com dismiss on click (factory)
    ├── theme.js            # Tema light/dark + Chart.js sync (factory)
    ├── events.js           # Inicialização de listeners + forms + exports (factory)
    └── modules/
        ├── search.js       # Pesquisa textual + BOM + export (JSON/MD/PDF/CSV)
        ├── abc.js          # Curva ABC: gráfico (bar+line), grid e tabela
        └── compare.js      # Comparativo Inter-Regional: stats + bar chart
```

## 🎯 Arquitetura

### Dependency Injection (DI)

Todos os módulos são **factory functions** que recebem suas dependências explicitamente via `main.js`:

```js
const state = createState();
const dom = createDom();
const utils = createUtils(state);
const toast = createToast(dom, CONFIG);
const theme = createTheme(state);
const api = createApi(CONFIG, toast, utils, state, dom);
const search = createSearch(CONFIG, state, dom, utils, api, toast);
// ...
const events = createEvents(dom, { search, abc, compare, theme, toast, state, utils, modal });
```

**Vantagens:** testabilidade, substituição de implementações, fluxo de dependências explícito.

### CSS @layer Cascade System

```
@layer reset, tokens, components, utilities, responsive;
```

| Layer | Prioridade | Conteúdo |
|-------|-----------|----------|
| `reset` | Mais baixa | `02-reset.css` |
| `tokens` | | `01-variables.css` |
| `components` | | `03-navbar.css` a `11-toast.css` |
| `utilities` | | `12-utilities.css` |
| `responsive` | Mais alta | `13-responsive.css` |

### Chart.js Centralização

Toda lógica de cores para gráficos está centralizada em `getChartTheme()` em `utils.js`:

```js
const { textColor, gridColor, primaryColor, successColor, errorColor } = getChartTheme(state.theme);
```

Isso elimina a duplicação do padrão `isDark ? '#xxx' : '#yyy'` que antes existia em `abc.js`, `compare.js`, `modal.js` e `theme.js`.

## 🔌 API Endpoints

### Consulta Pública

| Endpoint | Método | Descrição |
|----------|--------|-----------|
| `/api/v1/public/stats` | GET | Estatísticas do banco (total records, preços, etc.) |
| `/api/v1/public/filters` | GET | Filtros dinâmicos (ufs, datas, regimes) |
| `/api/v1/public/insumos` | GET | Busca textual de insumos |
| `/api/v1/public/insumos/{codigo}` | GET | Detalhes de um insumo específico |
| `/api/v1/public/composicoes` | GET | Busca textual de composições |
| `/api/v1/public/composicoes/{codigo}` | GET | Detalhes de uma composição específica |

### Business Intelligence (BI)

| Endpoint | Método | Descrição |
|----------|--------|-----------|
| `/api/v1/public/bi/curva-abc` | POST | Curva ABC — body: `[códigos]` |
| `/api/v1/public/bi/composicao/{codigo}/bom` | GET | Bill of Materials (árvore hierárquica) |
| `/api/v1/public/bi/composicao/{codigo}/hora-homem` | GET | Total de horas de mão de obra |
| `/api/v1/public/bi/composicao/{codigo}/otimizar` | GET | Top 5 insumos de maior impacto financeiro |
| `/api/v1/public/bi/item/{tipo}/{codigo}/historico` | GET | Série histórica de preços (12 meses) |

## 🧪 Testes

```bash
# Abrir no browser com flag de teste
https://autosinapi.lamp.local/demo/?runTests=true

# Ou via console do browser
AutoSINAPITests.runAll()
AutoSINAPITests.runUnitTests()
AutoSINAPITests.runInterfaceTests()
AutoSINAPITests.runE2ETests()
AutoSINAPITests.showManualChecklist()
```

## 🎨 Tecnologias

- **HTML5** semântico com ARIA labels + skip link + forms nativos
- **CSS** modular com `@layer`, custom properties, `clamp()`, `color-mix()`, `container queries`, 10+ breakpoints (320px → 3840px)
- **JavaScript** ES Modules com Dependency Injection, zero build step
- **Chart.js** (multi-theme via `getChartTheme()`)
- **Suíte de testes** auto-contida (sem dependências externas)

## 🌐 Compatibilidade

- Navegadores modernos (ES Modules, CSS custom properties, `@layer`)
- Chrome 61+, Firefox 60+, Safari 11+, Edge 16+
- Servido via HTTPS (Kong Gateway)
- Responsivo de smartwatch (320px) até 8K (3840px)
- Dark mode automático + toggle manual

## 🛠️ Desenvolvimento

```bash
# Para desenvolver localmente
cd demo/
python3 -m http.server 8080
# Abrir http://localhost:8080/?runTests=true
```

### Princípios de design

- **Dependency Injection** — cada módulo recebe dependências via factory function
- **Single Source of Truth** — estado centralizado no objeto `state`
- **DRY** — `getChartTheme()` e `createChartConfig()` eliminam duplicação de lógica de gráficos
- **Fail-safe** — optional chaining (`?.`) previne crashes em DOM ausente
- **XSS-safe** — `escapeHtml()` em todo output de dados do usuário
- **Accessibility-first** — navegação por teclado, ARIA labels, `prefers-reduced-motion`, `forced-colors`
- **Mobile-first** — base CSS em 375px, breakpoints progressivos até 3840px
