# AutoSINAPI Demo

Interface web responsiva que demonstra o potencial da **AutoSINAPI** — API RESTful para dados de custos da construção civil (SINAPI/IBGE).

## 📁 Estrutura

```
demo/
├── index.html              # HTML semântico com acessibilidade (ARIA)
├── style.css               # CSS principal (importa css/)
├── tests.js                # Suíte de testes unitários + interface + E2E
├── README.md               # Este arquivo
│
├── css/                    # CSS modular — 13 arquivos
│   ├── 01-variables.css    # Custom properties + dark theme tokens
│   ├── 02-reset.css        # Reset + tipografia base
│   ├── 03-navbar.css       # Navegação + mobile menu
│   ├── 04-hero.css         # Hero section + estatísticas
│   ├── 05-search.css       # Search box + filtros + state chips
│   ├── 06-results.css      # Grid/List views + skeleton + loader
│   ├── 07-charts.css       # Chart containers
│   ├── 08-compare.css      # Comparativo stats
│   ├── 09-modal.css        # Modal de detalhes
│   ├── 10-footer.css       # Footer
│   ├── 11-toast.css        # Toast notifications
│   ├── 12-utilities.css    # .hidden, .sr-only
│   └── 13-responsive.css   # Media queries (320px → 8K)
│
└── js/                     # JavaScript modular — ES Modules + DI
    ├── main.js             # Entry point: DI wiring + init
    ├── config.js           # Constantes (API_BASE, timeouts)
    ├── state.js            # Estado centralizado (factory)
    ├── dom.js              # Cache DOM + $/$$ helpers (factory)
    ├── utils.js            # Utilitários + ChartFactory + ViewToggle (factory)
    ├── api.js              # Camada HTTP + endpoints (factory)
    ├── toast.js            # Notificações (factory)
    ├── theme.js            # Tema light/dark + Chart.js sync (factory)
    ├── events.js           # Inicialização de listeners (factory)
    └── modules/
        ├── search.js       # Pesquisa & BOM (factory)
        ├── abc.js          # Curva ABC / BI (factory)
        └── compare.js      # Comparativo Inter-Regional (factory)
```

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

## 🔌 API Endpoints

| Endpoint | Método | Descrição |
|----------|--------|-----------|
| `/api/v1/public/stats` | GET | Estatísticas do banco |
| `/api/v1/public/filters` | GET | Filtros dinâmicos (ufs, datas, regimes) |
| `/api/v1/public/insumos` | GET | Busca de insumos |
| `/api/v1/public/insumos/{codigo}` | GET | Insumo específico |
| `/api/v1/public/composicoes` | GET | Busca de composições |
| `/api/v1/public/composicoes/{codigo}` | GET | Composição específica |
| `/api/v1/public/bi/curva-abc` | POST | Curva ABC (body: `[códigos]`) |
| `/api/v1/public/bi/composicao/{codigo}/bom` | GET | Bill of Materials |
| `/api/v1/public/bi/item/{tipo}/{codigo}/historico` | GET | Histórico de custo |

## 🎨 Tecnologias

- **HTML5** semântico com ARIA labels + skip link
- **CSS** modular com custom properties, dark mode, 10+ breakpoints (320px→8K)
- **JavaScript** ES Modules com Dependency Injection, zero build step
- **Chart.js** para visualização de dados
- **Suíte de testes** auto-contida (sem dependências externas)

## 🌐 Compatibilidade

- Navegadores modernos (ES Modules, CSS custom properties)
- Chrome 61+, Firefox 60+, Safari 11+, Edge 16+
- Servido via HTTPS (Kong Gateway)
- Responsivo de smartwatch (320px) até 8K

## 🛠️ Desenvolvimento

```bash
# Para desenvolver localmente
cd demo/
python3 -m http.server 8080
# Abrir http://localhost:8080/?runTests=true
```

**Princípios de design:**
- Dependency Injection — cada módulo recebe dependências via factory
- Single Source of Truth — estado centralizado no objeto `state`
- Zero duplicação — ChartFactory e ViewToggle eliminam código repetido
- Fail-safe — optional chaining previne crashes em DOM ausente
- XSS-safe — escapeHtml em todo output de usuário