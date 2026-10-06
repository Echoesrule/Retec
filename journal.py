"""RETEC Journal engine.

Pure logic for the Journal's news-ingestion pipeline. Nothing in this module
touches the database or Flask: the models live in ``app.py`` with the rest of
the schema, and ``app.py`` owns the transactions. Keeping the parsing,
normalisation, de-duplication, sanitising and drafting here means each piece
can be reasoned about (and exercised) on its own.

The pipeline the admin sees is deliberately one-directional:

    fetch -> validate -> normalise -> deduplicate -> DRAFT -> admin review

Nothing here can publish. ``build_draft_body`` and ``AiEditor.draft`` return
*proposals*; turning one into a published article is an explicit human action
in the admin area, and that boundary is the whole point of the system.

No third-party dependencies: RSS/Atom parsing uses the standard library
``xml.etree.ElementTree`` and sanitising uses ``html.parser``.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import socket
import unicodedata
from datetime import datetime, timezone
from difflib import SequenceMatcher
from email.utils import parsedate_to_datetime
from html import unescape
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from xml.etree import ElementTree

__all__ = [
    'FeedError', 'FeedItem',
    'normalise_url', 'url_fingerprint', 'is_safe_http_url',
    'normalise_title', 'title_fingerprint', 'titles_match',
    'strip_html', 'truncate', 'sanitize_html', 'estimate_reading_time',
    'fetch_feed', 'parse_feed',
    'AiEditor', 'compose_brief_body', 'DRAFT_SECTIONS',
    'due_slot', 'DEFAULT_NEWS_SOURCES', 'JOURNAL_CATEGORIES',
    'words_per_minute', 'user_agent',
]

# Words are read at roughly this rate; only used for the "x min read" label.
words_per_minute = 220

FEED_TIMEOUT = 15
MAX_FEED_BYTES = 4 * 1024 * 1024
MAX_ITEMS_PER_SOURCE = 25
MAX_EXCERPT_CHARS = 420


class FeedError(Exception):
    """A source could not be read. Carries a short, admin-readable reason."""


# --------------------------------------------------------------------------
# URLs
# --------------------------------------------------------------------------

# Analytics and campaign parameters that make one article look like several
# URLs. Removing them is what stops `?utm_source=twitter` and the bare link
# becoming two drafts of the same story.
TRACKING_PARAMS = frozenset({
    'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
    'utm_id', 'utm_reader', 'utm_name', 'utm_social', 'utm_social-type',
    'gclid', 'gbraid', 'wbraid', 'dclid', 'fbclid', 'msclkid', 'twclid',
    'igshid', 'mc_cid', 'mc_eid', 'yclid', '_hsenc', '_hsmi', 'hsCtaTracking',
    'vero_id', 'vero_conv', 'ref', 'referrer', 'source', 'spm', 'cmpid',
    'campaign_id', 'at_medium', 'at_campaign', 'ncid', 'smid', 'partner',
    'wt_mc', 'CMP', 'ito', 'ns_campaign', 'ns_mchannel', 'ns_source',
})

_SCHEME_RE = re.compile(r'^[a-z][a-z0-9+.\-]*://', re.I)


def is_safe_http_url(url):
    """True for an ``http(s)`` URL with a host and no embedded credentials.

    External input reaches us through feed fields, so this is the gate that
    keeps ``javascript:``, ``data:`` and credential-spoofing URLs out of the
    database and out of every template that renders a source link.
    """
    url = (url or '').strip()
    if not url or not _SCHEME_RE.match(url):
        return False
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    if parts.scheme.lower() not in ('http', 'https'):
        return False
    if parts.username or parts.password:
        return False
    try:
        host = parts.hostname or ''
        parts.port  # raises on a malformed port
    except ValueError:
        return False
    if not host or ' ' in host or '.' not in host and host != 'localhost':
        return False
    return True


def normalise_url(url, base_url=''):
    """Canonical form of a URL for storage and de-duplication.

    Resolves relative links against the feed, lowercases scheme and host,
    drops the fragment, removes tracking parameters, sorts what is left and
    drops a trailing slash. Returns ``''`` when the URL is unusable.
    """
    url = (url or '').strip()
    if not url:
        return ''
    if not _SCHEME_RE.match(url):
        if not base_url:
            return ''
        url = urljoin(base_url, url)
    if not is_safe_http_url(url):
        return ''
    try:
        parts = urlsplit(url)
    except ValueError:
        return ''
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if k.lower() not in TRACKING_PARAMS]
    path = re.sub(r'/{2,}', '/', parts.path) or '/'
    if len(path) > 1 and path.endswith('/'):
        path = path[:-1]
    return urlunsplit((
        parts.scheme.lower(),
        parts.netloc.lower(),
        path,
        urlencode(sorted(query), doseq=True),
        '',
    ))


def url_fingerprint(url):
    """Stable hash of a normalised URL, used as the de-duplication key.

    www and non-www, http and https, and trailing-slash variants all collapse
    onto the same value. The query string is dropped entirely when only
    tracking parameters were present, which is the common case.
    """
    normalised = normalise_url(url)
    if not normalised:
        return ''
    parts = urlsplit(normalised)
    host = parts.netloc[4:] if parts.netloc.startswith('www.') else parts.netloc
    material = '%s%s' % (host, parts.path)
    return hashlib.sha1(material.encode('utf-8')).hexdigest()


# --------------------------------------------------------------------------
# Titles
# --------------------------------------------------------------------------

# Function words carry no identity once we are asking "is this the same story".
_TITLE_STOPWORDS = frozenset({
    'a', 'an', 'and', 'as', 'at', 'but', 'by', 'for', 'from', 'has', 'have',
    'in', 'is', 'it', 'its', 'new', 'of', 'on', 'or', 'that', 'the', 'this',
    'to', 'was', 'were', 'will', 'with', 'you', 'your', 'says', 'said',
})

_PUNCT_RE = re.compile(r"[^\w\s]+", re.UNICODE)
_WS_RE = re.compile(r'\s+')

# "OpenAI ships a new model - TechCabal" and "... | Rest of World" are the same
# headline as "...", and syndicated copies rarely agree on the suffix.
_PUBLISHER_SUFFIX_RE = re.compile(r'\s+[|–—\-·:]{1,2}\s+[^-–—|]{2,40}$')


def _strip_publisher_suffix(title):
    title = (title or '').strip()
    stripped = _PUBLISHER_SUFFIX_RE.sub('', title)
    return stripped if len(stripped) >= 12 else title


def normalise_title(title):
    """Lowercased, punctuation-free, whitespace-collapsed form of a title."""
    title = unescape(title or '')
    title = unicodedata.normalize('NFKD', title)
    title = ''.join(ch for ch in title if not unicodedata.combining(ch))
    title = _PUNCT_RE.sub(' ', title.lower())
    return _WS_RE.sub(' ', title).strip()


def title_fingerprint(title):
    """Hash of the significant words in a title, order-insensitive.

    Two headlines built from the same words in a different order ("Kenya
    mobile money adoption" / "Mobile money adoption in Kenya") share a
    fingerprint, which catches the syndicated-copy case that URL matching
    cannot see.
    """
    words = [w for w in normalise_title(_strip_publisher_suffix(title)).split()
             if w not in _TITLE_STOPWORDS]
    if not words:
        words = normalise_title(title).split()
    if not words:
        return ''
    return hashlib.sha1(' '.join(sorted(words)).encode('utf-8')).hexdigest()


def titles_match(left, right, threshold=0.82):
    """True when two headlines are close enough to be the same story.

    The fingerprint catches reordered headlines; the ratio catches minor
    rewording, added suffixes and dropped articles.
    """
    left_key = normalise_title(_strip_publisher_suffix(left))
    right_key = normalise_title(_strip_publisher_suffix(right))
    if not left_key or not right_key:
        return False
    if left_key == right_key:
        return True
    if title_fingerprint(left) and title_fingerprint(left) == title_fingerprint(right):
        return True
    return SequenceMatcher(None, left_key, right_key).ratio() >= threshold


# --------------------------------------------------------------------------
# HTML
# --------------------------------------------------------------------------

def strip_html(html):
    """Plain text from an HTML fragment."""
    if not html:
        return ''
    text = re.sub(r'(?is)<(script|style)[^>]*>.*?</\1>', ' ', html)
    text = re.sub(r'(?s)<!--.*?-->', ' ', text)
    text = re.sub(r'(?i)<br\s*/?>|</p>|</div>|</h[1-6]>|</li>', '\n', text)
    text = re.sub(r'(?s)<[^>]+>', '', text)
    text = unescape(text)
    text = re.sub(r'[ \t\r\f\v]+', ' ', text)
    text = re.sub(r'\n\s*\n\s*', '\n\n', text)
    return text.strip()


def truncate(text, limit=MAX_EXCERPT_CHARS):
    """Trim to a word boundary, adding an ellipsis when shortened."""
    text = _WS_RE.sub(' ', (text or '')).strip()
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(' ', 1)[0].rstrip(' ,;:.-')
    return (cut or text[:limit]) + '…'


def estimate_reading_time(text_or_html):
    """Whole minutes for a body of copy, never less than one."""
    plain = strip_html(text_or_html) or (text_or_html or '')
    words = len(plain.split())
    return max(1, int(round(words / float(words_per_minute))))


# The allow-list for article HTML. It covers what the admin editor toolbar and
# component buttons can emit, plus the prose tags the templates themselves
# rely on. Anything outside it -- including every script-bearing element -- is
# dropped, which is what makes feed content and model output safe to render.
ALLOWED_TAGS = frozenset({
    'p', 'br', 'hr', 'span', 'div', 'section',
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'b', 'strong', 'i', 'em', 'u', 's', 'mark', 'sup', 'sub', 'small',
    'a', 'ul', 'ol', 'li', 'dl', 'dt', 'dd',
    'blockquote', 'q', 'cite', 'code', 'pre', 'kbd', 'samp',
    'figure', 'figcaption', 'img',
    'table', 'thead', 'tbody', 'tfoot', 'tr', 'th', 'td', 'caption',
    'abbr', 'time', 'bdi', 'bdo', 'wbr',
})

VOID_TAGS = frozenset({'br', 'hr', 'img', 'wbr'})

# Elements whose *content* is dropped too, not just the tag.
DROP_WITH_CONTENT = frozenset({
    'script', 'style', 'iframe', 'object', 'embed', 'applet', 'form',
    'input', 'button', 'select', 'option', 'textarea', 'noscript',
    'svg', 'math', 'frame', 'frameset', 'link', 'meta', 'base', 'template',
})

GLOBAL_ATTRS = frozenset({'class', 'id', 'title', 'lang', 'dir'})

TAG_ATTRS = {
    'a': frozenset({'href', 'target', 'rel'}),
    'img': frozenset({'src', 'alt', 'width', 'height', 'loading'}),
    'td': frozenset({'colspan', 'rowspan', 'headers'}),
    'th': frozenset({'colspan', 'rowspan', 'scope', 'headers'}),
    'time': frozenset({'datetime'}),
    'ol': frozenset({'start', 'reversed', 'type'}),
    'li': frozenset({'value'}),
    'blockquote': frozenset({'cite'}),
    'q': frozenset({'cite'}),
    'abbr': frozenset({'title'}),
}

_SAFE_CSS_CLASS = re.compile(r'^[A-Za-z0-9_][A-Za-z0-9_\- ]{0,80}$')
_SAFE_ID = re.compile(r'^[A-Za-z][A-Za-z0-9_\-]{0,80}$')
_SAFE_REL = re.compile(r'^[A-Za-z ]{0,80}$')
_ENTITIES = re.compile(r'&(?:#\d+|#x[0-9a-fA-F]+|[a-zA-Z]+);')


def _attr_value(name, value, tag):
    """Filter one attribute. Returns ``None`` when it must not be emitted."""
    name = (name or '').lower()
    value = unescape((value or '')).strip()

    if name == 'href':
        if tag != 'a':
            return None
        if value.startswith(('#', '/', 'mailto:', 'tel:')):
            return value
        return value if is_safe_http_url(value) else None
    if name == 'src':
        if tag != 'img':
            return None
        if value.startswith('/') and not value.startswith('//'):
            return value
        return value if is_safe_http_url(value) else None
    if name == 'class':
        return value if _SAFE_CSS_CLASS.match(value) else None
    if name == 'id':
        return value if _SAFE_ID.match(value) else None
    if name == 'rel':
        return value if _SAFE_REL.match(value) else None
    if name in ('target', 'lang', 'dir', 'loading', 'width', 'height',
                'colspan', 'rowspan', 'scope', 'headers', 'value', 'start',
                'reversed', 'type', 'datetime', 'cite'):
        return value if len(value) <= 80 and not _ENTITIES.search(value) else None
    if name == 'title':
        return value if len(value) <= 300 else None
    return None


def _render_attrs(tag, attrs):
    out = []
    for name, value in attrs:
        if name not in GLOBAL_ATTRS and name not in TAG_ATTRS.get(tag, ()):
            continue
        clean = _attr_value(name, value, tag)
        if clean is None:
            continue
        out.append('%s="%s"' % (name, clean.replace('"', '&quot;')))
    if tag == 'a' and any(n == 'target' and v == '_blank' for n, v in attrs):
        # Any link that opens a new tab must not hand the opener over with it.
        if not any(entry.startswith('rel=') for entry in out):
            out.append('rel="noopener noreferrer"')
    return (' ' + ' '.join(out)) if out else ''


def _has_usable_src(attrs):
    return any(name == 'src' and _attr_value('src', value, 'img')
               for name, value in attrs)


class _Sanitiser(HTMLParser):
    """Allow-list rewriter. Unknown tags are unwrapped, not escaped, so pasted
    prose keeps its paragraphs while losing its scripting."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.open_tags = []
        self.drop_depth = 0

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if self.drop_depth:
            if tag not in VOID_TAGS:
                self.drop_depth += 1
            return
        if tag in DROP_WITH_CONTENT:
            self.drop_depth = 1
            return
        if tag not in ALLOWED_TAGS:
            return
        if tag == 'img' and not _has_usable_src(attrs):
            return  # an image with no usable source is just a broken box
        self.parts.append('<%s%s>' % (tag, _render_attrs(tag, attrs)))
        if tag not in VOID_TAGS:
            self.open_tags.append(tag)

    def handle_startendtag(self, tag, attrs):
        tag = tag.lower()
        if self.drop_depth or tag in DROP_WITH_CONTENT:
            return
        if tag in ALLOWED_TAGS and not (tag == 'img' and not _has_usable_src(attrs)):
            self.parts.append('<%s%s>' % (tag, _render_attrs(tag, attrs)))

    def handle_endtag(self, tag):
        tag = tag.lower()
        if self.drop_depth:
            if tag not in VOID_TAGS:
                self.drop_depth -= 1
            return
        if tag in VOID_TAGS or tag not in ALLOWED_TAGS:
            return
        if tag not in self.open_tags:
            return
        while self.open_tags:
            current = self.open_tags.pop()
            self.parts.append('</%s>' % current)
            if current == tag:
                break

    def handle_data(self, data):
        # convert_charrefs=True means every surviving '&' here is a literal
        # ampersand, so it is re-escaped alongside the tag delimiters.
        if not self.drop_depth and data:
            self.parts.append(data.replace('&', '&amp;')
                                    .replace('<', '&lt;')
                                    .replace('>', '&gt;'))

    def result(self):
        while self.open_tags:
            self.parts.append('</%s>' % self.open_tags.pop())
        return ''.join(self.parts)


def sanitize_html(html):
    """Return an allow-listed copy of ``html``, safe to render unescaped."""
    if not html:
        return ''
    parser = _Sanitiser()
    try:
        parser.feed(str(html))
        parser.close()
    except Exception:
        # A malformed fragment still gets its text through, just not its
        # structure -- never a silent pass-through of the original markup.
        return _escape_all(strip_html(html))
    return parser.result()


def _escape_all(text):
    return (text or '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


# --------------------------------------------------------------------------
# Feed fetching and parsing
# --------------------------------------------------------------------------

def user_agent():
    return ('Mozilla/5.0 (compatible; RETECJournal/1.0; +https://retec.dev/journal)')


class FeedItem:
    """One normalised entry from one feed.

    Only the fields RETEC needs for editorial processing are kept. The source
    article itself is never copied: the body stays where it is, and we store
    a link to it.
    """

    __slots__ = ('external_id', 'url', 'title', 'excerpt', 'published_at',
                 'image_url', 'author')

    def __init__(self, external_id='', url='', title='', excerpt='',
                 published_at=None, image_url='', author=''):
        self.external_id = (external_id or '').strip()[:255]
        self.url = url or ''
        self.title = (title or '').strip()
        self.excerpt = (excerpt or '').strip()
        self.published_at = published_at
        self.image_url = image_url or ''
        self.author = (author or '').strip()[:120]

    def as_dict(self):
        return {name: getattr(self, name) for name in self.__slots__}

    def __repr__(self):
        return '<FeedItem %r>' % (self.title or self.url)


# Namespaces we understand. Anything else in a feed is ignored rather than
# guessed at, so a malformed or hostile feed cannot smuggle fields through.
_NS = {
    'atom': 'http://www.w3.org/2005/Atom',
    'content': 'http://purl.org/rss/1.0/modules/content/',
    'dc': 'http://purl.org/dc/elements/1.1/',
    'media': 'http://search.yahoo.com/mrss/',
    'rdf': 'http://www.w3.org/1999/02/22-rdf-syntax-ns#',
    'rss1': 'http://purl.org/rss/1.0/',
}

_IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.webp', '.gif', '.avif')


def _text(node, *paths):
    """First non-empty text value among ``paths``, namespace-tolerant."""
    for path in paths:
        try:
            found = node.find(path, _NS)
        except SyntaxError:
            continue
        if found is not None:
            if found.text and found.text.strip():
                return found.text.strip()
            href = found.get('href')
            if href and href.strip():
                return href.strip()
    # Fall back to a suffix match so feeds that rename a namespace prefix but
    # keep the same URI are still read.
    wanted = {path.split(':')[-1] for path in paths}
    for child in node:
        if not isinstance(child.tag, str):
            continue
        if child.tag.split('}')[-1] in wanted:
            if child.text and child.text.strip():
                return child.text.strip()
            href = child.get('href')
            if href and href.strip():
                return href.strip()
    return ''


def _parse_datetime(value):
    """Best-effort UTC datetime from the many date formats feeds emit."""
    value = (value or '').strip()
    if not value:
        return None
    candidates = [value]
    if value.endswith('Z'):
        candidates.append(value[:-1] + '+00:00')
    for candidate in candidates:
        try:
            parsed = datetime.fromisoformat(candidate)
            return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc).astimezone(timezone.utc).replace(tzinfo=None)
        except ValueError:
            pass
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        return None
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def _first_image(node, base_url):
    """Pick an image URL from the usual media/enclosure places."""
    for tag in ('media:thumbnail', 'media:content'):
        found = node.find(tag, _NS)
        if found is not None:
            candidate = found.get('url') or found.get('href')
            if candidate:
                resolved = normalise_url(candidate, base_url)
                if resolved:
                    return resolved
    enclosure = node.find('enclosure')
    if enclosure is not None:
        mime = (enclosure.get('type') or '').lower()
        candidate = enclosure.get('url')
        if candidate and (mime.startswith('image/') or candidate.lower().split('?')[0].endswith(_IMAGE_EXTENSIONS)):
            resolved = normalise_url(candidate, base_url)
            if resolved:
                return resolved
    for tag in ('media:group', 'media:content'):
        group = node.find(tag, _NS)
        if group is None:
            continue
        for child in group.iter():
            candidate = child.get('url')
            if candidate:
                resolved = normalise_url(candidate, base_url)
                if resolved:
                    return resolved
    return ''


def parse_feed(payload, source_url=''):
    """Parse RSS 2.0, Atom or RDF into a list of :class:`FeedItem`.

    Raises :class:`FeedError` for anything that is not a usable feed, so the
    caller can record the reason against the source instead of silently
    ingesting nothing.
    """
    if not payload:
        raise FeedError('empty response')
    if isinstance(payload, bytes):
        if len(payload) > MAX_FEED_BYTES:
            raise FeedError('feed larger than %d MB' % (MAX_FEED_BYTES // 1048576))
        try:
            text = payload.decode('utf-8')
        except UnicodeDecodeError:
            try:
                text = payload.decode('latin-1')
            except Exception:
                raise FeedError('undecodable response')
    else:
        text = payload

    head = text.lstrip()[:200].lower()
    if '<html' in head or '<!doctype html' in head:
        raise FeedError('URL returned an HTML page, not a feed')

    try:
        root = ElementTree.fromstring(text.strip())
    except ElementTree.ParseError as exc:
        raise FeedError('malformed XML (%s)' % (str(exc)[:80],))

    tag = root.tag.split('}')[-1].lower()
    nodes = []
    if tag == 'rss' or tag == 'channel':
        channel = root.find('channel') if tag == 'rss' else root
        nodes = list(channel.findall('item')) if channel is not None else []
    elif tag == 'feed':
        nodes = list(root.findall('atom:entry', _NS))
    elif tag == 'rdf':
        nodes = list(root.findall('rss1:item', _NS)) or list(root.findall('item'))
    else:
        raise FeedError('unrecognised feed root <%s>' % tag)

    items, seen = [], set()
    for node in nodes:
        try:
            item = _parse_item(node, source_url)
        except Exception:
            continue  # one malformed entry must not lose the rest of the feed
        if not item or not item.title or not item.url:
            continue
        key = url_fingerprint(item.url) or normalise_title(item.title)
        if not key or key in seen:
            continue
        seen.add(key)
        items.append(item)
        if len(items) >= MAX_ITEMS_PER_SOURCE:
            break
    return items


def _parse_item(node, source_url):
    # An Atom entry's first <link> is usually rel="self", the feed's own URL, so
    # the alternate is looked up explicitly before falling back to plain <link>.
    link = ''
    for child in node.findall('atom:link', _NS):
        if (child.get('rel') or 'alternate') == 'alternate' and child.get('href'):
            link = child.get('href')
            break
    if not link:
        link = _text(node, 'link', 'atom:link', 'rss1:link')
    url = normalise_url(link, source_url)
    title = _text(node, 'title', 'atom:title', 'rss1:title')
    raw_excerpt = _text(node, 'description', 'atom:summary', 'rss1:description',
                        'atom:content', 'content:encoded')
    excerpt = truncate(strip_html(raw_excerpt), MAX_EXCERPT_CHARS)
    published = _parse_datetime(_text(
        node, 'pubDate', 'atom:published', 'atom:updated', 'dc:date',
        'rss1:pubDate'))
    return FeedItem(
        external_id=_text(node, 'guid', 'atom:id', 'rss1:guid'),
        url=url,
        title=unescape(title)[:300],
        excerpt=excerpt,
        published_at=published,
        image_url=_first_image(node, source_url),
        author=_text(node, 'dc:creator', 'atom:author/atom:name', 'author'),
    )


def _requests():
    """Import requests on demand.

    The app already depends on it; importing lazily keeps this module usable
    for its parsing and sanitising work in environments that do not.
    """
    import requests
    return requests


def requests_exceptions():
    """Exception tuple to catch around a feed fetch."""
    try:
        return (_requests().RequestException, socket.timeout)
    except ImportError:
        return (OSError,)


def fetch_feed(feed_url, timeout=FEED_TIMEOUT, session=None):
    """GET a feed and return its raw bytes.

    The body is read whole (bounded by ``MAX_FEED_BYTES``) so that a truncated
    document is a parse error rather than a silently short feed.
    """
    if not is_safe_http_url(feed_url):
        raise FeedError('feed URL is not a valid http(s) address')

    try:
        requests = _requests()
    except ImportError:
        raise FeedError('requests is not installed')

    if session is None:
        session = requests.Session()

    try:
        response = session.get(
            feed_url,
            timeout=timeout,
            headers={
                'User-Agent': user_agent(),
                'Accept': 'application/rss+xml, application/atom+xml, '
                          'application/xml;q=0.9, */*;q=0.8',
            },
            stream=True,
        )
        if response.status_code == 429:
            retry = response.headers.get('Retry-After')
            raise FeedError('rate limited by source (HTTP 429)%s'
                            % (', retry after %ss' % retry if retry else ''))
        if response.status_code >= 400:
            raise FeedError('source returned HTTP %d' % response.status_code)
        content_type = (response.headers.get('Content-Type') or '').lower()
        if 'html' in content_type and 'xml' not in content_type:
            raise FeedError('source returned HTML, not a feed')
        payload = b''
        for chunk in response.iter_content(65536):
            payload += chunk
            if len(payload) > MAX_FEED_BYTES:
                raise FeedError('feed larger than %d MB'
                                % (MAX_FEED_BYTES // 1048576))
    except FeedError:
        raise
    except Exception as exc:
        raise FeedError('network error (%s)' % type(exc).__name__.lower())

    if not payload:
        raise FeedError('source returned an empty body')
    return payload


# --------------------------------------------------------------------------
# Editorial drafting
# --------------------------------------------------------------------------

# The editorial skeleton every generated Brief follows. Keys are the section
# labels as they appear in the body; order is the reading order.
DRAFT_SECTIONS = (
    ('what_happened', 'What Happened'),
    ('why_it_matters', 'Why It Matters'),
    ('who_is_affected', 'Who Is Affected'),
    ('what_businesses_should_consider', 'What Businesses Should Consider'),
    ('retec_perspective', 'RETEC Perspective'),
)

_AI_SYSTEM_PROMPT = (
    'You are the editor at RETEC, a Kenyan digital studio that builds websites, '
    'web applications and custom software for businesses. You write short, '
    'precise business briefings.\n'
    '\n'
    'You are given the headline, summary and publication date of a third-party '
    'news report. Write RETEC\'s own analysis of it.\n'
    '\n'
    'Hard rules:\n'
    '- Never reproduce or closely paraphrase sentences from the source. You are '
    'commenting on the story, not republishing it.\n'
    '- Never invent figures, dates, company names or quotations that are not in '
    'the source material. If a detail is unknown, write about it generally.\n'
    '- Write for the owner of a small or mid-sized Kenyan business deciding what '
    'to do about technology. Concrete and calm. No hype.\n'
    '- Plain text only. No HTML, no markdown, no bullet characters, no headings.\n'
    '- Each section is 2 to 4 sentences.\n'
    '\n'
    'Reply with a single JSON object and nothing else, with exactly these keys: '
    '"headline" (string, max 90 characters, written in RETEC\'s voice and not '
    'a copy of the source headline), "excerpt" (string, max 200 characters), '
    'and one key per section: '
    + ', '.join('"%s"' % key for key, _ in DRAFT_SECTIONS) + '.'
)


def _paragraph(text):
    """One sanitised paragraph from plain or HTML input."""
    return '<p>%s</p>' % sanitize_html(strip_html(text)).strip()


def compose_brief_body(sections, fallback_excerpt=''):
    """Turn drafted section text into sanitised article HTML.

    Sections with no usable text are skipped rather than rendered as an empty
    heading, so a partial model response still produces a readable draft.
    """
    parts = []
    for key, label in DRAFT_SECTIONS:
        body = (sections.get(key) or '').strip()
        if not body:
            continue
        parts.append('<h2>%s</h2>' % label)
        for block in re.split(r'\n\s*\n', body):
            block = block.strip()
            if block:
                parts.append(_paragraph(block))
    if not parts and fallback_excerpt:
        parts.append(_paragraph(fallback_excerpt))
    return '\n'.join(parts)


class AiEditor:
    """Optional AI drafting against any OpenAI-compatible chat endpoint.

    Credentials come from the environment and are only ever used server-side;
    nothing here reaches a template. With no key configured the editor simply
    reports itself disabled and the pipeline still creates a draft from the
    normalised metadata alone.
    """

    def __init__(self, api_key=None, base_url=None, model=None, timeout=45, session=None):
        self.api_key = (api_key if api_key is not None else os.environ.get('JOURNAL_AI_API_KEY', '')).strip()
        self.base_url = (base_url if base_url is not None else
                         os.environ.get('JOURNAL_AI_BASE_URL', 'https://api.openai.com/v1')).strip().rstrip('/')
        self.model = (model if model is not None else
                      os.environ.get('JOURNAL_AI_MODEL', 'gpt-4o-mini')).strip()
        self.timeout = timeout
        self._session = session

    @property
    def enabled(self):
        return bool(self.api_key and self.model)

    def draft(self, item, source_name=''):
        """Return ``{'headline', 'excerpt', 'sections'}`` or ``None``.

        ``None`` means "no draft produced" -- no key, a failed call, or a
        response we could not read. Callers must treat every outcome as a
        draft proposal and never publish it.
        """
        if not self.enabled:
            return None
        session = self._session
        if session is None:
            import requests
            session = requests.Session()
            self._session = session

        prompt = (
            'Source: %s\n'
            'Headline: %s\n'
            'Published: %s\n'
            'Summary supplied by the source: %s\n'
        ) % (
            source_name or 'an external publication',
            item.title,
            item.published_at.strftime('%d %B %Y') if item.published_at else 'not stated',
            item.excerpt or 'not supplied',
        )

        payload = {
            'model': self.model,
            'temperature': 0.4,
            'max_tokens': 1100,
            'response_format': {'type': 'json_object'},
            'messages': [
                {'role': 'system', 'content': _AI_SYSTEM_PROMPT},
                {'role': 'user', 'content': prompt},
            ],
        }
        headers = {
            'Authorization': 'Bearer %s' % self.api_key,
            'Content-Type': 'application/json',
        }
        try:
            response = session.post(
                '%s/chat/completions' % self.base_url,
                json=payload, headers=headers, timeout=self.timeout,
            )
        except Exception:
            return None
        if response.status_code >= 400:
            return None
        try:
            body = response.json()
            raw = body['choices'][0]['message']['content']
        except Exception:
            return None

        data = _extract_json_object(raw)
        if not isinstance(data, dict):
            return None

        sections = {}
        for key, _ in DRAFT_SECTIONS:
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                sections[key] = truncate(strip_html(value), 1600)
        if not sections:
            return None
        return {
            'headline': truncate(strip_html(data.get('headline') or ''), 120),
            'excerpt': truncate(strip_html(data.get('excerpt') or ''), 200),
            'sections': sections,
        }


def _extract_json_object(raw):
    """Read a JSON object out of a model response.

    Models wrap JSON in prose or code fences often enough that a bare
    ``json.loads`` is not worth the failure rate.
    """
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip()
    fence = re.search(r'```(?:json)?\s*(.+?)```', text, re.S)
    if fence:
        text = fence.group(1).strip()
    if not text.startswith('{'):
        start, end = text.find('{'), text.rfind('}')
        if start == -1 or end <= start:
            return None
        text = text[start:end + 1]
    try:
        return json.loads(text)
    except ValueError:
        return None


# --------------------------------------------------------------------------
# Scheduling
# --------------------------------------------------------------------------

def due_slot(now=None, interval_minutes=60):
    """Return the bucket key a run belongs to, or ``None`` if one just ran.

    Callers persist the returned key. Bucketing by time (rather than storing
    "last run at") makes the interval self-describing and lets a unique index
    on the key act as a cross-process lock, so two gunicorn workers waking at
    the same moment cannot both fetch.
    """
    now = now or datetime.utcnow()
    if interval_minutes <= 0:
        return None
    minutes = (now - datetime(1970, 1, 1)).total_seconds() / 60.0
    return '%d' % int(minutes // interval_minutes)


def minutes_since(when, now=None):
    """Whole minutes elapsed since ``when``; ``None`` when never."""
    if not when:
        return None
    now = now or datetime.utcnow()
    return int((now - when).total_seconds() // 60)


def suggested_fetch_time(when, now=None):
    """Human-friendly 'last successful fetch' rendering for the admin table."""
    minutes = minutes_since(when, now)
    if minutes is None:
        return 'never'
    if minutes < 1:
        return 'just now'
    if minutes < 60:
        return '%d min ago' % minutes
    if minutes < 60 * 24:
        hours = minutes // 60
        return '%d hour%s ago' % (hours, '' if hours == 1 else 's')
    days = minutes // (60 * 24)
    if days < 30:
        return '%d day%s ago' % (days, '' if days == 1 else 's')
    return (when or now).strftime('%d %b %Y')


# Categories offered as filters. Free text is still accepted on an article, so
# this is a starting set for the seeder rather than a hard constraint.
JOURNAL_CATEGORIES = [
    'Business', 'Technology', 'AI', 'Digital Economy', 'Design',
    'Development', 'Cybersecurity', 'E-Commerce', 'Startups',
    'Digital Infrastructure',
]

# Source categories used by the ingestion pipeline.
SOURCE_CATEGORIES = [
    'KENYA / BUSINESS', 'TECHNOLOGY', 'AI', 'STARTUPS', 'CYBERSECURITY',
    'E-COMMERCE', 'DIGITAL ECONOMY', 'GLOBAL TECHNOLOGY',
]

# Starter sources, written into the database once so that adding, editing,
# disabling or removing a feed from here on is an admin action rather than a
# code change. Every URL below was reachable and served actual RSS at the time
# of writing; a dead feed degrades to a logged error, never to a failed run.
DEFAULT_NEWS_SOURCES = [
    # (name, feed_url, website_url, category)
    ('Standard Media — Business', 'https://www.standardmedia.co.ke/rss/business.php',
     'https://www.standardmedia.co.ke/', 'KENYA / BUSINESS'),
    ('Capital Business', 'https://www.capitalfm.co.ke/news/feed',
     'https://www.capitalfm.co.ke/', 'KENYA / BUSINESS'),
    ('Nation Africa', 'https://www.nation.africa/kenya/rss.xml',
     'https://www.nation.africa/kenya', 'KENYA / BUSINESS'),
    ('The East African', 'https://www.theeastafrican.co.ke/rss.xml',
     'https://www.theeastafrican.co.ke/', 'KENYA / BUSINESS'),
    ('TechCrunch', 'https://techcrunch.com/feed/', 'https://techcrunch.com/',
     'TECHNOLOGY'),
    ('The Verge', 'https://www.theverge.com/rss/index.xml', 'https://www.theverge.com/',
     'TECHNOLOGY'),
    ('Ars Technica', 'https://feeds.arstechnica.com/arstechnica/index',
     'https://arstechnica.com/', 'GLOBAL TECHNOLOGY'),
    ('Hacker News', 'https://hnrss.org/frontpage', 'https://news.ycombinator.com/',
     'TECHNOLOGY'),
    ('MIT Technology Review — AI',
     'https://www.technologyreview.com/topic/artificial-intelligence/feed',
     'https://www.technologyreview.com/', 'AI'),
    ('VentureBeat AI', 'https://feeds.feedburner.com/venturebeat/SZYF',
     'https://venturebeat.com/category/ai/', 'AI'),
    ('TechCrunch — Startups', 'https://techcrunch.com/category/startups/feed/',
     'https://techcrunch.com/category/startups/', 'STARTUPS'),
    ('TechCabal', 'https://techcabal.com/feed/', 'https://techcabal.com/',
     'STARTUPS'),
    ('BleepingComputer', 'https://www.bleepingcomputer.com/feed/',
     'https://www.bleepingcomputer.com/', 'CYBERSECURITY'),
    ('Krebs on Security', 'https://krebsonsecurity.com/feed/',
     'https://krebsonsecurity.com/', 'CYBERSECURITY'),
    ('African E-Commerce', 'https://www.africanecommerce.com/feed/',
     'https://www.africanecommerce.com/', 'E-COMMERCE'),
    ('Rest of World', 'https://restofworld.org/feed/latest/',
     'https://restofworld.org/', 'DIGITAL ECONOMY'),
]

# How recently a draft must have been seen for title-similarity matching to
# consider it. Older drafts are matched on URL and external id only, which
# keeps the per-item query bounded.
DEDUPE_WINDOW_DAYS = 120
DEDUPE_TITLE_CANDIDATES = 200