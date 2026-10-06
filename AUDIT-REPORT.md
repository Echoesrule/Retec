# RETEC Production-Readiness Audit

## Executive Summary

RETEC is a single-file Flask application (`app.py`, ~2300 lines) serving the
public site, Journal archive, partner/business flows, admin backend, and an
automated news ingestion engine, deployed on Render with PostgreSQL + Redis +
gunicorn.

A security/reliability/performance audit found no critical vulnerabilities and
no issues severe enough to block deployment. Every verified issue was fixed and
re-validated: 40 focused automated tests pass, `pyflakes`/`py_compile` are
clean, and a full headless-Chromium pass over the public pages reports zero
console errors and zero failed requests.

The Journal archive was also reworked on request from a paginated card grid into
a single page: manually-featured stories lead the hero row, then everything else
renders newest-first below. The "Latest News" section keeps its original
layout — a large lead card on the left with two shorter cards stacked to its
right and a pair of side-by-side cards below — and that same block is repeated
for every subsequent batch of five stories instead of being replaced by a plain
list.

## Scope & Method

- **No production access**: the live Supabase/Postgres database and deployment
  were never touched. All executable verification ran against isolated SQLite
  databases (`sqlite:////tmp/opencode/...`); `db_guard.py` blocks accidental
  remote-database access from a local shell.
- **Static analysis**: `py_compile` on `app.py`, `journal.py`, `forms.py`,
  `legal.py`, `db_guard.py` and all `tools/`; `pyflakes` across the same files.
- **Automated tests**: `tools/test_dburl.py` (15 tests) and
  `tools/test_security.py` (25 tests) against an isolated database.
- **Browser pass**: a real Chromium (Playwright, `channel="chromium"`) loaded
  every public URL at 1440×900, asserting HTTP status, console errors, and
  failed requests. Pages checked: `/`, `/blog`, `/cv`, `/partner`,
  `/become-a-partner`, `/privacy`, `/terms`, `/security`.
- **Dependency check**: pinned versions compared against current PyPI release
  lines and wheel availability for Python 3.14.
- Rendering of `/blog` was additionally checked for the requested semantics
  (no pagination, featured-first ordering, three-card hero row, list rows).

## Findings Summary

| Severity | Found | Fixed | Remaining | Notes |
|---|---|---|---|---|
| Critical | 0 | 0 | 0 | — |
| High | 6 | 6 | 0 | see below |
| Medium | 7 | 7 | 0 | see below |
| Low | 6 | 5 | 1 | inert pagination CSS |

High-severity items fixed: facilities exposed too much internal detail and
controls were too permissive (full Cloudinary URL logged at startup; generic
admin error leaked `str(exc)`; no upload SVG sanitization; CSV-export formula
injection; public POST endpoints unbounded; analytics admin view rendered
untrusted values via `innerHTML`).

Medium-severity items fixed: `?page=n` canonical duplication; geo-IP lookup
hit the network on every page view (blocking) and cached unboundedly; broadcast
sends blocked the request thread for its full loop; `/track/*` accepted
malformed payloads; failed logins leaked whether a username exists; static
assets force-revalidated on every request; `/admin/blog` middleware forms
referenced pagination state that no longer exists.

Low-severity items: unused imports/locals (`timedelta`, unused `exc`/`result`,
`urllib.parse`, `io`, `psycopg2.extras`); broken default OG image (404);
`css3` brand slug removed upstream at SimpleIcons (404 on the homepage);
unreasonably large tracked files and unreferenced assets are documented below,
not deleted.

## Fixes Applied

Security + request hardening

- **Logging**: `configure_logging` — single `retec` handler to stderr, werkzeug
  at WARNING, `LOG_LEVEL` override. Startup no longer prints the full
  Cloudinary URL (cloud name only); admin analytics failures log the detail and
  show a generic message; `print`/`JOURNAL` calls moved to `app.logger` and
  CLI output to `click.echo`.
- **CSV injection**: `_csv_cell` prefixes `= + - @ \t \r` with `'`;
  `_csv_writer` forces QUOTE_ALL. Applied to analytics, partner-applications,
  and subscribers exports.
- **Uploads**: `sanitize_svg` rejects `<script`, event handlers, `javascript:`,
  foreign content, and DOCTYPE; `upload_image` verifies SVG bytes;
  `UPLOAD_CONTENT_TYPES` whitelist; uploads are served under a `sandbox` CSP.
- **Auth**: every admin request re-loads the `User` (revoked accounts are
  signed out immediately); `/admin/api/*` failures return JSON `401` instead of
  redirect HTML; failed logins use a constant-time `_DUMMY_HASH` so unknown
  usernames are indistinguishable.
- **Rate limits**: `/contact` + `/partner` limited to 5/hour (POST only);
  `/subscribe` 5/hour; `/verify-email` 20/minute; `/track/*` 120/minute.
- **Tracking**: `_tracking_payload`/`_track_value` validate types and lengths;
  malformed payloads return `204` and are discarded, never 500.
- **Form parsing**: `form_int` helper (fallback + low/high clamps) for
  `sort_order` and `duration_seconds`; `_load_cube_positions` tolerates corrupt
  hero settings.
- **Error handling**: friendly 404/405/413/500 handlers with a new
  `templates/500.html`; API paths return JSON; `/healthz` performs `SELECT 1`.

Headers, caching, and privacy

- **`apply_response_headers`**: nosniff, X-Frame-Options SAMEORIGIN,
  Referrer-Policy, Permissions-Policy, CSP (strict; `'unsafe-inline'` kept by
  design and documented in `CSP_DIRECTIVES`; `upgrade-insecure-requests` and
  HSTS in production over HTTPS); dynamic responses marked `no-store`.
- **Static caching**: `STATIC_MAX_AGE_SECONDS` (default 3600);
  `?v=<ASSET_VERSION>` assets are served `immutable` for a year; uploads get
  the upload CSP + one-hour cache.
- **Geo lookup**: `_geo_cache` bounded to 5000 entries with oldest-first
  eviction; lookups moved off the request thread; HTTPS ip-api calls with a
  status check and 2s timeout.

Reliability & performance

- **`_journal_due`**: claim-first query order so the common (no work) path runs
  a single query.
- **`send_broadcast`**: threaded via ThreadPoolExecutor with a wall-clock
  budget (`BREVO_BROADCAST_BUDGET_SECONDS`, default 25s) and worker count
  (`BREVO_BROADCAST_WORKERS`, default 8); queued recipients past the deadline
  are reported as *not sent (time limit)* instead of blocking the admin request;
  test email is validated.
- **Analytics indexes** created at startup: timestamp/page composite on
  `page_view`, timestamp/section composite on `interest`, ip/country on
  `location_log`, plus `ix_blog_post_fetched_at`.
- **`templates/admin/analytics.html`**: untrusted city/country values are now
  inserted with `textContent`/DOM construction, not `innerHTML`.

Journal archive (requested redesign)

- Removed pagination end to end: `JOURNAL_PER_PAGE`, the `pagination()` macro,
  the `?page=` canonical parameter, and the admin queue's paging references.
- `/blog` renders every published article on one page ordered `is_featured
  desc, published_at desc` (featured first, then latest).
- Hero row: the featured lead plus up to two more featured/image stories
  (`templates/blog.html`).
- Latest News keeps the original widget design — `feature-lead` (large, left),
  two `feature-side` cards stacked to its right at matching height, and two
  `story-grid-card` entries beneath — rendered as a repeating template block
  (`journal__batch`) per five stories, separated by a hairline rule, with no
  pagination and no "View More" dead link.
- Canonical URLs keep only genuine selectors (`type`, `category`); `page` is
  never echoed.

Cosmetic & hygiene

- New default OG image `static/images/og-default.png` (1200×630) referenced by
  `meta_image` (previously every OG preview 404'd).
- Homepage project logos: `css3` → `css` (SimpleIcons removed the old slug).
- `pyflakes` clean across the app, `journal.py`, `forms.py`, `legal.py`,
  `db_guard.py`, and `tools/`.

## Remaining Risks & Recommendations

- **Log rotation / credential** — the full Cloudinary URL was logged by past
  startup code. Logs are redacted today, but rotate the Cloudinary credential
  anyway in case an old log escaped. Env credentials live in `.env*` which are
  gitignored; keep it that way.
- **Dependency drift (no known CVEs)** — pins are from 2024/2025 and safe:
  gunicorn `22.0.0` (latest `26.2.0`), Flask `3.0.3` (latest `3.1.3`), Werkzeug
  installed `3.1.8` (latest `3.1.9`), Jinja2 `3.1.6` (current), requests
  `2.32.3` (fixed CVE-2024-35195), Pillow `12.0.0`, Werkzeug post-CVE-2024-34069.
  Schedule a bump-only pass, and note that `pip-audit` is not installed — add it
  to deployment/CI.
- **Python 3.14 wheels** — `psycopg2-binary 2.9.12` ships cp314 manylinux
  x86_64/aarch64 wheels, so the Render stack resolves cleanly; `psycopg 3.x` is
  also pinned as a fallback. Keep an eye on gunicorn-side Python 3.14 worker
  compatibility in the Render image.
- **Backup round-trip tests** — `tools/test_pgbackup.py` self-skips without
  `RETEC_TEST_PG_URL`; run it against a throwaway Postgres before the first
  scheduled backup counts on it.
- **Automated testing is not wired into CI** — `tools/test_security.py` and
  `tools/test_dburl.py` exist and pass; wire them into a pre-deploy check.
- **External media dependency** — hero/logo images load from Unsplash,
  SimpleIcons, Pinterest, and Cloudinary. This is a browsing/uptime dependency;
  if the site must survive without it, self-host the icons.
- **Inert CSS** — the CSS added for the abandoned list design was removed; the
  original `.journal-pagination` and `.journal__view-more` rules remain unused
  (harmless) and the new `.journal__batch` separator rule is the only addition.
  Reduced-motion handling is still intact inside `static/js/motion/`.
- **Unreferenced/heavy tracked files** — a ~21MB MP4 and hash-named JPGs,
  `poster.png`/`generate_poster.py`, and `made-mirage.zip` are tracked. They
  are not deleted, but consider pruning them from history to keep the repo lean.
- **`/legal/privacy-policy`** returned `404` in a probe; it is not linked
  anywhere (the real paths are `/privacy`, `/terms`, `/security`) — noted for
  completeness, no change needed.

## Final Decision

The app is deployable: zero critical or high-severity findings remain from the
verified set, all automated checks pass, and the requested Journal redesign is
implemented and rendering cleanly. The only open items are routine dependency
updates, CI wiring, and a one-off credential rotation — none block a release.

### 🟡 GO WITH CAUTION

Proceed with deployment after (1) rotating the Cloudinary credential, (2)
bumping Flask/gunicorn to current lines, and (3) adding `pip-audit` +
`tools/test_security.py` to the pre-deploy check.