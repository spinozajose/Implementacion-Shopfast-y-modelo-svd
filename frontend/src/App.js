// Frontend ShopFast (EP3, sección 13): simulación de tienda + dashboard de métricas.
// Escrito con createElement (sin JSX) para compilar con Vite sin plugins adicionales.
import { createElement as h, useCallback, useEffect, useState } from 'react';
import {
  getMetrics, getModelInfo, getRecommendations, getRelated, trackInteraction,
} from './api.js';
import {
  INTERACTIONS, SAMPLE_USERS, barPercent, formatMs, formatPrice, formatRating,
} from './util.js';

const errorText = (e) => (e.status ? `${e.message} (HTTP ${e.status})` : e.message);

// ---------------------------------------------------------------- Tienda
function ProductCard({ item, onInteract, onRelated, related }) {
  return h('article', { className: 'card' },
    h('div', { className: 'card-top' },
      h('span', { className: 'rank' }, `#${item.rank}`),
      h('span', { className: 'cat' }, item.category)),
    h('h3', null, item.name),
    h('p', { className: 'price' }, formatPrice(item.price)),
    h('p', { className: 'score' }, `Puntaje estimado: ${formatRating(item.predicted_rating)}`),
    h('p', { className: 'reason' }, item.reason),
    h('div', { className: 'actions' },
      INTERACTIONS.map((a) =>
        h('button', { key: a.type, onClick: () => onInteract(item.product_id, a.type) }, a.label)),
      h('button', { className: 'ghost', onClick: () => onRelated(item.product_id) }, 'Relacionados')),
    related && related.productId === item.product_id
      ? h('ul', { className: 'related' },
        related.items.length === 0 ? h('li', null, 'Sin relacionados') : null,
        related.items.map((r) => h('li', { key: r.product_id }, `${r.name} · ${formatPrice(r.price)}`)))
      : null);
}

export function Store() {
  const [userId, setUserId] = useState(SAMPLE_USERS[0]);
  const [custom, setCustom] = useState('');
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [toast, setToast] = useState(null);
  const [related, setRelated] = useState(null);

  const load = useCallback(async (id) => {
    setLoading(true); setError(null); setRelated(null);
    try {
      const { data, ms } = await getRecommendations(id);
      setResult({ ...data, ms });
    } catch (e) {
      setResult(null); setError(errorText(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(userId); }, [userId, load]);

  const interact = async (productId, type) => {
    try {
      const { ms } = await trackInteraction(result.user_id, productId, type);
      setToast({ ok: true, text: `Interacción «${type}» sobre ${productId} aceptada (HTTP 202, ${ms} ms). `
        + 'Se procesa de forma asíncrona vía RabbitMQ.' });
    } catch (e) {
      setToast({ ok: false, text: errorText(e) });
    }
  };

  const showRelated = async (productId) => {
    try {
      const { data } = await getRelated(productId);
      setRelated({ productId, items: data.related });
    } catch (e) {
      setToast({ ok: false, text: errorText(e) });
    }
  };

  return h('section', null,
    h('div', { className: 'controls' },
      h('label', null, 'Usuario de prueba ',
        h('select', { value: SAMPLE_USERS.includes(userId) ? userId : '', onChange: (e) => setUserId(e.target.value) },
          SAMPLE_USERS.map((u) => h('option', { key: u, value: u }, u)))),
      h('span', { className: 'or' }, 'o'),
      h('input', { placeholder: 'ID de usuario (ej. U01234)', value: custom,
        onChange: (e) => setCustom(e.target.value) }),
      h('button', { disabled: !custom.trim(), onClick: () => setUserId(custom.trim()) }, 'Cargar')),
    loading ? h('p', { className: 'muted' }, 'Cargando recomendaciones…') : null,
    error ? h('p', { className: 'msg bad' }, error) : null,
    result ? h('p', { className: 'muted' },
      `Usuario ${result.user_id} · modelo ${result.model_version} · respuesta en ${result.ms} ms (medido en el navegador) `,
      result.fallback ? h('span', { className: 'badge' }, 'FALLBACK: usuario sin historial → más populares') : null)
      : null,
    toast ? h('p', { className: `msg ${toast.ok ? 'good' : 'bad'}` }, toast.text) : null,
    result ? h('div', { className: 'grid' },
      result.recommendations.map((item) =>
        h(ProductCard, { key: item.product_id, item, onInteract: interact, onRelated: showRelated, related })))
      : null);
}

// ---------------------------------------------------------------- Dashboard
const Tile = ({ label, value }) =>
  h('div', { className: 'tile' }, h('div', { className: 'tile-v' }, value), h('div', { className: 'tile-l' }, label));

export function Dashboard() {
  const [metrics, setMetrics] = useState(null);
  const [model, setModel] = useState(null);
  const [error, setError] = useState(null);
  const [auto, setAuto] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const [m, i] = await Promise.all([getMetrics(), getModelInfo()]);
      setMetrics(m.data); setModel(i.data); setError(null);
    } catch (e) {
      setError(errorText(e));
    }
  }, []);

  useEffect(() => {
    refresh();
    if (!auto) return undefined;
    const t = setInterval(refresh, 5000);
    return () => clearInterval(t);
  }, [auto, refresh]);

  if (error) return h('p', { className: 'msg bad' }, error);
  if (!metrics) return h('p', { className: 'muted' }, 'Cargando métricas…');

  const lat = metrics.recommendation_latency_ms;
  const byType = metrics.interactions_by_type;
  const maxType = Math.max(0, ...Object.values(byType));
  const tm = (model && model.training_metrics) || {};

  return h('section', null,
    h('div', { className: 'controls' },
      h('label', null, h('input', { type: 'checkbox', checked: auto, onChange: (e) => setAuto(e.target.checked) }),
        ' Actualizar cada 5 s'),
      h('button', { onClick: refresh }, 'Actualizar ahora')),
    h('p', { className: 'muted' }, 'Datos reales del prototipo (API y base SQLite). El dataset es sintético.'),
    h('div', { className: 'tiles' },
      h(Tile, { label: 'Interacciones en BD', value: metrics.db.interactions.toLocaleString('es-CL') }),
      h(Tile, { label: 'Publicadas en RabbitMQ (sesión)', value: metrics.interactions_published }),
      h(Tile, { label: 'Respuestas fallback', value: metrics.fallback_responses }),
      h(Tile, { label: 'Latencia p95 /recommendations', value: formatMs(lat.p95) }),
      h(Tile, { label: 'Latencia p50', value: formatMs(lat.p50) }),
      h(Tile, { label: 'Muestras de latencia', value: lat.samples })),
    h('h2', null, 'Interacciones por tipo'),
    h('div', { className: 'bars' },
      Object.entries(byType).map(([k, v]) =>
        h('div', { key: k, className: 'bar-row' },
          h('span', { className: 'bar-l' }, k),
          h('div', { className: 'bar' }, h('div', { className: 'bar-fill', style: { width: `${barPercent(v, maxType)}%` } })),
          h('span', { className: 'bar-v' }, v.toLocaleString('es-CL'))))),
    h('h2', null, 'Productos más recomendados'),
    h('table', null,
      h('thead', null, h('tr', null, ['Producto', 'Categoría', 'Veces recomendado'].map((c) => h('th', { key: c }, c)))),
      h('tbody', null, metrics.top_recommended_products.map((p) =>
        h('tr', { key: p.product_id },
          h('td', null, p.name), h('td', null, p.category), h('td', null, p.times_recommended))))),
    h('h2', null, `Modelo ${model ? model.version : ''}`),
    h('table', null,
      h('tbody', null,
        ['rmse', 'mae', 'precision@10', 'recall@10', 'f1@10'].map((k) =>
          h('tr', { key: k }, h('td', null, k.toUpperCase()), h('td', null, tm[k] ?? 'n/d'))))),
    h('p', { className: 'muted' },
      'Métricas sobre datos sintéticos: no demuestran mejora de conversión ni de ticket promedio.'));
}

// ---------------------------------------------------------------- App
export default function App() {
  const [tab, setTab] = useState('store');
  return h('div', { className: 'app' },
    h('header', null,
      h('h1', null, 'ShopFast'),
      h('p', { className: 'muted' }, 'Simulación de tienda sobre la API de recomendaciones · Prototipo EP3'),
      h('nav', null,
        h('button', { className: tab === 'store' ? 'active' : '', onClick: () => setTab('store') }, 'Tienda'),
        h('button', { className: tab === 'dash' ? 'active' : '', onClick: () => setTab('dash') }, 'Dashboard'))),
    h('main', null, tab === 'store' ? h(Store) : h(Dashboard)));
}
