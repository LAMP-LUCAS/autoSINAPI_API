/**
 * AutoSINAPI Demo — Entry Point
 * Arquitetura modular com Dependency Injection
 * @version 3.0.0
 */
import { CONFIG } from './config.js';
import { createState } from './state.js';
import { createDom } from './dom.js';
import { createUtils } from './utils.js';
import { createToast } from './toast.js';
import { createTheme } from './theme.js';
import { createApi } from './api.js';
import { createSearch } from './modules/search.js';
import { createABC } from './modules/abc.js';
import { createCompare } from './modules/compare.js';
import { createModal } from './modules/modal.js';
import { createEvents } from './events.js';

// ── Injeção de Dependências ──────────────────
const state = createState();
const dom = createDom();
const utils = createUtils(state);
const toast = createToast(dom, CONFIG);
const theme = createTheme(state);
const api = createApi(CONFIG, toast, utils, state, dom);
const search = createSearch(CONFIG, state, dom, utils, api, toast);
const abc = createABC(CONFIG, state, dom, utils, api, toast, theme);
const compare = createCompare(CONFIG, state, dom, utils, api, toast);
const modal = createModal(CONFIG, state, dom, utils, api, toast);
const events = createEvents(dom, { search, abc, compare, theme, toast, state, utils, modal });

// ── Inicialização ────────────────────────────
async function init() {
  theme.init();
  events.init();
  await Promise.all([api.populateFilters(), api.fetchStats()]);
}

(document.readyState === 'loading')
  ? document.addEventListener('DOMContentLoaded', init)
  : init();

// ── Globais para handlers inline (HTML) ──────
window.exportSearch = (fmt) => search.export(fmt);
window.exportBOM = (fmt) => toast.show(`Export BOM ${fmt} em desenvolvimento`, 'info');
window.closeModal = () => modal.close();

// ── Testabilidade (dev apenas) ───────────────
if (['localhost', '127.0.0.1'].includes(window.location.hostname) || window.location.hostname.includes('lamp.local')) {
  window.AutoSINAPI = { state, search, abc, compare, theme, api, toast, utils, modal };
  console.log('[AutoSINAPI] Test interface: window.AutoSINAPI');
}