/** @file Módulo de Comparativo Inter-Regional */
import { createChartConfig, getChartTheme } from '../utils.js';

export function createCompare(config, state, dom, utils, api, toast) {
  const REGIONS = {
    'Sudeste': ['SP', 'RJ', 'MG', 'ES'],
    'Sul': ['PR', 'SC', 'RS'],
    'Nordeste': ['BA', 'PE', 'CE', 'MA', 'PB', 'RN', 'AL', 'SE', 'PI'],
    'Norte': ['AM', 'PA', 'AC', 'RO', 'RR', 'AP', 'TO'],
    'Centro-Oeste': ['GO', 'MT', 'MS', 'DF'],
  };

  function cleanupChart() {
    state.compare.chart?.destroy();
    state.compare.chart = null;
  }

  function updateChipUI() {
    if (!dom.stateChips) return;
    const chips = dom.stateChips.querySelectorAll('.state-chip');
    chips.forEach(chip => {
      const uf = chip.dataset.uf;
      const isSelected = state.compare.selectedStates.has(uf);
      chip.classList.toggle('selected', isSelected);
      chip.setAttribute('aria-pressed', isSelected);
    });
    const count = state.compare.selectedStates.size;
    if (dom.selectedStatesCount) {
      dom.selectedStatesCount.textContent = `${count} estado${count !== 1 ? 's' : ''} selecionado${count !== 1 ? 's' : ''}`;
    }
  }

  function toggleState(uf) {
    if (state.compare.selectedStates.has(uf)) {
      state.compare.selectedStates.delete(uf);
    } else {
      state.compare.selectedStates.add(uf);
    }
    updateChipUI();
  }

  function selectAll() {
    const ufs = state.filters.ufs.length > 0 ? state.filters.ufs : ['SP', 'RJ', 'MG', 'PR', 'SC', 'RS', 'BA', 'PE', 'GO'];
    ufs.forEach(uf => state.compare.selectedStates.add(uf));
    updateChipUI();
  }

  function clearAll() {
    state.compare.selectedStates.clear();
    updateChipUI();
  }

  function presetRegions() {
    state.compare.selectedStates.clear();
    const representative = ['SP', 'RJ', 'MG', 'PR', 'BA', 'AM', 'GO', 'DF'];
    representative.forEach(uf => {
      if (state.filters.ufs.includes(uf) || state.filters.ufs.length === 0) {
        state.compare.selectedStates.add(uf);
      }
    });
    updateChipUI();
  }

  async function perform() {
    const code = dom.compareCode?.value?.trim();
    if (!code) { toast.show('Digite um código SINAPI', 'warning'); return; }

    const type = dom.compareType?.value || 'insumos';
    const date = dom.compareDateFilter?.value || utils.getDefaultDate();
    const regime = dom.compareRegimeFilter?.value || utils.getDefaultRegime();

    const selectedUfs = [...state.compare.selectedStates];
    if (selectedUfs.length === 0) {
      toast.show('Selecione pelo menos um estado', 'warning');
      return;
    }

    state.compare.loading = true;
    dom.compareSkeleton?.classList.remove('hidden');
    dom.compareResults?.classList.add('hidden');
    cleanupChart();

    try {
      const promises = selectedUfs.map(uf =>
        api.request(`${config.API_BASE}/${type}/${encodeURIComponent(code)}?uf=${uf}&data_referencia=${date}&regime=${encodeURIComponent(regime)}`)
          .then(data => ({ uf, data, success: true }))
          .catch(() => ({ uf, data: null, success: false }))
      );

      const results = await Promise.all(promises);
      const validData = results.filter(r => r.success && r.data);

      if (validData.length === 0) {
        throw new Error('Item não encontrado em nenhum estado para esta referência.');
      }

      state.compare.data = validData.map(r => ({
        uf: r.uf,
        descricao: r.data.descricao,
        valor: parseFloat(r.data.preco_mediano || r.data.custo_total || 0)
      }));

      render();
    } catch (error) {
      toast.show(error.message, 'error');
    } finally {
      state.compare.loading = false;
      setTimeout(() => dom.compareSkeleton?.classList.add('hidden'), 300);
    }
  }

  function render() {
    cleanupChart();
    const data = state.compare.data;
    if (!data?.length) return;

    dom.compareResults?.classList.remove('hidden');
    if (dom.compareItemName) dom.compareItemName.textContent = data[0].descricao;

    const values = data.map(d => d.valor).filter(v => v > 0);
    if (values.length > 0 && dom.compareStats) {
      dom.compareStats.classList.remove('hidden');
      const min = Math.min(...values);
      const max = Math.max(...values);
      const avg = values.reduce((a, b) => a + b, 0) / values.length;

      if (dom.compareMin) {
          const minItem = data.find(d => d.valor === min);
          dom.compareMin.textContent = utils.formatCurrency(min);
          if (dom.compareMinUf) dom.compareMinUf.textContent = minItem.uf;
      }
      if (dom.compareMax) {
          const maxItem = data.find(d => d.valor === max);
          dom.compareMax.textContent = utils.formatCurrency(max);
          if (dom.compareMaxUf) dom.compareMaxUf.textContent = maxItem.uf;
      }
      if (dom.compareAvg) dom.compareAvg.textContent = utils.formatCurrency(avg);
      if (dom.compareVariation) dom.compareVariation.textContent = `${((max - min) / min * 100).toFixed(1)}%`;
    }

    if (dom.compareChart) {
      const chartLabels = data.map(d => d.uf);
      const chartValues = data.map(d => d.valor);
      const { textColor, gridColor, primaryColor, successColor, errorColor } = getChartTheme(state.theme);

      const minVal = Math.min(...chartValues.filter(v => v > 0));
      const maxVal = Math.max(...chartValues.filter(v => v > 0));

      const ctx = dom.compareChart.getContext('2d');
      const existing = Chart.getChart(ctx.canvas);
      if (existing) existing.destroy();
      const configChart = {
        type: 'bar',
        data: {
          labels: chartLabels,
          datasets: [{
            label: 'Valor (R$)',
            data: chartValues,
            backgroundColor: chartValues.map(v => {
              if (v === minVal) return successColor;
              if (v === maxVal) return errorColor;
              return primaryColor;
            }),
            borderRadius: 6
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: {
            y: {
              beginAtZero: true,
              ticks: { color: textColor },
              grid: { color: gridColor }
            },
            x: {
              ticks: { color: textColor },
              grid: { color: gridColor }
            }
          }
        }
      };
      state.compare.chart = new Chart(ctx, configChart);
    }
  }

  return { perform, render, toggleState, selectAll, clearAll, presetRegions };
}
