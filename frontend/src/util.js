export const SAMPLE_USERS = [
  ...Array.from({ length: 10 }, (_, i) => `U${String(i + 1).padStart(5, '0')}`),
  'U_COLD01', // usuario sin historial: activa el fallback por popularidad
];

export const INTERACTIONS = [
  { type: 'view', label: 'Ver' },
  { type: 'click', label: 'Clic' },
  { type: 'cart', label: 'Carrito' },
  { type: 'purchase', label: 'Comprar' },
];

export const formatPrice = (n) => (typeof n === 'number' ? `USD ${n.toFixed(2)}` : '–');
export const formatRating = (n) => (typeof n === 'number' ? n.toFixed(2) : 'n/d');
export const formatMs = (n) => (typeof n === 'number' ? `${n.toFixed(1)} ms` : 'sin datos');

// Ancho (0–100) de una barra respecto del máximo del conjunto.
export const barPercent = (value, max) => (max > 0 ? Math.round((value / max) * 100) : 0);
