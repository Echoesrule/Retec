#!/usr/bin/env python3
"""Parse a database URL into connection parts for the backup/restore scripts.

Used instead of bash string surgery because getting the host, port or database
name wrong here means dumping the wrong thing, or the wrong thing entirely.
Stdlib only (urllib.parse), so it runs anywhere the app runs.

    python3 tools/_dburl.py <url> user|pass|host|port|dbname|session_port
"""

import sys
from urllib.parse import urlsplit, unquote

# Supabase exposes two poolers:
#   6543  transaction pooler  -> pg_dump/psql CANNOT use this; it needs a real
#                               session, and the transaction pooler hands the
#                               connection straight back to the pool mid-query.
#   5432  session pooler      -> works with pg_dump and psql.
# Port 6543 is silently rewritten to 5432 for backup/restore.
TRANSACTION_POOLER_PORT = '6543'
SESSION_POOLER_PORT = '5432'


def parse(url):
    parts = urlsplit(url)
    # urlsplit puts netloc as "user:pass@host:port"; split off the userinfo.
    netloc = parts.netloc
    userinfo = ''
    if '@' in netloc:
        userinfo, netloc = netloc.rsplit('@', 1)
    user = password = ''
    if ':' in userinfo:
        user, password = userinfo.split(':', 1)
    elif userinfo:
        user = userinfo
    host, _, port = netloc.partition(':')
    return {
        'user': unquote(user),
        'pass': unquote(password),
        'host': host,
        'port': port,
        'dbname': unquote(parts.path.lstrip('/')),
    }


def session_port(port):
    """Rewrite the transaction-pooler port to the session pooler."""
    if not port or port == TRANSACTION_POOLER_PORT:
        return SESSION_POOLER_PORT
    return port


def main(argv):
    if len(argv) < 2:
        sys.stderr.write(__doc__)
        return 2
    url = argv[1]
    field = argv[2] if len(argv) > 2 else 'all'

    if not url:
        sys.stderr.write('empty url\n')
        return 1

    if field == 'session_port':
        print(session_port(url) if url.isdigit() else session_port(parse(url)['port']))
        return 0

    try:
        info = parse(url)
    except ValueError as exc:
        sys.stderr.write('could not parse url: %s\n' % exc)
        return 1

    if not info['host']:
        sys.stderr.write('no host in url\n')
        return 1

    if field == 'all':
        for key in ('user', 'host', 'port', 'dbname'):
            print('%s=%s' % (key, info[key]))
        return 0

    if field not in info:
        sys.stderr.write('unknown field %r\n' % field)
        return 1
    if field == 'pass':
        # Never print the password by accident; the scripts use PGPASSWORD.
        sys.stderr.write('refusing to print password; use the PGPASSWORD env var\n')
        return 1
    print(info[field])
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
