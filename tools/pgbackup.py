#!/usr/bin/env python3
"""Backup and restore a PostgreSQL database using only psycopg2.

Why not pg_dump?
----------------
Supabase's pooler breaks pg_dump: it hangs indefinitely at "reading
user-defined functions" (verified against this project's own Supabase
instance on 2026-09-30), and the direct ``db.<ref>.supabase.co`` host is
unreachable without IPv6. ``psql`` works fine over the pooler, and psycopg2
speaks the same protocol, so this module talks to Postgres directly and
emits plain SQL that ``psql`` or this module can restore.

    python3 tools/pgbackup.py dump    --url "$DATABASE_URL" --out backups/db.sql.gz
    python3 tools/pgbackup.py restore --url "$DATABASE_URL" --in  backups/db.sql.gz
    python3 tools/pgbackup.py inspect --in backups/db.sql.gz
    python3 tools/pgbackup.py selftest

Dump format (plain SQL, gzipped):

  * per-table ``DROP TABLE IF EXISTS ... CASCADE`` then ``CREATE TABLE``, so a
    restore is idempotent and needs no separate ``--clean`` step
  * data as ``COPY ... FROM stdin`` blocks, which are lossless for newlines,
    tabs, backslashes, NUL bytes, quotes and arbitrary client encodings
  * column types, defaults and NOT NULL preserved
  * primary keys, unique constraints, foreign keys and plain indexes preserved
  * enums and domains created before the tables that use them
  * sequences reset with ``setval`` after the data is loaded

Tables with no rows still contribute their DDL, so a restore always reproduces
the full schema. The file is written to ``.partial`` and renamed only on
success, so an interrupted run never leaves a truncated file that looks valid.
It is chmod 600 because it contains personal data.
"""

import argparse
import gzip
import os
import re
import sys

try:
    import psycopg2
    from psycopg2 import sql
    from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
except ImportError:  # pragma: no cover
    sys.stderr.write('psycopg2 is required: pip install psycopg2-binary\n')
    raise

__all__ = ['dump_database', 'restore_database', 'inspect_dump', 'render_dump',
           'main', 'RestoredStats']

SCHEMA = 'public'
COPY_END = '\\.'


class RestoreError(RuntimeError):
    pass


# --------------------------------------------------------------------------
# connection
# --------------------------------------------------------------------------
def connect(url, application_name='retec-backup'):
    return psycopg2.connect(url, application_name=application_name)


def _q(cur, *parts):
    """Quote an identifier using the server's own rules."""
    return sql.Identifier(*parts).as_string(cur.connection)


# --------------------------------------------------------------------------
# introspection
# --------------------------------------------------------------------------
def list_tables(cur):
    return [r[0] for r in _rows(cur, """
        SELECT table_name FROM information_schema.tables
         WHERE table_schema = %s AND table_type = 'BASE TABLE'
         ORDER BY table_name""", (SCHEMA,))]


def get_columns(cur, table):
    rows = _rows(cur, """
        SELECT column_name, data_type, udt_name, is_nullable, column_default,
               character_maximum_length, numeric_precision, numeric_scale,
               datetime_precision, is_identity, identity_generation
          FROM information_schema.columns
         WHERE table_schema = %s AND table_name = %s
         ORDER BY ordinal_position""", (SCHEMA, table))

    out = []
    for (name, data_type, udt_name, nullable, default, char_len,
         num_prec, num_scale, dt_prec, is_identity, identity_gen) in rows:
        parts = [sql.Identifier(name)]

        if is_identity == 'YES':
            parts.append(sql.SQL('GENERATED {} AS IDENTITY').format(
                sql.SQL((identity_gen or 'BY DEFAULT').upper())))
        elif data_type == 'ARRAY':
            parts.append(sql.SQL('{}[]').format(sql.SQL(udt_name)))
        elif data_type == 'character varying' and char_len:
            parts.append(sql.SQL('varchar({})').format(sql.Literal(char_len)))
        elif data_type == 'character':
            parts.append(sql.SQL('char({})').format(sql.Literal(char_len or 1)))
        elif data_type == 'numeric' and num_prec is not None:
            parts.append(sql.SQL('numeric({}, {})').format(
                sql.Literal(num_prec), sql.Literal(num_scale or 0)))
        elif data_type == 'timestamp without time zone' and dt_prec is not None:
            parts.append(sql.SQL('timestamp ({})').format(sql.Literal(dt_prec)))
        elif data_type == 'timestamp with time zone' and dt_prec is not None:
            parts.append(sql.SQL('timestamptz ({})').format(sql.Literal(dt_prec)))
        elif data_type == 'time without time zone' and dt_prec is not None:
            parts.append(sql.SQL('time ({})').format(sql.Literal(dt_prec)))
        elif data_type == 'time with time zone' and dt_prec is not None:
            parts.append(sql.SQL('timetz ({})').format(sql.Literal(dt_prec)))
        elif data_type == 'interval' and dt_prec is not None:
            parts.append(sql.SQL('interval ({})').format(sql.Literal(dt_prec)))
        elif data_type == 'USER-DEFINED':
            parts.append(sql.SQL(udt_name))
        else:
            parts.append(sql.SQL(data_type))

        # column_default arrives as already-valid SQL text, e.g.
        # "nextval('project_id_seq'::regclass)" or "''::text".
        if default is not None and is_identity != 'YES':
            parts.append(sql.SQL('DEFAULT {}').format(sql.SQL(default)))
        if nullable == 'NO':
            parts.append(sql.SQL('NOT NULL'))

        out.append(sql.SQL(' ').join(parts))
    return out


def get_primary_key(cur, table):
    # to_regclass() takes an already-quoted name, so table names containing
    # spaces, quotes or mixed case resolve correctly.
    return [r[0] for r in _rows(cur, """
        SELECT a.attname
          FROM pg_index i
          JOIN pg_attribute a ON a.attrelid = i.indrelid
                             AND a.attnum = ANY(i.indkey)
         WHERE i.indrelid = to_regclass(%s) AND i.indisprimary
         ORDER BY array_position(i.indkey, a.attnum)""",
        (_q(cur, SCHEMA, table),))]


def _constraints(cur, table, contype):
    return _rows(cur, """
        SELECT conname, pg_get_constraintdef(oid)
          FROM pg_constraint
         WHERE conrelid = to_regclass(%s) AND contype = %s
         ORDER BY conname""", (_q(cur, SCHEMA, table), contype))


def get_indexes(cur, table):
    """Indexes that are not already created by a PK/UNIQUE constraint."""
    return _rows(cur, """
        SELECT indexname, indexdef
          FROM pg_indexes
         WHERE schemaname = %s AND tablename = %s
           AND indexname NOT IN (SELECT conname FROM pg_constraint
                                  WHERE conrelid = to_regclass(%s)
                                    AND contype IN ('p','u'))
         ORDER BY indexname""", (SCHEMA, table, _q(cur, SCHEMA, table)))


def get_enums(cur):
    by_type = {}
    for name, label in _rows(cur, """
            SELECT t.typname, e.enumlabel
              FROM pg_type t
              JOIN pg_enum e ON e.enumtypid = t.oid
              JOIN pg_namespace n ON n.oid = t.typnamespace
             WHERE n.nspname = %s
             ORDER BY t.typname, e.enumsortorder""", (SCHEMA,)):
        by_type.setdefault(name, []).append(label)
    return by_type


def get_sequences(cur):
    """Sequence name -> creation parameters, so a restore can rebuild them.

    This matters: ``DROP TABLE ... CASCADE`` also drops the sequences owned by
    its columns, so a dump that only records ``nextval('x_seq'::regclass)``
    cannot be restored anywhere. The sequences are created first, then the
    tables, then the OWNED BY links and setval.
    """
    rows = _rows(cur, """
        SELECT s.relname,
               format_type(s.seqtypid, NULL),
               ps.start_value, ps.min_value, ps.max_value,
               ps.increment_by, ps.cycle, ps.cache_size
          FROM pg_class s
          JOIN pg_namespace n ON n.oid = s.relnamespace
          LEFT JOIN pg_sequences ps ON ps.schemaname = n.nspname
                                   AND ps.sequencename = s.relname
         WHERE s.relkind = 'S' AND n.nspname = %s
         ORDER BY s.relname""", (SCHEMA,))

    out = {}
    for name, data_type, start, minv, maxv, inc, cycle, cache in rows:
        out[name] = {
            'data_type': data_type or 'bigint',
            # pg_sequences is NULL for sequences it cannot describe; fall back
            # to the usual serial defaults rather than emitting nothing.
            'start': 1 if start is None else start,
            'min': 1 if minv is None else minv,
            'max': 9223372036854775807 if maxv is None else maxv,
            'increment': 1 if inc is None else inc,
            'cycle': bool(cycle),
            'cache': 1 if cache is None else cache,
        }
    return out


def get_sequence_owner(cur, sequence):
    """(table, column) a sequence is attached to, or (None, None)."""
    rows = _rows(cur, """
        SELECT t.relname, a.attname
          FROM pg_depend d
          JOIN pg_class c ON c.oid = d.objid
          JOIN pg_class t ON t.oid = d.refobjid
          JOIN pg_attribute a ON a.attrelid = d.refobjid
                             AND a.attnum = d.refobjsubid
         WHERE c.relkind = 'S' AND c.relname = %s
           AND d.refclassid = 'pg_class'::regclass
         LIMIT 1""", (sequence,))
    return (rows[0][0], rows[0][1]) if rows else (None, None)


def _rows(cur, statement, args=None):
    cur.execute(statement, args)
    return cur.fetchall()


# --------------------------------------------------------------------------
# dump
# --------------------------------------------------------------------------
class _CopySink:
    """File-like sink for COPY output; counts rows as they stream through.

    COPY text format is one row per line, so counting newlines counts rows.
    Bytes are buffered as text because the surrounding statements are text.
    """

    def __init__(self, chunks):
        self._chunks = chunks
        self._pending = b''
        self.rows = 0

    def write(self, data):
        if isinstance(data, str):
            data = data.encode('utf-8')
        self._pending += data
        while b'\n' in self._pending:
            line, self._pending = self._pending.split(b'\n', 1)
            self.rows += 1
            self._chunks.append(line.decode('utf-8', 'surrogateescape'))
        return len(data)

    def flush(self):
        if self._pending:
            self._chunks.append(self._pending.decode('utf-8', 'surrogateescape'))
            self._pending = b''

    def take(self):
        self.flush()
        return self._chunks


def render_dump(cur):
    """Build the dump. Returns (list_of_text_lines, stats)."""
    tables = list_tables(cur)
    enums = get_enums(cur)
    lines = [
        '-- RETEC database backup',
        '-- generated by tools/pgbackup.py (psycopg2; pg_dump does not work',
        '-- through the Supabase pooler)',
        '-- tables: %d' % len(tables),
        '',
        "SET client_encoding = 'UTF8';",
        'SET standard_conforming_strings = on;',
        'SET search_path = %s;' % SCHEMA,
        '',
    ]

    # Types must exist before the tables that reference them.
    #
    # CREATE TYPE has no IF NOT EXISTS, and a bare DROP TYPE ... CASCADE could
    # take out live columns, so the create is made conditional inside a
    # single-line DO block. Single-line matters: the restore path executes
    # statement-by-statement, and it is still valid for psql.
    for type_name, labels in sorted(enums.items()):
        quoted = ', '.join("'%s'" % l.replace("'", "''") for l in labels)
        lines.append('-- enum %s' % type_name)
        lines.append(
            'DO $$ BEGIN '
            "IF NOT EXISTS (SELECT 1 FROM pg_type t "
            'JOIN pg_namespace n ON n.oid = t.typnamespace '
            "WHERE t.typname = '%s' AND n.nspname = '%s') THEN "
            'CREATE TYPE %s AS ENUM (%s); '
            'END IF; END $$;'
            % (type_name.replace("'", "''"), SCHEMA, _q(cur, type_name), quoted))
    if enums:
        lines.append('')

    # Sequences must exist BEFORE the tables, because serial columns carry a
    # DEFAULT nextval('...') that is resolved when the table is created.
    sequences = get_sequences(cur)
    for seq, spec in sorted(sequences.items()):
        lines.append('-- sequence: %s' % seq)
        lines.append(
            'CREATE SEQUENCE IF NOT EXISTS %s AS %s INCREMENT BY %d '
            'MINVALUE %d MAXVALUE %d START WITH %d CACHE %d%s;'
            % (_q(cur, SCHEMA, seq), spec['data_type'], spec['increment'],
               spec['min'], spec['max'], spec['start'], spec['cache'],
               ' CYCLE' if spec['cycle'] else ''))
    if sequences:
        lines.append('')

    total_rows = 0
    populated = 0

    for table in tables:
        qtable = _q(cur, SCHEMA, table)
        lines.append('-- ---- table: %s ----' % table)
        lines.append('DROP TABLE IF EXISTS %s CASCADE;' % qtable)

        body = [sql.SQL('  ') + c for c in get_columns(cur, table)]
        pk = get_primary_key(cur, table)
        if pk:
            body.append(sql.SQL('  PRIMARY KEY ({})').format(
                sql.SQL(', ').join(sql.Identifier(c) for c in pk)))
        for conname, condef in _constraints(cur, table, 'u'):
            body.append(sql.SQL('  CONSTRAINT {} {}').format(
                sql.Identifier(conname), sql.SQL(condef)))
        for conname, condef in _constraints(cur, table, 'f'):
            body.append(sql.SQL('  CONSTRAINT {} {}').format(
                sql.Identifier(conname), sql.SQL(condef)))
        lines.append('CREATE TABLE %s (' % qtable)
        lines.append(sql.SQL(',\n').join(body).as_string(cur.connection))
        lines.append(');')

        for indexname, indexdef in get_indexes(cur, table):
            lines.append('-- index %s' % indexname)
            lines.append('%s;' % indexdef)

        # Data as COPY: lossless, and it preserves encoding round-trip.
        # The FROM stdin header must be written before the rows, otherwise a
        # restore creates the table and silently loads nothing.
        lines.append('COPY %s FROM stdin;' % qtable)
        sink = _CopySink(lines)
        cur.copy_expert(
            sql.SQL('COPY {} TO STDOUT WITH (FORMAT text)').format(
                sql.Identifier(SCHEMA, table)),
            sink)
        total_rows += sink.rows
        if sink.rows:
            populated += 1
        lines.append(COPY_END)
        lines.append('')

    # After the data is loaded: re-link each sequence to its column so a
    # later column drop takes the sequence with it, then advance it past the
    # highest id already present so the next insert does not collide.
    for seq in sorted(sequences):
        table, column = get_sequence_owner(cur, seq)
        lines.append('-- sequence ownership: %s' % seq)
        if table and column:
            lines.append('ALTER SEQUENCE %s OWNED BY %s.%s;'
                         % (_q(cur, SCHEMA, seq), _q(cur, SCHEMA, table),
                            _q(cur, column)))
        # setval's first argument is a regclass parsed from text, so it needs
        # the same double-quoting as any other identifier.
        qseq_text = _q(cur, SCHEMA, seq)
        if table and column:
            lines.append(
                "SELECT setval('%s', GREATEST(COALESCE(MAX(%s), 0), 1), true) "
                'FROM %s;' % (qseq_text, _q(cur, column), _q(cur, SCHEMA, table)))
        else:
            lines.append("SELECT setval('%s', 1, false);" % qseq_text)
    lines.append('')

    return lines, {'tables': len(tables), 'populated': populated, 'rows': total_rows}


def dump_database(url, out_path):
    conn = connect(url, 'retec-backup-dump')
    try:
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        with conn.cursor() as cur:
            lines, stats = render_dump(cur)
    finally:
        conn.close()

    payload = ('\n'.join(lines) + '\n').encode('utf-8', 'surrogateescape')
    directory = os.path.dirname(os.path.abspath(out_path))
    if directory:
        os.makedirs(directory, exist_ok=True)
    tmp = out_path + '.partial'
    # mtime=0 keeps the gzip header deterministic, so two dumps of identical
    # data are byte-identical (nice for checksums and for diffing).
    with open(tmp, 'wb') as raw_fh:
        with gzip.GzipFile(filename='', mode='wb', compresslevel=9,
                           fileobj=raw_fh, mtime=0) as fh:
            fh.write(payload)
    os.replace(tmp, out_path)
    os.chmod(out_path, 0o600)  # contains personal data
    return stats


# --------------------------------------------------------------------------
# restore
# --------------------------------------------------------------------------
class RestoredStats(dict):
    pass


_COPY_HEADER = re.compile(r'^COPY\s+(?P<target>.+?)\s+FROM\s+stdin;$', re.I)


def split_statements(lines):
    """Split dump lines into complete SQL statements.

    Line-by-line execution is not enough: ``CREATE TABLE`` spans several
    lines, and a ``DO $$ ... $$;`` block can contain semicolons that are not
    statement terminators. So this tracks quoting state and only ends a
    statement at a semicolon that is genuinely at the top level.

    Yields ``(kind, payload)`` where kind is 'sql' or 'copy'.
    """
    buf = []
    in_single = False
    in_double = False
    in_line_comment = False
    dollar_tag = None      # non-None while inside a $tag$ ... $tag$ block

    def flush():
        statement = '\n'.join(buf).strip()
        del buf[:]
        if statement:
            return statement
        return None

    for line in lines:
        if not buf and line.strip() == COPY_END:
            # Stray terminator with no preceding COPY header; ignore it.
            continue

        buf.append(line)
        text = line

        # Scan the line for quote transitions.
        i = 0
        while i < len(text):
            ch = text[i]

            if in_line_comment:
                break

            if dollar_tag is not None:
                if text.startswith(dollar_tag, i):
                    i += len(dollar_tag)
                    dollar_tag = None
                    continue
                i += 1
                continue

            if in_single:
                if ch == "'":
                    if i + 1 < len(text) and text[i + 1] == "'":
                        i += 2      # escaped '' inside a string
                        continue
                    in_single = False
                i += 1
                continue

            if in_double:
                if ch == '"':
                    if i + 1 < len(text) and text[i + 1] == '"':
                        i += 2      # escaped "" inside an identifier
                        continue
                    in_double = False
                i += 1
                continue

            # Not inside anything.
            if ch == "'":
                in_single = True
                i += 1
                continue
            if ch == '"':
                in_double = True
                i += 1
                continue
            if text.startswith('--', i):
                in_line_comment = True
                break
            if ch == '$':
                match = re.match(r'\$[A-Za-z_][A-Za-z0-9_]*\$|\$\$', text[i:])
                if match:
                    dollar_tag = match.group(0)
                    i += len(dollar_tag)
                    continue
            i += 1

        in_line_comment = False

        if in_single or in_double or dollar_tag is not None:
            continue    # statement not finished yet

        stripped = line.rstrip()
        if stripped.endswith(';'):
            statement = flush()
            if statement is None:
                continue
            if _COPY_HEADER.match(statement.strip()):
                yield 'copy', statement.strip()
            else:
                yield 'sql', statement
        elif stripped == COPY_END:
            # COPY terminator: hand the buffered rows to the caller.
            buf.pop()
            yield 'copyrows', flush()

    # Anything left over means the dump was cut short mid-statement.
    leftover = flush()
    if leftover and not leftover.endswith(';'):
        raise RestoreError(
            'dump is truncated: last statement is incomplete and has no ";" '
            'terminator: %r' % leftover[:120])


def restore_database(url, in_path, progress=None):
    """Apply a dump. DESTRUCTIVE: the dump contains DROP TABLE statements."""
    if not os.path.exists(in_path):
        raise RestoreError('no such dump: %s' % in_path)
    with gzip.open(in_path, 'rb') as fh:
        raw = fh.read()
    text = raw.decode('utf-8', 'surrogateescape')
    lines = text.split('\n')

    # The parser is a generator and can raise on a truncated dump, so force it
    # to run to completion *before* touching the database. Otherwise a corrupt
    # dump would be discovered halfway through applying it.
    events = list(split_statements(lines))

    conn = connect(url, 'retec-backup-restore')
    stats = RestoredStats(statements=0, tables=0, rows=0)
    try:
        # Autocommit, not a transaction: a dump contains its own DROP TABLEs,
        # and wrapping the lot in one transaction would hold locks for the
        # whole restore. The pre-restore backup is the safety net here.
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        from io import StringIO
        with conn.cursor() as cur:
            for index, (kind, payload) in enumerate(events, start=1):
                if kind == 'sql':
                    if payload.upper().startswith('CREATE TABLE '):
                        stats['tables'] += 1
                    try:
                        cur.execute(payload)
                        stats['statements'] += 1
                    except Exception as exc:
                        raise RestoreError(
                            'failed on statement %d: %r -- %s'
                            % (index, payload[:160], exc))
                elif kind in ('copy', 'copyrows'):
                    header = payload if kind == 'copy' else None
                    rows_text = None if kind == 'copy' else payload
                    if header is None:
                        raise RestoreError(
                            'dump is malformed: data rows with no COPY header')
                    buffer = StringIO((rows_text or '') + ('\n' if rows_text else ''))
                    target = _COPY_HEADER.match(header).group('target')
                    try:
                        cur.copy_expert(header, buffer)
                    except Exception as exc:
                        raise RestoreError(
                            'failed loading data for %s: %s' % (target, exc))
                    count = rows_text.count('\n') if rows_text else 0
                    stats['rows'] += count
                    if progress:
                        progress('%s: %d rows' % (target, count))
        conn.commit()
    finally:
        conn.close()
    return stats


# --------------------------------------------------------------------------
# inspect
# --------------------------------------------------------------------------
def inspect_dump(in_path):
    with gzip.open(in_path, 'rt', encoding='utf-8', errors='surrogateescape') as fh:
        text = fh.read()
    rows = 0
    copies = 0
    for block in re.findall(r'^COPY [^\n]*\n(.*?)^\\\.$', text, re.M | re.S):
        copies += 1
        rows += block.count('\n')
    return {
        'tables': len(re.findall(r'^CREATE TABLE ', text, re.M)),
        'copy_blocks': copies,
        'rows': rows,
        'sequences': len(re.findall(r'^SELECT setval\(', text, re.M)),
        'uncompressed_bytes': len(text),
    }


# --------------------------------------------------------------------------
# cli
# --------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        description='PostgreSQL backup/restore via psycopg2 (pg_dump-free)')
    sub = ap.add_subparsers(dest='cmd', required=True)

    p = sub.add_parser('dump')
    p.add_argument('--url', required=True)
    p.add_argument('--out', required=True)

    p = sub.add_parser('restore')
    p.add_argument('--url', required=True)
    p.add_argument('--in', dest='inp', required=True)

    p = sub.add_parser('inspect')
    p.add_argument('--in', dest='inp', required=True)

    args = ap.parse_args(argv)

    if args.cmd == 'dump':
        s = dump_database(args.url, args.out)
        print('dumped %d tables (%d with data, %d rows) -> %s'
              % (s['tables'], s['populated'], s['rows'], args.out))
        return 0
    if args.cmd == 'restore':
        s = restore_database(args.url, args.inp)
        print('restored: %d statements, %d tables, %d rows'
              % (s['statements'], s['tables'], s['rows']))
        return 0
    if args.cmd == 'inspect':
        for key, value in sorted(inspect_dump(args.inp).items()):
            print('%-20s %s' % (key, value))
        return 0
    return 1


if __name__ == '__main__':
    sys.exit(main())
