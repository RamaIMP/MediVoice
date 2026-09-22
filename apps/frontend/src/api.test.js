import { test } from 'node:test';
import assert from 'node:assert/strict';
import { request } from './api.js';

test('sends JSON to the configured backend', async (t) => {
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    assert.equal(url, 'https://example.test/api/sessions');
    assert.equal(options.method, 'POST');
    assert.deepEqual(JSON.parse(options.body), {});
    return Response.json({ session_id: 'test' });
  });
  assert.deepEqual(await request('/api/sessions', {}, { baseUrl: 'https://example.test' }), { session_id: 'test' });
});

test('preserves safe server error messages', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => Response.json({ detail: 'Session expired' }, { status: 404 }));
  await assert.rejects(request('/test'), /Session expired/);
});

test('does not expose non-JSON proxy responses', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => new Response('private upstream diagnostic', { status: 502 }));
  await assert.rejects(request('/test'), /unreadable response/);
});

test('network failures have an actionable message', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => { throw new TypeError('fetch failed'); });
  await assert.rejects(request('/test'), /Check your connection/);
});

test('hung requests are aborted', async (t) => {
  t.mock.method(globalThis, 'fetch', async (url, { signal }) => new Promise((resolve, reject) => {
    signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')), { once: true });
  }));
  await assert.rejects(request('/test', undefined, { timeoutMs: 5 }), /took too long/);
});
