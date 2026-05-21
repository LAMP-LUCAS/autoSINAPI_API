/** @file Estado centralizado da aplicação */
export function createState() {
  return {
    theme: localStorage.getItem('autosinapi-theme') ||
           (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'),
    filters: { ufs: [], dates: [], regimes: [] },
    search: { results: [], loading: false, sortBy: 'name_asc', viewMode: 'grid' },
    abc: { data: null, loading: false, viewMode: 'grid', chart: null },
    compare: { data: null, loading: false, chart: null, selectedStates: new Set() },
  };
}