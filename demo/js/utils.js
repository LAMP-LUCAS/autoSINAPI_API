/** @file Utilitários — funções puras e helpers */
import { CONFIG } from './config.js';

/**
 * Converte cor hex (#rgb ou #rrggbb) para rgba
 * @param {string} hex
 * @param {number} alpha
 * @returns {string} rgba(r, g, b, alpha)
 */
export function hexToRgba(hex, alpha = 1) {
  const v = parseInt(hex.slice(1), 16);
  if (hex.length === 4) {
    const r = (v >> 8) * 17, g = ((v >> 4) & 0xf) * 17, b = (v & 0xf) * 17;
    return `rgba(${r},${g},${b},${alpha})`;
  }
  return `rgba(${v>>16},${(v>>8)&255},${v&255},${alpha})`;
}

/**
 * Retorna paleta de cores Chart.js baseada no tema
 * @param {'light'|'dark'} theme
 * @returns {{ textColor: string, gridColor: string, primaryColor: string, successColor: string, errorColor: string }}
 */
export function getChartTheme(theme) {
  const isDark = theme === 'dark';
  return {
    textColor: isDark ? '#f0f0f0' : '#1a1a1a',
    gridColor: isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.1)',
    primaryColor: isDark ? '#60a5fa' : '#2563eb',
    successColor: isDark ? '#34d399' : '#10b981',
    errorColor: isDark ? '#f87171' : '#ef4444',
  };
}

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
    getDefaultDate() {
      const now = new Date();
      return this.getDefault('dates', `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`);
    },
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

    /** Descarrega conteúdo como arquivo (Blob + URL + download) */
    downloadAsFile(content, filename, mimeType = 'text/plain') {
      const blob = new Blob([content], { type: mimeType });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
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
  const { textColor, gridColor } = getChartTheme(theme);

  return {
    type,
    data: { labels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { labels: { color: textColor } } },
      scales: {
        x: { ticks: { color: textColor }, grid: { color: gridColor } },
        y: { ticks: { color: textColor }, grid: { color: gridColor }, beginAtZero: true },
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