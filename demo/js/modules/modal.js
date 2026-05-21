/** @file Módulo do Modal de Detalhes (Histórico + BOM) */
import { createChartConfig } from '../utils.js';

export function createModal(config, state, dom, utils, api, toast) {
  let historyChartInstance = null;

  function cleanup() {
    if (historyChartInstance) {
      historyChartInstance.destroy();
      historyChartInstance = null;
    }
  }

  async function show(tipo, codigo) {
    if (!codigo) return;
    
    const tipoPlural = tipo === 'insumo' ? 'insumos' : 'composicoes';
    const tipoSingular = tipo === 'insumo' ? 'insumo' : 'composicao';

    dom.detailModal?.classList.remove('hidden');
    document.body.style.overflow = 'hidden';
    cleanup();

    if (dom.bomTableContainer) dom.bomTableContainer.innerHTML = '<div class="loader"></div>';
    if (dom.modalTitle) dom.modalTitle.textContent = 'Carregando detalhes...';
    if (dom.modalDesc) dom.modalDesc.textContent = '';
    if (dom.modalCode) dom.modalCode.textContent = codigo;
    if (dom.modalUn) dom.modalUn.textContent = '...';

    if (dom.bomSection) {
      dom.bomSection.classList.toggle('hidden', tipoSingular === 'insumo');
    }

    try {
      const uf = dom.stateFilter?.value || utils.getDefaultUf();
      const date = dom.dateFilter?.value || utils.getDefaultDate();
      const regime = dom.regimeFilter?.value || utils.getDefaultRegime();

      const itemUrl = `${config.API_BASE}/${tipoPlural}/${encodeURIComponent(codigo)}?uf=${uf}&data_referencia=${date}&regime=${encodeURIComponent(regime)}`;
      const itemData = await api.request(itemUrl);

      if (dom.modalTitle) dom.modalTitle.textContent = tipoSingular === 'insumo' ? 'Detalhes do Insumo' : 'Detalhes da Composição';
      if (dom.modalDesc) dom.modalDesc.textContent = itemData.descricao || 'Sem descrição';
      if (dom.modalUn) dom.modalUn.textContent = itemData.unidade || 'N/A';
      if (dom.modalTypeBadge) {
        dom.modalTypeBadge.textContent = tipoSingular.toUpperCase();
        dom.modalTypeBadge.className = `type-tag tag-${tipoSingular === 'insumo' ? 'insumo' : 'comp'}`;
      }

      const historyUrl = `${config.API_BASE}/bi/item/${tipoSingular}/${encodeURIComponent(codigo)}/historico?uf=${uf}&regime=${encodeURIComponent(regime)}&meses=12`;
      const historyData = await api.request(historyUrl).catch(() => []);

      if (dom.historyChart && historyData.length > 0) {
        const ctx = dom.historyChart.getContext('2d');
        const configChart = createChartConfig('line',
          historyData.map(h => h.data_referencia),
          [{
            label: 'Preço Histórico',
            data: historyData.map(h => h.valor),
            borderColor: state.theme === 'dark' ? '#60a5fa' : '#3b82f6',
            backgroundColor: state.theme === 'dark' ? 'rgba(96,165,250,0.1)' : 'rgba(59,130,246,0.1)',
            fill: true,
            tension: 0.4,
          }],
          state.theme,
          { scales: { y: { beginAtZero: false } } }
        );
        historyChartInstance = new Chart(ctx, configChart);
      }

      if (tipoSingular === 'composicao' && dom.bomTableContainer) {
        const bomUrl = `${config.API_BASE}/bi/composicao/${encodeURIComponent(codigo)}/bom?uf=${uf}&data_referencia=${date}&regime=${encodeURIComponent(regime)}`;
        const bomData = await api.request(bomUrl).catch(() => []);

        if (bomData.length === 0) {
          dom.bomTableContainer.innerHTML = '<p class="empty-state">Sem dados de Bill of Materials disponíveis.</p>';
        } else {
          // Consolidação de itens duplicados no frontend para garantir visão Flat
          const consolidated = bomData.reduce((acc, curr) => {
            const key = `${curr.item_codigo}-${curr.tipo_item}`;
            if (!acc[key]) {
              acc[key] = { ...curr };
            } else {
              acc[key].coeficiente_total = (acc[key].coeficiente_total || 0) + (curr.coeficiente_total || 0);
              acc[key].custo_impacto_total = (acc[key].custo_impacto_total || 0) + (curr.custo_impacto_total || 0);
              acc[key].nivel = Math.min(acc[key].nivel, curr.nivel);
            }
            return acc;
          }, {});

          const rows = Object.values(consolidated).sort((a, b) => a.nivel - b.nivel);

          dom.bomTableContainer.innerHTML = `
            <table class="data-table">
              <thead>
                <tr>
                  <th>Nível</th>
                  <th>Código</th>
                  <th>Descrição</th>
                  <th>Unidade</th>
                  <th>Qtd. Coef</th>
                  <th>Total</th>
                </tr>
              </thead>
              <tbody>
                ${rows.map(bom => `
                  <tr>
                    <td><span style="font-weight:700; color:var(--primary);">${bom.nivel}</span></td>
                    <td><small class="modal-code-badge">${bom.item_codigo}</small></td>
                    <td class="text-left">
                        <span class="type-tag tag-${bom.tipo_item?.toLowerCase() === 'insumo' ? 'insumo' : 'comp'}" style="font-size:0.5rem; padding:0.1rem 0.3rem;">${bom.tipo_item}</span><br>
                        ${utils.escapeHtml(bom.descricao || 'N/A')}
                    </td>
                    <td>${utils.escapeHtml(bom.unidade || 'N/A')}</td>
                    <td>${(bom.coeficiente_total || 0).toLocaleString('pt-BR', { minimumFractionDigits: 4 })}</td>
                    <td><strong>${utils.formatCurrency(bom.custo_impacto_total || 0)}</strong></td>
                  </tr>
                `).join('')}
              </tbody>
            </table>
          `;
        }
      }
    } catch (error) {
      toast.show('Erro ao carregar detalhes', 'error');
      close();
    }
  }

  function close() {
    dom.detailModal?.classList.add('hidden');
    document.body.style.overflow = 'auto';
    cleanup();
  }

  return { show, close };
}
