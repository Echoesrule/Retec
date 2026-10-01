"""Refuse to talk to a remote database unless it is provably safe to.

Background
----------
On 2026-09-30 a throwaway test script ran ``db.drop_all()`` against the live
Supabase production database and destroyed every content table. The cause was
mundane: ``app.py`` reads ``DATABASE_URL`` from ``.env`` at import time, the
script forgot to override it, and the test harness happened to be the only
thing between a typo and total data loss. Supabase's free plan has no
point-in-time recovery, so the data was unrecoverable.

Documentation did not prevent it, so this module does. There are two
independent locks, and both must be defeated deliberately.

Lock 1 -- boot guard (``assert_boot_allowed``)
    Importing the app with a *remote* ``DATABASE_URL`` raises unless the
    process is running on Render (where production actually lives) or
    ``RETEC_ALLOW_REMOTE_DB=1`` is set in the real process environment.
    Local development can therefore never silently attach to production.

Lock 2 -- drop guard (``guard_destructive_operations``)
    ``db.drop_all()`` and ``db.drop_table()`` raise if the configured database
    is remote, *even on Render*, unless ``RETEC_ALLOW_DESTRUCTIVE=1`` is set.
    This is the lock that would have saved the data on 2026-09-30.

What counts as "remote"
----------------------
Anything that is not SQLite and not a loopback address. A local PostgreSQL on
127.0.0.1 is treated as local, so a developer can still run a real Postgres
during development.
"""

import os
import sys

__all__ = [
    'is_local_url', 'is_remote_url', 'assert_boot_allowed',
    'guard_destructive_operations', 'LocalOnlyViolation', 'RemoteDatabaseRefused',
]

# Hosts that are unambiguously not "the internet".
_LOOPBACK_HOSTS = frozenset({
    'localhost', '127.0.0.1', '::1', '[::1]', '0.0.0.0',
    'host.docker.internal', 'db',  # docker-compose service name
})

# Environment variables set by the hosting platform we deploy to.
_RENDER_MARKERS = ('RENDER', 'RENDER_SERVICE_ID', 'RENDER_GIT_BRANCH')

# Placeholders that mean "not configured", so a stray value cannot masquerade
# as a real production connection.
_EMPTY_VALUES = frozenset({'', 'None', 'null', 'undefined'})


class RemoteDatabaseRefused(RuntimeError):
    """Raised at import time when a remote database is used unexpectedly."""


class LocalOnlyViolation(RuntimeError):
    """Raised when a destructive operation is attempted on a remote database."""


def _host_of(url):
    """Best-effort hostname from a SQLAlchemy database URL.

    Falls back to a hand parse so it works for both the ``scheme://`` form and
    SQLAlchemy's odd ``scheme://user:pass@host/db`` variants without needing
    SQLAlchemy imported (this module must be usable before the app is built).
    """
    if not url:
        return ''
    if url.startswith('sqlite'):
        return 'localhost'
    marker = '://'
    idx = url.find(marker)
    rest = url[idx + len(marker):] if idx != -1 else url
    # Strip any query string / fragment first.
    for sep in ('?', '#'):
        rest = rest.split(sep, 1)[0]
    # Drop credentials: everything up to the last '@' is userinfo.
    if '@' in rest:
        rest = rest.rsplit('@', 1)[1]
    # What is left starts with host[:port]/dbname
    host = rest.split('/', 1)[0]
    if host.startswith('['):          # IPv6 literal, optionally [::1]:5432
        host = host.split(']', 1)[0] + ']'
    elif host.count(':') == 1:        # host:port
        host = host.split(':', 1)[0]
    return host.strip().lower()


def is_local_url(url):
    """True for SQLite and loopback databases; False for anything remote."""
    if not url or url in _EMPTY_VALUES:
        return True  # unconfigured -> default to the safe interpretation
    if url.startswith('sqlite'):
        return True
    host = _host_of(url)
    if not host:
        return True
    if host in _LOOPBACK_HOSTS:
        return True
    # Bare filenames, e.g. 'portfolio.db' with no scheme at all.
    if '://' not in url and not host.endswith(('.db', '.sqlite', '.sqlite3')):
        return True
    return False


def is_remote_url(url):
    """Convenience inverse of :func:`is_local_url`."""
    return not is_local_url(url)


def _redact(url):
    """Host-only form of a URL, safe to print in an error message."""
    if not url:
        return '(unset)'
    host = _host_of(url) or '(unparseable)'
    scheme = url.split('://', 1)[0] if '://' in url else 'sqlite'
    return '%s://%s' % (scheme, host)


def assert_boot_allowed(url, environ=None, where='this process'):
    """Refuse to start with a remote database unless explicitly permitted.

    Returns the resolved "am I allowed to touch a remote DB" decision so
    callers can reuse it. Raises :class:`RemoteDatabaseRefused` otherwise.
    """
    environ = os.environ if environ is None else environ

    if not is_remote_url(url):
        return True

    if any(environ.get(marker) for marker in _RENDER_MARKERS):
        # Genuine production deploy. Allowed, but say so out loud.
        print('[db-guard] REMOTE database %s in use: this looks like a '
              'production deploy. Destructive operations remain locked.'
              % _redact(url), file=sys.stderr)
        return True

    if environ.get('RETEC_ALLOW_REMOTE_DB') == '1':
        print('[db-guard] REMOTE database %s ALLOWED via '
              'RETEC_ALLOW_REMOTE_DB=1. Do not do this casually.'
              % _redact(url), file=sys.stderr)
        return True

    raise RemoteDatabaseRefused(
        '\n'
        '================================================================\n'
        ' REFUSING TO CONNECT TO A REMOTE DATABASE\n'
        '================================================================\n'
        ' %s would start against a remote database:\n'
        '     %s\n'
        '\n'
        ' On 2026-09-30 a test script did exactly this and ran drop_all()\n'
        ' against production, destroying all content. Free-tier Supabase has\n'
        ' no point-in-time recovery, so it was unrecoverable.\n'
        '\n'
        ' Local development is meant to run on SQLite or loopback Postgres.\n'
        '\n'
        ' To fix this properly, remove DATABASE_URL from .env and use:\n'
        '     DATABASE_URL=sqlite:///portfolio.db\n'
        '\n'
        ' If you genuinely need the remote database right now, you must opt\n'
        ' in explicitly and knowingly:\n'
        '     RETEC_ALLOW_REMOTE_DB=1 <command>\n'
        '\n'
        ' Note that opt-in does NOT unlock drop_all()/drop_table(); those\n'
        ' additionally require RETEC_ALLOW_DESTRUCTIVE=1 and will still\n'
        ' refuse unless both are set.\n'
        '================================================================\n'
        % (where, _redact(url))
    )


def guard_destructive_operations(db, url, environ=None):
    """Wrap ``db.drop_all`` / ``db.drop_table`` so they cannot nuke production.

    This is deliberately not conditional on the boot guard: even a genuine
    production deploy, or an explicit ``RETEC_ALLOW_REMOTE_DB=1`` escape
    hatch, still cannot drop tables without ``RETEC_ALLOW_DESTRUCTIVE=1``.
    """
    environ = os.environ if environ is None else environ

    def _permitted():
        return (
            environ.get('RETEC_ALLOW_DESTRUCTIVE') == '1'
            and environ.get('RETEC_CONFIRM_DESTRUCTIVE') == url
        )

    def _refuse(op):
        raise LocalOnlyViolation(
            '\n'
            '================================================================\n'
            ' BLOCKED: %s() on a remote database\n'
            '================================================================\n'
            ' Database: %s\n'
            '\n'
            ' This operation is what destroyed the production data on\n'
            ' 2026-09-30. It is blocked even on Render, and even with\n'
            ' RETEC_ALLOW_REMOTE_DB=1.\n'
            '\n'
            ' Almost every use of this in a test is a mistake: a fresh\n'
            ' schema is one line away with a throwaway SQLite file.\n'
            '\n'
            '     DATABASE_URL="sqlite:////tmp/test.db" your_script.py\n'
            '\n'
            ' If you truly mean to destroy this remote database, set both:\n'
            '     RETEC_ALLOW_DESTRUCTIVE=1\n'
            '     RETEC_CONFIRM_DESTRUCTIVE=%s\n'
            '================================================================\n'
            % (op, _redact(url), url)
        )

    if is_local_url(url):
        return  # local database: no need to intercept anything

    if not hasattr(db, '_retec_guarded'):
        original_drop_all = db.drop_all

        def drop_all(*args, **kwargs):
            if not _permitted():
                _refuse('drop_all')
            print('[db-guard] drop_all() EXECUTING on %s -- '
                  'destructive operations were explicitly unlocked.' % _redact(url),
                  file=sys.stderr)
            return original_drop_all(*args, **kwargs)

        def drop_table(name, *args, **kwargs):
            if not _permitted():
                _refuse('drop_table')
            print('[db-guard] drop_table(%r) EXECUTING on %s -- '
                  'destructive operations were explicitly unlocked.' % (name, _redact(url)),
                  file=sys.stderr)
            return db.metadata.tables[name].drop(db.engine, *args, **kwargs)

        db.drop_all = drop_all
        db.drop_table = drop_table
        db._retec_guarded = True
        print('[db-guard] drop_all()/drop_table() are LOCKED on %s. '
              'Set RETEC_ALLOW_DESTRUCTIVE=1 + RETEC_CONFIRM_DESTRUCTIVE to unlock.'
              % _redact(url), file=sys.stderr)


if __name__ == '__main__':
    # Manual self-check: `python db_guard.py <url> [remote|local]`
    target = sys.argv[1] if len(sys.argv) > 1 else os.environ.get('DATABASE_URL', '')
    print('url      :', _redact(target))
    print('host     :', _host_of(target))
    print('local?   :', is_local_url(target))
    print('remote?  :', is_remote_url(target))
    if len(sys.argv) > 2:
        want_remote = sys.argv[2] == 'remote'
        assert is_remote_url(target) == want_remote, 'classification mismatch'
        print('assertion: OK')
    try:
        assert_boot_allowed(target, environ={})
        print('boot     : ALLOWED (local)')
    except RemoteDatabaseRefused as exc:
        print('boot     : REFUSED as expected for remote\n')
        print(str(exc).splitlines()[1])
