import test from 'node:test';
import assert from 'node:assert/strict';
import { formatPrice, formatRating, formatMs, barPercent, SAMPLE_USERS } from './util.js';

test('formatPrice', () => {
  assert.equal(formatPrice(12.5), 'USD 12.50');
  assert.equal(formatPrice(undefined), '–');
});
test('formatRating', () => {
  assert.equal(formatRating(4.2567), '4.26');
  assert.equal(formatRating(null), 'n/d');
});
test('formatMs', () => {
  assert.equal(formatMs(3.14159), '3.1 ms');
  assert.equal(formatMs(null), 'sin datos');
});
test('barPercent', () => {
  assert.equal(barPercent(50, 200), 25);
  assert.equal(barPercent(5, 0), 0);
});
test('usuarios de ejemplo incluyen uno sin historial', () => {
  assert.equal(SAMPLE_USERS[0], 'U00001');
  assert.ok(SAMPLE_USERS.includes('U_COLD01'));
});
