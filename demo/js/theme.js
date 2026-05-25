/** @file Tema — light/dark toggle + Chart.js sync */
import { getChartTheme } from './utils.js';

export function createTheme(state) {
  function updateChart(chart) {
    const { textColor, gridColor } = getChartTheme(state.theme);

    const { scales, plugins } = chart.options;
    if (scales?.x) {
      scales.x.ticks && (scales.x.ticks.color = textColor);
      scales.x.grid && (scales.x.grid.color = gridColor);
    }
    if (scales?.y) {
      scales.y.ticks && (scales.y.ticks.color = textColor);
      scales.y.grid && (scales.y.grid.color = gridColor);
    }
    if (plugins?.legend?.labels) {
      plugins.legend.labels.color = textColor;
    }
    chart.update();
  }

  return {
    init() {
      document.documentElement.setAttribute('data-theme', state.theme);
    },

    toggle() {
      state.theme = state.theme === 'dark' ? 'light' : 'dark';
      localStorage.setItem('autosinapi-theme', state.theme);
      document.documentElement.setAttribute('data-theme', state.theme);
      [state.abc.chart, state.compare.chart].forEach(chart => {
        if (chart) updateChart(chart);
      });
    },

    updateChart,
  };
}