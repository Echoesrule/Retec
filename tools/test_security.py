"""Regression tests for the security and reliability fixes from the final audit.

Run with an isolated database, never against the configured production one:

    DATABASE_URL="sqlite:////tmp/opencode/retec-test.db" .venv/bin/python -m pytest tools/test_security.py

or without pytest:

    DATABASE_URL="sqlite:////tmp/opencode/retec-test.db" .venv/bin/python tools/test_security.py

Importing app runs db.create_all() and the startup migration block, so the
DATABASE_URL above is what keeps this away from the live database.
"""

import io
import os
import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault('SECRET_KEY', 'test-secret-key-not-for-production')

import app as retec  # noqa: E402
from app import (  # noqa: E402
    Subscriber, _csv_cell, _load_cube_positions, _sanitize_cube_positions,
    _track_value, form_int, sanitize_svg,
)

application = retec.app


class HelperTests(unittest.TestCase):
    """Pure functions, no request context needed."""

    def test_csv_formula_injection_is_neutralised(self):
        # Spreadsheets evaluate a leading =, +, - or @ as a formula. Every one
        # of these values comes from a field an unauthenticated visitor fills in.
        for payload in ('=cmd|\'/c calc\'!A1', '+1+1', '-2+3', '@SUM(1+1)',
                        '\t=1+1', '\r=1+1'):
            self.assertTrue(_csv_cell(payload).startswith("'"),
                            'formula payload not neutralised: %r' % payload)

    def test_csv_leaves_ordinary_values_alone(self):
        self.assertEqual(_csv_cell('Alice Smith'), 'Alice Smith')
        self.assertEqual(_csv_cell('alice@example.com'), 'alice@example.com')
        self.assertEqual(_csv_cell(''), '')
        self.assertEqual(_csv_cell(None), '')
        self.assertEqual(_csv_cell(42), 42)

    def test_csv_passes_datetime_through_unchanged(self):
        # Retained as a datetime so the CSV module formats it the same way the
        # column always has, rather than stringifying it to an ISO timestamp.
        stamp = datetime(2026, 1, 2, 3, 4, 5)
        self.assertEqual(_csv_cell(stamp), stamp)

    def test_form_int_falls_back_instead_of_raising(self):
        # A bare int() on this input produced an unhandled ValueError and a 500.
        self.assertEqual(form_int('abc'), 0)
        self.assertEqual(form_int(None, 6), 6)
        self.assertEqual(form_int('', 6), 6)
        self.assertEqual(form_int('7'), 7)
        self.assertEqual(form_int(' 7 '), 7)

    def test_form_int_clamps_to_bounds(self):
        self.assertEqual(form_int('999999', 6, low=1, high=600), 600)
        self.assertEqual(form_int('-5', 6, low=1, high=600), 1)

    def test_svg_with_active_content_is_refused(self):
        hostile = [
            b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
            b'<svg xmlns="http://www.w3.org/2000/svg"><rect onload="alert(1)"/></svg>',
            b'<svg><a xlink:href="javascript:alert(1)">x</a></svg>',
            b'<svg><foreignObject><body onload="alert(1)"/></foreignObject></svg>',
            b'<!DOCTYPE svg [<!ENTITY x "y">]><svg xmlns="http://www.w3.org/2000/svg"/>',
        ]
        for payload in hostile:
            self.assertIsNone(sanitize_svg(payload),
                              'hostile svg accepted: %r' % payload[:60])

    def test_clean_svg_is_accepted(self):
        clean = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><circle r="5"/></svg>'
        self.assertIsNotNone(sanitize_svg(clean))

    def test_cube_positions_tolerate_bad_stored_value(self):
        # This setting is parsed on every homepage render; one bad row used to
        # take the whole page down.
        self.assertIsNone(_load_cube_positions(None))
        self.assertIsNone(_load_cube_positions(''))
        self.assertIsNone(_load_cube_positions('{truncated'))
        self.assertIsNone(_load_cube_positions('"a string"'))
        self.assertIsNone(_load_cube_positions('[]'))
        self.assertEqual(_load_cube_positions('[{"x": 1, "y": 2}]'),
                         [{'x': 1, 'y': 2}])

    def test_cube_positions_sanitizer_drops_bad_entries(self):
        cleaned = _sanitize_cube_positions([
            {'x': 50, 'y': 50},
            {'x': 'not a number', 'y': 10},
            'not a dict',
        ])
        self.assertEqual(cleaned, [{'x': 50.0, 'y': 50.0}])

    def test_track_values_are_clipped_and_type_checked(self):
        # Non-string values used to be passed straight into a String column.
        self.assertEqual(_track_value({'page': 12345}, 'page', '/', 200), '/')
        self.assertEqual(_track_value({'page': {'a': 1}}, 'page', '/', 200), '/')
        self.assertEqual(_track_value({'page': None}, 'page', '/', 200), '/')
        self.assertEqual(_track_value({'page': ''}, 'page', '/', 200), '/')
        self.assertEqual(len(_track_value({'page': 'x' * 500}, 'page', '/', 200)), 200)
        self.assertEqual(_track_value({}, 'page', '/', 200), '/')


class RequestTests(unittest.TestCase):
    """Exercises routes through the test client."""

    def setUp(self):
        application.config.update(TESTING=True, WTF_CSRF_ENABLED=False,
                                  RATELIMIT_ENABLED=False)
        # Flask-SQLAlchemy scopes its session to the app context, and these tests
        # touch models directly outside a request.
        self.app_context = application.app_context()
        self.app_context.push()
        self.client = application.test_client()

    def tearDown(self):
        retec.db.session.remove()
        self.app_context.pop()

    def test_security_headers_present_on_pages(self):
        headers = self.client.get('/').headers
        self.assertIn('Content-Security-Policy', headers)
        self.assertIn('Permissions-Policy', headers)
        self.assertEqual(headers['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(headers['X-Frame-Options'], 'SAMEORIGIN')

    def test_versioned_static_is_immutably_cached(self):
        headers = self.client.get('/static/css/style.css?v=1').headers
        self.assertIn('immutable', headers['Cache-Control'])

    def test_unversioned_static_is_briefly_cached(self):
        headers = self.client.get('/static/css/style.css').headers
        self.assertIn('max-age=3600', headers['Cache-Control'])

    def test_asset_version_is_stable_across_requests(self):
        # It used to be int(time.time()), so no asset could ever be cached.
        import re
        first = self.client.get('/').get_data(as_text=True)
        second = self.client.get('/').get_data(as_text=True)
        pattern = r'style\.css\?v=(\d+)'
        self.assertEqual(set(re.findall(pattern, first)),
                         set(re.findall(pattern, second)))
        self.assertTrue(re.search(pattern, first))

    def test_healthz_reports_database(self):
        response = self.client.get('/healthz')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['checks']['database'], 'ok')

    def test_admin_api_unauthenticated_returns_401_json(self):
        # Was a 302 to the login page, so a fetch() died parsing HTML.
        for path in ('/admin/api/analytics/summary',
                     '/admin/api/analytics/top-pages',
                     '/admin/api/analytics/cities'):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 401, path)
            self.assertTrue(response.is_json, path)
            self.assertIn('error', response.get_json())

    def test_admin_api_404_is_json(self):
        response = self.client.get('/admin/api/analytics/nope')
        self.assertEqual(response.status_code, 404)
        self.assertTrue(response.is_json)

    def test_malformed_analytics_payloads_do_not_crash(self):
        # Each of these returned a 500 before the input was validated.
        bad_payloads = [
            {'page': 12345}, {'page': {'a': 1}}, {'page': None},
            {'page': ['x']}, 'not a dict', 'a plain string', 42, [],
        ]
        for payload in bad_payloads:
            response = self.client.post('/track/pageview', json=payload)
            self.assertEqual(response.status_code, 204, repr(payload))
        for payload in [{'section': 5}, {'action': {'x': 1}},
                        {'section': None}, {'action': []}]:
            response = self.client.post('/track/interest', json=payload)
            self.assertEqual(response.status_code, 204, repr(payload))

    def _make_admin(self):
        user = retec.User.query.filter_by(username='audit-test-admin').first()
        if user is None:
            user = retec.User(username='audit-test-admin',
                              password_hash=retec.bcrypt.generate_password_hash(
                                  'audit-test-password').decode('utf-8'))
            retec.db.session.add(user)
            retec.db.session.commit()
        return user

    def test_stale_admin_session_is_rejected(self):
        # A deleted admin stayed authorised for the life of the cookie, because
        # admin_required only checked that admin_id was present in the session.
        user = self._make_admin()
        with self.client.session_transaction() as session:
            session['admin_id'] = user.id
            session['admin_username'] = user.username
        response = self.client.get('/admin/api/analytics/summary')
        self.assertEqual(response.status_code, 200)

        retec.db.session.delete(user)
        retec.db.session.commit()
        response = self.client.get('/admin/api/analytics/summary')
        self.assertEqual(response.status_code, 401)
        self.assertTrue(response.is_json)

    def _login_as_admin(self):
        user = self._make_admin()
        with self.client.session_transaction() as session:
            session['admin_id'] = user.id
            session['admin_username'] = user.username
        return user

    def test_subscriber_csv_export_escapes_submitted_formula(self):
        # A name of =cmd|... was written verbatim into a file the admin then
        # opens in a spreadsheet, which executes it with the admin's privileges.
        self._login_as_admin()
        attack = Subscriber(email='attacker@example.com',
                            name="=cmd|'/c calc'!A1", source='@SUM(1+1)')
        retec.db.session.add(attack)
        retec.db.session.commit()
        try:
            response = self.client.get('/admin/subscribers/export.csv')
            self.assertEqual(response.status_code, 200)
            body = response.get_data(as_text=True)
            self.assertIn("\"'=cmd|'/c calc'!A1\"", body)
            self.assertIn('"\'@SUM(1+1)"', body)
        finally:
            retec.db.session.delete(attack)
            retec.db.session.commit()

    def test_partner_csv_export_escapes_submitted_formula(self):
        self._login_as_admin()
        attack = retec.PartnerApplication(
            name="=HYPERLINK(\"http://evil\",\"click\")",
            email='attacker@example.com', company='+1+1')
        retec.db.session.add(attack)
        retec.db.session.commit()
        try:
            response = self.client.get('/admin/partner-applications/export.csv')
            self.assertEqual(response.status_code, 200)
            body = response.get_data(as_text=True)
            self.assertIn('"\'=HYPERLINK', body)
            self.assertNotIn(',=HYPERLINK', body)
        finally:
            retec.db.session.delete(attack)
            retec.db.session.commit()

    def test_canonical_url_does_not_duplicate_pages(self):
        import re
        html = self.client.get('/blog?page=2&category=Foo').get_data(as_text=True)
        canonical = re.search(r'<link rel="canonical" href="([^"]+)"', html)
        self.assertIsNotNone(canonical)
        self.assertIn('page=2', canonical.group(1))
        self.assertIn('category=Foo', canonical.group(1))

        html = self.client.get('/blog?page=1').get_data(as_text=True)
        canonical = re.search(r'<link rel="canonical" href="([^"]+)"', html)
        self.assertIsNotNone(canonical)
        self.assertNotIn('page=', canonical.group(1))

    def test_default_open_graph_image_exists(self):
        response = self.client.get('/static/images/og-default.png')
        self.assertEqual(response.status_code, 200)
        self.assertIn('image/png', response.headers['Content-Type'])

    

    def test_public_form_limits_apply_to_post_only(self):
        # Unscoped limits counted page views, so the sixth visitor to load the
        # contact or partner section was refused before submitting anything.
        source = Path(retec.__file__).read_text()
        self.assertNotIn('@limiter.limit("5 per hour")', source)
        self.assertGreaterEqual(
            source.count('@limiter.limit("5 per hour", methods=["POST"])'), 2)

    def test_subscribe_has_a_post_rate_limit(self):
        # Signups can trigger third-party list sync; the limit is POST-scoped so
        # ordinary page loads are not counted against it.
        source = Path(retec.__file__).read_text()
        subscribe_block = source.split('def subscribe():')[0].rsplit("@app.route('/subscribe'", 1)[-1]
        self.assertIn('@limiter.limit(', subscribe_block)
        self.assertIn('methods=["POST"]', subscribe_block)


if __name__ == '__main__':
    unittest.main(verbosity=2)