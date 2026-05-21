/** @file Cache DOM — query helpers e cache de elementos */
export const $ = (sel, ctx = document) => ctx.querySelector(sel);
export const $$ = (sel, ctx = document) => [...ctx.querySelectorAll(sel)];

export function createDom() {
  return {
    themeToggle: $('#themeToggle'),
    mobileMenuBtn: $('#mobileMenuBtn'),
    mobileMenu: $('#mobileMenu'),
    // Hero
    exampleBtns: $$('.example-btn'),
    heroTotalRecords: $('#hero-total-records'),
    statPrecos: $('#stat-precos'),
    statComposicoes: $('#stat-composicoes'),
    statInsumos: $('#stat-insumos'),
    // Search
    searchInput: $('#searchInput'),
    stateFilter: $('#stateFilter'),
    dateFilter: $('#dateFilter'),
    regimeFilter: $('#regimeFilter'),
    searchBtn: $('#searchBtn'),
    resultsGrid: $('#resultsGrid'),
    resultsActions: $('#resultsActions'),
    resultsCount: $('#resultsCount'),
    sortSelect: $('#sortSelect'),
    btnGrid: $('#btnGrid'),
    btnList: $('#btnList'),
    searchSkeleton: $('#searchSkeleton'),
    noResults: $('#noResults'),
    loader: $('#loader'),
    // ABC
    abcInput: $('#abcInput'),
    abcStateFilter: $('#abcStateFilter'),
    abcDateFilter: $('#abcDateFilter'),
    abcRegimeFilter: $('#abcRegimeFilter'),
    abcBtn: $('#abcBtn'),
    abcSkeleton: $('#abcSkeleton'),
    abcResults: $('#abcResults'),
    abcResultsActions: $('#abcResultsActions'),
    abcResultsCount: $('#abcResultsCount'),
    btnAbcGrid: $('#btnAbcGrid'),
    btnAbcList: $('#btnAbcList'),
    abcChart: $('#abcChart'),
    abcGrid: $('#abcGrid'),
    abcTable: $('#abcTable'),
    abcTableWrapper: $('#abcTableWrapper'),
    // Compare
    compareType: $('#compareType'),
    compareCode: $('#compareCode'),
    compareDateFilter: $('#compareDateFilter'),
    compareRegimeFilter: $('#compareRegimeFilter'),
    compareBtn: $('#compareBtn'),
    stateChips: $('#stateChips'),
    selectAllStates: $('#selectAllStates'),
    clearAllStates: $('#clearAllStates'),
    presetRegions: $('#presetRegions'),
    selectedStatesCount: $('#selectedStatesCount'),
    compareSkeleton: $('#compareSkeleton'),
    compareResults: $('#compareResults'),
    compareChart: $('#compareChart'),
    compareItemName: $('#compareItemName'),
    compareStats: $('#compareStats'),
    compareMin: $('#compareMin'),
    compareMax: $('#compareMax'),
    compareAvg: $('#compareAvg'),
    compareVariation: $('#compareVariation'),
    // Modal
    detailModal: $('#detailModal'),
    historyChart: $('#historyChart'),
    // Toast
    toast: $('#toast'),
  };
}