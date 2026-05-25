/** @file Módulo do Modal de Detalhes (Histórico + BOM + Man-Hours + Otimização) */
import { createChartConfig, getChartTheme, hexToRgba } from '../utils.js';

export function createModal(config, state, dom, utils, api, toast, heatmap) {
  let historyChartInstance = null;
  let bomViewMode = 'cards';
  let bomDataCache = [];
  let currentItemData = null;
  let currentTipo = null;
  let lastFocusedElement = null;

  function trapFocus(event) {
    const focusable = dom.detailModal?.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
    if (!focusable || focusable.length === 0) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.key === 'Tab') {
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
  }

  function cleanup() {
    if (historyChartInstance) {
      historyChartInstance.destroy();
      historyChartInstance = null;
    }
    bomDataCache = [];
    if (state.heatmap) state.heatmap.data = null;
    if (state.heatmap && state.heatmap.chart) {
      state.heatmap.chart.destroy();
      state.heatmap.chart = null;
    }
    if (state.heatmap && state.heatmap.map) {
      state.heatmap.map.remove();
      state.heatmap.map = null;
    }
  }

  function setBomView(mode) {
    bomViewMode = mode;
    if (dom.btnBomGrid) dom.btnBomGrid.classList.toggle('active', mode === 'cards');
    if (dom.btnBomList) dom.btnBomList.classList.toggle('active', mode === 'table');
    if (dom.bomGrid) dom.bomGrid.classList.toggle('hidden', mode !== 'cards');
    if (dom.bomTableWrapper) dom.bomTableWrapper.classList.toggle('hidden', mode !== 'table');
  }

  function renderBomSearch() {
    if (dom.bomSearchInput && dom.bomGrid) {
      dom.bomSearchInput.value = '';
      dom.bomSearchInput.classList.remove('has-filter');
    }
  }

  function filterBom(query) {
    const q = (query || '').toLowerCase().trim();
    if (!dom.bomGrid) return;

    const cards = dom.bomGrid.querySelectorAll('.bom-card');
    const tableRows = dom.bomTableContainer?.querySelectorAll('.data-table tbody tr');

    const showAll = !q;

    cards.forEach(card => {
      const text = card.textContent.toLowerCase();
      card.style.display = (!showAll && !text.includes(q)) ? 'none' : '';
    });

    tableRows?.forEach(row => {
      const text = row.textContent.toLowerCase();
      row.style.display = (!showAll && !text.includes(q)) ? 'none' : '';
    });

    if (dom.bomSearchInput) {
      dom.bomSearchInput.classList.toggle('has-filter', !!q);
    }
  }

  async function show(tipo, codigo) {
    if (!codigo) return;

    const tipoPlural = tipo === 'insumo' ? 'insumos' : 'composicoes';
    const tipoSingular = tipo === 'insumo' ? 'insumo' : 'composicao';

    dom.detailModal?.classList.remove('hidden');
    document.body.style.overflow = 'hidden';
    lastFocusedElement = document.activeElement;
    cleanup();

    setTimeout(() => {
      const closeBtn = dom.detailModal?.querySelector('.modal-close');
      if (closeBtn) closeBtn.focus();
    }, 100);
    dom.detailModal?.addEventListener('keydown', trapFocus);

    // Reset state
    if (dom.bomGrid) dom.bomGrid.innerHTML = '';
    if (dom.bomTableContainer) dom.bomTableContainer.innerHTML = '';
    if (dom.optimizationContainer) dom.optimizationContainer.innerHTML = '';
    if (dom.modalStatsRow) dom.modalStatsRow.innerHTML = '';
    if (dom.bomCostComparison) dom.bomCostComparison.innerHTML = '';
    if (dom.modalTitle) dom.modalTitle.textContent = 'Carregando detalhes...';
    if (dom.modalDesc) dom.modalDesc.textContent = '';
    if (dom.modalCode) dom.modalCode.textContent = codigo;
    if (dom.modalPrice) dom.modalPrice.textContent = '...';
    if (dom.modalPriceUnit) dom.modalPriceUnit.textContent = '';
    if (dom.modalUf) dom.modalUf.textContent = '...';
    if (dom.modalRef) dom.modalRef.textContent = '...';
    if (dom.modalRegime) dom.modalRegime.textContent = '...';
    if (dom.modalStatusBadge) dom.modalStatusBadge.textContent = '';
    if (dom.modalStatusBadge) dom.modalStatusBadge.className = '';
    if (dom.modalClassificacao) dom.modalClassificacao.textContent = '';
    if (dom.modalGrupo) dom.modalGrupo.textContent = '';

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

      currentItemData = itemData;
      currentTipo = tipoSingular;
      const valor = tipoSingular === 'insumo' ? (itemData.preco_mediano || 0) : (itemData.custo_total || 0);

      if (dom.modalTitle) dom.modalTitle.textContent = tipoSingular === 'insumo' ? 'Detalhes do Insumo' : 'Detalhes da Composição';
      if (dom.modalDesc) dom.modalDesc.textContent = itemData.descricao || 'Sem descrição';
      if (dom.modalPrice) dom.modalPrice.textContent = utils.formatCurrency(valor);
      if (dom.modalPriceUnit) dom.modalPriceUnit.textContent = `/${itemData.unidade || 'un'}`;
      if (dom.modalTypeBadge) {
        dom.modalTypeBadge.textContent = tipoSingular === 'insumo' ? 'INSUMO' : 'COMPOSIÇÃO';
        dom.modalTypeBadge.className = `type-tag tag-${tipoSingular === 'insumo' ? 'insumo' : 'comp'}`;
      }

      // Status badge
      if (dom.modalStatusBadge && itemData.status && itemData.status !== 'ATIVO') {
        dom.modalStatusBadge.textContent = 'INATIVO';
        dom.modalStatusBadge.className = 'badge badge-inativo';
      }

      // Classificacao / Grupo
      if (dom.modalClassificacao && tipoSingular === 'insumo' && itemData.classificacao) {
        dom.modalClassificacao.textContent = itemData.classificacao;
      }
      if (dom.modalGrupo && tipoSingular === 'composicao' && itemData.grupo) {
        dom.modalGrupo.textContent = itemData.grupo;
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

      // Fetch Maintenance History (1.7) — silent 404 is expected
      if (dom.maintenanceSection) dom.maintenanceSection.classList.add('hidden');
      if (dom.maintenanceContainer) dom.maintenanceContainer.innerHTML = '';
      const maintUrl = `${config.API_BASE}/bi/item/${tipoSingular}/${encodeURIComponent(codigo)}/manutencoes`;
      let maintData = null;
      try {
        const resp = await fetch(maintUrl);
        if (resp.ok) {
          maintData = await resp.json();
        } else if (resp.status !== 404) {
          console.warn('[Modal] Maintenance fetch failed:', resp.status, await resp.text().catch(() => ''));
        }
      } catch (err) {
        console.warn('[Modal] Maintenance fetch network error:', err);
      }

      if (maintData && maintData.length > 0 && dom.maintenanceSection && dom.maintenanceContainer) {
        dom.maintenanceSection.classList.remove('hidden');
        dom.maintenanceContainer.innerHTML = maintData.map(m => `
          <div class="maint-item">
            <span class="maint-date">${utils.escapeHtml(m.data_referencia)}</span>
            <span class="maint-type ${m.tipo_manutencao === 'ATIVACAO' ? 'maint-active' : 'maint-inactive'}">${utils.escapeHtml(m.tipo_manutencao)}</span>
            <span class="maint-desc">${utils.escapeHtml(m.descricao_item || '')}</span>
          </div>
        `).join('');
      }

      // Heatmap Regional (1.11)
      dom.heatmapSection?.classList.add('hidden');
      if (heatmap) {
        heatmap.render(codigo, tipoSingular, date, regime);
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

          // Cache for search
          bomDataCache = rows;

          // Total BOM (all items) for percentage reference in tree display
          const totalBomCost = rows.reduce((sum, r) => sum + (r.custo_impacto_total || 0), 0);

          // BOM Cost Comparison (1.4) — only leaf INSUMO items to avoid vertical duplication
          if (dom.bomCostComparison && itemData.custo_total != null) {
            const oficial = Number(itemData.custo_total) || 0;

            // Filter to leaf insumos only (skip sub-composicoes to avoid double-count)
            const insumos = rows.filter(r => r.tipo_item === 'INSUMO');
            const totalInsumos = insumos.reduce((sum, r) => sum + (r.custo_impacto_total || 0), 0);

            // Breakdown by category
            const maoDeObra = insumos.filter(r => r.unidade === 'H')
              .reduce((sum, r) => sum + (r.custo_impacto_total || 0), 0);
            const equipamento = insumos.filter(r => r.unidade === 'CHP')
              .reduce((sum, r) => sum + (r.custo_impacto_total || 0), 0);
            const material = totalInsumos - maoDeObra - equipamento;

            const pct = (v) => oficial > 0 ? ((v / oficial) * 100).toFixed(1) : '0.0';

            dom.bomCostComparison.innerHTML = `
              <div class="bom-cost-item bom-cost-header">
                <span class="bom-cost-label">Insumos</span>
                <span class="bom-cost-value">${utils.formatCurrency(totalInsumos)}</span>
                <span class="bom-cost-pct">${pct(totalInsumos)}%</span>
              </div>
              <div class="bom-cost-item bom-cost-labor">
                <span class="bom-cost-label">Mão de Obra</span>
                <span class="bom-cost-value">${utils.formatCurrency(maoDeObra)}</span>
                <span class="bom-cost-pct">${pct(maoDeObra)}%</span>
              </div>
              <div class="bom-cost-item bom-cost-material">
                <span class="bom-cost-label">Material</span>
                <span class="bom-cost-value">${utils.formatCurrency(material)}</span>
                <span class="bom-cost-pct">${pct(material)}%</span>
              </div>
              <div class="bom-cost-item bom-cost-equip">
                <span class="bom-cost-label">Equipamento</span>
                <span class="bom-cost-value">${utils.formatCurrency(equipamento)}</span>
                <span class="bom-cost-pct">${pct(equipamento)}%</span>
              </div>
              <div class="bom-cost-item bom-cost-oficial">
                <span class="bom-cost-label">Custo Oficial</span>
                <span class="bom-cost-value">${utils.formatCurrency(oficial)}</span>
                <span class="bom-cost-pct">100%</span>
              </div>
            `;
          }

          // Show toggle
          if (dom.bomViewToggle) dom.bomViewToggle.classList.remove('hidden');

          // Cards view
          renderBomCards(rows, totalBomCost);

          // Table view
          renderBomTable(rows, totalBomCost);
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

      // Stats row
      if (dom.modalStatsRow) {
        const stats = [];
        stats.push({ label: 'Unidade', value: utils.escapeHtml(itemData.unidade || 'N/A') });
        if (itemData.classificacao) stats.push({ label: 'Classificação', value: utils.escapeHtml(itemData.classificacao) });
        if (itemData.grupo) stats.push({ label: 'Grupo', value: utils.escapeHtml(itemData.grupo) });
        if (itemData.status && itemData.status !== 'ATIVO') stats.push({ label: 'Status', value: itemData.status });

        dom.modalStatsRow.innerHTML = stats.map(s => `
          <div class="modal-stat-item">
            <span class="modal-stat-label">${s.label}</span>
            <span class="modal-stat-value">${s.value}</span>
          </div>
        `).join('');
      }

      // Initialize BOM view
      setBomView(bomViewMode);
      renderBomSearch();

    } catch (error) {
      console.error('[Modal] Fatal error loading details:', error);
      toast.show(`Erro ao carregar detalhes: ${error.message || 'Erro desconhecido'}`, 'error');
      close();
    }
  }

  function renderBomCards(rows, totalBomCost) {
    if (!dom.bomGrid) return;
    dom.bomGrid.innerHTML = rows.map(bom => {
      const nivel = bom.nivel ?? 1;
      const pct = totalBomCost > 0 ? ((bom.custo_impacto_total || 0) / totalBomCost * 100).toFixed(1) : '0.0';
      const indent = (nivel - 1) * 16;
      const tipoItem = bom.tipo_item === 'COMPOSICAO' ? 'comp' : 'insumo';
      const tipoLabel = bom.tipo_item === 'COMPOSICAO' ? 'COMP' : 'INS';
      const levelColors = ['', 'var(--primary)', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6'];
      const levelColor = levelColors[Math.min(nivel, levelColors.length - 1)] || 'var(--text-muted)';

      return `
        <div class="bom-card" style="--bom-indent: ${indent}px; border-left: 3px solid ${levelColor};">
          <div class="bom-card-header">
            <span class="bom-level-badge" style="background: ${levelColor};">${nivel}</span>
            <span class="type-tag tag-${tipoItem}" style="font-size:0.55rem; padding:0.15rem 0.4rem;">${tipoLabel}</span>
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

  function renderBomTable(rows, totalBomCost) {
    if (!dom.bomTableContainer) return;
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
            return `
              <tr>
                <td><span style="font-weight:700; color:var(--primary);">${nivel}</span></td>
                <td><small class="modal-code-badge">${bom.item_codigo}</small></td>
                <td><span class="type-tag tag-${tipoItem}" style="font-size:0.55rem; padding:0.15rem 0.4rem;">${tipoLabel}</span></td>
                <td class="text-left desc-col" style="--bom-indent: ${4 + indent}px;">${utils.escapeHtml(bom.descricao || 'N/A')}</td>
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

  function exportPdf() {
    if (!currentItemData || bomDataCache.length === 0) {
      toast.show('Nenhum dado de BOM disponível para exportar.', 'warning');
      return;
    }
    try {
      const { jsPDF } = window.jspdf;
      const doc = new jsPDF({ unit: 'mm', format: 'a4' });
      const pageW = doc.internal.pageSize.getWidth();

      let y = 15;
      doc.setFontSize(16);
      doc.setTextColor(37, 99, 235);
      doc.text('AutoSINAPI — Detalhes da Composição', pageW / 2, y, { align: 'center' });
      y += 10;

      doc.setFontSize(10);
      doc.setTextColor(100, 116, 139);
      doc.text(`Gerado em: ${new Date().toLocaleDateString('pt-BR')}`, pageW - 15, y, { align: 'right' });
      y += 8;

      doc.setDrawColor(37, 99, 235);
      doc.setLineWidth(0.5);
      doc.line(15, y, pageW - 15, y);
      y += 6;

      doc.setFontSize(11);
      doc.setTextColor(30, 41, 59);
      doc.setFont(undefined, 'bold');
      doc.text(`${currentItemData.descricao || 'Sem descrição'}`, 15, y);
      y += 5;
      doc.setFont(undefined, 'normal');

      const meta = [
        `Código: ${currentItemData.codigo || ''}`,
        `UF: ${dom.modalUf?.textContent || '-'}`,
        `Referência: ${dom.modalRef?.textContent || '-'}`,
        `Regime: ${dom.modalRegime?.textContent || '-'}`,
        `Unidade: ${currentItemData.unidade || '-'}`,
      ];
      const metaStr = meta.join('  |  ');
      doc.setFontSize(8);
      doc.setTextColor(100, 116, 139);
      doc.text(metaStr, 15, y);
      y += 5;

      doc.setFontSize(14);
      doc.setTextColor(30, 41, 59);
      doc.setFont(undefined, 'bold');
      doc.text('Estrutura Analítica (BOM)', 15, y);
      y += 6;

      const tableBody = bomDataCache.map(item => [
        item.nivel?.toString() || '1',
        item.item_codigo?.toString() || '',
        item.tipo_item === 'COMPOSICAO' ? 'COMP' : 'INS',
        item.descricao || '',
        item.unidade || '',
        (item.coeficiente_total || 0).toLocaleString('pt-BR', { minimumFractionDigits: 4, maximumFractionDigits: 4 }),
        'R$ ' + (item.custo_impacto_total || 0).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
      ]);

      doc.autoTable({
        startY: y,
        head: [['Nível', 'Código', 'Tipo', 'Descrição', 'Un.', 'Coeficiente', 'Impacto']],
        body: tableBody,
        theme: 'grid',
        headStyles: { fillColor: [37, 99, 235], textColor: 255, fontSize: 8, fontStyle: 'bold' },
        bodyStyles: { fontSize: 7, textColor: [30, 41, 59] },
        alternateRowStyles: { fillColor: [248, 250, 252] },
        columnStyles: {
          0: { cellWidth: 12, halign: 'center' },
          1: { cellWidth: 18, halign: 'center' },
          2: { cellWidth: 12, halign: 'center' },
          3: { cellWidth: 'auto' },
          4: { cellWidth: 12, halign: 'center' },
          5: { cellWidth: 22, halign: 'right' },
          6: { cellWidth: 28, halign: 'right' },
        },
        margin: { left: 15, right: 15 },
        didDrawPage: (data) => {
          doc.setFontSize(7);
          doc.setTextColor(148, 163, 184);
          doc.text(`AutoSINAPI — Página ${doc.internal.getNumberOfPages()}`, pageW / 2, 290, { align: 'center' });
        },
      });

      y = doc.lastAutoTable.finalY + 8;

      const totalImpacto = bomDataCache.reduce((s, i) => s + (i.custo_impacto_total || 0), 0);
      doc.setFontSize(9);
      doc.setTextColor(30, 41, 59);
      doc.setFont(undefined, 'bold');
      doc.text(`Custo Total BOM: R$ ${totalImpacto.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}`, 15, y);
      if (currentItemData.custo_total != null) {
        const oficial = Number(currentItemData.custo_total) || 0;
        doc.text(`Custo Oficial: R$ ${oficial.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}`, pageW - 15, y, { align: 'right' });
      }

      doc.save(`autosinapi-bom-${currentItemData.codigo || 'export'}.pdf`);
      toast.show('PDF exportado com sucesso!', 'success');
    } catch (err) {
      console.error('[Modal] PDF export failed:', err);
      toast.show('Erro ao exportar PDF.', 'error');
    }
  }

  function exportChart() {
    if (!dom.historyChart) return;
    try {
      const dataUrl = dom.historyChart.toDataURL('image/png');
      utils.downloadAsFile(dataUrl, 'historico-preco.png', 'image/png');
      toast.show('Gráfico exportado como PNG!', 'success');
    } catch {
      toast.show('Erro ao exportar gráfico.', 'error');
    }
  }

  function close() {
    dom.detailModal?.classList.add('hidden');
    document.body.style.overflow = 'auto';
    dom.detailModal?.removeEventListener('keydown', trapFocus);
    cleanup();
    if (lastFocusedElement) {
      lastFocusedElement.focus();
      lastFocusedElement = null;
    }
  }

  return { show, close, setBomView, exportChart, filterBom, exportPdf };
}
