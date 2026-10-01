#!/usr/bin/env python3
"""Tests for tools/_dburl.py -- run: python3 tools/test_dburl.py"""

import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _dburl  # noqa: E402


class TestParse(unittest.TestCase):
    def test_supabase_pooler_with_sslmode(self):
        u = ('postgresql://postgres.abc123:P%40ssw0rd%2Fkey@'
             'aws-0-eu-west-1.pooler.supabase.com:6543/postgres?sslmode=require')
        i = _dburl.parse(u)
        self.assertEqual(i['user'], 'postgres.abc123')
        self.assertEqual(i['pass'], 'P@ssw0rd/key')
        self.assertEqual(i['host'], 'aws-0-eu-west-1.pooler.supabase.com')
        self.assertEqual(i['port'], '6543')
        self.assertEqual(i['dbname'], 'postgres')  # query string must not leak

    def test_plain_url_no_query(self):
        i = _dburl.parse('postgresql://u:p@db.example.com:5432/retec')
        self.assertEqual(i['host'], 'db.example.com')
        self.assertEqual(i['port'], '5432')
        self.assertEqual(i['dbname'], 'retec')

    def test_direct_supabase_host(self):
        i = _dburl.parse('postgresql://u:p@db.abcdefgh.supabase.co:5432/postgres')
        self.assertEqual(i['host'], 'db.abcdefgh.supabase.co')
        self.assertEqual(i['dbname'], 'postgres')

    def test_password_with_colon_and_at(self):
        # rsplit on '@' means the LAST @ separates host from userinfo.
        i = _dburl.parse('postgresql://u:p:a@ss@host.example.com:5432/retec')
        self.assertEqual(i['host'], 'host.example.com')
        self.assertEqual(i['pass'], 'p:a@ss')

    def test_missing_port(self):
        i = _dburl.parse('postgresql://u:p@host.example.com/retec')
        self.assertEqual(i['host'], 'host.example.com')
        self.assertEqual(i['port'], '')
        self.assertEqual(i['dbname'], 'retec')

    def test_password_only_userinfo(self):
        i = _dburl.parse('postgresql://justuser@host.example.com:5432/retec')
        self.assertEqual(i['user'], 'justuser')
        self.assertEqual(i['pass'], '')

    def test_legacy_postgres_scheme(self):
        i = _dburl.parse('postgres://u:p@host.example.com:5432/retec')
        self.assertEqual(i['dbname'], 'retec')


class TestSessionPort(unittest.TestCase):
    def test_6543_becomes_5432(self):
        self.assertEqual(_dburl.session_port('6543'), '5432')

    def test_empty_becomes_5432(self):
        self.assertEqual(_dburl.session_port(''), '5432')

    def test_5432_unchanged(self):
        self.assertEqual(_dburl.session_port('5432'), '5432')

    def test_other_port_unchanged(self):
        self.assertEqual(_dburl.session_port('65432'), '65432')


class TestCli(unittest.TestCase):
    def run_cli(self, url, field):
        r = subprocess.run(
            [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                          '_dburl.py'), url, field],
            capture_output=True, text=True)
        return r.returncode, r.stdout.strip(), r.stderr.strip()

    def test_fields(self):
        u = 'postgresql://u:p@host.example.com:6543/mydb?sslmode=require'
        for field, want in [('user', 'u'), ('host', 'host.example.com'),
                            ('port', '6543'), ('dbname', 'mydb'), ('session_port', '5432')]:
            code, out, _ = self.run_cli(u, field)
            self.assertEqual(code, 0, field)
            self.assertEqual(out, want, field)

    def test_refuses_to_print_password(self):
        code, out, err = self.run_cli('postgresql://u:secret@h:5432/d', 'pass')
        self.assertEqual(code, 1)
        self.assertNotIn('secret', out)
        self.assertNotIn('secret', err)
        self.assertIn('PGPASSWORD', err)

    def test_empty_url_errors(self):
        code, _, err = self.run_cli('', 'host')
        self.assertEqual(code, 1)
        self.assertIn('empty', err)

    def test_garbage_url_errors(self):
        code, _, err = self.run_cli('not-a-url', 'host')
        self.assertEqual(code, 1)
        self.assertTrue(err)


if __name__ == '__main__':
    unittest.main(verbosity=2)
