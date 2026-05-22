export function createComparison(config, state, dom, utils, api, toast, modal) {
  async function perform() {
    const code1 = dom.comparisonCode1?.value.trim();
    const code2 = dom.comparisonCode2?.value.trim();
    if (!code1 || !code2) {
      toast.show('Informe os códigos das duas composições', 'warning');
      return;
    }

    state.comparison.loading = true;
    dom.comparisonSkeleton?.classList.remove('hidden');
    dom.comparisonResults?.classList.add('hidden');

    try {
      const uf = dom.comparisonUfFilter?.value || 'SP';
      const date = dom.comparisonDateFilter?.value || utils.getDefaultDate();
      const regime = dom.comparisonRegimeFilter?.value || utils.getDefaultRegime();

      // Buscar detalhes e BOM em paralelo
      const [leftData, rightData] = await Promise.all([
        fetchFullCompositionData(code1, uf, date, regime),
        fetchFullCompositionData(code2, uf, date, regime)
      ]);

      if (leftData.bom.length === 0 && rightData.bom.length === 0) {
        toast.show('Nenhum dado encontrado para as composições informadas.', 'info');
        dom.comparisonResults?.classList.add('hidden');
        if (dom.comparisonViewToggle) dom.comparisonViewToggle.style.display = 'none';
      } else {
        state.comparison.left = leftData;
        state.comparison.right = rightData;
        renderTables(leftData, rightData);
        renderChart(leftData, rightData);
        dom.comparisonResults?.classList.remove('hidden');
        if (dom.comparisonViewToggle) dom.comparisonViewToggle.style.display = 'flex';
      }
    } catch (err) {
      console.error('[Comparison] Erro ao carregar composições:', err);
      toast.show(err.message.includes('Nenhum') ? err.message : 'Erro ao carregar composições', 'error');
    } finally {
      state.comparison.loading = false;
      dom.comparisonSkeleton?.classList.add('hidden');
    }
  }

  async function fetchFullCompositionData(codigo, uf, date, regime) {
    const detailsUrl = `${config.API_BASE}/composicoes/${encodeURIComponent(codigo)}?uf=${encodeURIComponent(uf)}&data_referencia=${encodeURIComponent(date)}&regime=${encodeURIComponent(regime)}`;
    const bomUrl = `${config.API_BASE}/bi/composicao/${encodeURIComponent(codigo)}/bom?uf=${encodeURIComponent(uf)}&data_referencia=${encodeURIComponent(date)}&regime=${encodeURIComponent(regime)}`;

    const [details, bom] = await Promise.all([
      api.request(detailsUrl).catch(() => ({ codigo, descricao: `Composição ${codigo}`, custo_total: 0 })),
      api.request(bomUrl).catch(() => [])
    ]);

    return {
      ...details,
      bom: Array.isArray(bom) ? bom : []
    };
  }

  function renderTables(left, right) {
    const leftFlat = flattenBom(left.bom);
    const rightFlat = flattenBom(right.bom);
    const leftTotal = left.custo_total || leftFlat.reduce((s, i) => s + (i.custo_impacto_total || 0), 0);
    const rightTotal = right.custo_total || rightFlat.reduce((s, i) => s + (i.custo_impacto_total || 0), 0);

    // Render Headers com links para modal
    const renderHeader = (el, data, total) => {
      if (!el) return;
      el.innerHTML = `
        <div class="comparison-header-content">
          <span class="comp-code clickable" onclick="AutoSINAPI.modal.show('composicao', '${data.codigo}')">#${data.codigo}</span>
          <div class="comp-info">
            <span class="comp-name clickable" onclick="AutoSINAPI.modal.show('composicao', '${data.codigo}')">${utils.escapeHtml(data.descricao)}</span>
            <span class="comp-total">${utils.formatCurrency(total)}</span>
          </div>
        </div>
      `;
    };

    renderHeader(dom.comparisonName1, left, leftTotal);
    renderHeader(dom.comparisonName2, right, rightTotal);

    renderSingleTable(dom.comparisonLeftTable, leftFlat);
    renderSingleTable(dom.comparisonRightTable, rightFlat);

    renderDeltaTable(leftFlat, rightFlat);
  }

  function flattenBom(bom) {
    if (!bom || !Array.isArray(bom)) return [];
    return bom.map(item => ({ ...item, nivel: item.nivel || 0 }));
  }

  function renderSingleTable(tbody, items) {
    if (!tbody) return;
    const sorted = items.sort((a, b) => a.nivel - b.nivel);
    tbody.innerHTML = sorted.map(item => `
      <tr class="clickable" onclick="AutoSINAPI.modal.show('${item.tipo_item.toLowerCase()}', '${item.item_codigo}')">
        <td class="cmp-nivel" style="padding-left: ${item.nivel * 1 + 0.5}rem">
          <span class="nivel-dots">${'.'.repeat(item.nivel)}</span>
          <span class="item-desc">${utils.escapeHtml(item.descricao || '')}</span>
        </td>
        <td><span class="badge badge-sm ${item.tipo_item === 'INSUMO' ? 'badge-insumo' : 'badge-comp'}">${item.tipo_item[0]}</span></td>
        <td>${item.unidade || '-'}</td>
        <td class="text-right">${utils.formatCurrency(item.custo_impacto_total || 0)}</td>
      </tr>
    `).join('');
  }

  function renderDeltaTable(leftFlat, rightFlat) {
    const tbody = dom.comparisonDeltaTable;
    if (!tbody) return;

    const leftMap = new Map(leftFlat.map(i => [i.item_codigo + '_' + i.tipo_item, i]));
    const rightMap = new Map(rightFlat.map(i => [i.item_codigo + '_' + i.tipo_item, i]));
    const allKeys = new Set([...leftMap.keys(), ...rightMap.keys()]);

    const rows = [];
    for (const key of allKeys) {
      const l = leftMap.get(key);
      const r = rightMap.get(key);
      const lCost = l?.custo_impacto_total || 0;
      const rCost = r?.custo_impacto_total || 0;
      const diff = lCost - rCost;
      const pct = rCost > 0 ? (diff / rCost * 100) : (lCost > 0 ? 100 : 0);
      rows.push({
        codigo: l?.item_codigo || r?.item_codigo,
        tipo: l?.tipo_item || r?.tipo_item || '',
        descricao: l?.descricao || r?.descricao || key,
        unidade: l?.unidade || r?.unidade || '',
        leftCost: lCost,
        rightCost: rCost,
        diff,
        pct,
      });
    }

    rows.sort((a, b) => Math.abs(b.diff) - Math.abs(a.diff));

    tbody.innerHTML = rows.map(row => {
      const absDiff = Math.abs(row.diff);
      const cls = row.diff > 0.01 ? 'text-success' : row.diff < -0.01 ? 'text-error' : '';
      return `
        <tr class="clickable" onclick="AutoSINAPI.modal.show('${row.tipo.toLowerCase()}', '${row.codigo}')">
          <td class="item-desc-cell">${utils.escapeHtml(row.descricao)}</td>
          <td>${row.unidade}</td>
          <td class="text-right">${utils.formatCurrency(row.leftCost)}</td>
          <td class="text-right">${utils.formatCurrency(row.rightCost)}</td>
          <td class="text-right ${cls}"><strong>${row.diff > 0 ? '+' : ''}${utils.formatCurrency(row.diff)}</strong></td>
          <td class="text-right ${cls}">${row.pct > 0 ? '+' : ''}${row.pct.toFixed(1)}%</td>
        </tr>
      `;
    }).join('');
  }

  function getCategoria(item) {
    const unid = (item.unidade || '').toUpperCase();
    if (unid === 'H') return 'Mão de Obra';
    if (['CHP', 'CHI'].includes(unid)) return 'Equipamento';
    return 'Material';
  }

  function renderChart(left, right) {
    const canvas = dom.comparisonChart;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const existing = Chart.getChart(canvas);
    if (existing) existing.destroy();
    state.comparison.chart = null;

    const CATS = { 'Mão de Obra': 0, 'Material': 0, 'Equipamento': 0 };
    const leftCat = { ...CATS };
    const rightCat = { ...CATS };

    for (const item of flattenBom(left.bom)) {
      const cat = getCategoria(item);
      leftCat[cat] = (leftCat[cat] || 0) + (item.custo_impacto_total || 0);
    }
    for (const item of flattenBom(right.bom)) {
      const cat = getCategoria(item);
      rightCat[cat] = (rightCat[cat] || 0) + (item.custo_impacto_total || 0);
    }

    const labels = Object.keys(CATS).filter(k => leftCat[k] > 0 || rightCat[k] > 0);
    const leftData = labels.map(l => leftCat[l]);
    const rightData = labels.map(l => rightCat[l]);

    if (state.comparison.chart) state.comparison.chart.destroy();

    const textColor = getComputedStyle(document.documentElement).getPropertyValue('--text-main').trim() || '#1e293b';
    const mutedColor = getComputedStyle(document.documentElement).getPropertyValue('--text-muted').trim() || '#64748b';

    state.comparison.chart = new Chart(ctx, {
      type: 'bar',
      data: {
        labels,
        datasets: [
          { label: `Composição ${left.codigo}`, data: leftData, backgroundColor: '#3b82f680', borderColor: '#3b82f6', borderWidth: 1 },
          { label: `Composição ${right.codigo}`, data: rightData, backgroundColor: '#f59e0b80', borderColor: '#f59e0b', borderWidth: 1 },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { position: 'bottom', labels: { color: textColor, font: { size: 10 } } },
          tooltip: {
            callbacks: {
              label: ctx => `${ctx.dataset.label}: ${utils.formatCurrency(ctx.parsed.y)}`,
            },
          },
        },
        scales: {
          x: { ticks: { color: mutedColor, font: { size: 9 } }, grid: { display: false } },
          y: { ticks: { color: mutedColor, font: { size: 9 }, callback: v => utils.formatCurrency(v) }, grid: { color: mutedColor + '20' } },
        },
      },
    });
  }

  function setView(view) {
    const tableContainer = document.getElementById('comparisonTablesView');
    const chartContainer = document.getElementById('comparisonChartView');
    const btns = dom.comparisonViewToggle?.querySelectorAll('.btn-toggle');
    
    if (!tableContainer || !chartContainer) return;

    if (view === 'tables') {
      tableContainer.classList.remove('hidden');
      chartContainer.classList.add('hidden');
    } else {
      tableContainer.classList.add('hidden');
      chartContainer.classList.remove('hidden');
      if (state.comparison.chart) {
        state.comparison.chart.resize();
      }
    }

    if (btns) {
      btns.forEach(b => {
        b.classList.toggle('active', b.dataset.view === view);
      });
    }
  }

  return { perform, setView };
}
