import os, json, re
os.environ['DATABASE_URL'] = 'sqlite:////tmp/opencode/retec-final.db'
os.environ['SECRET_KEY'] = 'test-secret-key-not-production'
os.environ['TESTING'] = 'true'

import app as A
app = A.app
app.config['TESTING'] = True
app.config['WTF_CSRF_ENABLED'] = True  # templates render form.csrf_token, so it must stay on
app.config['RATELIMIT_ENABLED'] = False
A.get_github_stats = lambda: None
A.get_github_projects = lambda: []
A.app.jinja_env.globals['get_github_stats'] = lambda: None

c = app.test_client()
fails = []
def check(name, cond, extra=''):
    print(('PASS ' if cond else 'FAIL ') + name + (' :: ' + str(extra) if extra else ''))
    if not cond: fails.append(name)

# --- headers on a page ---
r = c.get('/')
h = r.headers
check('CSP present', 'Content-Security-Policy' in h)
check('Permissions-Policy present', 'Permissions-Policy' in h)
check('nosniff', h.get('X-Content-Type-Options') == 'nosniff')
check('frame options', h.get('X-Frame-Options') == 'SAMEORIGIN')
check('dynamic no-store', 'no-store' in h.get('Cache-Control',''))

# --- stable asset version ---
body1 = c.get('/').get_data(as_text=True)
body2 = c.get('/').get_data(as_text=True)
v1 = set(re.findall(r'style\.css\?v=(\d+)', body1))
v2 = set(re.findall(r'style\.css\?v=(\d+)', body2))
check('asset version stable', v1 and v1 == v2, v1)

# --- static caching ---
r = c.get('/static/css/style.css?v=123')
check('versioned static immutable', 'immutable' in r.headers.get('Cache-Control',''), r.headers.get('Cache-Control'))
r = c.get('/static/css/style.css')
check('unversioned static has max-age', 'max-age=3600' in r.headers.get('Cache-Control',''), r.headers.get('Cache-Control'))

# --- healthz ---
r = c.get('/healthz')
check('healthz 200', r.status_code == 200, r.get_data(as_text=True)[:120])

# --- canonical ---
r = c.get('/blog?page=2&category=Foo')
m = re.search(r'<link rel="canonical" href="([^"]+)"', r.get_data(as_text=True))
canon = m.group(1) if m else ''
check('canonical keeps real params', 'page=2' in canon and 'category=Foo' in canon, canon)
r = c.get('/blog?page=1')
m = re.search(r'<link rel="canonical" href="([^"]+)"', r.get_data(as_text=True))
check('canonical drops page=1', m and 'page=' not in m.group(1), m.group(1) if m else None)

# --- og image resolves ---
m = re.search(r'og:image" content="([^"]+)"', r.get_data(as_text=True))
og = m.group(1) if m else ''
check('og image points at og-default.png', 'og-default.png' in og, og)
check('og image actually serves', c.get('/static/images/og-default.png').status_code == 200)

# --- CSV injection ---
cells = [A._csv_cell(v) for v in ['=cmd|calc', '+1+1', '-1', '@SUM(A1)', 'normal', '', None, '=2+2']]
check('csv formula prefixed', all(c2.startswith("'") for c2, v in zip(cells[:5], ['=cmd|calc','+1+1','-1','@SUM(A1)'])))
check('csv normal untouched', cells[4] == 'normal' and cells[5] == '' and cells[6] == '')
check('csv datetime passthrough', A._csv_cell(__import__('datetime').datetime(2024,1,1)) != '')

# --- form_int ---
check('form_int bad input', A.form_int('abc') == 0)
check('form_int clamp', A.form_int('99999', 6, low=1, high=600) == 600)
check('form_int None', A.form_int(None, 5) == 5)

# --- svg sanitizer ---
bad = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
ok  = b'<svg xmlns="http://www.w3.org/2000/svg"><circle r="5"/></svg>'
onx = b'<svg xmlns="http://www.w3.org/2000/svg"><rect onload="alert(1)"/></svg>'
ent = b'<!DOCTYPE svg [<!ENTITY x "y">]><svg xmlns="http://www.w3.org/2000/svg"/>'
check('svg script rejected', A.sanitize_svg(bad) is None)
check('svg onload rejected', A.sanitize_svg(onx) is None)
check('svg doctype rejected', A.sanitize_svg(ent) is None)
check('svg clean accepted', A.sanitize_svg(ok) is not None)

# --- uploads CSP ---
r = c.get('/static/uploads/default-og.png')
print('  (upload asset absent in test repo, status %s)' % r.status_code)

# --- malformed analytics payloads ---
for payload in [{'page': 12345}, {'page': {'a': 1}}, {'page': None}, {'page': ['x']}, 'notadict', 'plain string']:
    r = c.post('/track/pageview', json=payload)
    check('track pageview handles %r' % (payload,), r.status_code == 204, r.status_code)
for payload in [{'section': 5}, {'action': {'x':1}}, {'section': None}]:
    r = c.post('/track/interest', json=payload)
    check('track interest handles %s' % list(payload)[0], r.status_code == 204, r.status_code)

# --- admin api 401 json ---
r = c.get('/admin/api/analytics/summary')
check('admin api 401 not 302', r.status_code == 401, r.status_code)
check('admin api returns json', r.is_json, r.get_data(as_text=True)[:80])

# --- error handlers ---
r = c.post('/admin/api/analytics/summary')  # GET-only route, POST attempt
check('405 handler on api', r.status_code == 405 and r.is_json, r.status_code)
r = c.get('/admin/api/analytics/nope')
check('admin api 404 json', r.status_code == 404 and r.is_json, r.status_code)
r = c.post('/contact', data={})
check('contact POST missing csrf -> 4xx not 500', 400 <= r.status_code < 500, r.status_code)

print()
print('FAILURES:', fails if fails else 'none')
