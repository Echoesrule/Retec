import os, sys, threading, time, socket
os.environ['DATABASE_URL'] = 'sqlite:////tmp/opencode/retec-test2.db'
os.environ['SECRET_KEY'] = 'browser-check-secret'
import app as A
A.app.config['TESTING'] = True
# GitHub API calls on every render make page loads ~10s; stub them out.
A.get_github_stats = lambda: None
A.get_github_projects = lambda: []
A.app.jinja_env.globals['get_github_stats'] = lambda: None

from werkzeug.serving import make_server
srv = make_server('127.0.0.1', 5099, A.app, threaded=True)
threading.Thread(target=srv.serve_forever, daemon=True).start()
time.sleep(1)

from playwright.sync_api import sync_playwright

PAGES = ['/', '/blog', '/cv', '/partner', '/become-a-partner', '/privacy',
         '/terms', '/security', '/legal/privacy-policy']

with sync_playwright() as p:
    browser = p.chromium.launch()
    for path in PAGES:
        ctx = browser.new_context(ignore_https_errors=True)
        page = ctx.new_page()
        errors, failed = [], []
        page.on('console', lambda m: errors.append(f'{m.type}: {m.text}') if m.type == 'error' else None)
        page.on('pageerror', lambda e: errors.append(f'pageerror: {e}'))
        page.on('requestfailed', lambda r: failed.append(f'{r.url} :: {r.failure}'))
        try:
            resp = page.goto('http://127.0.0.1:5099' + path, wait_until='load', timeout=25000)
            status = resp.status if resp else '?'
        except Exception as e:
            status = 'ERROR ' + str(e)[:80]
            errors.append('nav: ' + str(e)[:120])
        page.wait_for_timeout(1200)
        real_failed = [f for f in failed if 'ERR_ABORTED' not in f]
        print(f'\n=== {path}  [{status}]')
        for e in errors: print('   CONSOLE:', e[:220])
        for f in real_failed[:8]: print('   REQFAIL:', f[:220])
        if not errors and not real_failed: print('   clean')
        ctx.close()
    browser.close()
srv.shutdown()
