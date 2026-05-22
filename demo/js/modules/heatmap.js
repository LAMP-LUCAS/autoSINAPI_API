export function createHeatmap(config, state, dom, utils, api, toast) {
  const REGIOES = {
    NORTE: ['AC', 'AP', 'AM', 'PA', 'RO', 'RR', 'TO'],
    NORDESTE: ['AL', 'BA', 'CE', 'MA', 'PB', 'PE', 'PI', 'RN', 'SE'],
    CENTRO_OESTE: ['DF', 'GO', 'MS', 'MT'],
    SUDESTE: ['ES', 'MG', 'RJ', 'SP'],
    SUL: ['PR', 'RS', 'SC'],
  };
  const REGIAO_LABELS = {
    NORTE: 'Norte', NORDESTE: 'Nordeste', CENTRO_OESTE: 'Centro-Oeste',
    SUDESTE: 'Sudeste', SUL: 'Sul',
  };
  const REGIAO_CORES = {
    NORTE: '#3498db', NORDESTE: '#e74c3c', CENTRO_OESTE: '#f1c40f',
    SUDESTE: '#2ecc71', SUL: '#9b59b6',
  };
  const GEOJSON_URL = `${config.API_BASE}/data/geo/brazil-ufs.json`;

  function getRegiao(uf) {
    for (const [regiao, ufs] of Object.entries(REGIOES)) {
      if (ufs.includes(uf)) return regiao;
    }
    return 'OUTROS';
  }

  function destroyMap() {
    if (state.heatmap.map) {
      state.heatmap.map.remove();
      state.heatmap.map = null;
    }
  }

  function destroyChart() {
    if (state.heatmap.chart) {
      state.heatmap.chart.destroy();
      state.heatmap.chart = null;
    }
  }

  function render(codigo, tipo, data_referencia, regime) {
    const date = data_referencia || dom.modalRef?.textContent;
    const reg = regime || dom.modalRegime?.textContent;
    if (!codigo || !date) return;

    dom.heatmapSection?.classList.remove('hidden');

    const tipoMap = { insumo: 'insumo', composicao: 'composicao', insumos: 'insumo', composicoes: 'composicao' };
    const t = tipoMap[tipo] || 'insumo';

    api.request(`${config.API_BASE}/bi/item/${t}/${encodeURIComponent(codigo)}/precos-uf?data_referencia=${encodeURIComponent(date)}&regime=${encodeURIComponent(reg)}`)
      .then(data => {
        state.heatmap.data = data;
        if (!data || data.length === 0) {
          toast.show('Nenhum dado de preço regional encontrado para este item.', 'info');
          dom.heatmapSection?.classList.add('hidden');
          return;
        }
        if (typeof L !== 'undefined') {
          renderMap(data).catch(() => renderChart(data));
        } else {
          renderChart(data);
        }
      })
      .catch(err => {
        console.error('[Heatmap] Erro ao carregar preços por UF:', err);
        toast.show(err.message.includes('Nenhum') ? err.message : 'Nenhum dado de preço regional encontrado para este item.', 'info');
        dom.heatmapSection?.classList.add('hidden');
      });
  }

  async function renderMap(data) {
    destroyMap();
    destroyChart();

    dom.heatmapCanvas?.classList.add('hidden');
    dom.heatmapMapContainer?.classList.remove('hidden');

    const geoJson = await fetch(GEOJSON_URL).then(r => {
      if (!r.ok) throw new Error(`GeoJSON fetch: ${r.status}`);
      return r.json();
    });

    if (!geoJson || !geoJson.features || geoJson.features.length === 0) {
      throw new Error('GeoJSON vazio');
    }

    const priceMap = new Map(data.map(d => [d.uf, d.valor]));
    const values = data.map(d => d.valor);
    const min = Math.min(...values);
    const max = Math.max(...values);
    const range = max - min || 1;
    const avg = values.reduce((s, v) => s + v, 0) / values.length;

    function getColor(price) {
      const ratio = (price - min) / range;
      const r = Math.round(34 + ratio * 205);
      const g = Math.round(197 - ratio * 131);
      const b = Math.round(94 - ratio * 54);
      return `rgb(${r},${g},${b})`;
    }

    const map = L.map('heatmapMap', {
      center: [-15.0, -52.0],
      zoom: 4,
      zoomControl: true,
      scrollWheelZoom: false,
    });

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; <a href="https://openstreetmap.org">OSM</a>',
      maxZoom: 10,
    }).addTo(map);

    const geoLayer = L.geoJSON(geoJson, {
      style: feature => {
        const uf = (feature.properties.sigla || feature.properties.UF || '').toUpperCase();
        const price = priceMap.get(uf);
        return {
          fillColor: price != null ? getColor(price) : '#ccc',
          weight: 1.5,
          opacity: 1,
          color: '#fff',
          fillOpacity: 0.85,
        };
      },
      onEachFeature: (feature, layer) => {
        const uf = (feature.properties.sigla || feature.properties.UF || '').toUpperCase();
        const nome = feature.properties.nome || uf;
        const price = priceMap.get(uf);
        const reg = getRegiao(uf);
        const regCor = REGIAO_CORES[reg] || '#999';

        layer.bindTooltip(`
          <strong style="color:${regCor}">${nome} (${uf})</strong><br>
          <span style="font-size:0.85em">${REGIAO_LABELS[reg] || reg}</span><br>
          <strong>R$ ${price != null ? price.toLocaleString('pt-BR', { minimumFractionDigits: 2 }) : 'N/D'}</strong>
          ${price != null ? `<span style="color:${price < avg ? '#22c55e' : '#ef4444'}"> ${price < avg ? '▼' : '▲'} ${Math.abs(((price - avg) / avg) * 100).toFixed(1)}% vs média</span>` : ''}
        `, { sticky: true });

        layer.on({
          mouseover: e => e.target.setStyle({ weight: 3, color: '#333', fillOpacity: 1 }),
          mouseout: e => geoLayer.resetStyle(e.target),
        });
      },
    }).addTo(map);

    const legend = L.control({ position: 'bottomright' });
    legend.onAdd = () => {
      const div = L.DomUtil.create('div', 'heatmap-legend-container');
      div.innerHTML = '<strong style="font-size:0.75rem">Preço</strong><br>';
      const steps = 5;
      for (let i = 0; i < steps; i++) {
        const v = min + (max - min) * (i / (steps - 1));
        div.innerHTML +=
          `<span class="heatmap-legend-bar" style="background:${getColor(v)};display:inline-block;width:14px;height:14px;margin-right:4px;vertical-align:middle;border-radius:2px;"></span>` +
          `<span style="font-size:0.7rem">R$ ${v.toLocaleString('pt-BR', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}</span><br>`;
      }
      div.innerHTML += `<span style="font-size:0.6rem;color:#888">▲/>média ▼/< média</span>`;
      return div;
    };
    legend.addTo(map);

    const regLegend = L.control({ position: 'bottomleft' });
    regLegend.onAdd = () => {
      const div = L.DomUtil.create('div', 'heatmap-legend-container');
      div.innerHTML = '<strong style="font-size:0.75rem">Regiões</strong><br>';
      for (const [reg, cor] of Object.entries(REGIAO_CORES)) {
        div.innerHTML +=
          `<span style="display:inline-block;width:10px;height:10px;background:${cor};margin-right:4px;vertical-align:middle;border-radius:50%;"></span>` +
          `<span style="font-size:0.65rem">${REGIAO_LABELS[reg]}</span><br>`;
      }
      return div;
    };
    regLegend.addTo(map);

    state.heatmap.map = map;

    setTimeout(() => map.invalidateSize(), 200);
  }

  function renderChart(data) {
    destroyMap();
    destroyChart();

    dom.heatmapMapContainer?.classList.add('hidden');
    dom.heatmapCanvas?.classList.remove('hidden');

    if (!data || data.length === 0) {
      dom.heatmapSection?.classList.add('hidden');
      return;
    }

    const regionOrder = ['NORTE', 'NORDESTE', 'CENTRO_OESTE', 'SUDESTE', 'SUL'];
    const withRegiao = data.map(d => ({ ...d, regiao: getRegiao(d.uf) }));
    withRegiao.sort((a, b) => {
      const ra = regionOrder.indexOf(a.regiao);
      const rb = regionOrder.indexOf(b.regiao);
      if (ra !== rb) return ra - rb;
      return a.valor - b.valor;
    });

    const ufs = withRegiao.map(d => d.uf);
    const values = withRegiao.map(d => d.valor);
    const min = values[0];
    const max = values[values.length - 1];
    const range = max - min || 1;
    const avg = values.reduce((s, v) => s + v, 0) / values.length;

    const ctx = dom.heatmapChart?.getContext('2d');
    if (!ctx) return;
    const existing = Chart.getChart(ctx.canvas);
    if (existing) existing.destroy();

    const textColor = getComputedStyle(document.documentElement).getPropertyValue('--text-main').trim() || '#1e293b';
    const mutedColor = getComputedStyle(document.documentElement).getPropertyValue('--text-muted').trim() || '#64748b';

    state.heatmap.chart = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: ufs,
        datasets: [{
          label: 'Preço',
          data: values,
          backgroundColor: withRegiao.map(d => {
            const ratio = (d.valor - min) / range;
            const r = Math.round(34 + ratio * (239 - 34));
            const g = Math.round(197 - ratio * 157);
            const b = Math.round(94 - ratio * 54);
            return `rgb(${r},${g},${b})`;
          }),
          borderColor: withRegiao.map(d => {
            const ratio = (d.valor - min) / range;
            const r = Math.round(34 + ratio * (239 - 34));
            const g = Math.round(197 - ratio * 157);
            const b = Math.round(94 - ratio * 54);
            return `rgb(${r},${g},${b})`;
          }),
          borderWidth: 1,
          borderRadius: 4,
        }],
      },
      options: {
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: ctx => {
                const uf = ctx.label;
                const reg = getRegiao(uf);
                return `${REGIAO_LABELS[reg] || reg} | ${uf}: ${ctx.parsed.x < avg ? '▼' : '▲'} R$ ${ctx.parsed.x.toFixed(2)}${ctx.parsed.x === min ? ' (menor)' : ctx.parsed.x === max ? ' (maior)' : ''}`;
              },
            },
          },
        },
        scales: {
          x: {
            ticks: { color: mutedColor, font: { size: 9 }, callback: v => 'R$ ' + Number(v).toFixed(2) },
            grid: { color: mutedColor + '20' },
          },
          y: {
            ticks: { color: textColor, font: { size: 9 } },
            grid: { display: false },
          },
        },
      },
    });
  }

  return { render };
}