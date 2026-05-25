/** @file Estado centralizado da aplicação */
export function createState() {
  return {
    theme: localStorage.getItem('autosinapi-theme') ||
           (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'),
    filters: { ufs: [], dates: [], regimes: [], classificacoes: [], grupos: [] },
    search: { results: [], loading: false, sortBy: 'name_asc', viewMode: 'grid', searchType: 'insumos' },
    abc: { data: null, loading: false, viewMode: 'grid', chart: null, groupByClassificacao: false, groupedData: null },
    compare: { data: null, loading: false, chart: null, selectedStates: new Set() },
    trends: { data: null, loading: false, chart: null },
    heatmap: { data: null, chart: null },
    comparison: { left: null, right: null, loading: false, chart: null },
    admin: { taskId: null, pollingInterval: null },
  };
}