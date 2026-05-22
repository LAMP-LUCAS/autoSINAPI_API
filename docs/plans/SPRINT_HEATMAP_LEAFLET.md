# 🗺️ Sprint: Mapa de Calor Geográfico (Leaflet/Mapbox)

> **Status:** Planejada — Sprint independente após correção do ETL
> **Objetivo:** Substituir o gráfico de barras horizontal do heatmap por um **mapa coroplético interativo** do Brasil, colorindo cada UF pelo preço do item selecionado.

---

## 📋 Contexto

### Situação Atual

O módulo `heatmap.js` (Sprint 1c, item 1.11) atualmente exibe um **gráfico de barras horizontal** com as 27 UFs ordenadas por região geográfica. Embora funcional, isso não corresponde ao especificado: "Integração Leaflet/Mapbox para visualização geográfica de preços."

### Melhorias já aplicadas (base para o mapa)

- Endpoint `GET /bi/item/{tipo}/{codigo}/precos-uf` retorna `[{uf, valor}, ...]` para todas as 27 UFs ✅
- UFs agrupadas por região (Norte, Nordeste, Centro-Oeste, Sudeste, Sul) com cores distintas ✅
- Legenda de regiões no heatmap card ✅

---

## 🎯 Escopo da Sprint

### Tarefa 1: Adicionar dependência Leaflet

**Arquivo:** `demo/index.html`

Adicionar o CDN do Leaflet antes do `</head>`:

```html
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
```

**Alternativa (recomendada para performance):** Usar módulo ES ou import map.

### Tarefa 2: Obter/Criar GeoJSON do Brasil (UFs)

**Formato:** GeoJSON com 27 features, uma por UF, com:
- `properties.uf` → sigla (SP, RJ, MG, etc.)
- `properties.nome` → nome completo (São Paulo, etc.)
- `properties.regiao` → região (SUDESTE, etc.)
- `geometry` → polígono da UF

**Opções de fonte:**
1. **IBGE (recomendado):** [geoftp.ibge.gov.br](https://geoftp.ibge.gov.br/organizacao_do_territorio/malhas_territoriais/malhas_municipais/municipio_2022/Brasil/BR/)
2. **GitHub community:** Procurar por `brazil-states.geojson` em repositórios públicos (ex: `codeforboston/brazil`)
3. **Simplificado (apenas 27 polígonos):** Criar GeoJSON manual simplificado com coordenadas aproximadas (menos preciso, mas leve)

**Recomendação:** Pré-processar o GeoJSON para remover simplificações desnecessárias e manter apenas UFs (não municípios). Servir o arquivo estático em `demo/data/brazil-ufs-simplified.geojson`.

### Tarefa 3: Implementar o mapa coroplético

**Arquivo:** `demo/js/modules/heatmap.js` (modificar `renderChart`)

**Algoritmo:**

```javascript
async function renderMap(data) {
  // 1. Buscar GeoJSON (fetch estático)
  const geoJson = await fetch('/demo/data/brazil-ufs-simplified.geojson').then(r => r.json());

  // 2. Mapear dados de preço por UF
  const priceMap = new Map(data.map(d => [d.uf, d.valor]));
  const values = data.map(d => d.valor);
  const min = Math.min(...values);
  const max = Math.max(...values);

  // 3. Função de cor (verde → amarelo → vermelho)
  function getColor(price) {
    const ratio = (price - min) / (max - min || 1);
    const r = Math.round(34 + ratio * 205);
    const g = Math.round(197 - ratio * 131);
    const b = Math.round(94 - ratio * 54);
    return `rgb(${r},${g},${b})`;
  }

  // 4. Criar mapa Leaflet
  const map = L.map('heatmapMap', {
    center: [-14.2, -51.9], // Centro do Brasil
    zoom: 4,
    zoomControl: true,
    scrollWheelZoom: false,  // Evita zoom acidental
  });

  // 5. Adicionar tile layer (OpenStreetMap ou Mapbox)
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '© OpenStreetMap',
    maxZoom: 8,
  }).addTo(map);

  // 6. Adicionar camada coroplética
  L.geoJSON(geoJson, {
    style: feature => ({
      fillColor: getColor(priceMap.get(feature.properties.uf)),
      weight: 1,
      opacity: 1,
      color: '#fff',
      fillOpacity: 0.8,
    }),
    onEachFeature: (feature, layer) => {
      const uf = feature.properties.uf;
      const price = priceMap.get(uf);
      layer.bindTooltip(`
        <strong>${feature.properties.nome} (${uf})</strong><br>
        Preço: R$ ${(price || 0).toLocaleString('pt-BR')}
      `);
      layer.on({
        mouseover: e => { e.target.setStyle({ weight: 3, color: '#333', fillOpacity: 1 }); },
        mouseout: e => { geoJsonLayer.resetStyle(e.target); },
      });
    },
  }).addTo(map);

  // 7. Legenda (cantos inferior direito)
  const legend = L.control({ position: 'bottomright' });
  legend.onAdd = () => {
    const div = L.DomUtil.create('div', 'info legend');
    const grades = [min, min + (max - min) * 0.25, min + (max - min) * 0.5, min + (max - min) * 0.75, max];
    div.innerHTML = '<strong>Preço</strong><br>';
    grades.forEach((g, i) => {
      div.innerHTML +=
        `<i style="background:${getColor(g)};width:12px;height:12px;display:inline-block;margin-right:4px;"></i>` +
        `R$ ${g.toFixed(0)}${grades[i + 1] ? ' – R$ ' + grades[i + 1].toFixed(0) + '<br>' : ''}`;
    });
    return div;
  };
  legend.addTo(map);

  // 8. Armazenar instância para cleanup
  state.heatmap.map = map;
}
```

### Tarefa 4: Atualizar o HTML e CSS

**HTML** (`demo/index.html`):
Substituir o canvas do heatmap por um container div:

```html
<div class="modal-card heatmap-card hidden" id="heatmapSection">
  <h4>Mapa de Calor Regional</h4>
  <div class="heatmap-legend" aria-label="Legenda das regiões">
    <!-- manter legendas atuais -->
  </div>
  <div id="heatmapMap" class="heatmap-map-container" style="height: 350px; border-radius: var(--radius-lg);"></div>
</div>
```

**CSS** (`demo/css/12-utilities.css`):
```css
.heatmap-map-container {
    height: 350px;
    border-radius: var(--radius-lg);
    overflow: hidden;
}
/* Leaflet overrides */
.heatmap-map-container .leaflet-container {
    font-family: 'Inter', sans-serif;
}
.heatmap-map-container .info.legend {
    background: var(--bg-card);
    padding: 8px 12px;
    border-radius: var(--radius-md);
    box-shadow: 0 2px 8px rgba(0,0,0,0.15);
    font-size: 0.75rem;
    line-height: 1.5;
    color: var(--text-main);
}
```

### Tarefa 5: Atualizar o cleanup no modal

**Arquivo:** `demo/js/modules/modal.js`

Na função `cleanup()`, adicionar remoção do mapa Leaflet:

```javascript
if (state.heatmap && state.heatmap.map) {
    state.heatmap.map.remove();
    state.heatmap.map = null;
}
```

---

## 🔧 Considerações Técnicas

### Performance
- O GeoJSON do Brasil com 27 estados simplificado deve ter < 500KB
- Leaflet + OpenStreetMap tiles são gratuitos e rápidos
- Alternativa paga: Mapbox (mais bonito, < 50.000 requests/mês grátis)

### Fallback
Manter o gráfico de barras horizontal como fallback caso o mapa não carregue (erro de rede, CSP blocking, etc.):

```javascript
if (typeof L === 'undefined') {
    renderChart(data); // fallback bar chart
    return;
}
```

### Responsividade
O Leaflet lida bem com redimensionamento. Usar `map.invalidateSize()` quando o modal for aberto para recalcular o tamanho do mapa.

---

## 📂 Arquivos Afetados

| Arquivo | Mudança |
|---|---|
| `demo/index.html` | Adicionar Leaflet CDN + container div `#heatmapMap` |
| `demo/js/modules/heatmap.js` | Nova função `renderMap()` + fallback para `renderChart()` |
| `demo/js/modules/modal.js` | Cleanup do mapa Leaflet no `cleanup()` |
| `demo/js/state.js` | Adicionar `state.heatmap.map = null` |
| `demo/css/12-utilities.css` | Estilo para `.heatmap-map-container` |
| `demo/data/brazil-ufs-simplified.geojson` | **Novo arquivo** — GeoJSON simplificado |

---

## ✅ Critérios de Aceite

1. [ ] Mapa do Brasil é exibido no modal ao abrir um item
2. [ ] Cada UF é colorida conforme o preço (verde → vermelho)
3. [ ] Tooltip ao passar mouse mostra UF + nome + valor
4. [ ] Legenda no canto inferior direito mostra a escala de cores
5. [ ] Scroll do mapa está desabilitado (não interfere com scroll da página)
6. [ ] Ao fechar o modal, o mapa é destruído corretamente (sem memory leak)
7. [ ] Fallback: se Leaflet não carregar, bar chart original é exibido
8. [ ] Responsivo: mapa se ajusta ao tamanho do modal em mobile/desktop
9. [ ] Dark mode: cores do mapa/tooltip/legenda respeitam o tema

---

## 🔗 Dependências

- Nenhuma. Esta sprint é independente — pode ser executada em paralelo com a correção do ETL (classificacao/grupo).
- O endpoint `precos-uf` já existe e retorna dados para todos os 27 estados.