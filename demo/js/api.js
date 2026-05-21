/** @file Camada de API — fetch wrapper + endpoints */
export function createApi(config, toast, utils, state, dom) {
  const BASE = config.API_BASE;

  /** Unified fetch with error handling — body consumed ONCE */
  async function request(url, options = {}) {
    try {
      const response = await fetch(url, options);
      const body = await response.json().catch(() => ({ message: `HTTP ${response.status}` }));
      if (!response.ok) throw new Error(body.message || `HTTP ${response.status}`);
      return body;
    } catch (error) {
      toast.show(`Erro: ${error.message}`, 'error');
      throw error;
    }
  }

  return {
    request,

    async fetchStats() {
      try {
        const stats = await request(`${BASE}/stats`);
        if (dom.statPrecos) dom.statPrecos.textContent = utils.formatNumber(stats.precos);
        if (dom.statComposicoes) dom.statComposicoes.textContent = utils.formatNumber(stats.composicoes);
        if (dom.statInsumos) dom.statInsumos.textContent = utils.formatNumber(stats.insumos);
        if (dom.heroTotalRecords) dom.heroTotalRecords.textContent = `${utils.formatNumber(stats.precos)} registros`;
      } catch (error) {
        console.error('Stats fetch failed:', error);
      }
    },

    async populateFilters() {
      try {
        const filters = await request(`${BASE}/filters`);

        state.filters.ufs = filters.ufs || [];
        state.filters.dates = filters.datas || [];
        state.filters.regimes = filters.regimes || [];

        const populate = (sel, arr) => {
          if (!sel) return;
          sel.innerHTML = arr.map(v => `<option value="${v}">${v}</option>`).join('');
        };

        populate(dom.stateFilter, state.filters.ufs);
        populate(dom.dateFilter, state.filters.dates);
        populate(dom.regimeFilter, state.filters.regimes);
        populate(dom.abcStateFilter, state.filters.ufs);
        populate(dom.abcDateFilter, state.filters.dates);
        populate(dom.abcRegimeFilter, state.filters.regimes);
        populate(dom.compareDateFilter, state.filters.dates);
        populate(dom.compareRegimeFilter, state.filters.regimes);

        if (dom.stateFilter) dom.stateFilter.value = utils.getDefaultUf();
        if (dom.dateFilter) dom.dateFilter.value = utils.getDefaultDate();
        if (dom.regimeFilter) dom.regimeFilter.value = utils.getDefaultRegime();
        if (dom.abcStateFilter) dom.abcStateFilter.value = utils.getDefaultUf();
        if (dom.abcDateFilter) dom.abcDateFilter.value = utils.getDefaultDate();
        if (dom.abcRegimeFilter) dom.abcRegimeFilter.value = utils.getDefaultRegime();
        if (dom.compareDateFilter) dom.compareDateFilter.value = utils.getDefaultDate();
        if (dom.compareRegimeFilter) dom.compareRegimeFilter.value = utils.getDefaultRegime();

        if (dom.stateChips && state.filters.ufs.length > 0) {
          dom.stateChips.innerHTML = state.filters.ufs.map(uf =>
            `<button type="button" class="state-chip" data-uf="${uf}" aria-pressed="false">${uf}</button>`
          ).join('');
        }
      } catch (error) {
        console.error('Filter population failed:', error);
        state.filters.ufs = ['SP', 'RJ', 'MG', 'PR', 'SC', 'RS', 'BA', 'PE', 'GO'];
        state.filters.dates = [utils.getDefaultDate()];
        state.filters.regimes = ['DESONERADO', 'NAO_DESONERADO', 'SEM_ENCARGOS'];
      }
    },
  };
}