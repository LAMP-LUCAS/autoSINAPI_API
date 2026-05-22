export function createComparison(config, state, dom, utils, api, toast) {
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

      const url1 = `${config.API_BASE}/bi/composicao/${encodeURIComponent(code1)}/bom?uf=${encodeURIComponent(uf)}&data_referencia=${encodeURIComponent(date)}&regime=${encodeURIComponent(regime)}`;
      const url2 = `${config.API_BASE}/bi/composicao/${encodeURIComponent(code2)}/bom?uf=${encodeURIComponent(uf)}&data_referencia=${encodeURIComponent(date)}&regime=${encodeURIComponent(regime)}`;

      const [leftResp, rightResp] = await Promise.all([
        api.request(url1).catch(err => { console.warn('[Comparison] BOM 1 vazio:', err.message); return []; }),
        api.request(url2).catch(err => { console.warn('[Comparison] BOM 2 vazio:', err.message); return []; }),
      ]);

      const left = { codigo: code1, nome: `Composição ${code1}`, bom: Array.isArray(leftResp) ? leftResp : [] };
      const right = { codigo: code2, nome: `Composição ${code2}`, bom: Array.isArray(rightResp) ? rightResp : [] };

      const leftFlat = flattenBom(left.bom);
      const rightFlat = flattenBom(right.bom);

      if (leftFlat.length === 0 && rightFlat.length === 0) {
        toast.show('Nenhum dado de BOM encontrado para as composições informadas.', 'info');
        dom.comparisonResults?.classList.add('hidden');
      } else {
        state.comparison.left = left;
        state.comparison.right = right;
        renderTables(left, right, leftFlat, rightFlat);
        renderChart(left, right);
        dom.comparisonResults?.classList.remove('hidden');
      }
    } catch (err) {
      console.error('[Comparison] Erro ao carregar composições:', err);
      toast.show(err.message.includes('Nenhum') ? err.message : 'Erro ao carregar composições', 'error');
    } finally {
      state.comparison.loading = false;
      dom.comparisonSkeleton?.classList.add('hidden');
    }
  }

  function flattenBom(bom) {
    if (!bom || !Array.isArray(bom)) return [];
    return bom.map(item => ({ ...item, nivel: item.nivel || 0 }));
  }

  function renderTables(left, right, leftFlat, rightFlat) {
    const leftTotal = leftFlat.reduce((s, i) => s + (i.custo_impacto_total || 0), 0);
    const rightTotal = rightFlat.reduce((s, i) => s + (i.custo_impacto_total || 0), 0);

    dom.comparisonName1.textContent = `${left.nome} (${left.codigo}) — Total: ${utils.formatCurrency(leftTotal)}`;
    dom.comparisonName2.textContent = `${right.nome} (${right.codigo}) — Total: ${utils.formatCurrency(rightTotal)}`;

    renderSingleTable(dom.comparisonLeftTable, leftFlat);
    renderSingleTable(dom.comparisonRightTable, rightFlat);

    renderDeltaTable(leftFlat, rightFlat);
  }

  function renderSingleTable(tbody, items) {
    if (!tbody) return;
    const sorted = items.sort((a, b) => a.nivel - b.nivel);
    tbody.innerHTML = sorted.map(item => `
      <tr>
        <td class="cmp-nivel" style="padding-left: ${item.nivel * 1.5 + 0.5}rem">${'.'.repeat(item.nivel)}${item.descricao || ''}</td>
        <td>${item.tipo_item || '-'}</td>
        <td>${item.unidade || '-'}</td>
        <td>${utils.formatCurrency(item.custo_impacto_total || 0)}</td>
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
        descricao: l?.descricao || r?.descricao || key,
        tipo: l?.tipo_item || r?.tipo_item || '',
        unidade: l?.unidade || r?.unidade || '',
        leftCost: lCost,
        rightCost: rCost,
        diff,
        pct,
      });
    }

    rows.sort((a, b) => Math.abs(b.diff) - Math.abs(a.diff));

    tbody.innerHTML = rows.map(row => {
      const cls = row.diff > 0.01 ? 'text-success' : row.diff < -0.01 ? 'text-error' : '';
      return `
        <tr>
          <td>${utils.escapeHtml(row.descricao)}</td>
          <td>${row.tipo}</td>
          <td>${row.unidade}</td>
          <td>${utils.formatCurrency(row.leftCost)}</td>
          <td>${utils.formatCurrency(row.rightCost)}</td>
          <td class="${cls}">${row.diff > 0 ? '+' : ''}${utils.formatCurrency(row.diff)}</td>
          <td class="${cls}">${row.pct > 0 ? '+' : ''}${row.pct.toFixed(1)}%</td>
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

  return { perform };
}
