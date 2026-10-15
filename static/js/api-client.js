/* RETEC API client — the single boundary between the UI and the backend.
 *
 * Why this exists: Vercel proxies the whole site to a Render web service
 * (see vercel.json). A free Render instance sleeps when idle and, on wake,
 * can answer a request with its own HTML startup page, a timeout, or a 5xx.
 * Anything that parses a response must therefore (a) never treat HTML as data,
 * (b) retry only what is safe, and (c) surface a typed error the caller can act
 * on. Centralising that here means no component grows its own retry loop.
 *
 * No polling, no timers left running, no dependencies. Non-idempotent requests
 * are never retried unless a caller explicitly opts in, so a cold start cannot
 * submit a form twice.
 */
(function (window) {
    'use strict';

    var JSON_TYPE = /^application\/(?:[\w.+-]+\+)?json\b/i;
    var HTML_TYPE = /(?:text\/html|application\/xhtml\+xml)/i;

    var DEFAULT_TIMEOUT = 12000;
    var MAX_ATTEMPTS = 3;
    var BASE_DELAY = 600;
    var MAX_DELAY = 4000;
    var WARMUP_PATH = '/healthz';
    var WARMUP_TTL = 4 * 60 * 1000;
    var WARMUP_KEY = 'retec_backend_warmup';
    var WARMUP_TIMEOUT = 5000;

    var RETRYABLE_STATUS = { 408: 1, 425: 1, 429: 1, 500: 1, 502: 1, 503: 1, 504: 1 };

    var inflight = {};
    var warmPromise = null;

    function makeError(code, message, extra) {
        var error = new Error(message);
        error.name = 'RetecRequestError';
        error.code = code;
        if (extra) {
            for (var key in extra) {
                if (Object.prototype.hasOwnProperty.call(extra, key)) error[key] = extra[key];
            }
        }
        return error;
    }

    function looksLikeHtml(text) {
        return /^\s*(?:<!doctype|<html|<\?xml)/i.test(text || '');
    }

    function isJsonContentType(header) {
        return JSON_TYPE.test((header || '').toLowerCase());
    }

    function isHtmlContentType(header) {
        return HTML_TYPE.test((header || '').toLowerCase());
    }

    /* An error a bounded retry could plausibly clear: a cold/down Render
       instance surfaces as a timeout, a network failure, a retryable 5xx, or
       its own HTML startup page. Used by callers to decide on messaging. */
    function isUnavailable(error) {
        if (!error) return false;
        var code = error.code;
        return code === 'timeout' || code === 'network' ||
            code === 'unexpected_html' || code === 'invalid_json' ||
            (code === 'http' && RETRYABLE_STATUS[error.status] === 1);
    }

    function backoff(attempt) {
        var base = Math.min(MAX_DELAY, BASE_DELAY * Math.pow(2, attempt - 1));
        return base + Math.floor(Math.random() * 250);
    }

    function sleep(ms, signal) {
        return new Promise(function (resolve, reject) {
            var timer = window.setTimeout(resolve, ms);
            if (!signal) return;
            if (signal.aborted) {
                window.clearTimeout(timer);
                reject(makeError('aborted', 'Request aborted'));
                return;
            }
            signal.addEventListener('abort', function () {
                window.clearTimeout(timer);
                reject(makeError('aborted', 'Request aborted'));
            }, { once: true });
        });
    }

    function readJson(response) {
        var contentType = response.headers && response.headers.get
            ? response.headers.get('content-type') : '';
        if (isHtmlContentType(contentType)) {
            throw makeError('unexpected_html', 'Backend returned HTML instead of JSON',
                { status: response.status, retryable: true });
        }
        return response.text().then(function (text) {
            if (looksLikeHtml(text)) {
                throw makeError('unexpected_html', 'Backend returned HTML instead of JSON',
                    { status: response.status, retryable: true });
            }
            if (text === '') {
                if (contentType && !isJsonContentType(contentType)) {
                    throw makeError('invalid_json', 'Backend returned a non-JSON body',
                        { status: response.status, retryable: true });
                }
                return null;
            }
            try {
                return JSON.parse(text);
            } catch (parseError) {
                throw makeError('invalid_json', 'Backend returned invalid JSON',
                    { status: response.status, retryable: true });
            }
        });
    }

    function fetchJSON(url, options) {
        options = options || {};
        var method = (options.method || 'GET').toUpperCase();
        var idempotent = method === 'GET' || method === 'HEAD';
        var allowedAttempts = options.attempts || (idempotent ? MAX_ATTEMPTS : 1);
        var timeout = options.timeout || DEFAULT_TIMEOUT;
        var fetcher = options.fetch || window.fetch;
        var key = options.dedupeKey;
        var externalSignal = options.signal;

        if (typeof fetcher !== 'function') {
            return Promise.reject(makeError('unsupported', 'fetch is not available'));
        }

        if (key && inflight[key]) {
            inflight[key].abort(makeError('superseded', 'Superseded by a newer request'));
        }
        var controller = typeof window.AbortController === 'function'
            ? new window.AbortController() : null;
        if (key) inflight[key] = controller;
        if (externalSignal && controller) {
            if (externalSignal.aborted) controller.abort();
            else externalSignal.addEventListener('abort', function () { controller.abort(); }, { once: true });
        }

        var attempt = 0;

        function finish() {
            if (key && inflight[key] === controller) delete inflight[key];
        }

        function run() {
            attempt += 1;
            /* A fresh controller per attempt: the timeout aborts only this
               attempt, so a timed-out request can still retry (and its backoff
               can still be waited out). The outer controller only carries
               supersede/consumer cancellation. */
            var attemptController = typeof window.AbortController === 'function'
                ? new window.AbortController() : null;
            if (attemptController && controller) {
                if (controller.signal.aborted) attemptController.abort();
                else controller.signal.addEventListener('abort', function () {
                    attemptController.abort();
                }, { once: true });
            }
            var requestOptions = {
                method: method,
                headers: options.headers || {},
                credentials: options.credentials || 'same-origin',
                cache: 'no-store',
                body: options.body
            };
            if (attemptController) requestOptions.signal = attemptController.signal;

            var timedOut = false;
            var timer = null;
            if (attemptController && timeout) {
                timer = window.setTimeout(function () {
                    timedOut = true;
                    attemptController.abort();
                }, timeout);
            }

            return fetcher(url, requestOptions).then(function (response) {
                if (timer) window.clearTimeout(timer);
                if (!response.ok) {
                    throw makeError('http', 'Request failed with status ' + response.status, {
                        status: response.status,
                        retryable: RETRYABLE_STATUS[response.status] === 1
                    });
                }
                return readJson(response);
            }, function (networkError) {
                if (timer) window.clearTimeout(timer);
                if (timedOut) {
                    throw makeError('timeout', 'Request timed out', { retryable: true });
                }
                if (networkError && networkError.name === 'AbortError') {
                    throw makeError('aborted', 'Request aborted', { retryable: false });
                }
                throw makeError('network', 'Network request failed',
                    { retryable: true, cause: networkError });
            });
        }

        function loop() {
            return run().then(function (data) {
                finish();
                return data;
            }, function (error) {
                var canRetry = attempt < allowedAttempts &&
                    error && error.retryable !== false && isUnavailable(error);
                if (!canRetry) {
                    finish();
                    throw error;
                }
                if (typeof options.onRetry === 'function') {
                    try { options.onRetry(attempt, error); } catch (ignored) {}
                }
                var waitSignal = controller ? controller.signal : null;
                return sleep(backoff(attempt), waitSignal).then(loop, function (abortError) {
                    finish();
                    throw abortError;
                });
            });
        }

        return loop();
    }

    /* Deduplicated readiness ping. Concurrent callers share one request, and a
       failed ping is not cached, so a later caller can try again. Best-effort:
       it never rejects. */
    function ensureWarm() {
        if (warmPromise) return warmPromise;
        if (typeof window.fetch !== 'function') {
            return Promise.resolve(false);
        }
        var controller = typeof window.AbortController === 'function'
            ? new window.AbortController() : null;
        var requestOptions = { method: 'GET', cache: 'no-store', credentials: 'same-origin' };
        if (controller) {
            requestOptions.signal = controller.signal;
            window.setTimeout(function () { controller.abort(); }, WARMUP_TIMEOUT);
        }
        warmPromise = window.fetch(WARMUP_PATH, requestOptions).then(function (response) {
            return !!response && response.status < 500;
        }).catch(function () {
            warmPromise = null;
            return false;
        });
        return warmPromise;
    }

    /* Fire-and-forget wake-up, at most once per tab per TTL. */
    function warmup() {
        try {
            var last = Number(window.sessionStorage.getItem(WARMUP_KEY) || 0);
            if (last && (Date.now() - last) < WARMUP_TTL) return ensureWarm();
            window.sessionStorage.setItem(WARMUP_KEY, String(Date.now()));
        } catch (storageError) { /* private mode: warm anyway */ }
        return ensureWarm();
    }

    function reset() {
        inflight = {};
        warmPromise = null;
    }

    window.RETEC_API = {
        fetchJSON: fetchJSON,
        ensureWarm: ensureWarm,
        warmup: warmup,
        isUnavailable: isUnavailable,
        reset: reset,
        error: makeError
    };

    warmup();
})(window);
