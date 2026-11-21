// Cliente de la API. El navegador llama a /api; nginx reenvía a la API y agrega la API Key,
// de modo que la clave no queda dentro del código JavaScript entregado al navegador.
const BASE = '/api';

export class ApiError extends Error {
  constructor(status, code, message) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

export async function request(path, options = {}) {
  const t0 = performance.now();
  let res;
  try {
    res = await fetch(BASE + path, { headers: { 'Content-Type': 'application/json' }, ...options });
  } catch {
    throw new ApiError(0, 'network', 'No se pudo contactar la API');
  }
  const ms = Math.round(performance.now() - t0);
  let data = null;
  try {
    data = await res.json();
  } catch {
    /* respuesta sin cuerpo JSON */
  }
  if (!res.ok) {
    throw new ApiError(res.status, data?.error ?? 'error', data?.message ?? res.statusText);
  }
  return { data, ms };
}

export const getRecommendations = (userId) => request(`/recommendations/${encodeURIComponent(userId)}`);
export const getRelated = (productId) => request(`/products/${encodeURIComponent(productId)}/related`);
export const getMetrics = () => request('/metrics');
export const getModelInfo = () => request('/model/info');
export const trackInteraction = (user_id, product_id, interaction_type) =>
  request('/track-interaction', {
    method: 'POST',
    body: JSON.stringify({ user_id, product_id, interaction_type }),
  });
