/** @file Módulo de Curva ABC (BI) */
import { createChartConfig, createViewToggle, getChartTheme } from '../utils.js';

export function createABC(config, state, dom, utils, api, toast) {
  const viewToggle = createViewToggle(
    'display',
    { grid: dom.abcGrid, tableWrapper: dom.abcTableWrapper, btnGrid: dom.btnAbcGrid, btnList: dom.btnAbcList },
    state.abc
  );

  function cleanupChart() {
    state.abc.chart?.destroy();
    state.abc.chart = null;
  }

  function toggleGroupBy() {
    state.abc.groupByClassificacao = !state.abc.groupByClassificacao;
    if (dom.abcToggleGroup) {
      dom.abcToggleGroup.classList.toggle('active', state.abc.groupByClassificacao);
    }
    if (state.abc.data) render();
  }

  async function perform() {
    const codes = dom.abcInput?.value?.trim();
    if (!codes) { toast.show('Digite pelo menos um código', 'warning'); return; }

    state.abc.loading = true;
    dom.abcSkeleton?.classList.remove('hidden');
    dom.abcResults?.classList.add('hidden');
    dom.abcResultsActions?.classList.add('hidden');
    cleanupChart();

    try {
      const uf = dom.abcStateFilter?.value || utils.getDefaultUf();
      const date = dom.abcDateFilter?.value || utils.getDefaultDate();
      const regime = dom.abcRegimeFilter?.value || utils.getDefaultRegime();
      const codeList = codes.split(',').map(c => parseInt(c.trim(), 10)).filter(n => !isNaN(n));

      if (state.abc.groupByClassificacao) {
        const url = `${config.API_BASE}/bi/curva-abc/por-classificacao?uf=${uf}&data_referencia=${date}&regime=${encodeURIComponent(regime)}`;
        const data = await api.request(url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(codeList),
        });
        state.abc.groupedData = Array.isArray(data) ? data : (data.data || []);
        state.abc.data = null;
      } else {
        const url = `${config.API_BASE}/bi/curva-abc?uf=${uf}&data_referencia=${date}&regime=${encodeURIComponent(regime)}`;
        const data = await api.request(url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(codeList),
        });
        state.abc.data = Array.isArray(data) ? data : (data.data || []);
        state.abc.groupedData = null;
      }
      render();
    } catch (error) {
      toast.show(`Erro ABC: ${error.message}`, 'error');
    } finally {
      state.abc.loading = false;
      setTimeout(() => dom.abcSkeleton?.classList.add('hidden'), 300);
    }
  }

  function render() {
    const data = state.abc.data;
    const grouped = state.abc.groupedData;

    if (!data?.length && !grouped?.length) return;

    dom.abcResults?.classList.remove('hidden');
    dom.abcResultsActions?.classList.remove('hidden');

    if (grouped?.length) {
      renderGrouped(grouped);
    } else if (data?.length) {
      renderIndividual(data);
    }

    viewToggle.setView(state.abc.viewMode || 'grid');
  }

  function renderIndividual(data) {
    if (dom.abcResultsCount) dom.abcResultsCount.textContent = `${data.length} insumo(s) analisado(s)`;

    // Update table header for individual mode
    const thead = dom.abcTable?.querySelector('thead');
    if (thead) {
      thead.innerHTML = `<tr>
        <th scope="col">Classificação</th>
        <th scope="col">Código</th>
        <th scope="col">Descrição do Insumo</th>
        <th scope="col">Unidade</th>
        <th scope="col">Impacto Total</th>
        <th scope="col">% Acumulado</th>
      </tr>`;
    }

    if (dom.abcGrid) {
      dom.abcGrid.innerHTML = data.map(item => `
        <div class="card" data-codigo="${item.codigo}" data-tipo="insumo">
          <span class="type-tag tag-${(item.classe_abc || 'C').toLowerCase()}">Classe ${item.classe_abc}</span>
          <h3>${utils.escapeHtml(item.descricao)}</h3>
          <div class="price-row">
            <span class="val">${utils.formatCurrency(item.custo_total_agregado)}</span>
            <span class="unit">${(item.percentual_acumulado || 0).toFixed(1)}% acum.</span>
          </div>
        </div>
      `).join('');
    }

    const tbody = dom.abcTable?.querySelector('tbody');
    if (tbody) {
      tbody.innerHTML = data.map(item => `
        <tr>
          <td><span class="type-tag tag-${(item.classe_abc || 'C').toLowerCase()}">${item.classe_abc}</span></td>
          <td>${item.codigo}</td>
          <td class="text-left">${utils.escapeHtml(item.descricao)}</td>
          <td>${item.unidade}</td>
          <td><strong>${utils.formatCurrency(item.custo_total_agregado)}</strong></td>
          <td>${(item.percentual_acumulado || 0).toFixed(1)}%</td>
        </tr>
      `).join('');
    }

    if (dom.abcChart) {
      const { textColor, gridColor, primaryColor, errorColor } = getChartTheme(state.theme);
      const labels = data.slice(0, 15).map(i => i.descricao.substring(0, 20) + '...');
      const impacts = data.slice(0, 15).map(i => i.custo_total_agregado);
      const accumulated = data.slice(0, 15).map(i => i.percentual_acumulado);

      const chartConfig = {
        type: 'bar',
        data: {
          labels,
          datasets: [
            {
              label: 'Impacto Financeiro (R$)',
              data: impacts,
              backgroundColor: primaryColor,
              yAxisID: 'y',
            },
            {
              label: '% Acumulado',
              data: accumulated,
              type: 'line',
              borderColor: errorColor,
              borderWidth: 2,
              pointRadius: 3,
              yAxisID: 'y1',
            }
          ]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          scales: {
            y: { type: 'linear', display: true, position: 'left', beginAtZero: true, ticks: { color: textColor }, grid: { color: gridColor } },
            y1: { type: 'linear', display: true, position: 'right', min: 0, max: 100, grid: { drawOnChartArea: false }, ticks: { color: textColor } },
            x: { ticks: { color: textColor }, grid: { color: gridColor } }
          },
          plugins: { legend: { labels: { color: textColor } } }
        }
      };
      state.abc.chart = new Chart(dom.abcChart.getContext('2d'), chartConfig);
    }
  }

  function renderGrouped(data) {
    if (dom.abcResultsCount) dom.abcResultsCount.textContent = `${data.length} classificação(ões) encontrada(s)`;

    // Update table header for grouped mode
    const thead = dom.abcTable?.querySelector('thead');
    if (thead) {
      thead.innerHTML = `<tr>
        <th scope="col">Classificação</th>
        <th scope="col">Categoria</th>
        <th scope="col">Qtd Insumos</th>
        <th scope="col">Custo Total</th>
        <th scope="col">% do Total</th>
      </tr>`;
    }

    if (dom.abcGrid) {
      dom.abcGrid.innerHTML = data.map(item => `
        <div class="card">
          <span class="badge badge-classificacao">${utils.escapeHtml(item.classificacao)}</span>
          <h3>${utils.escapeHtml(item.classificacao)}</h3>
          <div class="price-row">
            <span class="val">${utils.formatCurrency(item.custo_total)}</span>
            <span class="unit">${item.total_insumos} insumo(s) · ${(item.percentual || 0).toFixed(1)}%</span>
          </div>
        </div>
      `).join('');
    }

    const tbody = dom.abcTable?.querySelector('tbody');
    if (tbody) {
      tbody.innerHTML = data.map(item => `
        <tr>
          <td><span class="badge badge-classificacao">${utils.escapeHtml(item.classificacao)}</span></td>
          <td class="text-left"><strong>${utils.escapeHtml(item.classificacao)}</strong></td>
          <td>${item.total_insumos}</td>
          <td><strong>${utils.formatCurrency(item.custo_total)}</strong></td>
          <td>${(item.percentual || 0).toFixed(1)}%</td>
        </tr>
      `).join('');
    }

    if (dom.abcChart) {
      const { textColor, gridColor } = getChartTheme(state.theme);
      const colors = ['#2563eb', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#14b8a6', '#f97316', '#6366f1', '#84cc16'];
      const labels = data.map(i => i.classificacao);
      const values = data.map(i => i.custo_total);

      const chartConfig = {
        type: 'bar',
        data: {
          labels,
          datasets: [{
            label: 'Custo por Classificação (R$)',
            data: values,
            backgroundColor: labels.map((_, idx) => colors[idx % colors.length]),
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          indexAxis: 'y',
          scales: {
            x: { beginAtZero: true, ticks: { color: textColor, callback: (v) => utils.formatCurrency(v) }, grid: { color: gridColor } },
            y: { ticks: { color: textColor }, grid: { display: false } }
          },
          plugins: { legend: { display: false } }
        }
      };
      state.abc.chart = new Chart(dom.abcChart.getContext('2d'), chartConfig);
    }
  }

  return { perform, render, setView: viewToggle.setView, toggleGroupBy };
}