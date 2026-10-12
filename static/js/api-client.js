/* RETEC API client — cold-start resilience for the Render-hosted backend.
 *
 * The site is reached through Vercel, which proxies to the Render web service.
 * An idle Render instance can delay the first byte or answer with its own
 * startup HTML, so every consumer goes through this one place, which:
 *   - warms the backend in the background (fire-and-forget, once per tab), and
 *   - refuses to hand a non-API response (HTML, bad status, timeout) to the UI.
 *
 * No polling, no long-running timers, no new dependencies. Non-idempotent
 * requests are never retried, so a cold start cannot submit a form twice.
 */
(function (window) {
    'use strict';

    var DEFAULT_TIMEOUT = 8000;
    var MAX_ATTEMPTS = 3;
    var RETRY_DELAYS = [700, 2000];
    var WARMUP_PATH = '/healthz';
    var WARMUP_TTL = 4 * 60 * 1000;
    var WARMUP_KEY = 'retec_backend_warmup';

    function sleep(ms) {
        return new Promise(function (resolve) { window.setTimeout(resolve, ms); });
    }

    function looksLikeHtml(text) {
        return /^\s*(<!doctype|<html|<\?xml)/i.test(text || '');
    }

    function isRetryableStatus(status) {
        return status === 408 || status === 425 || status === 429 ||
            status === 500 || status === 502 || status === 503 || status === 504;
    }

    function readBody(response) {
        return response.text().then(function (text) {
            if (looksLikeHtml(text)) {
                var htmlError = new Error('Backend returned HTML instead of JSON');
                htmlError.code = 'unexpected_html';
                htmlError.status = response.status;
                throw htmlError;
            }
            if (!text) return {};
            try {
                return JSON.parse(text);
            } catch (parseFailure) {
                var jsonError = new Error('Backend returned invalid JSON');
                jsonError.code = 'invalid_json';
                jsonError.status = response.status;
                throw jsonError;
            }
        });
    }

    function fetchJSON(url, options) {
        options = options || {};
        var method = (options.method || 'GET').toUpperCase();
        var idempotent = method === 'GET' || method === 'HEAD';
        var maxAttempts = options.attempts || (idempotent ? MAX_ATTEMPTS : 1);
        var timeout = options.timeout || DEFAULT_TIMEOUT;
        var fetcher = window.fetch;
        var attempt = 0;

        if (typeof fetcher !== 'function') {
            return Promise.reject(new Error('fetch is not available'));
        }

        function run() {
            attempt += 1;
            var controller = typeof window.AbortController === 'function'
                ? new window.AbortController() : null;
            var timer = null;
            var requestOptions = {
                method: method,
                headers: options.headers || {},
                credentials: options.credentials || 'same-origin',
                cache: 'no-store',
                body: options.body
            };
            if (controller) requestOptions.signal = controller.signal;
            if (controller && timeout) {
                timer = window.setTimeout(function () { controller.abort(); }, timeout);
            }

            return fetcher(url, requestOptions).then(function (response) {
                if (timer) window.clearTimeout(timer);
                if (!response.ok) {
                    var statusError = new Error('Request failed with status ' + response.status);
                    statusError.status = response.status;
                    statusError.retryable = isRetryableStatus(response.status);
                    throw statusError;
                }
                return readBody(response);
            }, function (networkError) {
                if (timer) window.clearTimeout(timer);
                var error = networkError || new Error('Network request failed');
                error.retryable = error.retryable !== false;
                throw error;
            }).catch(function (error) {
                if (attempt < maxAttempts && error && error.retryable !== false) {
                    var delay = RETRY_DELAYS[attempt - 1];
                    if (delay == null) delay = RETRY_DELAYS[RETRY_DELAYS.length - 1];
                    return sleep(delay).then(run);
                }
                throw error;
            });
        }

        return run();
    }

    /* Fire-and-forget wake-up: runs at most once per tab within WARMUP_TTL and
       never blocks render or surfaces an error. A sleeping Render instance
       starts booting on the first byte; fetchJSON's bounded retries cover the
       remainder. */
    function warmup() {
        try {
            var last = Number(window.sessionStorage.getItem(WARMUP_KEY) || 0);
            if (last && (Date.now() - last) < WARMUP_TTL) return;
            window.sessionStorage.setItem(WARMUP_KEY, String(Date.now()));
        } catch (storageError) { /* private mode: warm anyway */ }
        if (typeof window.fetch !== 'function') return;
        try {
            window.fetch(WARMUP_PATH, {
                method: 'GET',
                cache: 'no-store',
                credentials: 'same-origin',
                keepalive: true
            }).catch(function () {});
        } catch (fetchError) { /* ignore */ }
    }

    window.RETEC_API = { fetchJSON: fetchJSON, warmup: warmup };
    warmup();
})(window);
