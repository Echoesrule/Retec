'use strict';

/* Tests for static/js/api-client.js.

   No test framework is installed for the frontend, so this uses Node's
   built-in test runner:

     node --test tools/api-client.test.js

   The client is loaded into a VM with a minimal fake `window`; timers are
   compressed so backoff does not slow the suite. */

const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');
const assert = require('node:assert/strict');

const CLIENT = path.resolve(__dirname, '..', 'static', 'js', 'api-client.js');

function createWindow() {
    const store = {};
    const win = {
        setTimeout: (fn, ms) => setTimeout(fn, Math.min(ms || 0, 5)),
        clearTimeout,
        AbortController,
        sessionStorage: {
            getItem: (key) => (key in store ? store[key] : null),
            setItem: (key, value) => { store[key] = String(value); },
        },
    };
    win.window = win;
    return win;
}

function load(win) {
    const code = fs.readFileSync(CLIENT, 'utf8');
    vm.runInNewContext(code, {
        window: win, Promise, Date, Number, JSON, Error, RegExp, String,
        Math, Object, Array, console,
    });
    return win.RETEC_API;
}

const jsonResponse = (obj, status = 200) =>
    new Response(JSON.stringify(obj), { status, headers: { 'content-type': 'application/json' } });
const htmlResponse = (status = 200) =>
    new Response('<!DOCTYPE html><html><body>Render is starting...</body></html>',
        { status, headers: { 'content-type': 'text/html' } });

function dataFetcher(handler) {
    let calls = 0;
    const fn = (url, opts) => {
        if (url === '/healthz') return Promise.resolve(jsonResponse({ status: 'ok' }));
        calls += 1;
        return handler(calls, url, opts);
    };
    return { fn, count: () => calls };
}

test('successful JSON response resolves with parsed data', async () => {
    const win = createWindow();
    win.fetch = dataFetcher(() => Promise.resolve(jsonResponse({ ok: true, n: 2 }))).fn;
    const api = load(win);
    assert.deepEqual(await api.fetchJSON('/data'), { ok: true, n: 2 });
});

test('Render startup HTML is rejected, never parsed as data', async () => {
    const win = createWindow();
    const f = dataFetcher(() => Promise.resolve(htmlResponse()));
    win.fetch = f.fn;
    const api = load(win);
    await assert.rejects(api.fetchJSON('/data'), (e) => e.code === 'unexpected_html');
    assert.equal(f.count(), 3, 'idempotent GET should retry the full budget');
});

test('HTML body is detected even without an HTML content type', async () => {
    const win = createWindow();
    const body = '<?xml version="1.0"?><html><body>waking up</body></html>';
    const f = dataFetcher(() => Promise.resolve(new Response(body, {
        status: 200, headers: { 'content-type': 'text/plain' } })));
    win.fetch = f.fn;
    const api = load(win);
    await assert.rejects(api.fetchJSON('/data'), (e) => e.code === 'unexpected_html');
    assert.equal(f.count(), 3);
});

test('invalid JSON is rejected and retried', async () => {
    const win = createWindow();
    const f = dataFetcher(() => Promise.resolve(new Response('not json', {
        status: 200, headers: { 'content-type': 'application/json' } })));
    win.fetch = f.fn;
    const api = load(win);
    await assert.rejects(api.fetchJSON('/data'), (e) => e.code === 'invalid_json');
    assert.equal(f.count(), 3);
});

test('a transient 503 is retried and recovers', async () => {
    const win = createWindow();
    const f = dataFetcher((n) => Promise.resolve(
        n < 3 ? new Response('', { status: 503 }) : jsonResponse({ ok: true })));
    win.fetch = f.fn;
    const api = load(win);
    assert.deepEqual(await api.fetchJSON('/data'), { ok: true });
    assert.equal(f.count(), 3);
});

test('a 4xx error is not retried and surfaces as http', async () => {
    const win = createWindow();
    const f = dataFetcher(() => Promise.resolve(new Response('', { status: 400 })));
    win.fetch = f.fn;
    const api = load(win);
    await assert.rejects(api.fetchJSON('/data'), (e) => e.code === 'http' && e.status === 400);
    assert.equal(f.count(), 1);
});

test('network failure is retried then surfaced as network', async () => {
    const win = createWindow();
    const f = dataFetcher(() => Promise.reject(new TypeError('Failed to fetch')));
    win.fetch = f.fn;
    const api = load(win);
    await assert.rejects(api.fetchJSON('/data'), (e) => e.code === 'network' && e.retryable === true);
    assert.equal(f.count(), 3);
});

test('a slow response times out and is surfaced as timeout', async () => {
    const win = createWindow();
    let calls = 0;
    win.fetch = (url, opts) => {
        if (url === '/healthz') return Promise.resolve(jsonResponse({}));
        calls += 1;
        return new Promise((_resolve, reject) => {
            opts.signal.addEventListener('abort', () => {
                const err = new Error('aborted');
                err.name = 'AbortError';
                reject(err);
            });
        });
    };
    const api = load(win);
    await assert.rejects(api.fetchJSON('/data', { timeout: 10 }), (e) => e.code === 'timeout');
    assert.equal(calls, 3);
});

test('a timed-out attempt can retry and recover (fresh controller per attempt)', async () => {
    const win = createWindow();
    let calls = 0;
    win.fetch = (url, opts) => {
        if (url === '/healthz') return Promise.resolve(jsonResponse({}));
        calls += 1;
        if (calls === 1) {
            return new Promise((_resolve, reject) => {
                opts.signal.addEventListener('abort', () => {
                    const err = new Error('aborted');
                    err.name = 'AbortError';
                    reject(err);
                });
            });
        }
        return Promise.resolve(jsonResponse({ recovered: true }));
    };
    const api = load(win);
    assert.deepEqual(await api.fetchJSON('/data', { timeout: 10 }), { recovered: true });
    assert.equal(calls, 2);
});

test('non-idempotent POST is not retried (no duplicate submissions)', async () => {
    const win = createWindow();
    const f = dataFetcher(() => Promise.resolve(htmlResponse()));
    win.fetch = f.fn;
    const api = load(win);
    await assert.rejects(
        api.fetchJSON('/submit', { method: 'POST', body: '{}' }),
        (e) => e.code === 'unexpected_html');
    assert.equal(f.count(), 1);
});

test('POST with an explicit attempt budget is retried', async () => {
    const win = createWindow();
    const f = dataFetcher((n) => Promise.resolve(
        n < 2 ? new Response('', { status: 503 }) : jsonResponse({ valid: true })));
    win.fetch = f.fn;
    const api = load(win);
    assert.deepEqual(
        await api.fetchJSON('/verify-email', { method: 'POST', body: '{}', attempts: 3 }),
        { valid: true });
    assert.equal(f.count(), 2);
});

test('dedupeKey cancels the superseded request', async () => {
    const win = createWindow();
    const pending = [];
    win.fetch = (url, opts) => {
        if (url === '/healthz') return Promise.resolve(jsonResponse({}));
        return new Promise((resolve, reject) => {
            opts.signal.addEventListener('abort', () => {
                const err = new Error('aborted');
                err.name = 'AbortError';
                reject(err);
            });
            pending.push({ resolve });
        });
    };
    const api = load(win);
    const first = api.fetchJSON('/same', { dedupeKey: 'slot', attempts: 1 });
    const second = api.fetchJSON('/same', { dedupeKey: 'slot', attempts: 1 });
    await Promise.resolve();
    assert.equal(pending.length, 2);
    pending[1].resolve(jsonResponse({ ok: true }));
    assert.deepEqual(await second, { ok: true });
    await assert.rejects(first, (e) => e.code === 'aborted');
});

test('an empty 204 resolves to null', async () => {
    const win = createWindow();
    win.fetch = dataFetcher(() => Promise.resolve(new Response(null, { status: 204 }))).fn;
    const api = load(win);
    assert.equal(await api.fetchJSON('/data'), null);
});

test('concurrent readiness checks collapse into a single ping', async () => {
    const win = createWindow();
    let health = 0;
    let release;
    win.fetch = (url) => {
        if (url === '/healthz') {
            health += 1;
            return new Promise((resolve) => { release = () => resolve(jsonResponse({ status: 'ok' })); });
        }
        return Promise.resolve(jsonResponse({}));
    };
    const api = load(win);
    const a = api.ensureWarm();
    const b = api.ensureWarm();
    release();
    await Promise.all([a, b]);
    assert.equal(health, 1);
});

test('isUnavailable classifies cold-start errors and ignores real ones', async () => {
    const win = createWindow();
    win.fetch = dataFetcher(() => Promise.resolve(new Response('', { status: 400 }))).fn;
    const api = load(win);
    assert.equal(api.isUnavailable({ code: 'timeout' }), true);
    assert.equal(api.isUnavailable({ code: 'network' }), true);
    assert.equal(api.isUnavailable({ code: 'unexpected_html' }), true);
    assert.equal(api.isUnavailable({ code: 'http', status: 503 }), true);
    assert.equal(api.isUnavailable({ code: 'http', status: 400 }), false);
    assert.equal(api.isUnavailable(null), false);
});
