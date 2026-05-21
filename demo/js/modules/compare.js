/** @file Módulo de Comparativo Inter-Regional */
import { createChartConfig } from '../utils.js';

export function createCompare(config, state, dom, utils, api, toast) {
  function cleanupChart() {
    state.compare.chart?.destroy();
    state.compare.chart = null;
  }

  async function perform() {
    const code = dom.compareCode?.value?.trim();
    if (!code) { toast.show('Digite um código SINAPI', 'warning'); return; }

    const type = dom.compareType?.value || 'insumos';
    const date = dom.compareDateFilter?.value || utils.getDefaultDate();
    const regime = dom.compareRegimeFilter?.value || utils.getDefaultRegime();

    // Dinamismo: Usar TODAS as UFs disponíveis no banco (carregadas via API)
    const availableUfs = state.filters.ufs.length > 0 ? state.filters.ufs : ['SP', 'RJ', 'MG', 'AC', 'BA', 'PR', 'AM', 'CE'];

    state.compare.loading = true;
    dom.compareSkeleton?.classList.remove('hidden');
    dom.compareResults?.classList.add('hidden');
    cleanupChart();

    try {
      const promises = availableUfs.map(uf =>
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

      const ctx = dom.compareChart.getContext('2d');
      const configChart = {
        type: 'bar',
        data: {
          labels: chartLabels,
          datasets: [{
            label: 'Valor (R$)',
            data: chartValues,
            backgroundColor: chartValues.map((_, i) => `hsl(${220 + (i * 10)}, 70%, 60%)`),
            borderRadius: 6
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: { y: { beginAtZero: true } }
        }
      };
      state.compare.chart = new Chart(ctx, configChart);
    }
  }

  return { perform, render };
}
