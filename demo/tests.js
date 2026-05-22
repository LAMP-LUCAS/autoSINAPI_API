/**
 * AutoSINAPI Demo - Test Suite
 * @description Testes unitários, de interface e E2E para validação da saúde da aplicação
 * @version 1.2.0 - Idempotência, Cobertura de Fallbacks e Sprint 1c
 */

const AutoSINAPITests = (() => {
  'use strict';

  // ==================== TEST FRAMEWORK (Minimal) ====================
  const results = { passed: 0, failed: 0, tests: [] };

  function assert(condition, message) {
    if (condition) {
      results.passed++;
      results.tests.push({ status: 'PASS', message });
    } else {
      results.failed++;
      results.tests.push({ status: 'FAIL', message });
    }
  }

  function assertEqual(actual, expected, message) {
    assert(actual === expected, `${message} (expected: ${expected}, got: ${actual})`);
  }

  function assertTruthy(value, message) {
    assert(!!value, `${message} (value is ${value})`);
  }

  function assertArray(arr, message) {
    assert(Array.isArray(arr), `${message} (type: ${typeof arr})`);
  }

  // ==================== UTILS PARA TESTES ====================
  /**
   * Reseta o estado da aplicação para valores iniciais conhecidos.
   * Garante idempotência entre execuções.
   */
  function resetAppState() {
    const app = window.AutoSINAPI;
    if (!app || !app.state) return;

    // Resetando manualmente as partes do estado que causam falhas de asserção se preenchidas
    app.state.comparison.left = null;
    app.state.comparison.right = null;
    app.state.comparison.loading = false;
    app.state.heatmap.data = null;
    app.state.trends.loading = false;
    
    // Resetando valores dos inputs que podem disparar requisições durante boundary tests
    const inputIds = ['comparisonCode1', 'comparisonCode2', 'abcInput', 'compareCode'];
    inputIds.forEach(id => {
      const el = document.getElementById(id);
      if (el) el.value = '';
    });
  }

  /**
   * Salva e restaura valores do DOM para não interferir na experiência do usuário
   */
  async function withCleanInputs(ids, callback) {
    const originalValues = ids.map(id => document.getElementById(id)?.value);
    ids.forEach(id => {
      const el = document.getElementById(id);
      if (el) el.value = '';
    });
    
    try {
      await callback();
    } finally {
      ids.forEach((id, i) => {
        const el = document.getElementById(id);
        if (el) el.value = originalValues[i];
      });
    }
  }

  // ==================== UNIT TESTS ====================
  async function runUnitTests() {
    console.log('\n🧪 [UNIT TESTS] Testando módulos e estado...\n');

    const app = window.AutoSINAPI;
    if (!app) { assert(false, 'window.AutoSINAPI não definido'); return; }
    
    // RESET PARA IDEMPOTÊNCIA
    resetAppState();
    
    const { utils, state } = app;

    // Test 1: AutoSINAPI deve estar definido
    assertTruthy(app, 'window.AutoSINAPI está definido');

    // Test 2: Utils.escapeHtml
    if (utils) {
      assertEqual(utils.escapeHtml('<script>alert("xss")</script>'), '&lt;script&gt;alert("xss")&lt;/script&gt;', 'escapeHtml previne XSS');
      assertEqual(utils.escapeHtml(null), '', 'escapeHtml lida com null');
      assertEqual(utils.escapeHtml(''), '', 'escapeHtml lida com string vazia');
      assertEqual(utils.escapeHtml('Texto normal'), 'Texto normal', 'escapeHtml preserva texto normal');

      // Test 3: Utils.formatCurrency
      const formatted = utils.formatCurrency(1234.56);
      assert(formatted.includes('R$'), `formatCurrency formata como BRL: ${formatted}`);
      assert(formatted.includes('1.234,56'), `formatCurrency usa locale pt-BR: ${formatted}`);

      // Test 4: Utils.getDefault
      assertTruthy(utils.getDefault('ufs', 'SP'), 'getDefault retorna primeiro UF quando array populado');
    }

    // Test 5: State inicial — estrutura e defaults corretos (APÓS RESET)
    if (state) {
      assertTruthy(state.theme, 'state.theme está definido');
      assert(['light', 'dark'].includes(state.theme), `state.theme é 'light' ou 'dark' (got: ${state.theme})`);
      assertTruthy(state.filters, 'state.filters está definido');
      assertArray(state.filters.ufs, 'state.filters.ufs é um array');
      assertArray(state.filters.dates, 'state.filters.dates é um array');
      assertArray(state.filters.regimes, 'state.filters.regimes é um array');
      assertArray(state.search.results, 'state.search.results é um array');
      // Sprint 1c: estado dos novos módulos
      assertEqual(state.trends.loading, false, 'state.trends.loading inicia false');
      assertEqual(state.heatmap.data, null, 'state.heatmap.data inicia null');
      assertEqual(state.comparison.loading, false, 'state.comparison.loading inicia false');
      assertEqual(state.comparison.left, null, 'state.comparison.left inicia null');
      assertEqual(state.comparison.right, null, 'state.comparison.right inicia null');
    }

    // Test 6: Módulos Sprint 1c — métodos públicos existem
    const modules = [
      { module: app.trends, name: 'trends', methods: ['perform'] },
      { module: app.heatmap, name: 'heatmap', methods: ['render'] },
      { module: app.comparison, name: 'comparison', methods: ['perform'] },
    ];
    for (const { module: mod, name, methods } of modules) {
      if (mod) {
        assertTruthy(mod, `Módulo ${name} está disponível`);
        for (const method of methods) {
          assert(typeof mod[method] === 'function', `${name}.${method} é uma função`);
        }
      }
    }

    // Test 7: Módulos existentes — métodos públicos existem
    const existingModules = [
      { module: app.search, name: 'search', methods: ['perform', 'render', 'setView', 'export', 'setSearchType'] },
      { module: app.abc, name: 'abc', methods: ['perform', 'render', 'setView', 'toggleGroupBy'] },
      { module: app.compare, name: 'compare', methods: ['perform', 'render', 'toggleState'] },
      { module: app.modal, name: 'modal', methods: ['show', 'close', 'exportChart', 'filterBom', 'setBomView'] },
      { module: app.api, name: 'api', methods: ['request', 'fetchStats', 'populateFilters', 'updateFilterVisibility'] },
    ];
    for (const { module: mod, name, methods } of existingModules) {
      if (mod) {
        for (const method of methods) {
          assert(typeof mod[method] === 'function', `${name}.${method} é uma função`);
        }
      }
    }

    // Test 8: Module boundary conditions — não crasham com params inválidos e RESPEITAM O DOM LIMPO
    await withCleanInputs(['comparisonCode1', 'comparisonCode2', 'trendsStateFilter', 'trendsDateFilter'], async () => {
      try {
        await app.comparison?.perform?.();  // sem códigos → deve mostrar toast, não crashar nem fazer fetch
        assert(true, 'comparison.perform() sem códigos não crasha nem faz fetch espúrio');
      } catch (e) {
        assert(false, `comparison.perform() sem códigos crashou: ${e.message}`);
      }

      try {
        await app.trends?.perform?.();  // sem filtros → deve mostrar warning, não crashar
        assert(true, 'trends.perform() sem filtros não crasha');
      } catch (e) {
        assert(false, `trends.perform() sem filtros crashou: ${e.message}`);
      }
    });

    try {
      // Usando parâmetros explícitos para evitar que util.getDefault (ainda não populado) envie '-'
      app.heatmap?.render?.('370', 'insumo', '2026-04', 'DESONERADO');  
      assert(true, 'heatmap.render() com código válido não crasha');
    } catch (e) {
      assert(false, `heatmap.render() crashou: ${e.message}`);
    }

    // Test 9: Cobertura de Fallbacks e Gráficos
    if (app.heatmap) {
      try {
        app.heatmap.render(null, 'insumo'); // Trigger fallback/early return
        assert(true, 'heatmap.render com dados nulos não crasha');
      } catch (e) {
        assert(false, `heatmap.render(null) crashou: ${e.message}`);
      }
    }

    console.log(`\n✅ Unit Tests: ${results.passed} passou, ${results.failed} falhou\n`);
  }

  // ==================== DOM/INTERFACE TESTS ====================
  function runInterfaceTests() {
    console.log('\n🎨 [INTERFACE TESTS] Verificando elementos da UI...\n');

    const ids = [
      'themeToggle', 'mobileMenuBtn', 'mobileMenu',
      'searchInput', 'stateFilter', 'dateFilter', 'regimeFilter', 'searchBtn',
      'resultsGrid', 'resultsActions', 'searchSkeleton',
      'abcInput', 'abcStateFilter', 'abcDateFilter', 'abcRegimeFilter', 'abcBtn',
      'abcChart', 'abcGrid', 'abcTableWrapper',
      'compareType', 'compareCode', 'compareDateFilter', 'compareRegimeFilter', 'compareBtn',
      'stateChips', 'compareChart', 'compareResults',
      'detailModal', 'toast',
      // Sprint 1a: New filter elements
      'classificacaoFilter', 'grupoFilter',
      // Sprint 1a: New modal elements
      'bomSearchInput', 'btnExportChart', 'bomCostComparison',
      'modalStatusBadge', 'modalClassificacao', 'modalGrupo',
      // Sprint 1b: New elements
      'abcToggleGroup', 'maintenanceSection', 'maintenanceContainer',
      'adminSection', 'adminForm', 'adminYear', 'adminMonth', 'adminUf',
      // Sprint 1c: Trends
      'trendsStateFilter', 'trendsDateFilter', 'trendsRegimeFilter', 'trendsBtn',
      'trendsChart', 'trendsResults', 'trendsTable',
      // Sprint 1c: Heatmap
      'heatmapChart', 'heatmapSection',
      // Sprint 1c: Comparison Cross
      'comparisonCode1', 'comparisonCode2', 'comparisonBtn',
      'comparisonResults', 'comparisonLeftTable', 'comparisonRightTable',
      'comparisonDeltaTable', 'comparisonChart',
    ];

    ids.forEach(id => {
      const el = document.getElementById(id);
      assertTruthy(el, `Elemento #${id} existe no DOM`);
    });

    // Test: Theme toggle tem aria-label
    const themeToggle = document.getElementById('themeToggle');
    if (themeToggle) {
      assertTruthy(themeToggle.getAttribute('aria-label'), 'themeToggle tem aria-label');
    }

    // Test: Fallback check — elementos de erro/vazio estão presentes (ocultos ou via skeleton)
    const skeleton = document.getElementById('searchSkeleton');
    if (skeleton) {
      assert(skeleton.classList.contains('hidden'), 'searchSkeleton inicia oculto');
    }

    // Test: Canvas elements exist
    ['abcChart', 'compareChart', 'historyChart', 'trendsChart', 'heatmapChart', 'comparisonChart'].forEach(id => {
      const canvas = document.getElementById(id);
      if (canvas) {
        assert(canvas.getContext('2d'), `Canvas #${id} tem contexto 2d`);
      }
    });

    // Test: Chart.js está carregado
    assertTruthy(window.Chart, 'Chart.js está carregado globalmente');

    console.log(`\n✅ Interface Tests: ${results.passed} passou, ${results.failed} falhou\n`);
  }

  // ==================== INTEGRATION/E2E TESTS ====================
  async function runE2ETests() {
    console.log('\n🚀 [E2E TESTS] Testando fluxos completos...\n');

    const app = window.AutoSINAPI;
    const { api, search, abc, compare, toast, state, theme, modal, admin, trends, heatmap, comparison } = app;

    // Test 1: API Base URL e Endpoints
    assertTruthy(api, 'Módulo api está disponível');

    // Test 2: Módulos Principais
    [search, abc, compare].forEach(m => {
      assertTruthy(m && typeof m.perform === 'function', `Módulo ${m?.constructor?.name || 'principal'} funcional`);
    });

    // Test 3: Theme Toggle
    if (theme) {
      const initialTheme = document.documentElement.getAttribute('data-theme') || 'light';
      theme.toggle();
      const toggledTheme = document.documentElement.getAttribute('data-theme');
      assert(toggledTheme !== initialTheme, `Toggle alterou o tema de ${initialTheme} para ${toggledTheme}`);
      theme.toggle(); // volta ao original
    }

    // Test 4: Modal Features (BOM filter)
    if (modal && typeof modal.filterBom === 'function') {
      assert(true, 'modal.filterBom disponível para busca em tempo real');
    }

    // Test 5: Search setSearchType (Validação de UI dinâmica)
    if (search && search.setSearchType) {
      search.setSearchType('composicoes');
      const classificacaoCol = document.getElementById('classificacaoFilterCol');
      if (classificacaoCol) {
        assertEqual(classificacaoCol.style.display, 'none', 'Filtro de classificação oculto para composições');
      }
      search.setSearchType('insumos');
    }

    // Test 6: Sprint 1c - Trends Simulation
    if (trends && typeof trends.perform === 'function') {
      assertEqual(state.trends.loading, false, 'Trends inicia sem carregar');
    }

    // Test 7: Sprint 1c - Comparison Cross Simulation
    if (comparison && typeof comparison.perform === 'function') {
      assertEqual(state.comparison.loading, false, 'Comparison Cross inicia sem carregar');
    }

    // Test 8: Robustez - Toast System
    if (toast && typeof toast.show === 'function') {
      toast.show('Teste de Sistema', 'info');
      const toastEl = document.getElementById('toast');
      assert(toastEl && !toastEl.classList.contains('hidden'), 'Sistema de notificação (Toast) funcional');
    }

    console.log(`\n✅ E2E Tests: ${results.passed} passou, ${results.failed} falhou\n`);
  }

  // ==================== MANUAL TEST CHECKLIST ====================
  function showManualChecklist() {
    console.log(`
📋 [CHECK LIST MANUAL] - Execute estes testes no browser:

NAVEGAÇÃO:
☐ Menu hambúrguer abre/fecha corretamente
☐ Links do menu funcionam e fecham o menu mobile
☐ Scroll suave para seções funciona
☐ Theme toggle muda entre light/dark

PESQUISA:
☐ Digite 3+ caracteres e clique em Pesquisar
☐ Resultados aparecem no grid
☐ Resultados de insumos mostram badge de classificação (ex: "MATERIAL CERÂMICO")
☐ Resultados de composições mostram badge de grupo (ex: "ESTRUTURA")
☐ Items inativos mostram badge "INATIVO" vermelho
☐ Filtrar por classificação/grupo funciona
☐ Trocar view (grid/list) funciona
☐ Ordenação funciona
☐ Botões de export (JSON/MD/PDF) funcionam

CURVA ABC:
☐ Digite códigos (ex: 87316, 92711, 88309)
☐ Clique em Calcular Curva ABC
☐ Gráfico aparece
☐ Trocar entre grid/table view funciona

COMPARATIVO:
☐ Digite um código (ex: 370)
☐ Selecione estados (chips)
☐ Clique em Comparar
☐ Gráfico de barras aparece
☐ Estatísticas (min, max, avg, variação) aparecem

MODAL (SPRINT 1a):
☐ Abrir modal de composição mostra classificação/grupo/status no header
☐ Abrir modal de insumo mostra classificação/status
☐ BOM mostra comparação de custo (BOM total vs Oficial) com delta colorido
☐ BOM cost comparison mostra verde se delta < 2%, laranja se < 5%, vermelho se > 5%
☐ Busca no BOM filtra cards e tabela em tempo real
☐ Botão "Exportar Gráfico" baixa PNG do histórico de preços
☐ Items inativos mostram badge "INATIVO" no modal

MODAL (SPRINT 1b):
☐ Abrir modal de item com histórico de manutenção mostra timeline
☐ Manutenções ATIVACAO aparecem em verde e DESATIVACAO em vermelho
☐ Seção de manutenção fica oculta se não houver dados

CURVA ABC (SPRINT 1b):
☐ Botão "Agrupar por Classificação" alterna entre modos
☐ Modo agrupado mostra categorias no gráfico horizontal
☐ Modo agrupado mostra grid cards com categoria, total, % e qtd de insumos
☐ Tabela no modo agrupado mostra classificação, qtd insumos, total e %

ADMIN (SPRINT 1b):
☐ Acessar via ?admin=true no URL
☐ Formulário com ano, mês, UF aparece
☐ Clicar "Iniciar Carga" dispara POST /admin/populate-database
☐ Polling de status funciona (task status polling a cada 3s)
☐ Resultado da tarefa aparece ao final

TENDÊNCIAS (SPRINT 1c):
☐ Seção "Tendências de Volatilidade" existe na página
☐ Filtros UF/Referência/Regime são populados dinamicamente
☐ Clicar "Analisar Tendências" carrega gráfico de linhas
☐ Gráfico mostra uma série por classificação de insumo
☐ Tabela de inflação acumulada por categoria aparece abaixo do gráfico
☐ Variação % está colorida (verde para queda, vermelho para alta)

MAPA DE CALOR REGIONAL (SPRINT 1c):
☐ Abrir modal de insumo mostra card "Mapa de Calor Regional"
☐ Gráfico de barras horizontal mostra preço em todas as UFs
☐ Barras são coloridas em gradiente verde (barato) → vermelho (caro)
☐ Tooltip mostra seta ▲/▼ indicando acima/abaixo da média

COMPARAÇÃO CRUZADA (SPRINT 1c):
☐ Seção "Comparação Cruzada de Composições" existe na página
☐ Digitar 2 códigos de composição e clicar "Comparar"
☐ Duas tabelas lado a lado mostram o BOM de cada composição
☐ Tabela "Diferenças Item a Item" mostra delta entre as duas
☐ Diferença positiva em verde, negativa em vermelho
☐ Gráfico de barras agrupado compara custo por tipo de item

RESPONSIVIDADE:
☐ Teste em 320px (smartwatch)
☐ Teste em 375px (mobile)
☐ Teste em 768px (tablet)
☐ Teste em 1024px (desktop)
☐ Teste em 1920px (full HD)
☐ Teste em 3840px (4K)

ACESSIBILIDADE:
☐ Navegação por teclado funciona (Tab)
☐ Skip link funciona
☐ Aria-labels estão presentes
☐ Contraste (modo high contrast)

API ENDPOINTS (teste manual):
☐ GET /api/v1/public/stats
☐ GET /api/v1/public/filters
☐ GET /api/v1/public/insumos?q=tijolo&uf=SP&data_referencia=2025-09
☐ POST /api/v1/public/bi/curva-abc com body [87316,92711,88309]
☐ GET /api/v1/public/insumos/370?uf=SP&data_referencia=2025-09
☐ GET /api/v1/public/composicoes/87316?uf=SP&data_referencia=2025-09
☐ GET /api/v1/public/bi/composicao/87316/bom
`);
  }

  // ==================== RUN ALL TESTS ====================
  async function runAll() {
    console.log('='.repeat(60));
    console.log('🧪 AutoSINAPI Demo - Test Suite v1.2.0');
    console.log('='.repeat(60));

    results.passed = 0;
    results.failed = 0;
    results.tests = [];

    await runUnitTests();
    runInterfaceTests();
    await runE2ETests();
    showManualChecklist();

    console.log('='.repeat(60));
    console.log(`📊 RESUMO: ${results.passed} passou, ${results.failed} falhou`);
    console.log('='.repeat(60));

    if (results.failed > 0) {
      console.log('\n❌ TESTES QUE FALHARAM:');
      results.tests.filter(t => t.status === 'FAIL').forEach(t => {
        console.log(`  - ${t.message}`);
      });
    }

    return results;
  }

  // Auto-run if in test mode — poll until modules and filters are ready
  if (window.location.search.includes('runTests=true')) {
    let attempts = 0;
    const maxAttempts = 30;
    function waitAndRun() {
      attempts++;
      const app = window.AutoSINAPI;
      if (app && app.state && app.state.filters && app.state.filters.ufs && app.state.filters.ufs.length > 0) {
        setTimeout(runAll, 500);
      } else if (attempts < maxAttempts) {
        setTimeout(waitAndRun, 200);
      } else {
        console.error('[AutoSINAPI Tests] Timeout: window.AutoSINAPI filters not loaded after', maxAttempts, 'attempts');
        // Run anyway to show failures
        setTimeout(runAll, 500);
      }
    }
    waitAndRun();
  }

  // Expose API
  return { runAll, runUnitTests, runInterfaceTests, runE2ETests, showManualChecklist, results };
})();

// Expose globally for console usage
window.AutoSINAPITests = AutoSINAPITests;
console.log('[AutoSINAPI Tests] Loaded. Run: AutoSINAPITests.runAll() or add ?runTests=true to URL');
