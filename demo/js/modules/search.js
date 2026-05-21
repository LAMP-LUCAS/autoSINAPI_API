/** @file Módulo de Pesquisa / BOM */
import { createViewToggle } from '../utils.js';

export function createSearch(config, state, dom, utils, api, toast) {
  const viewToggle = createViewToggle(
    'class',
    { container: dom.resultsGrid, baseClass: 'results-grid', btnGrid: dom.btnGrid, btnList: dom.btnList },
    state.search
  );

  async function perform() {
    const query = dom.searchInput?.value?.trim();
    if (!query || query.length < 3) {
      toast.show('Digite pelo menos 3 caracteres', 'warning');
      return;
    }

    state.search.loading = true;
    dom.searchSkeleton?.classList.remove('hidden');
    if (dom.resultsGrid) dom.resultsGrid.innerHTML = '';
    dom.noResults?.classList.add('hidden');

    try {
      const uf = dom.stateFilter?.value || utils.getDefaultUf();
      const date = dom.dateFilter?.value || utils.getDefaultDate();
      const regime = dom.regimeFilter?.value || utils.getDefaultRegime();
      const url = `${config.API_BASE}/insumos?q=${encodeURIComponent(query)}&uf=${uf}&data_referencia=${date}&regime=${encodeURIComponent(regime)}`;

      const data = await api.request(url);
      state.search.results = Array.isArray(data) ? data : (data.data || []);
      render();
    } catch {
      dom.resultsGrid.innerHTML = '<p class="empty-state">Erro ao buscar resultados.</p>';
    } finally {
      state.search.loading = false;
      setTimeout(() => dom.searchSkeleton?.classList.add('hidden'), 300);
    }
  }

  function render() {
    const results = state.search.results;
    if (!results?.length) {
      dom.resultsGrid.innerHTML = '';
      dom.noResults?.classList.remove('hidden');
      dom.resultsActions?.classList.add('hidden');
      return;
    }

    dom.resultsActions?.classList.remove('hidden');
    if (dom.resultsCount) dom.resultsCount.textContent = `${results.length} resultado(s)`;

    const sorted = [...results].sort((a, b) => {
      switch (state.search.sortBy) {
        case 'name_asc': return (a.descricao || '').localeCompare(b.descricao || '');
        case 'name_desc': return (b.descricao || '').localeCompare(a.descricao || '');
        case 'price_desc': return (b.preco_mediano || 0) - (a.preco_mediano || 0);
        case 'price_asc': return (a.preco_mediano || 0) - (b.preco_mediano || 0);
        default: return 0;
      }
    });

    dom.resultsGrid.innerHTML = sorted.map(item => `
      <div class="card" data-codigo="${item.codigo}" data-tipo="insumo" role="listitem">
        <span class="type-tag tag-insumo">INSUMO</span>
        <h3>${utils.escapeHtml(item.descricao || 'Sem descrição')}</h3>
        <div class="price-row">
          <span class="val">${utils.formatCurrency(item.preco_mediano || 0)}</span>
          <span class="unit">${utils.escapeHtml(item.unidade || 'N/A')}</span>
        </div>
      </div>
    `).join('');
  }

  function exportData(format) {
    const data = state.search.results;
    if (!data?.length) { toast.show('Nada para exportar', 'warning'); return; }

    const content = format === 'json'
      ? JSON.stringify(data, null, 2)
      : [Object.keys(data[0]).join(','), ...data.map(r =>
          Object.values(r).map(v => `"${(v || '').toString().replace(/"/g, '""')}"`).join(',')
        )].join('\n');

    const blob = new Blob([content], { type: format === 'json' ? 'application/json' : 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `sinapi-pesquisa.${format === 'json' ? 'json' : 'csv'}`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return { perform, render, setView: viewToggle.setView, export: exportData };
}