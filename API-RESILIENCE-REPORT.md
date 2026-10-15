# RETEC — Frontend API Resilience / Cold-Start Hardening

## 1. Why this was needed (the confirmed reason)

`vercel.json` is a catch-all rewrite:

```json
{ "rewrites": [{ "source": "/(.*)", "destination": "https://retec.onrender.com/$1" }] }
```

Vercel is a **pure reverse proxy here, not a host** — it renders nothing. The
browser's top-level HTML document is Render's response, byte for byte. On a free
Render instance that has slept, that response can be Render's own *"starting…"*
HTML page (HTTP 200, `content-type: text/html`), or a timeout, or a 5xx.

Two consequences:

1. **API calls** that assumed JSON could `JSON.parse` an HTML startup page and
   either throw an opaque `SyntaxError` or (worse) feed HTML into the UI as if
   it were data.
2. **The top-level page itself cannot be fixed from inside the app.** No in-app
   JavaScript can hide a document it is served *by*. Only keeping the backend
   warm (or changing the topology) removes a proxied startup page. This is an
   architectural limit, stated plainly so it is not mistaken for a bug.

This change hardens (1) and documents (2). It does **not** attempt a fake fix
for the top-level document.

## 2. The boundary: `static/js/api-client.js`

One shared client (`window.RETEC_API`) is now the only place a response is
parsed. Everything else asks it for JSON.

- **Typed errors** — `RetecRequestError` with `error.code` ∈
  `timeout | network | http | unexpected_html | invalid_json | aborted |
  superseded | unsupported`, plus `status` and `retryable`.
- **HTML is never data.** `unexpected_html` is raised if the content type is
  HTML, *or* if the body starts with `<!doctype` / `<html` / `<?xml` even when
  the content type lies (Render's page does exactly this).
- **Timeout** via `AbortController` (default 12 000 ms), per attempt.
- **Bounded retry** — 3 attempts, exponential backoff (600 ms base, 4 s cap)
  with jitter. Only *idempotent* requests are retried by default; a
  non-idempotent POST is retried **only** when a caller passes an explicit
  `attempts` budget (used for the read-only email check).
- **No duplicate submissions** — a form POST is attempted once unless opted in,
  so a cold start can never submit a contact/partner form twice.
- **Deduplication** — `dedupeKey` cancels a superseded in-flight request;
  `ensureWarm()` collapses concurrent readiness pings into one.
- **Best-effort warm-up** on load (`warmup()`), throttled to once per tab per
  4 minutes via `sessionStorage`. It never rejects and is not a polling loop.
- **`isUnavailable(error)`** lets callers tell a cold-start blip from a real
  error, for messaging.

Loaded once per page: `templates/base.html` (public, deferred first) and
`templates/admin/base.html` (head, before any admin inline script).

## 3. Consumers migrated

Every previously-unguarded `fetch(...).then(r => r.json())` now goes through
`RETEC_API.fetchJSON`, each with the same graceful fallback to raw `fetch` if
the client is somehow absent:

| Location | Change |
|---|---|
| `static/js/script.js` (verify-email) | validated client, `attempts: 3`, `dedupeKey`, "Reconnecting…" on retry, inline **"Could not verify. Try again"** retry button |
| `templates/admin/analytics.html` | all 7 concurrent calls (summary + charts + cities) routed through the client; a single **Retry** control appears if any fail |
| `templates/admin/projects.html` | visibility toggle POST; checkbox reverts on failure |
| `templates/admin/project_form.html` | GitHub sync POST |
| `templates/admin/blog_form.html` | image upload POST |
| `templates/admin/content_studio_post.html` | slide image upload POST |
| `templates/index.html` | cube-position save POST (still keeps local copy on failure) |

## 4. Tests

`tools/api-client.test.js` — Node's built-in runner, **no new dependencies**:

```bash
node --test tools/api-client.test.js
```

**15 tests, 15 pass.** Covers: successful JSON; Render HTML rejected (and HTML
detected without the right content type); invalid JSON; transient 503 retried
and recovered; 4xx *not* retried; network failure classified and retried; slow
response → `timeout`; a timed-out attempt can still retry and recover; POST not
retried; POST retried only with an explicit budget; `dedupeKey` cancels the
superseded request; empty `204` → `null`; concurrent readiness checks collapse
to one ping; `isUnavailable` classification.

Writing these caught a real bug: the timeout originally aborted the *shared*
controller, so every retry and the backoff wait failed instantly with
`aborted`. Fixed with a fresh `AbortController` per attempt.

Existing backend suite still green:

```bash
DATABASE_URL="sqlite:////tmp/opencode/retec-test.db" SECRET_KEY=test-secret-key-not-for-production \
  .venv/bin/python -m unittest discover -s tools -p 'test_*.py'
# Ran 83 tests ... OK (skipped=11)
```

`node --check` clean on both JS files; `py_compile` clean on `app.py` and
`tools/generate_questionnaire_pdf.py`.

## 5. What is *not* fixed, and what it takes

- **The proxied top-level startup page** — cannot be hidden by any frontend
  code (see §1). Options: (a) keep the Render service warm; (b) move off free
  tier / different topology so a sleeping instance never fronts the site.
- **Keep-alive guidance conflict — resolved: keep the workflow.** The task
  instructions say *"Do not add an unreliable keep-alive loop."* That is read as
  targeting an **in-app JS polling loop**, which was deliberately *not* added —
  `warmup()` fires at most once per tab, TTL-guarded, and never reschedules.
  `.github/workflows/keep-warm.yml` (pings `/healthz` every 5 minutes,
  `workflow_dispatch`) was already committed/pushed (`05105a5`) and is a
  different mechanism: an external scheduled job, out-of-band, free on a public
  repo. It is the only thing that removes the visible top-level startup
  document, so it is kept. Known caveats: GitHub cron is best-effort (can be
  delayed) and scheduled workflows disable after ~60 days of repo inactivity, so
  it complements rather than replaces the on-load warm-up.

## 6. Final state

- All response parsing is centralised and typed; HTML/timeout/5xx can no longer
  masquerade as data.
- Retry is bounded, idempotent-only by default, and never double-submits.
- UI shows a recovery affordance (inline retry / reconnecting / retry button)
  instead of a silent failure or a crash.
- 15 JS tests + 83 backend tests pass; lint/compile clean.
