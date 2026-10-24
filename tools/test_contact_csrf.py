"""Contact form CSRF regression tests.

Run with an isolated database, for example:
    DATABASE_URL="sqlite:////tmp/retec-contact-csrf.db" \
      SECRET_KEY="test-only-secret" .venv/bin/python tools/test_contact_csrf.py

Importing app initializes the configured database, so never use the default
DATABASE_URL when running this file.
"""

import json
import os
import re
import sys
import uuid
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault('SECRET_KEY', 'test-only-secret')

import app as retec  # noqa: E402


class ContactCsrfTests(unittest.TestCase):
    def setUp(self):
        retec.app.config.update(
            TESTING=True,
            WTF_CSRF_ENABLED=True,
            RATELIMIT_ENABLED=False,
            WTF_CSRF_TIME_LIMIT=3600,
        )
        self.client = retec.app.test_client()
        self.email = 'csrf-%s@example.com' % uuid.uuid4().hex

    def _rendered_token(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('session=', response.headers.get('Set-Cookie', ''))
        match = re.search(
            r'<form class="contact__form".*?<input type="hidden" '
            r'name="csrf_token" value="([^"]+)"',
            response.get_data(as_text=True), re.S)
        self.assertIsNotNone(match, 'homepage should render the contact CSRF field')
        return match.group(1)

    def _valid_form(self, token):
        return {
            'csrf_token': token,
            'name': 'Test Contact',
            'email': self.email,
            'business': '',
            'project_type': '',
            'budget': '',
            'message': 'A valid test enquiry for CSRF regression coverage.',
            'website': '',
        }

    def test_valid_session_and_csrf_token_allow_submission(self):
        token = self._rendered_token()
        with patch.object(retec, 'send_email', return_value=True), \
                patch.object(retec, 'save_subscriber'):
            response = self.client.post('/contact', data=self._valid_form(token))
        self.assertEqual(response.status_code, 302)
        with retec.app.app_context():
            self.assertEqual(retec.Enquiry.query.filter_by(
                email=self.email).count(), 1)

    def test_csrf_token_without_its_session_is_rejected(self):
        token = self._rendered_token()
        response = retec.app.test_client().post(
            '/contact', data=self._valid_form(token))
        self.assertEqual(response.status_code, 400)
        self.assertIn('CSRF session token is missing',
                      response.get_data(as_text=True))

    def test_missing_csrf_token_is_rejected(self):
        self._rendered_token()
        response = self.client.post('/contact', data=self._valid_form(''))
        self.assertEqual(response.status_code, 400)

    def test_invalid_csrf_token_is_rejected(self):
        self._rendered_token()
        response = self.client.post(
            '/contact', data=self._valid_form('invalid-test-token'))
        self.assertEqual(response.status_code, 400)

    def test_root_route_proxies_to_flask_backend(self):
        config_path = Path(__file__).resolve().parent.parent / 'vercel.json'
        config = json.loads(config_path.read_text())
        root_route = next(route for route in config['routes']
                          if route.get('src') == '/')
        self.assertEqual(root_route['dest'], 'https://retec.onrender.com/')


if __name__ == '__main__':
    unittest.main()
