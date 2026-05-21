/**
 * AutoSINAPI Demo - Test Suite
 * @description Testes unitários, de interface e E2E para validação da saúde da aplicação
 * @usage Inclua no HTML via <script src="tests.js"></script> ou rode no console do browser
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

  // ==================== UNIT TESTS ====================
  function runUnitTests() {
    console.log('\n🧪 [UNIT TESTS] Iniciando testes unitários...\n');

    // Test 1: AutoSINAPI deve estar definido
    assertTruthy(window.AutoSINAPI, 'window.AutoSINAPI está definido');

    // Test 2: Utils.escapeHtml
    const { utils } = window.AutoSINAPI;
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

    // Test 5: State inicial
    const { state } = window.AutoSINAPI;
    if (state) {
      assertTruthy(state.theme, 'state.theme está definido');
      assert(['light', 'dark'].includes(state.theme), `state.theme é 'light' ou 'dark' (got: ${state.theme})`);
      assertTruthy(state.filters, 'state.filters está definido');
      assertArray(state.search.results, 'state.search.results é um array');
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

    // Test: Mobile menu tem aria-expanded
    const mobileMenuBtn = document.getElementById('mobileMenuBtn');
    if (mobileMenuBtn) {
      assertTruthy(mobileMenuBtn.getAttribute('aria-expanded'), 'mobileMenuBtn tem aria-expanded');
      assertTruthy(mobileMenuBtn.getAttribute('aria-controls'), 'mobileMenuBtn tem aria-controls');
    }

    // Test: Canvas elements exist
    ['abcChart', 'compareChart', 'historyChart'].forEach(id => {
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

    const { api, search, abc, compare, toast } = window.AutoSINAPI;

    // Test 1: API Base URL
    assertTruthy(api, 'Módulo api está disponível');
    // Note: We can't test the actual API here without making real requests
    // In a real E2E setup with Playwright/Cypress, we would test the actual API calls

    // Test 2: Simular busca (sem fazer fetch real)
    if (search) {
      assertTruthy(search.perform, 'search.perform está definido');
      assertTruthy(search.render, 'search.render está definido');
      assertTruthy(search.setView, 'search.setView está definido');
      assertTruthy(search.export, 'search.export está definido');
    }

    // Test 3: Simular ABC
    if (abc) {
      assertTruthy(abc.perform, 'abc.perform está definido');
      assertTruthy(abc.render, 'abc.render está definido');
      assertTruthy(abc.setView, 'abc.setView está definido');
    }

    // Test 4: Simular Compare
    if (compare) {
      assertTruthy(compare.perform, 'compare.perform está definido');
      assertTruthy(compare.render, 'compare.render está definido');
      assertTruthy(compare.toggleState, 'compare.toggleState está definido');
    }

    // Test 5: Theme
    const { theme, state } = window.AutoSINAPI;
    if (theme) {
      assertTruthy(theme.toggle, 'theme.toggle está definido');
      assertTruthy(theme.init, 'theme.init está definido');
      const initialTheme = state?.theme || 'light';
      // Toggle theme and check
      theme.toggle();
      const newTheme = document.documentElement.getAttribute('data-theme');
      assert(['light', 'dark'].includes(newTheme), `Theme toggle funcionou: ${newTheme}`);
      // Toggle back
      theme.toggle();
    }

    // Test 6: Modal Sprint 1a features
    const { modal } = window.AutoSINAPI;
    if (modal) {
      assertTruthy(modal.exportChart, 'modal.exportChart está definido');
      assertTruthy(modal.filterBom, 'modal.filterBom está definido');
      assertTruthy(modal.setBomView, 'modal.setBomView está definido');
    }

    // Test 7: API filter updates
    const { api } = window.AutoSINAPI;
    if (api) {
      assertTruthy(api.updateFilterVisibility, 'api.updateFilterVisibility está definido');
      assertTruthy(api.populateFilters, 'api.populateFilters está definido');
    }

    // Test 8: Search setSearchType works via updateFilterVisibility chain
    if (search) {
      assertTruthy(search.setSearchType, 'search.setSearchType está definido');
      search.setSearchType('composicoes');
      const classificacaoCol = document.getElementById('classificacaoFilterCol');
      if (classificacaoCol) {
        assertEqual(classificacaoCol.style.display, 'none', 'classificacaoFilterCol fica oculto ao buscar composições');
      }
      search.setSearchType('insumos');
    }

    // Test 9: ABC group toggle
    if (abc) {
      assertTruthy(abc.toggleGroupBy, 'abc.toggleGroupBy está definido');
    }

    // Test 10: Admin module
    const { admin } = window.AutoSINAPI;
    if (admin) {
      assertTruthy(admin.initVisibility, 'admin.initVisibility está definido');
      assertTruthy(admin.triggerPopulation, 'admin.triggerPopulation está definido');
      assertTruthy(admin.stopPolling, 'admin.stopPolling está definido');
    }

    // Test 11: Modal Sprint 1b features
    if (modal) {
      // exportChart and filterBom tested in Sprint 1a
      assertTruthy(modal.show, 'modal.show está definido');
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
    console.log('🧪 AutoSINAPI Demo - Test Suite');
    console.log('='.repeat(60));

    results.passed = 0;
    results.failed = 0;
    results.tests = [];

    runUnitTests();
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

  // Auto-run if in test mode — poll until modules are ready
  if (window.location.search.includes('runTests=true')) {
    let attempts = 0;
    const maxAttempts = 30;
    function waitAndRun() {
      attempts++;
      if (window.AutoSINAPI) {
        setTimeout(runAll, 500);
      } else if (attempts < maxAttempts) {
        setTimeout(waitAndRun, 200);
      } else {
        console.error('[AutoSINAPI Tests] Timeout: window.AutoSINAPI not found after', maxAttempts, 'attempts');
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
