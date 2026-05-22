/** @file Camada de API — fetch wrapper + endpoints */
export function createApi(config, toast, utils, state, dom) {
  const BASE = config.API_BASE;

  async function request(url, options = {}) {
    const response = await fetch(url, options);
    const body = await response.json().catch(() => ({ detail: `HTTP ${response.status}` }));
    if (!response.ok) {
      const errMsg = body.detail || body.message || `HTTP ${response.status}`;
      console.error(`[API] ${response.status} ${url}: ${errMsg}`);
      throw new Error(errMsg);
    }
    return body;
  }

  function updateFilterVisibility() {
    const isInsumo = state.search.searchType === 'insumos';
    const classificacaoCol = document.getElementById('classificacaoFilterCol');
    const grupoCol = document.getElementById('grupoFilterCol');
    if (classificacaoCol) classificacaoCol.style.display = isInsumo ? '' : 'none';
    if (grupoCol) grupoCol.style.display = isInsumo ? 'none' : '';
  }

  async function fetchStats() {
    try {
      const stats = await request(`${BASE}/stats`);
      if (dom.statPrecos) dom.statPrecos.textContent = utils.formatNumber(stats.precos);
      if (dom.statComposicoes) dom.statComposicoes.textContent = utils.formatNumber(stats.composicoes);
      if (dom.statInsumos) dom.statInsumos.textContent = utils.formatNumber(stats.insumos);
      if (dom.heroTotalRecords) dom.heroTotalRecords.textContent = `${utils.formatNumber(stats.precos)} registros`;
    } catch (error) {
      console.error('Stats fetch failed:', error);
    }
  }

  async function populateFilters() {
    try {
      const filters = await request(`${BASE}/filters`);

      state.filters.ufs = filters.ufs || [];
      state.filters.dates = filters.datas || [];
      state.filters.regimes = filters.regimes || [];
      state.filters.classificacoes = filters.classificacoes || [];
      state.filters.grupos = filters.grupos || [];

      const populate = (sel, arr) => {
        if (!sel) return;
        sel.innerHTML = arr.map(v => `<option value="${v}">${v}</option>`).join('');
      };

      populate(dom.stateFilter, state.filters.ufs);
      populate(dom.dateFilter, state.filters.dates);
      populate(dom.regimeFilter, state.filters.regimes);
      populate(dom.classificacaoFilter, state.filters.classificacoes);
      populate(dom.grupoFilter, state.filters.grupos);
      populate(dom.abcStateFilter, state.filters.ufs);
      populate(dom.abcDateFilter, state.filters.dates);
      populate(dom.abcRegimeFilter, state.filters.regimes);
      populate(dom.compareDateFilter, state.filters.dates);
      populate(dom.compareRegimeFilter, state.filters.regimes);
      populate(dom.trendsStateFilter, state.filters.ufs);
      populate(dom.trendsDateFilter, state.filters.dates);
      populate(dom.trendsRegimeFilter, state.filters.regimes);
      populate(dom.comparisonUfFilter, state.filters.ufs);
      populate(dom.comparisonDateFilter, state.filters.dates);
      populate(dom.comparisonRegimeFilter, state.filters.regimes);

      if (dom.stateFilter) dom.stateFilter.value = utils.getDefaultUf();
      if (dom.dateFilter) dom.dateFilter.value = utils.getDefaultDate();
      if (dom.regimeFilter) dom.regimeFilter.value = utils.getDefaultRegime();
      if (dom.classificacaoFilter) dom.classificacaoFilter.value = '';
      if (dom.grupoFilter) dom.grupoFilter.value = '';
      if (dom.abcStateFilter) dom.abcStateFilter.value = utils.getDefaultUf();
      if (dom.abcDateFilter) dom.abcDateFilter.value = utils.getDefaultDate();
      if (dom.abcRegimeFilter) dom.abcRegimeFilter.value = utils.getDefaultRegime();
      if (dom.compareDateFilter) dom.compareDateFilter.value = utils.getDefaultDate();
      if (dom.compareRegimeFilter) dom.compareRegimeFilter.value = utils.getDefaultRegime();
      if (dom.trendsStateFilter) dom.trendsStateFilter.value = 'SP';
      if (dom.trendsDateFilter) dom.trendsDateFilter.value = utils.getDefaultDate();
      if (dom.trendsRegimeFilter) dom.trendsRegimeFilter.value = utils.getDefaultRegime();
      if (dom.comparisonUfFilter) dom.comparisonUfFilter.value = 'SP';
      if (dom.comparisonDateFilter) dom.comparisonDateFilter.value = utils.getDefaultDate();
      if (dom.comparisonRegimeFilter) dom.comparisonRegimeFilter.value = utils.getDefaultRegime();

      if (dom.stateChips && state.filters.ufs.length > 0) {
        dom.stateChips.innerHTML = state.filters.ufs.map(uf =>
          `<button type="button" class="state-chip" data-uf="${uf}" aria-pressed="false">${uf}</button>`
        ).join('');
      }

      updateFilterVisibility();
    } catch (error) {
      console.error('Filter population failed:', error);
      state.filters.ufs = ['SP', 'RJ', 'MG', 'PR', 'SC', 'RS', 'BA', 'PE', 'GO'];
      state.filters.dates = [utils.getDefaultDate()];
      state.filters.regimes = ['DESONERADO', 'NAO_DESONERADO', 'SEM_ENCARGOS'];
      populate(dom.stateFilter, state.filters.ufs);
      populate(dom.dateFilter, state.filters.dates);
      populate(dom.regimeFilter, state.filters.regimes);
      populate(dom.abcStateFilter, state.filters.ufs);
      populate(dom.abcDateFilter, state.filters.dates);
      populate(dom.abcRegimeFilter, state.filters.regimes);
      populate(dom.compareDateFilter, state.filters.dates);
      populate(dom.compareRegimeFilter, state.filters.regimes);
      populate(dom.trendsStateFilter, state.filters.ufs);
      populate(dom.trendsDateFilter, state.filters.dates);
      populate(dom.trendsRegimeFilter, state.filters.regimes);
      populate(dom.comparisonUfFilter, state.filters.ufs);
      populate(dom.comparisonDateFilter, state.filters.dates);
      populate(dom.comparisonRegimeFilter, state.filters.regimes);
    }
  }

  return { request, fetchStats, populateFilters, updateFilterVisibility };
}