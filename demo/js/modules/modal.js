/** @file Módulo do Modal de Detalhes (Histórico + BOM + Man-Hours + Otimização) */
import { createChartConfig, getChartTheme, hexToRgba } from '../utils.js';

export function createModal(config, state, dom, utils, api, toast) {
  let historyChartInstance = null;
  let bomViewMode = 'cards';

  function cleanup() {
    if (historyChartInstance) {
      historyChartInstance.destroy();
      historyChartInstance = null;
    }
  }

  function setBomView(mode) {
    bomViewMode = mode;
    if (dom.btnBomGrid) dom.btnBomGrid.classList.toggle('active', mode === 'cards');
    if (dom.btnBomList) dom.btnBomList.classList.toggle('active', mode === 'table');
    if (dom.bomGrid) dom.bomGrid.classList.toggle('hidden', mode !== 'cards');
    if (dom.bomTableWrapper) dom.bomTableWrapper.classList.toggle('hidden', mode !== 'table');
  }

  async function show(tipo, codigo) {
    if (!codigo) return;

    const tipoPlural = tipo === 'insumo' ? 'insumos' : 'composicoes';
    const tipoSingular = tipo === 'insumo' ? 'insumo' : 'composicao';

    dom.detailModal?.classList.remove('hidden');
    document.body.style.overflow = 'hidden';
    cleanup();

    // Reset state
    if (dom.bomGrid) dom.bomGrid.innerHTML = '';
    if (dom.bomTableContainer) dom.bomTableContainer.innerHTML = '';
    if (dom.optimizationContainer) dom.optimizationContainer.innerHTML = '';
    if (dom.modalStatsRow) dom.modalStatsRow.innerHTML = '';
    if (dom.modalTitle) dom.modalTitle.textContent = 'Carregando detalhes...';
    if (dom.modalDesc) dom.modalDesc.textContent = '';
    if (dom.modalCode) dom.modalCode.textContent = codigo;
    if (dom.modalPrice) dom.modalPrice.textContent = '...';
    if (dom.modalPriceUnit) dom.modalPriceUnit.textContent = '';
    if (dom.modalUf) dom.modalUf.textContent = '...';
    if (dom.modalRef) dom.modalRef.textContent = '...';
    if (dom.modalRegime) dom.modalRegime.textContent = '...';

    // Hide composition-specific sections by default
    if (dom.bomSection) dom.bomSection.classList.add('hidden');
    if (dom.manHoursSection) dom.manHoursSection.classList.add('hidden');
    if (dom.optimizationSection) dom.optimizationSection.classList.add('hidden');
    if (dom.bomViewToggle) dom.bomViewToggle.classList.add('hidden');

    try {
      const uf = dom.stateFilter?.value || utils.getDefaultUf();
      const date = dom.dateFilter?.value || utils.getDefaultDate();
      const regime = dom.regimeFilter?.value || utils.getDefaultRegime();

      // Update meta info
      if (dom.modalUf) dom.modalUf.textContent = uf;
      if (dom.modalRef) dom.modalRef.textContent = date;
      if (dom.modalRegime) dom.modalRegime.textContent = regime === 'NAO_DESONERADO' ? 'Não Desonerado' : regime === 'DESONERADO' ? 'Desonerado' : regime;

      // Fetch item details
      const itemUrl = `${config.API_BASE}/${tipoPlural}/${encodeURIComponent(codigo)}?uf=${uf}&data_referencia=${date}&regime=${encodeURIComponent(regime)}`;
      const itemData = await api.request(itemUrl);

      const valor = tipoSingular === 'insumo' ? (itemData.preco_mediano || 0) : (itemData.custo_total || 0);

      if (dom.modalTitle) dom.modalTitle.textContent = tipoSingular === 'insumo' ? 'Detalhes do Insumo' : 'Detalhes da Composição';
      if (dom.modalDesc) dom.modalDesc.textContent = itemData.descricao || 'Sem descrição';
      if (dom.modalPrice) dom.modalPrice.textContent = utils.formatCurrency(valor);
      if (dom.modalPriceUnit) dom.modalPriceUnit.textContent = `/${itemData.unidade || 'un'}`;
      if (dom.modalTypeBadge) {
        dom.modalTypeBadge.textContent = tipoSingular === 'insumo' ? 'INSUMO' : 'COMPOSIÇÃO';
        dom.modalTypeBadge.className = `type-tag tag-${tipoSingular === 'insumo' ? 'insumo' : 'comp'}`;
      }

      // Fetch history
      const historyUrl = `${config.API_BASE}/bi/item/${tipoSingular}/${encodeURIComponent(codigo)}/historico?uf=${uf}&regime=${encodeURIComponent(regime)}&meses=12`;
      const historyData = await api.request(historyUrl).catch((err) => {
        console.warn('[Modal] History fetch failed:', err);
        return [];
      });

      if (dom.historyChart && historyData.length > 0) {
        const ctx = dom.historyChart.getContext('2d');
        const { primaryColor, textColor, gridColor } = getChartTheme(state.theme);
        const configChart = createChartConfig('line',
          historyData.map(h => h.data_referencia),
          [{
            label: 'Preço Histórico',
            data: historyData.map(h => h.valor),
            borderColor: primaryColor,
            backgroundColor: hexToRgba(primaryColor, 0.1),
            fill: true,
            tension: 0.4,
            pointRadius: 3,
            pointHoverRadius: 6,
          }],
          state.theme,
          {
            scales: {
              y: {
                beginAtZero: false,
                ticks: {
                  callback: (v) => utils.formatCurrency(v),
                  color: textColor,
                },
                grid: { color: gridColor },
              },
              x: {
                ticks: { color: textColor },
                grid: { color: gridColor },
              }
            },
            plugins: {
              tooltip: {
                callbacks: {
                  label: (ctx) => ` ${utils.formatCurrency(ctx.parsed.y)}`
                }
              }
            }
          }
        );
        historyChartInstance = new Chart(ctx, configChart);
      } else if (dom.historyChart) {
        const chartContainer = dom.historyChart.parentElement;
        chartContainer.innerHTML = '<p class="empty-state">Sem dados históricos disponíveis.</p>';
      }

      // Composition-specific data
      if (tipoSingular === 'composicao') {
        // Fetch BOM
        const bomUrl = `${config.API_BASE}/bi/composicao/${encodeURIComponent(codigo)}/bom?uf=${uf}&data_referencia=${date}&regime=${encodeURIComponent(regime)}`;
        const bomData = await api.request(bomUrl).catch((err) => {
          console.warn('[Modal] BOM fetch failed:', err);
          return [];
        });

        if (dom.bomSection) dom.bomSection.classList.remove('hidden');

        if (bomData.length > 0) {
          const consolidated = bomData.reduce((acc, curr) => {
            const key = `${curr.item_codigo}-${curr.tipo_item}`;
            if (!acc[key]) {
              acc[key] = { ...curr };
            } else {
              acc[key].coeficiente_total = (acc[key].coeficiente_total || 0) + (curr.coeficiente_total || 0);
              acc[key].custo_impacto_total = (acc[key].custo_impacto_total || 0) + (curr.custo_impacto_total || 0);
              acc[key].nivel = Math.min(acc[key].nivel ?? 1, curr.nivel ?? 1);
            }
            return acc;
          }, {});

          const rows = Object.values(consolidated).sort((a, b) => (a.custo_impacto_total || 0) - (b.custo_impacto_total || 0)).reverse();
          const totalBomCost = rows.reduce((sum, r) => sum + (r.custo_impacto_total || 0), 0);

          // Show toggle
          if (dom.bomViewToggle) dom.bomViewToggle.classList.remove('hidden');

          // Cards view
          if (dom.bomGrid) {
            dom.bomGrid.innerHTML = rows.map(bom => {
              const nivel = bom.nivel ?? 1;
              const pct = totalBomCost > 0 ? ((bom.custo_impacto_total || 0) / totalBomCost * 100).toFixed(1) : '0.0';
              const indent = (nivel - 1) * 16;
              const tipoItem = bom.tipo_item === 'COMPOSICAO' ? 'comp' : 'insumo';
              const tipoLabel = bom.tipo_item === 'COMPOSICAO' ? 'COMP' : 'INS';
              const tipoIcon = bom.tipo_item === 'COMPOSICAO' ? '📦' : '🔧';
              const levelColors = ['', 'var(--primary)', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6'];
              const levelColor = levelColors[Math.min(nivel, levelColors.length - 1)] || 'var(--text-muted)';
              const connector = nivel > 1 ? `<span style="color: var(--text-muted); font-size: 0.6rem; margin-right: 0.25rem;">└─</span>` : '';

              return `
                <div class="bom-card" style="--bom-indent: ${indent}px; border-left: 3px solid ${levelColor};">
                  <div class="bom-card-header">
                    <span class="bom-level-badge" style="background: ${levelColor};">${nivel}</span>
                    <span class="type-tag tag-${tipoItem}" style="font-size:0.55rem; padding:0.15rem 0.4rem;">${tipoLabel}</span>
                    ${connector}
                    <span class="bom-card-code">${bom.item_codigo}</span>
                  </div>
                  <h5 class="bom-card-desc">${utils.escapeHtml(bom.descricao || 'N/A')}</h5>
                  <div class="bom-card-footer">
                    <span>${utils.escapeHtml(bom.unidade || 'N/A')}</span>
                    <span class="bom-card-coef">${(bom.coeficiente_total || 0).toLocaleString('pt-BR', { minimumFractionDigits: 4, maximumFractionDigits: 4 })}</span>
                    <span class="bom-card-impact">${utils.formatCurrency(bom.custo_impacto_total || 0)}</span>
                    <span class="bom-card-pct">${pct}%</span>
                  </div>
                </div>
              `;
            }).join('');
          }

          // Table view
          if (dom.bomTableContainer) {
            dom.bomTableContainer.innerHTML = `
              <table class="data-table">
                <thead>
                  <tr>
                    <th>Nível</th>
                    <th>Código</th>
                    <th>Tipo</th>
                    <th>Descrição</th>
                    <th>Unidade</th>
                    <th>Coeficiente</th>
                    <th>Impacto</th>
                    <th>% do Total</th>
                  </tr>
                </thead>
                <tbody>
                  ${rows.map(bom => {
                    const nivel = bom.nivel ?? 1;
                    const pct = totalBomCost > 0 ? ((bom.custo_impacto_total || 0) / totalBomCost * 100).toFixed(1) : '0.0';
                    const tipoItem = bom.tipo_item === 'COMPOSICAO' ? 'comp' : 'insumo';
                    const tipoLabel = bom.tipo_item === 'COMPOSICAO' ? 'COMP' : 'INS';
                    const indent = (nivel - 1) * 12;
                    const connector = nivel > 1 ? `<span style="color: var(--text-muted); margin-right: 0.25rem;">└─</span>` : '';
                    return `
                      <tr>
                        <td><span style="font-weight:700; color:var(--primary);">${nivel}</span></td>
                        <td><small class="modal-code-badge">${bom.item_codigo}</small></td>
                        <td><span class="type-tag tag-${tipoItem}" style="font-size:0.55rem; padding:0.15rem 0.4rem;">${tipoLabel}</span></td>
                        <td class="text-left desc-col" style="--bom-indent: ${4 + indent}px;">${connector}${utils.escapeHtml(bom.descricao || 'N/A')}</td>
                        <td>${utils.escapeHtml(bom.unidade || 'N/A')}</td>
                        <td>${(bom.coeficiente_total || 0).toLocaleString('pt-BR', { minimumFractionDigits: 4, maximumFractionDigits: 4 })}</td>
                        <td><strong>${utils.formatCurrency(bom.custo_impacto_total || 0)}</strong></td>
                        <td><span style="color: var(--text-muted); font-size: 0.8rem;">${pct}%</span></td>
                      </tr>
                    `;
                  }).join('')}
                </tbody>
              </table>
            `;
          }
        } else if (dom.bomTableContainer) {
          dom.bomTableContainer.innerHTML = '<p class="empty-state">Sem dados de BOM disponíveis.</p>';
        }

        // Fetch Man-Hours
        const manHoursUrl = `${config.API_BASE}/bi/composicao/${encodeURIComponent(codigo)}/hora-homem`;
        const manHoursData = await api.request(manHoursUrl).catch((err) => {
          console.warn('[Modal] Man-Hours fetch failed:', err);
          return { total_hora_homem: 0 };
        });

        if (dom.manHoursSection) dom.manHoursSection.classList.remove('hidden');
        if (dom.manHoursValue) {
          const hh = manHoursData.total_hora_homem || 0;
          dom.manHoursValue.textContent = `${hh.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} h`;
        }

        // Fetch Optimization Candidates
        const optUrl = `${config.API_BASE}/bi/composicao/${encodeURIComponent(codigo)}/otimizar?uf=${uf}&data_referencia=${date}&regime=${encodeURIComponent(regime)}&top_n=5`;
        const optData = await api.request(optUrl).catch((err) => {
          console.warn('[Modal] Optimization fetch failed:', err);
          return [];
        });

        if (dom.optimizationSection) dom.optimizationSection.classList.remove('hidden');
        if (dom.optimizationContainer) {
          if (optData.length === 0) {
            dom.optimizationContainer.innerHTML = '<p class="empty-state">Sem candidatos para otimização.</p>';
          } else {
            dom.optimizationContainer.innerHTML = optData.map((item, idx) => `
              <div class="opt-item">
                <span class="opt-rank rank-${idx + 1}">${idx + 1}</span>
                <div class="opt-info">
                  <div class="opt-desc">${utils.escapeHtml(item.descricao || 'N/A')}</div>
                  <div class="opt-meta">Código: ${item.item_codigo} · ${utils.escapeHtml(item.unidade || '')} · Coef: ${(item.coeficiente_total || 0).toFixed(4)}</div>
                </div>
                <span class="opt-impact">${utils.formatCurrency(item.custo_impacto_total || 0)}</span>
              </div>
            `).join('');
          }
        }
      }

      // Stats row (no duplicate price - already shown in modalPriceDisplay)
      if (dom.modalStatsRow) {
        const stats = [];
        stats.push({ label: 'Unidade', value: utils.escapeHtml(itemData.unidade || 'N/A') });

        dom.modalStatsRow.innerHTML = stats.map(s => `
          <div class="modal-stat-item">
            <span class="modal-stat-label">${s.label}</span>
            <span class="modal-stat-value">${s.value}</span>
          </div>
        `).join('');
      }

      // Initialize BOM view
      setBomView(bomViewMode);

    } catch (error) {
      console.error('[Modal] Fatal error loading details:', error);
      toast.show(`Erro ao carregar detalhes: ${error.message || 'Erro desconhecido'}`, 'error');
      close();
    }
  }

  function close() {
    dom.detailModal?.classList.add('hidden');
    document.body.style.overflow = 'auto';
    cleanup();
  }

  return { show, close, setBomView };
}
