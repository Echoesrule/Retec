#!/usr/bin/env python3
"""Round-trip tests for tools/pgbackup.py against a real PostgreSQL.

Skips (exit 0) when RETEC_TEST_PG_URL is not set, so it is safe in CI that has
no database. Point it at a throwaway database -- the tests DROP and CREATE
tables and never touch anything else:

    export RETEC_TEST_PG_URL="postgresql://user@/dbname?host=/var/run/postgresql"
    python3 tools/test_pgbackup.py
"""

import gzip
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pgbackup  # noqa: E402

try:
    import psycopg2
except ImportError:
    psycopg2 = None

URL = os.environ.get('RETEC_TEST_PG_URL')

DDL = """
DROP TABLE IF EXISTS "mixed case test" CASCADE;
DROP TABLE IF EXISTS child CASCADE;
DROP TABLE IF EXISTS parent CASCADE;
DROP TABLE IF EXISTS site_setting CASCADE;
DROP TABLE IF EXISTS "tbl with space" CASCADE;

CREATE TABLE parent (
    id serial PRIMARY KEY,
    name varchar(50) NOT NULL,
    amount numeric(10,2) DEFAULT 0.00
);
CREATE TABLE child (
    id serial PRIMARY KEY,
    parent_id integer REFERENCES parent(id) ON DELETE CASCADE,
    label text UNIQUE
);
CREATE TABLE site_setting (key varchar(50) PRIMARY KEY, value text);
CREATE TABLE "tbl with space" (id serial PRIMARY KEY, val text);
CREATE TABLE "mixed case test" (
    id serial PRIMARY KEY,
    plain text,
    "quoted" varchar(50),
    "weird name!" text
);
CREATE TYPE mood AS ENUM ('happy', 'sad');
CREATE TABLE mood_table (id serial PRIMARY KEY, m mood);
"""

# Deliberately nasty: NULLs, embedded newlines, tabs, backslashes, quotes,
# semicolons, unicode, emoji, an empty string, and a very long value.
#
# E'' strings are used wherever the value contains a real newline or backslash,
# so the database stores the character rather than a two-character escape.
DATA = {
    'parent': "INSERT INTO parent (id, name, amount) VALUES "
              "(1, 'plain', 10.50), (2, 'has ''quote''', -3.25), "
              "(3, 'has ; semicolon', 0), (4, 'tab\\there', 99999999.99);",
    'child': "INSERT INTO child (id, parent_id, label) VALUES "
             "(1, 1, 'one'), (2, 1, E'multi\\nline\\r\\nlabel'), "
             "(3, 2, E'trailing backslash \\\\'), "
             "(4, 2, 'emoji \U0001f680 \u00e9\u00e8'), "
             "(5, NULL, 'orphan'), (6, 2, '');",
    'site_setting': "INSERT INTO site_setting VALUES "
                    "('name', 'RETEC'), ('quote', 'He said \"hi\" & left'), "
                    "('empty', ''), ('backslash', E'a\\\\b\\\\c');",
    'tbl with space': "INSERT INTO \"tbl with space\" (val) VALUES ('ok');",
    'mixed case test': "INSERT INTO \"mixed case test\" (plain, \"quoted\", \"weird name!\") "
                       "VALUES ('has ''quote'' and ; semi', 'Q\"Q', 'W!W'), "
                       "(E'multi\\nline', NULL, NULL);",
    'mood_table': "INSERT INTO mood_table (m) VALUES ('happy'), ('sad');",
}

EXPECTED = {
    'parent': [('1', 'plain', '10.50'), ('2', "has 'quote'", '-3.25'),
               ('3', 'has ; semicolon', '0.00'),
               ('4', 'tab\there', '99999999.99')],
    'child': [('1', '1', 'one'), ('2', '1', 'multi\nline\r\nlabel'),
              ('3', '2', 'trailing backslash \\'),
              ('4', '2', 'emoji \U0001f680 \u00e9\u00e8'),
              ('5', '', 'orphan'), ('6', '2', '')],
    'site_setting': [('empty', ''), ('name', 'RETEC'),
                     ('quote', 'He said "hi" & left'),
                     ('backslash', 'a\\b\\c')],
    'tbl with space': [('ok',)],
    'mixed case test': [('has \'quote\' and ; semi', 'Q"Q', 'W!W'),
                        ('multi\nline', None, None)],
    'mood_table': [('happy',), ('sad',)],
}


def snapshot(cur, table):
    """Read a table back as comparable tuples (never raises on NULL)."""
    cur.execute('SELECT * FROM "%s"' % table)
    cols = [d[0] for d in cur.description]
    out = []
    for row in cur.fetchall():
        out.append(tuple('' if v is None else str(v) for v in row))
    return cols, sorted(out)


@unittest.skipUnless(URL, 'set RETEC_TEST_PG_URL to run')
class TestRoundTrip(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.conn = psycopg2.connect(URL)
        cls.conn.autocommit = True
        with cls.conn.cursor() as cur:
            cur.execute(DDL)
            for statement in DATA.values():
                cur.execute(statement)
        cls.before = {}
        with cls.conn.cursor() as cur:
            for table in EXPECTED:
                cls.before[table] = snapshot(cur, table)

    @classmethod
    def tearDownClass(cls):
        with cls.conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS mood_table, child, parent, "
                        "site_setting, \"tbl with space\", "
                        "\"mixed case test\" CASCADE")
            cur.execute('DROP TYPE IF EXISTS mood')
        cls.conn.close()

    def _dump(self):
        fd, path = tempfile.mkstemp(suffix='.sql.gz')
        os.close(fd)
        self.addCleanup(os.unlink, path)
        stats = pgbackup.dump_database(URL, path)
        return path, stats

    def test_01_dump_contains_schema_and_data(self):
        path, stats = self._dump()
        self.assertEqual(stats["tables"], len(EXPECTED))
        self.assertGreater(stats['rows'], 0)
        with gzip.open(path, 'rt', encoding='utf-8') as fh:
            text = fh.read()
        # The header line restore keys off MUST be present, once per table.
        self.assertIn('COPY "public"."parent" FROM stdin;', text)
        self.assertEqual(text.count('FROM stdin;'), len(EXPECTED))
        self.assertIn('CREATE TYPE "mood"', text)
        self.assertIn('REFERENCES', text)   # FK preserved
        self.assertIn('UNIQUE', text)       # unique constraint preserved
        self.assertIn('setval', text)       # sequences handled

    def test_02_inspect_matches_reality(self):
        path, stats = self._dump()
        info = pgbackup.inspect_dump(path)
        self.assertEqual(info['copy_blocks'], len(EXPECTED))
        self.assertEqual(info['rows'], sum(len(v) for v in EXPECTED.values()))

    def test_03_dump_file_permissions_are_private(self):
        path, _ = self._dump()
        self.assertEqual(oct(os.stat(path).st_mode & 0o777), '0o600')

    def test_04_dumps_are_deterministic(self):
        a, _ = self._dump()
        b, _ = self._dump()
        with open(a, 'rb') as fa, open(b, 'rb') as fb:
            self.assertEqual(fa.read(), fb.read(),
                             'two dumps of identical data must be byte-identical')

    def test_05_restore_round_trip_is_lossless(self):
        path, _ = self._dump()
        # Destroy everything, then restore.
        with self.conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS mood_table, child, parent, "
                        "site_setting, \"tbl with space\", "
                        "\"mixed case test\" CASCADE")
            cur.execute('DROP TYPE IF EXISTS mood')
        stats = pgbackup.restore_database(URL, path)
        self.assertGreater(stats['rows'], 0)
        with self.conn.cursor() as cur:
            for table, expected in EXPECTED.items():
                cols, got = snapshot(cur, table)
                self.assertEqual(got, expected, 'table %s' % table)
                self.assertEqual(got, self.before[table][1],
                                 'table %s changed across the round trip' % table)

    def test_06_restore_is_idempotent(self):
        """Running the same dump twice must not error or duplicate rows."""
        path, _ = self._dump()
        # Not idempotent check: restoring twice must not error or duplicate rows.
        pgbackup.restore_database(URL, path)
        with self.conn.cursor() as cur:
            for table, expected in EXPECTED.items():
                _, got = snapshot(cur, table)
                self.assertEqual(len(got), len(expected), 'table %s' % table)

    def test_07_sequences_continue_after_restore(self):
        path, _ = self._dump()
        pgbackup.restore_database(URL, path)
        with self.conn.cursor() as cur:
            cur.execute("INSERT INTO parent (name) VALUES ('new row') RETURNING id")
            new_id = cur.fetchone()[0]
        with self.conn.cursor() as cur:
            cur.execute('SELECT max(id) FROM parent')
            max_id = cur.fetchone()[0]
        self.assertEqual(new_id, max_id,
                         'sequence did not advance past restored ids')
        self.assertGreaterEqual(new_id, 4)

    def test_08_truncated_dump_is_rejected(self):
        path, _ = self._dump()
        with gzip.open(path, 'rt', encoding='utf-8') as fh:
            text = fh.read()
        broken = text.split('FROM stdin;')[0] + 'COPY "public"."parent" FROM stdin;\n1\ttrunc\n'
        fd, bpath = tempfile.mkstemp(suffix='.sql.gz')
        os.close(fd)
        self.addCleanup(os.unlink, bpath)
        with gzip.open(bpath, 'wt', encoding='utf-8') as fh:
            fh.write(broken)
        with self.assertRaises(pgbackup.RestoreError) as ctx:
            pgbackup.restore_database(URL, bpath)
        self.assertIn('truncated', str(ctx.exception).lower())

    def test_09_bad_statement_reports_where(self):
        fd, bpath = tempfile.mkstemp(suffix='.sql.gz')
        os.close(fd)
        self.addCleanup(os.unlink, bpath)
        with gzip.open(bpath, 'wt', encoding='utf-8') as fh:
            # genuinely invalid SQL; a DROP on a missing schema is only a
            # notice in Postgres and would not raise.
            fh.write('-- header\nSET client_encoding = \'UTF8\';\n'
                     'THIS IS NOT VALID SQL AT ALL;\n')
        with self.assertRaises(pgbackup.RestoreError) as ctx:
            pgbackup.restore_database(URL, bpath)
        self.assertIn('failed on statement', str(ctx.exception))

    def test_10_missing_file_is_a_clear_error(self):
        with self.assertRaises(pgbackup.RestoreError):
            pgbackup.restore_database(URL, '/nonexistent/dump.sql.gz')

    def test_11_unicode_survives(self):
        path, _ = self._dump()
        pgbackup.restore_database(URL, path)
        with self.conn.cursor() as cur:
            cur.execute("SELECT val FROM \"tbl with space\"")
            self.assertEqual(cur.fetchone()[0], 'ok')
            cur.execute("SELECT label FROM child WHERE id = 4")
            self.assertIn('\U0001f680', cur.fetchone()[0])


if __name__ == '__main__':
    unittest.main(verbosity=2)
