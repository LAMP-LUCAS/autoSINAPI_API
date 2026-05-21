/** @file Módulo de Pesquisa / BOM */
import { createViewToggle } from '../utils.js';

export function createSearch(config, state, dom, utils, api, toast) {
  const viewToggle = createViewToggle(
    'class',
    { container: dom.resultsGrid, baseClass: 'results-grid', btnGrid: dom.btnGrid, btnList: dom.btnList },
    state.search
  );

  async function perform() {
    const query = dom.searchInput?.value?.trim();
    if (!query || query.length < 3) {
      toast.show('Digite pelo menos 3 caracteres', 'warning');
      return;
    }

    state.search.loading = true;
    dom.searchSkeleton?.classList.remove('hidden');
    if (dom.resultsGrid) dom.resultsGrid.innerHTML = '';
    dom.noResults?.classList.add('hidden');

    try {
      const uf = dom.stateFilter?.value || utils.getDefaultUf();
      const date = dom.dateFilter?.value || utils.getDefaultDate();
      const regime = dom.regimeFilter?.value || utils.getDefaultRegime();
      const searchType = state.search.searchType || 'insumos';

      let url = `${config.API_BASE}/${searchType}?q=${encodeURIComponent(query)}&uf=${uf}&data_referencia=${date}&regime=${encodeURIComponent(regime)}`;

      if (searchType === 'insumos') {
        const classificacao = dom.classificacaoFilter?.value;
        if (classificacao) url += `&classificacao=${encodeURIComponent(classificacao)}`;
      } else {
        const grupo = dom.grupoFilter?.value;
        if (grupo) url += `&grupo=${encodeURIComponent(grupo)}`;
      }

      const data = await api.request(url);
      const results = Array.isArray(data) ? data : (data.data || []);

      state.search.results = results.map(item => ({
        ...item,
        _tipo: searchType === 'insumos' ? 'insumo' : 'composicao',
        _preco: searchType === 'insumos' ? (item.preco_mediano || 0) : (item.custo_total || 0),
      }));

      render();
    } catch {
      dom.resultsGrid.innerHTML = '<p class="empty-state">Erro ao buscar resultados.</p>';
    } finally {
      state.search.loading = false;
      setTimeout(() => dom.searchSkeleton?.classList.add('hidden'), 300);
    }
  }

  function render() {
    const results = state.search.results;
    if (!results?.length) {
      dom.resultsGrid.innerHTML = '';
      dom.noResults?.classList.remove('hidden');
      dom.resultsActions?.classList.add('hidden');
      return;
    }

    dom.resultsActions?.classList.remove('hidden');
    if (dom.resultsCount) dom.resultsCount.textContent = `${results.length} resultado(s)`;

    const sorted = [...results].sort((a, b) => {
      switch (state.search.sortBy) {
        case 'name_asc': return (a.descricao || '').localeCompare(b.descricao || '');
        case 'name_desc': return (b.descricao || '').localeCompare(a.descricao || '');
        case 'price_desc': return (b._preco || 0) - (a._preco || 0);
        case 'price_asc': return (a._preco || 0) - (b._preco || 0);
        default: return 0;
      }
    });

    dom.resultsGrid.innerHTML = sorted.map(item => {
      const tipo = item._tipo;
      const tagClass = tipo === 'insumo' ? 'tag-insumo' : 'tag-comp';
      const tagLabel = tipo === 'insumo' ? 'INSUMO' : 'COMPOSIÇÃO';
      const preco = utils.formatCurrency(item._preco || 0);
      const classificacao = item.classificacao ? `<span class="badge badge-classificacao">${utils.escapeHtml(item.classificacao)}</span>` : '';
      const grupo = item.grupo ? `<span class="badge badge-grupo">${utils.escapeHtml(item.grupo)}</span>` : '';
      const status = item.status && item.status !== 'ATIVO' ? `<span class="badge badge-inativo">INATIVO</span>` : '';

      return `
        <div class="card" data-codigo="${item.codigo}" data-tipo="${tipo}" role="listitem">
          <div class="card-badges">
            <span class="type-tag ${tagClass}">${tagLabel}</span>
            ${tipo === 'insumo' ? classificacao : grupo}
            ${status}
          </div>
          <h3>${utils.escapeHtml(item.descricao || 'Sem descrição')}</h3>
          <div class="price-row">
            <span class="val">${preco}</span>
            <span class="unit">${utils.escapeHtml(item.unidade || 'N/A')}</span>
          </div>
        </div>
      `;
    }).join('');
  }

  function setSearchType(type) {
    state.search.searchType = type;
    if (dom.searchTypeInsumos) {
      dom.searchTypeInsumos.classList.toggle('active', type === 'insumos');
    }
    if (dom.searchTypeComposicoes) {
      dom.searchTypeComposicoes.classList.toggle('active', type === 'composicoes');
    }
    if (api.updateFilterVisibility) api.updateFilterVisibility();
  }

  function exportData(format) {
    const data = state.search.results;
    if (!data?.length) { toast.show('Nada para exportar', 'warning'); return; }

    const cleanData = data.map(({ _tipo, _preco, ...rest }) => rest);

    if (format === 'json') {
      utils.downloadAsFile(JSON.stringify(cleanData, null, 2), 'sinapi-pesquisa.json', 'application/json');
      toast.show('JSON exportado com sucesso!', 'success');
      return;
    }

    if (format === 'md') {
      const headers = Object.keys(cleanData[0]);
      const mdContent = [
        `# AutoSINAPI - Pesquisa`,
        ``,
        `| ${headers.join(' | ')} |`,
        `| ${headers.map(() => '---').join(' | ')} |`,
        ...cleanData.map(row => `| ${headers.map(h => row[h] ?? '').join(' | ')} |`),
      ].join('\n');
      utils.downloadAsFile(mdContent, 'sinapi-pesquisa.md', 'text/markdown');
      toast.show('Markdown exportado com sucesso!', 'success');
      return;
    }

    if (format === 'pdf' && window.jspdf) {
      const { jsPDF } = window.jspdf;
      const doc = new jsPDF();

      doc.setFontSize(16);
      doc.text('AutoSINAPI - Pesquisa', 14, 20);
      doc.setFontSize(10);
      doc.text(`Total: ${data.length} resultado(s) | Data: ${new Date().toLocaleDateString('pt-BR')}`, 14, 30);

      const headers = [['Código', 'Descrição', 'Unidade', 'Valor', 'Tipo']];
      const rows = data.map(item => [
        item.codigo,
        item.descricao || '',
        item.unidade || '',
        utils.formatCurrency(item._preco || 0),
        item._tipo === 'insumo' ? 'Insumo' : 'Composição',
      ]);

      doc.autoTable({
        head: headers,
        body: rows,
        startY: 35,
        styles: { fontSize: 8, cellPadding: 3 },
        headStyles: { fillColor: [37, 99, 235] },
        alternateRowStyles: { fillColor: [245, 247, 250] },
      });

      doc.save('sinapi-pesquisa.pdf');
      toast.show('PDF exportado com sucesso!', 'success');
      return;
    }

    if (format === 'pdf') {
      toast.show('Biblioteca jsPDF não carregada. Use JSON ou MD.', 'warning');
      return;
    }

    const content = [Object.keys(cleanData[0]).join(','), ...cleanData.map(r =>
      Object.values(r).map(v => `"${(v || '').toString().replace(/"/g, '""')}"`).join(',')
    )].join('\n');
    utils.downloadAsFile(content, 'sinapi-pesquisa.csv', 'text/csv');
    toast.show('CSV exportado com sucesso!', 'success');
  }

  return { perform, render, setView: viewToggle.setView, export: exportData, setSearchType };
}
