# RETEC — Working Notes for Agents

## Database safety (read before running anything)

`app.py` reads `DATABASE_URL` from `.env`, which points at the **live Supabase
PostgreSQL** database. `portfolio.db` in the repo root is a **stale artifact** —
it is empty, gitignored, and is *not* what the app talks to.

Any script, test or shell command that imports `app` therefore connects to
production. That includes `db.drop_all()`, `db.create_all()`, raw `DELETE`, and
ad-hoc `db.session.execute()` writes.

**Never run a destructive or exploratory statement against the default
connection.** To work on data, force an isolated database:

```bash
DATABASE_URL="sqlite:////tmp/opencode/retec-test.db" .venv/bin/python your_script.py
```

Use `sqlite:////absolute/path` (four slashes) for a real file. This exercises
the same models, routes and migrations without touching Supabase. Delete the
temp file when finished.

`db.create_all()` and the `ALTER TABLE` migration block at the bottom of
`app.py` both run at import time, so merely importing `app` is enough to
create tables. That is safe (additive only) but means an import is not a
read-only operation.

## Local dev

- Run: `.venv/bin/python app.py` (port 5000, debug/reloader on)
- The `inject_globals` context processor calls the GitHub API on **every**
  page render, so a single request can take ~10s. For fast tests, stub
  `app.get_github_stats` and `app.get_github_projects` to return `None` / `[]`.
- No test suite and no linter is configured. `python -m pyflakes` is not
  installed; use `.venv/bin/python -m py_compile` plus the Flask test client
  for verification.

## Architecture notes

- Single `app.py` (~2300 lines) holds models, routes and helpers. Public
  section copy lives in module-level lists near the bottom of the file
  (`services`, `process`, `partner_*`) rather than in templates.
- Public forms use Flask-WTF (`forms.py`) + a `website` honeypot field +
  `flask_limiter`. `ContactForm` and `PartnerForm` both follow this shape.
- CSRF: most admin POSTs and both public forms are protected. The admin login
  form and `/subscribe` are `@csrf.exempt`.
- The design system lives in `static/css/variables.css` (root tokens) plus a
  large `static/css/style.css` that has accumulated several generations of
  rules for the same selectors. Later rules win. **Append new scoped CSS at the
  end of `style.css`; do not add a new palette or override root tokens.**
- Motion is a GSAP + Lenis stack in `static/js/motion/`. Elements opt in with
  `data-motion="reveal|heading|text|label|stagger|card|image"`.
  `data-motion-delay` is in **milliseconds** and is clamped to 120
  (`core.js` `api.delay` does `parseInt(...)/1000`), so use `loop.index0 * 60`
  — a fractional value like `0.06` silently parses to `0`.
  Reduced motion is handled inside the modules.
