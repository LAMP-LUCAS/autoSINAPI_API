export function createTrends(config, state, dom, utils, api, toast) {
  const ENDPOINT = `${config.API_BASE}/bi/tendencias/por-classificacao`;

  async function perform() {
    const uf = dom.trendsStateFilter?.value;
    const date = dom.trendsDateFilter?.value;
    const regime = dom.trendsRegimeFilter?.value;
    const groupBy = dom.trendsGroupBy?.value || 'classificacao';
    const codes = dom.trendsCodes?.value?.trim();

    if (!uf || !date) {
      toast.show('Selecione UF e data de referência', 'warning');
      return;
    }

    if (groupBy === 'item' && !codes) {
      toast.show('Digite os códigos para análise individual', 'warning');
      return;
    }

    state.trends.loading = true;
    dom.trendsSkeleton?.classList.remove('hidden');
    dom.trendsResults?.classList.add('hidden');

    try {
      let url = `${ENDPOINT}?uf=${uf}&data_referencia=${date}&regime=${regime}&agrupar_por=${groupBy}&meses=12`;
      if (codes) url += `&codigos=${encodeURIComponent(codes)}`;
      
      const data = await api.request(url);
      state.trends.data = data;
      
      if (!data || data.length === 0) {
        toast.show('Nenhum dado de tendência encontrado para os filtros selecionados.', 'info');
        dom.trendsResults?.classList.add('hidden');
      } else {
        renderChart(data);
        renderTable(data, groupBy);
        dom.trendsResults?.classList.remove('hidden');
      }
    } catch (err) {
      console.error('[Trends] Erro ao carregar tendências:', err);
      toast.show(err.message.includes('Nenhum') ? err.message : 'Erro ao carregar tendências', 'error');
    } finally {
      state.trends.loading = false;
      dom.trendsSkeleton?.classList.add('hidden');
    }
  }

  function renderChart(data) {
    const groups = {};
    for (const item of data) {
      if (!groups[item.classificacao]) groups[item.classificacao] = [];
      groups[item.classificacao].push(item);
    }

    const months = [...new Set(data.map(d => d.mes))].sort();
    const colors = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#14b8a6', '#f97316', '#6366f1', '#d946ef'];
    let colorIdx = 0;

    const datasets = Object.entries(groups).map(([classificacao, items]) => {
      const values = months.map(m => {
        const found = items.find(i => i.mes === m);
        return found ? found.preco_medio : null;
      });
      const color = colors[colorIdx % colors.length];
      colorIdx++;
      return {
        label: classificacao,
        data: values,
        borderColor: color,
        backgroundColor: color + '30',
        fill: false,
        tension: 0.35,
        spanGaps: true,
        pointRadius: 2,
        pointHoverRadius: 5,
      };
    });

    const ctx = dom.trendsChart?.getContext('2d');
    if (!ctx) return;
    Chart.getChart(ctx.canvas)?.destroy();

    const textColor = getComputedStyle(document.documentElement).getPropertyValue('--text-main').trim() || '#1e293b';
    const mutedColor = getComputedStyle(document.documentElement).getPropertyValue('--text-muted').trim() || '#64748b';

    state.trends.chart = new Chart(ctx, {
      type: 'line',
      data: { labels: months, datasets },
      options: {
        responsive: true,
        maintainAspectRatio: true,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: { position: 'bottom', labels: { color: textColor, boxWidth: 12, padding: 12, font: { size: 10 } } },
          tooltip: {
            callbacks: {
              label: ctx => ctx.parsed.y !== null ? `${ctx.dataset.label}: R$ ${ctx.parsed.y.toFixed(2)}` : '',
            },
          },
        },
        scales: {
          x: {
            ticks: { color: mutedColor, font: { size: 10 } },
            grid: { display: false },
          },
          y: {
            beginAtZero: true,
            ticks: { color: mutedColor, font: { size: 10 }, callback: v => 'R$ ' + Number(v).toFixed(2) },
            grid: { color: mutedColor + '20' },
          },
        },
      },
    });
  }

  function renderTable(data, groupBy) {
    const groups = {};
    for (const item of data) {
      if (!groups[item.classificacao]) groups[item.classificacao] = [];
      groups[item.classificacao].push(item);
    }

    const table = dom.trendsTable;
    if (!table) return;

    const label = groupBy === 'classificacao' ? 'Classificação' : groupBy === 'grupo' ? 'Grupo' : 'Item (Código - Descrição)';
    const itemLabel = groupBy === 'classificacao' ? 'Insumos' : groupBy === 'grupo' ? 'Composições' : 'Item';

    // Update header
    const thead = table.querySelector('thead');
    if (thead) {
      thead.innerHTML = `
        <tr>
          <th scope="col">${label}</th>
          <th scope="col">Qtd. ${itemLabel}</th>
          <th scope="col">Preço Inicial</th>
          <th scope="col">Preço Final</th>
          <th scope="col">Variação (%)</th>
        </tr>
      `;
    }

    const tbody = table.querySelector('tbody');
    if (!tbody) return;

    const sorted = Object.entries(groups)
      .map(([cat, items]) => {
        items.sort((a, b) => a.mes.localeCompare(b.mes));
        const first = items[0]?.preco_medio || 0;
        const last = items[items.length - 1]?.preco_medio || 0;
        const variacao = first > 0 ? ((last - first) / first * 100) : 0;
        return { classificacao: cat, items, preco_inicial: first, preco_final: last, variacao, qtd: items[0]?.qtd_insumos || 0 };
      })
      .sort((a, b) => Math.abs(b.variacao) - Math.abs(a.variacao));

    tbody.innerHTML = sorted.map(cat => `
      <tr>
        <td><span class="badge badge-classificacao">${utils.escapeHtml(cat.classificacao)}</span></td>
        <td>${cat.qtd}</td>
        <td>${utils.formatCurrency(cat.preco_inicial)}</td>
        <td>${utils.formatCurrency(cat.preco_final)}</td>
        <td class="${cat.variacao >= 0 ? 'text-error' : 'text-success'}">${cat.variacao >= 0 ? '+' : ''}${cat.variacao.toFixed(2)}%</td>
      </tr>
    `).join('');
  }

  return { perform };
}
