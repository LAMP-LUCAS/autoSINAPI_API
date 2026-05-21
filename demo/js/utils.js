/** @file Utilitários — funções puras e helpers */
import { CONFIG } from './config.js';

export function createUtils(state) {
  return {
    escapeHtml(str) {
      if (typeof str !== 'string') return String(str || '');
      const div = document.createElement('div');
      div.textContent = str;
      return div.innerHTML;
    },

    formatCurrency(value) {
      return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(value || 0);
    },

    formatNumber(value) {
      return (value || 0).toLocaleString('pt-BR');
    },

    getDefault(filterKey, fallback) {
      const arr = state.filters[filterKey];
      return arr?.length > 0 ? arr[0] : fallback;
    },

    getDefaultUf() { return this.getDefault('ufs', CONFIG.FALLBACK_UF); },
    getDefaultDate() { return this.getDefault('dates', new Date().toISOString().split('T')[0]); },
    getDefaultRegime() { return this.getDefault('regimes', CONFIG.FALLBACK_REGIME); },

    async copyToClipboard(text) {
      try {
        await navigator.clipboard.writeText(text);
        return true;
      } catch {
        const ta = document.createElement('textarea');
        ta.value = text;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        return true;
      }
    },
  };
}

/**
 * Factory para configuração base de Chart.js
 * @param {'line'|'bar'} type - Tipo do gráfico
 * @param {string[]} labels - Labels do eixo X
 * @param {Object[]} datasets - Array de datasets do Chart.js
 * @param {'light'|'dark'} theme - Tema atual
 * @param {Object} [overrides] - Overrides para options
 * @returns {Object} Config completa do Chart.js
 */
export function createChartConfig(type, labels, datasets, theme, overrides = {}) {
  const isDark = theme === 'dark';
  const colors = isDark ? { text: '#f0f0f0', grid: 'rgba(255,255,255,0.1)' } : { text: '#1a1a1a', grid: 'rgba(0,0,0,0.1)' };

  return {
    type,
    data: { labels, datasets },
    options: {
      responsive: true,
      plugins: { legend: { labels: { color: colors.text } } },
      scales: {
        x: { ticks: { color: colors.text }, grid: { color: colors.grid } },
        y: { ticks: { color: colors.text }, grid: { color: colors.grid }, beginAtZero: true },
      },
      ...overrides,
    },
  };
}

/**
 * Factory para toggle de visualização grid/table
 * Suporta tipo 'display' (mostra/esconde blocos distintos) e 'class' (alterna classes em um único container)
 * @param {'display'|'class'} type - Tipo do toggle
 * @param {Object} domRefs - Referências dos elementos DOM
 * @param {Object} stateRef - Referência ao estado
 * @returns {Object} { setView(mode) }
 */
export function createViewToggle(type, domRefs, stateRef) {
  return {
    setView(mode) {
      stateRef.viewMode = mode;
      if (type === 'class') {
        if (domRefs.container) {
          domRefs.container.className = `${domRefs.baseClass} ${mode}-view`;
        }
        domRefs.btnGrid?.classList.toggle('active', mode === 'grid');
        domRefs.btnList?.classList.toggle('active', mode === 'list');
      } else {
        domRefs.grid?.classList.toggle('hidden', mode !== 'grid');
        domRefs.tableWrapper?.classList.toggle('hidden', mode !== 'table');
        domRefs.btnGrid?.classList.toggle('active', mode === 'grid');
        domRefs.btnList?.classList.toggle('active', mode === 'table');
      }
    },
  };
}