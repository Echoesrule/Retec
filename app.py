from concurrent.futures import ThreadPoolExecutor
from markupsafe import escape

import click
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, Response, make_response
from datetime import datetime, timezone, timedelta
import logging, os, requests, csv, io, re, sys, time, secrets, json, socket, threading, base64
from pathlib import Path
from urllib.parse import urlsplit, urlencode
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from functools import wraps
from werkzeug.utils import secure_filename
from werkzeug.middleware.proxy_fix import ProxyFix
from dotenv import load_dotenv
from forms import (ContactForm, PartnerForm, PROJECT_TYPES, BUDGET_OPTIONS,
                   COLLABORATION_TYPES)
import journal
import legal

import cloudinary
import cloudinary.uploader

load_dotenv()


def clean_env_int(value, default, low=None, high=None):
    """Environment integer with a fallback, so a typo cannot crash boot."""
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        parsed = default
    if low is not None and parsed < low:
        return low
    if high is not None and parsed > high:
        return high
    return parsed

# Fail fast, before Flask, SQLAlchemy or any model exists, if we have been
# pointed at a remote database by accident. See db_guard.py for why this is
# not optional and what the escape hatches are.
import db_guard

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)
_is_production = (
    os.environ.get('APP_ENV', '').lower() == 'production'
    or os.environ.get('FLASK_ENV', '').lower() == 'production'
    or os.environ.get('RENDER', '').lower() in ('1', 'true')
    or os.environ.get('VERCEL') == '1'
)


def configure_logging(application, production):
    """Make sure ``app.logger`` actually emits at INFO in production.

    Flask installs a WARNING-level handler on the application logger when
    ``app.debug`` is false, so without this every ``app.logger.info(...)`` in
    the Journal pipeline, the Brevo calls and the admin actions was silently
    discarded once deployed. Handlers attached here go to stderr, which is where
    gunicorn collects worker output, so nothing depends on a log file existing.
    """
    level = logging.INFO if not production else os.environ.get(
        'LOG_LEVEL', 'INFO').upper()
    resolved = getattr(logging, str(level).upper(), None)
    if not isinstance(resolved, int):
        resolved = logging.INFO
    root = logging.getLogger('retec')
    root.setLevel(resolved)
    root.propagate = False
    if not any(getattr(h, '_retec_handler', False) for h in root.handlers):
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s [%(name)s] %(message)s'))
        handler._retec_handler = True
        root.addHandler(handler)
    application.logger.setLevel(resolved)
    # Werkzeug's request log is off by default; the limiter and our own
    # after_request work are what matter, and duplicate access logs from a
    # reverse proxy in front of gunicorn are pure noise.
    logging.getLogger('werkzeug').setLevel(logging.WARNING)


configure_logging(app, _is_production)
_secret_key = os.environ.get('SECRET_KEY')
if not _secret_key:
    if _is_production:
        raise RuntimeError('SECRET_KEY must be configured in production.')
    _secret_key = secrets.token_hex(32)
    app.logger.warning('SECRET_KEY is unset; using an ephemeral development key.')
app.secret_key = _secret_key
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = os.environ.get(
    'SESSION_COOKIE_SECURE', 'true' if _is_production else 'false'
).lower() in ('1', 'true', 'yes')
# Static files are revalidated on every navigation when this is 0, which costs a
# round trip per asset per page load (~20 assets on the homepage). The real
# cache-busting is the `?v=` stamp in the templates, so an hour is a safe floor
# for everything that is not explicitly versioned.
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = clean_env_int(
    os.environ.get('STATIC_MAX_AGE_SECONDS'), 3600)
_db_url = os.environ.get('DATABASE_URL', 'sqlite:///portfolio.db')
if _db_url and _db_url.startswith('postgres://'):
    _db_url = _db_url.replace('postgres://', 'postgresql://', 1)
if _db_url and ('render.com' in _db_url or 'supabase.co' in _db_url) and 'sslmode=' not in _db_url:
    _db_url += '&sslmode=require' if '?' in _db_url else '?sslmode=require'
db_guard.assert_boot_allowed(_db_url, where='app.py')
app.config['SQLALCHEMY_DATABASE_URI'] = _db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,
    'pool_recycle': 300,
    'pool_timeout': 20,
}
app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['MAIL_FROM'] = os.environ.get('MAIL_FROM', 'contact.retec@gmail.com')
app.config['MAIL_TO'] = os.environ.get('MAIL_TO', 'hello@retec.dev')
app.config['BREVO_API_KEY'] = os.environ.get('BREVO_API_KEY', '')
app.config['BREVO_LIST_ID'] = os.environ.get('BREVO_LIST_ID', '')
app.config['ZEROBOUNCE_API_KEY'] = os.environ.get('ZEROBOUNCE_API_KEY', '')
app.config['CLOUDINARY_URL'] = os.environ.get('CLOUDINARY_URL', '')
app.config['SMS_NOTIFY_TO'] = os.environ.get('SMS_NOTIFY_TO', '')
app.config['SMS_SENDER'] = os.environ.get('SMS_SENDER', 'RETEC')
app.config['WTF_CSRF_TIME_LIMIT'] = 3600
app.config['WTF_CSRF_SSL_STRICT'] = True

# ===== JOURNAL CONFIGURATION =====
# Everything here is optional: with no scheduler, no interval and no AI key
# the Journal still works, it just has to be fetched by hand from the admin.
JOURNAL_SCHEDULER_ENABLED = os.environ.get('JOURNAL_SCHEDULER_ENABLED', '1') not in ('0', 'false', 'False')
JOURNAL_FETCH_INTERVAL_MINUTES = clean_env_int(os.environ.get('JOURNAL_FETCH_INTERVAL_MINUTES'), 60)
# Run the fetch off the request thread so no visitor waits on a feed.
JOURNAL_FETCH_IN_BACKGROUND = os.environ.get('JOURNAL_FETCH_IN_BACKGROUND', '1') not in ('0', 'false', 'False')
JOURNAL_AI_ENABLED = os.environ.get('JOURNAL_AI_ENABLED', '1') not in ('0', 'false', 'False')
JOURNAL_MAX_DRAFTS_PER_SOURCE = clean_env_int(os.environ.get('JOURNAL_MAX_DRAFTS_PER_SOURCE'), 8)
JOURNAL_PUBLISHER = {
    'name': 'RETEC',
    'url': 'https://retec.dev',
    'logo': '/static/images/logo.svg',
    'same_as': [
        'https://github.com/echoesrule',
        'https://www.linkedin.com/in/emmanuel-kiprono-14a800389',
    ],
}

_cloudinary_url = app.config['CLOUDINARY_URL']
if _cloudinary_url:
    cloudinary.config(cloudinary_url=_cloudinary_url)
    # Log the account/cloud name only. CLOUDINARY_URL embeds the API secret as
    # its password component, so logging any prefix of the URL put a working
    # credential into Render's log stream on every boot. Never log this value.
    _cloud_name = ''
    try:
        _cred = urlsplit(_cloudinary_url).netloc
        _cloud_name = _cred.rpartition(':')[0].partition('@')[0]
    except Exception:
        pass
    app.logger.info('STARTUP Cloudinary configured for cloud %s', _cloud_name or '(unknown)')
else:
    app.logger.info('STARTUP CLOUDINARY_URL not set, using local file storage')

csrf = CSRFProtect(app)
_rate_limit_storage_uri = os.environ.get('RATELIMIT_STORAGE_URI', 'memory://').strip() or 'memory://'
if _is_production and _rate_limit_storage_uri.startswith('memory://'):
    app.logger.warning('RATELIMIT_STORAGE_URI uses per-process memory in production; configure shared Redis storage.')
limiter = Limiter(
    get_remote_address,
    app=app,
    storage_uri=_rate_limit_storage_uri,
    default_limits=['200 per day', '50 per hour'],
)

db = SQLAlchemy(app)
# Second lock: even on a real production deploy, drop_all()/drop_table() are
# refused unless the operator sets two confirming env vars.
db_guard.guard_destructive_operations(db, _db_url)
bcrypt = Bcrypt(app)

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None
_tz = os.environ.get('TIMEZONE', 'Africa/Nairobi')
@app.template_filter('localtime')
def _localtime_filter(dt):
    if dt is None:
        return ''
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if ZoneInfo:
        try:
            return dt.astimezone(ZoneInfo(_tz))
        except Exception:
            pass
    return dt.astimezone(timezone.utc)

@app.template_filter('format_datetime')
def _format_datetime_filter(dt, fmt='%Y-%m-%d %H:%M'):
    if dt is None:
        return ''
    return dt.strftime(fmt)

@app.template_filter('journal_content')
def _journal_content_filter(value):
    """Render stored article HTML through the allow-list, then mark it safe.

    Content is sanitised on write; doing it again on read means an article that
    predates the sanitiser — or one restored from a backup — still cannot inject
    markup into the page. Markup that survives is escaped by the filter itself,
    so the trailing `|safe` in the template only means "this string is already
    HTML", not "trust it".
    """
    return journal.sanitize_html(value)

@app.template_filter('human_date')
def _human_date_filter(value, fmt='%B %d, %Y'):
    if not value:
        return ''
    return value.strftime(fmt).replace(' 0', ' ')

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'mp4', 'webm', 'ogg'}
VIDEO_EXTENSIONS = {'mp4', 'webm', 'ogg'}
# Sniffing targets for uploads. An SVG declares its own type in the XML header,
# so without an explicit entry it would be served as text/plain and some older
# browsers would download it instead of rendering it.
UPLOAD_CONTENT_TYPES = {
    'png': 'image/png', 'jpg': 'image/jpeg', 'jpeg': 'image/jpeg',
    'gif': 'image/gif', 'webp': 'image/webp', 'svg': 'image/svg+xml',
    'mp4': 'video/mp4', 'webm': 'video/webm', 'ogg': 'video/ogg',
}
# Scripts and event handlers that make an SVG self-executing. See
# upload_image for why a .svg under /static/uploads/ is a live risk.
_SVG_ACTIVE_RE = re.compile(
    r'<\s*script|\son[a-z]+\s*=|javascript:|<\s*(foreignObject|iframe|embed|object)'
    r'|<\s*handler\b|data:text/html',
    re.IGNORECASE)


def sanitize_svg(raw):
    """Reject an uploaded SVG that can execute, or return ``None``.

    An SVG is an XML document that can carry <script>, on* handlers and
    javascript: URLs. Any of those opened directly from RETEC's own origin
    runs with that origin's privileges, including access to the admin session
    cookie -- the file is only ever supposed to be an inert picture. Rather than
    try to strip the dangerous parts and hope the result still renders, an SVG
    that contains any of them is refused outright; there is no legitimate reason
    for an uploaded logo or icon to contain a script.
    """
    text = raw.decode('utf-8', 'replace')
    if _SVG_ACTIVE_RE.search(text):
        return None
    # A DOCTYPE with entity declarations is how XXE/billion-laughs payloads get
    # in, and this document never needs one.
    if re.search(r'<!DOCTYPE', text, re.IGNORECASE):
        return None
    return text

# ===== MODELS =====

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)

class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, default='')
    category = db.Column(db.String(100), default='')
    tags = db.Column(db.String(500), default='')
    image_filename = db.Column(db.String(200), default='')
    github_url = db.Column(db.String(500), default='')
    demo_url = db.Column(db.String(500), default='')
    featured = db.Column(db.Boolean, default=False)
    visible = db.Column(db.Boolean, default=True)
    status = db.Column(db.String(50), default='')
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def tag_list(self):
        return [t.strip() for t in self.tags.split(',') if t.strip()] or ['N/A']

# Single source of truth for the project lifecycle. Internal values stay in the
# database; the label is the only thing ever presented, so the enum is never
# exposed to the frontend or hardcoded into a card.
PROJECT_STATUSES = [
    ('live', 'Live'),
    ('in_progress', 'In Progress'),
    ('completed', 'Completed'),
    ('concept', 'Concept'),
    ('archived', 'Archived'),
]
PROJECT_STATUS_VALUES = {value for value, _ in PROJECT_STATUSES}
PROJECT_STATUS_LABELS = dict(PROJECT_STATUSES)

def clean_project_status(value):
    """Whitelist a submitted status. Unknown or missing values stay '' so the
    badge is hidden rather than showing a status nobody chose."""
    value = (value or '').strip()
    return value if value in PROJECT_STATUS_VALUES else ''

class PageView(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    page = db.Column(db.String(200), nullable=False)
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.String(500))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class Interest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    section = db.Column(db.String(100), nullable=False)
    action = db.Column(db.String(100))
    ip_address = db.Column(db.String(45))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class LocationLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ip_address = db.Column(db.String(45), nullable=False)
    country = db.Column(db.String(100), default='')
    city = db.Column(db.String(100), default='')
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class FunFact(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.Text, nullable=False, default='')
    active = db.Column(db.Boolean, default=True)
    sort_order = db.Column(db.Integer, default=0)
    duration_seconds = db.Column(db.Integer, default=6)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Testimonial(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(200), default='')
    text = db.Column(db.Text, nullable=False)
    avatar_filename = db.Column(db.String(200), default='')
    active = db.Column(db.Boolean, default=True)
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# ===== RETEC JOURNAL =====
#
# One article system for all three content types. The table keeps its original
# name (`blog_post`) and every column the old blog had, so existing articles
# survive the refactor untouched; the Journal only adds columns.

JOURNAL_CONTENT_TYPES = [
    ('insight', 'Insight'),
    ('brief', 'Brief'),
    ('case_study', 'Case Study'),
]
JOURNAL_CONTENT_TYPE_VALUES = {value for value, _ in JOURNAL_CONTENT_TYPES}
JOURNAL_CONTENT_TYPE_LABELS = dict(JOURNAL_CONTENT_TYPES)

# Labels used in card/detail templates: plural for filter chips, singular for
# the badge above a headline.
JOURNAL_CONTENT_TYPE_PLURALS = {
    'insight': 'Insights',
    'brief': 'Briefs',
    'case_study': 'Case Studies',
}

# Article lifecycle. `new` is the inbox state a fetched story lands in before
# anyone has looked at it; everything else is a deliberate editorial decision.
#
#   fetched -> new -> draft -> review -> published
#                                        \-> rejected -> draft (resubmitted)
#   any -> archived
#
# `published` can only ever be set by an authenticated admin action. The
# ingestion pipeline writes `new` and stops there.
JOURNAL_STATUSES = [
    ('new', 'New'),
    ('draft', 'Draft'),
    ('review', 'In Review'),
    ('published', 'Published'),
    ('rejected', 'Rejected'),
    ('archived', 'Archived'),
]
JOURNAL_STATUS_VALUES = {value for value, _ in JOURNAL_STATUSES}
JOURNAL_STATUS_LABELS = dict(JOURNAL_STATUSES)

# Legal transitions, enforced server-side. Anything absent is refused, so a
# crafted POST cannot resurrect a rejected story or publish an archived one
# without an explicit intermediate step.
JOURNAL_STATUS_TRANSITIONS = {
    'new': {'draft', 'review', 'published', 'rejected', 'archived'},
    'draft': {'review', 'published', 'rejected', 'archived'},
    'review': {'draft', 'published', 'rejected', 'archived'},
    'published': {'draft', 'archived'},
    'rejected': {'draft', 'archived'},
    'archived': {'draft'},
}


class JournalArticle(db.Model):
    """A single Journal article: RETEC original writing or a reviewed Brief."""

    __tablename__ = 'blog_post'
    __table_args__ = (
        db.Index('ix_blog_post_status', 'status'),
        db.Index('ix_blog_post_content_type', 'content_type'),
        db.Index('ix_blog_post_category', 'category'),
        db.Index('ix_blog_post_published_at', 'published_at'),
        db.Index('ix_blog_post_status_published_at', 'status', 'published_at'),
        db.Index('ix_blog_post_canonical_url', 'canonical_url'),
        db.Index('ix_blog_post_external_id', 'external_id'),
    )

    # ----- Editorial content -----
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(200), unique=True, nullable=False, index=True)
    # `summary` is the excerpt shown on cards and in meta descriptions.
    summary = db.Column(db.String(500), default='')
    content = db.Column(db.Text, nullable=False)
    image_filename = db.Column(db.String(200), default='')
    content_type = db.Column(db.String(30), default='insight')
    category = db.Column(db.String(100), default='')
    author = db.Column(db.String(120), default='')
    is_featured = db.Column(db.Boolean, default=False)
    reading_time = db.Column(db.Integer, nullable=True)
    # ----- Lifecycle -----
    # Indexed by the explicit `ix_blog_post_status` entry in __table_args__.
    status = db.Column(db.String(20), default='draft')
    # Legacy mirror of `status`. Kept in sync so older queries and the existing
    # `published_at` logic keep working; never read it as the source of truth.
    published = db.Column(db.Boolean, default=False)
    published_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # ----- External source (nullable; only Briefs set these) -----
    source_name = db.Column(db.String(200), default='')
    source_url = db.Column(db.String(500), default='')
    source_published_at = db.Column(db.DateTime, nullable=True)
    # ----- Ingestion bookkeeping (nullable) -----
    external_id = db.Column(db.String(255), nullable=True)
    canonical_url = db.Column(db.String(500), nullable=True)
    url_fingerprint = db.Column(db.String(40), nullable=True)
    title_fingerprint = db.Column(db.String(40), nullable=True)
    original_title = db.Column(db.String(300), default='')
    original_excerpt = db.Column(db.Text, default='')
    image_url = db.Column(db.String(500), default='')
    fetched_at = db.Column(db.DateTime, nullable=True)
    source_record_id = db.Column(db.Integer, nullable=True)
    ai_generated = db.Column(db.Boolean, default=False)

    # ----- Presentation helpers -----

    @property
    def content_type_label(self):
        return JOURNAL_CONTENT_TYPE_LABELS.get(self.content_type, 'Insight')

    @property
    def status_label(self):
        return JOURNAL_STATUS_LABELS.get(self.status, 'Draft')

    @property
    def is_published(self):
        return self.status == 'published'

    @property
    def is_external(self):
        """True when the article rests on a third-party source we must credit."""
        return bool(self.source_name or self.source_url)

    @property
    def display_date(self):
        return self.published_at or self.created_at

    @property
    def hero_image(self):
        """Best available image: an uploaded file first, then the fetched one.

        External images can vanish, so `cover_image` reports whether the URL
        is one we control; the templates fall back gracefully when it is not.
        """
        if self.image_filename:
            return get_image_url(self.image_filename)
        return self.image_url or ''

    @property
    def cover_image(self):
        return self.image_filename or ''

    def can_transition_to(self, status):
        return status in JOURNAL_STATUS_TRANSITIONS.get(self.status or 'draft', set())

    def apply_status(self, status):
        """Move the article to ``status``, keeping timestamps and the legacy
        `published` flag consistent. Assumes the transition has been checked."""
        self.status = status
        self.published = status == 'published'
        if status == 'published' and self.published_at is None:
            self.published_at = datetime.utcnow()

    def estimated_reading_time(self):
        return self.reading_time or journal.estimate_reading_time(self.content or '')


class NewsSource(db.Model):
    """A configured RSS/Atom source the Journal fetches Briefs from.

    Sources live in the database, never in code, so adding or retiring a feed
    is an admin action.
    """

    __tablename__ = 'news_source'
    __table_args__ = (
        db.Index('ix_news_source_active', 'is_active'),
    )

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    feed_url = db.Column(db.String(500), nullable=False, unique=True)
    website_url = db.Column(db.String(500), default='')
    category = db.Column(db.String(60), default='', index=True)
    is_active = db.Column(db.Boolean, default=True)
    last_fetched_at = db.Column(db.DateTime, nullable=True)
    last_success_at = db.Column(db.DateTime, nullable=True)
    last_error = db.Column(db.Text, default='')
    last_status = db.Column(db.String(20), default='')
    consecutive_failures = db.Column(db.Integer, default=0)
    articles_created = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def fetch_ago(self):
        return journal.suggested_fetch_time(self.last_success_at or self.last_fetched_at)

    @property
    def health(self):
        """One word the admin can scan in the sources table."""
        if not self.last_fetched_at:
            return 'untried'
        if not self.last_error:
            return 'ok'
        if self.consecutive_failures >= 5:
            return 'failing'
        return 'degraded'


class NewsFetchRun(db.Model):
    """One pass over one source, kept as the admin-facing ingestion log.

    `slot` doubles as the cross-process lock: the scheduler inserts the current
    time bucket, and a unique index on it means only one worker can claim a
    given interval. The row is rolled back with the rest of the run if the
    fetch fails, so a transient error is retried rather than skipped.
    """

    __tablename__ = 'news_fetch_run'
    __table_args__ = (
        db.Index('ix_news_fetch_run_slot', 'slot', unique=True),
    )

    id = db.Column(db.Integer, primary_key=True)
    source_id = db.Column(db.Integer, nullable=True)
    slot = db.Column(db.String(24), nullable=True)
    trigger = db.Column(db.String(20), default='schedule')
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    finished_at = db.Column(db.DateTime, nullable=True)
    ok = db.Column(db.Boolean, default=False)
    entries_seen = db.Column(db.Integer, default=0)
    drafts_created = db.Column(db.Integer, default=0)
    duplicates_skipped = db.Column(db.Integer, default=0)
    drafts_generated = db.Column(db.Integer, default=0)
    error = db.Column(db.Text, default='')


class BlogPost(db.Model):
    """DEPRECATED ALIAS.

    The Journal owns article content now. `JournalArticle` is the model;
    this name is kept only so an old import keeps working, and it resolves to
    the very same table.
    """
    __table__ = JournalArticle.__table__


def clean_journal_content_type(value):
    value = (value or '').strip().lower()
    return value if value in JOURNAL_CONTENT_TYPE_VALUES else 'insight'


def clean_journal_status(value):
    value = (value or '').strip().lower()
    return value if value in JOURNAL_STATUS_VALUES else ''


def clean_optional_int(value):
    try:
        value = int(value)
        return value if value > 0 else None
    except (TypeError, ValueError):
        return None

def form_int(value, default=0, low=None, high=None):
    """Coerce a submitted integer field, or fall back.

    `sort_order` was read with a bare `int(request.form.get(...))`, so typing a
    letter into the field produced an unhandled ValueError and a 500 rather than
    the validation message the form already shows for every other field. The
    optional bounds clamp an out-of-range number instead of trusting the browser.
    """
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    if low is not None and parsed < low:
        return low
    if high is not None and parsed > high:
        return high
    return parsed

def clean_optional_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, '%Y-%m-%d')
    except ValueError:
        return None

class SiteSetting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.Text, default='')
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

DISPOSABLE_DOMAINS = frozenset(
    line.strip().lower()
    for line in Path(__file__).resolve().with_name("disposable_domains.txt").read_text(encoding="utf-8").splitlines()
    if line.strip()
)

class Subscriber(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    name = db.Column(db.String(100), default='')
    source = db.Column(db.String(100), default='website')
    brevo_synced = db.Column(db.Boolean, default=False)
    validated = db.Column(db.Boolean, default=False)
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class PartnerApplication(db.Model):
    """Applications from the Become a Partner page.

    Kept separate from Subscriber on purpose: an applicant is a prospective
    collaborator, not a site subscriber, and mixing the two would put partner
    leads into the marketing list and the newsletter.
    """
    __tablename__ = 'partner_application'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(255), nullable=False)
    company = db.Column(db.String(200), default='')
    role = db.Column(db.String(150), default='')
    portfolio = db.Column(db.String(500), default='')
    collaboration_type = db.Column(db.String(50), default='')
    expertise = db.Column(db.String(300), default='')
    message = db.Column(db.Text, default='')
    status = db.Column(db.String(20), default='new')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# Review states for an application. Internal values only; the admin label is
# derived from these so an arbitrary submitted string can never be persisted.
PARTNER_APPLICATION_STATUSES = [
    ('new', 'New'),
    ('reviewing', 'Reviewing'),
    ('replied', 'Replied'),
    ('archived', 'Archived'),
]
PARTNER_APPLICATION_STATUS_VALUES = {value for value, _ in PARTNER_APPLICATION_STATUSES}

class Enquiry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), default='')
    business = db.Column(db.String(200), default='')
    email = db.Column(db.String(255), default='')
    project_type = db.Column(db.String(100), default='')
    budget = db.Column(db.String(100), default='')
    message = db.Column(db.Text, default='')
    ip_address = db.Column(db.String(45), default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# ===== HELPERS =====

_geo_cache = {}
_GEO_CACHE_MAX = 5000


def get_client_ip():
    return request.remote_addr


def _geo_cache_put(ip, value):
    """Insert into the geo cache, evicting the oldest key once it is full.

    This dict used to grow for the lifetime of the worker, keyed by IP, with no
    upper bound. On a long-lived process that is an unbounded memory leak driven
    by hostile traffic, since every distinct address gets its own entry.
    """
    if len(_geo_cache) >= _GEO_CACHE_MAX:
        # dicts preserve insertion order, so the first key is the oldest.
        _geo_cache.pop(next(iter(_geo_cache)), None)
    _geo_cache[ip] = value


def lookup_location(ip):
    if not ip or ip in ('127.0.0.1', '::1', 'localhost'):
        return None
    if ip in _geo_cache:
        return _geo_cache[ip]
    result = None
    try:
        # https, not http: this is analytics-only data, so there is no reason to
        # hand a third party a plaintext request and to trust the reply.
        r = requests.get(f'https://ip-api.com/json/{ip}?fields=status,country,city,query', timeout=2)
        if r.status_code == 200:
            data = r.json()
            # `fail`/`private` come back HTTP 200 with status set and no country.
            if data.get('status') == 'success' and data.get('country'):
                result = {'country': data['country'], 'city': data.get('city', '')}
    except Exception:
        # Geolocation is decorative; never let it affect the caller.
        pass
    # Failures are cached too, so a slow third party costs one timeout per IP
    # rather than one per request.
    _geo_cache_put(ip, result)
    return result

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def _csv_cell(value):
    """Neutralise spreadsheet formula injection in an exported CSV cell.

    Excel, LibreOffice and Google Sheets all treat a cell whose first character
    is `=`, `+`, `-` or `@` as a formula to evaluate. Every export here contains
    fields that are filled in by an unauthenticated visitor -- partner
    applications and subscribers in particular -- so an attacker who submits a
    name of `=cmd|'/c calc'!A1` gets that string written into the file an admin
    later opens, and it executes with the admin's privileges rather than the
    attacker's. Prefixing with an apostrophe is the standard mitigation: the
    cell still reads as the original text, and spreadsheets treat it as a
    literal.
    """
    if value is None:
        return ''
    if isinstance(value, (datetime,)):
        return value
    if isinstance(value, (int, float, bool)):
        return value
    text = str(value)
    if text[:1] in ('=', '+', '-', '@', '\t', '\r'):
        return "'" + text
    return text


def _csv_writer(output):
    # QUOTE_ALL so no submitted value can break out of its column by containing
    # a comma, quote or newline. Note that this alone is *not* the fix for
    # formula injection -- see _csv_cell.
    return csv.writer(output, quoting=csv.QUOTE_ALL)


def upload_image(file):
    if not file or not file.filename:
        return ''
    if not allowed_file(file.filename):
        return ''
    filename = secure_filename(f"{datetime.now().timestamp()}_{file.filename}")
    saved_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)

    if filename.rsplit('.', 1)[-1].lower() == 'svg':
        # Check the bytes, not the extension: `logo.svg` is a text file, and
        # anything it contains is what a browser will execute if it is opened.
        # Rejecting here is the only point before the file is already live on
        # disk and reachable at /static/uploads/.
        try:
            with file.stream as stream:
                raw = stream.read(1024 * 512)
        except Exception:
            return ''
        cleaned = sanitize_svg(raw)
        if cleaned is None:
            app.logger.warning('UPLOAD refused svg with active content: %s',
                               file.filename)
            return ''
        with open(saved_path, 'w', encoding='utf-8') as handle:
            handle.write(cleaned)
    else:
        file.save(saved_path)

    if _cloudinary_url:
        prev_timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(30)
        try:
            ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
            params = {'folder': 'portfolio'}
            if ext in VIDEO_EXTENSIONS:
                params['resource_type'] = 'video'
            result = cloudinary.uploader.upload(saved_path, **params)
            app.logger.info('UPLOAD Cloudinary success for %s', filename)
            return result['secure_url']
        except Exception as exc:
            app.logger.warning('UPLOAD Cloudinary failed for %s: %s: %s',
                               filename, type(exc).__name__, exc)
        finally:
            socket.setdefaulttimeout(prev_timeout)
    else:
        app.logger.info('UPLOAD no CLOUDINARY_URL set, saving locally: %s', filename)
    return filename

def get_image_url(image_filename):
    if not image_filename:
        return ''
    if image_filename.startswith(('http://', 'https://')):
        return image_filename
    return url_for('static', filename='uploads/' + image_filename)

def delete_image(image_filename):
    if not image_filename:
        return
    if image_filename.startswith(('http://', 'https://')):
        if _cloudinary_url and 'cloudinary' in image_filename:
            try:
                public_id = image_filename.split('/portfolio/')[-1].rsplit('.', 1)[0]
                resource_type = 'video' if '/video/' in image_filename else 'image'
                cloudinary.uploader.destroy(f'portfolio/{public_id}', resource_type=resource_type)
            except Exception:
                pass
        return
    path = os.path.join(app.config['UPLOAD_FOLDER'], image_filename)
    if os.path.exists(path):
        os.remove(path)

def admin_required(f):
    """Gate a route on a live admin account.

    The presence of `admin_id` in the signed session cookie was the whole
    check, so an admin who was deleted, or had their password changed by
    someone else, stayed fully authorised until the cookie expired. The session
    cookie has no server-side lifetime, which means up to a year by default. The
    user row is therefore re-read on every admin request: that is one indexed
    primary-key lookup, and it is what makes deleting an admin account actually
    revoke access.

    Admin JSON endpoints answer 401 with JSON. They previously answered 302 to
    the login page, so a fetch in the browser's console got HTML where it
    expected an object and died on a parse error instead of reporting 401.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'admin_id' not in session:
            if _wants_json():
                return jsonify({'error': 'Authentication required'}), 401
            flash('Please log in first.', 'error')
            return redirect(url_for('admin_login'))
        try:
            user = db.session.get(User, session['admin_id'])
        except Exception:
            db.session.rollback()
            user = None
        if user is None:
            session.pop('admin_id', None)
            session.pop('admin_username', None)
            app.logger.info('ADMIN rejected stale session for id=%s', session.get('admin_id'))
            if _wants_json():
                return jsonify({'error': 'Authentication required'}), 401
            flash('Your session is no longer valid. Please log in again.', 'error')
            return redirect(url_for('admin_login'))
        session['admin_username'] = user.username
        return f(*args, **kwargs)
    return decorated


def _wants_json():
    """True when the caller is an admin API client rather than a browser page."""
    return (
        request.path.startswith('/admin/api/')
        or request.accept_mimetypes.best_match(['application/json', 'text/html'])
           == 'application/json'
    )

def _get_setting(key, default=None):
    s = SiteSetting.query.filter_by(key=key).first()
    return s.value if s else default

def get_github_projects():
    try:
        r = requests.get('https://api.github.com/users/echoesrule/repos?sort=updated&per_page=20', timeout=5)
        if r.status_code != 200:
            return []
        repos = r.json()
        if not isinstance(repos, list):
            return []
        projects = []
        for repo in repos:
            if repo.get('fork'):
                continue
            tags = []
            if repo.get('language'):
                tags.append(repo['language'])
            tags.extend(repo.get('topics', [])[:4])
            projects.append({
                'title': repo['name'].replace('-', ' ').replace('_', ' ').title(),
                'description': repo.get('description') or 'No description provided.',
                'tags': tags or ['N/A'],
                'github': repo['html_url'],
                'image': repo['owner']['avatar_url']
            })
        return projects[:6]
    except Exception:
        return []

def get_projects(category=None):
    q = Project.query.filter_by(visible=True).order_by(Project.sort_order, Project.created_at.desc())
    if category:
        q = q.filter_by(category=category)
    db_projects = q.all()
    if db_projects:
        return [{
            'title': p.title,
            'description': p.description or 'No description provided.',
            'tags': p.tag_list(),
            'github': p.github_url or '#',
            'demo_url': p.demo_url or '',
            'image': get_image_url(p.image_filename),
            'id': p.id,
            'category': p.category,
            'status': clean_project_status(p.status),
            'status_label': PROJECT_STATUS_LABELS.get(clean_project_status(p.status), '')
        } for p in db_projects]
    if Project.query.count() == 0:
        return get_github_projects()
    return []

def get_github_stats():
    try:
        r = requests.get('https://api.github.com/users/echoesrule', timeout=5)
        if r.status_code != 200:
            return None
        data = r.json()
        return {'public_repos': data.get('public_repos', 0), 'followers': data.get('followers', 0)}
    except Exception:
        return None

ENQUIRY_CSV_HEADER = ['Date', 'Name', 'Business', 'Email', 'Project Type', 'Budget', 'IP', 'Message']

def _csv_safe(value):
    """Flatten a value to one line and neutralise spreadsheet formula injection."""
    text = '' if value is None else str(value)
    text = re.sub(r'\s+', ' ', text).strip()
    if text[:1] in ('=', '+', '-', '@', '\t', '\r'):
        text = "'" + text
    return text

def build_enquiries_csv():
    """Cumulative CSV of every enquiry received so far, oldest first."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(ENQUIRY_CSV_HEADER)
    for e in Enquiry.query.order_by(Enquiry.created_at.asc(), Enquiry.id.asc()).all():
        writer.writerow([
            e.created_at.strftime('%Y-%m-%d %H:%M UTC') if e.created_at else '',
            _csv_safe(e.name),
            _csv_safe(e.business),
            _csv_safe(e.email),
            _csv_safe(e.project_type),
            _csv_safe(e.budget),
            _csv_safe(e.ip_address),
            _csv_safe(e.message),
        ])
    output.seek(0)
    return output.getvalue()

def enquiries_csv_attachment():
    """Brevo attachment payload for the cumulative enquiry CSV, or None if unavailable."""
    try:
        content = build_enquiries_csv()
    except Exception:
        app.logger.exception('Enquiry CSV build failed: sending alert without attachment.')
        return None
    return {
        'name': f"retec-enquiries-{datetime.utcnow().strftime('%Y-%m-%d')}.csv",
        'content': base64.b64encode(content.encode('utf-8')).decode('ascii'),
    }

def send_email(name, email, business, project_type, budget, message, ip_address=''):
    api_key = app.config['BREVO_API_KEY']
    if not api_key or not app.config['MAIL_FROM'] or not app.config['MAIL_TO']:
        app.logger.warning('Contact email skipped: BREVO_API_KEY or sender/recipient not configured.')
        return False
    try:
        timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')
        body = (
            f"New RETEC project inquiry\n\n"
            f"Name: {name}\n"
            f"Business / Organization: {business or 'N/A'}\n"
            f"Email: {email}\n"
            f"Project Type: {project_type or 'Not specified'}\n"
            f"Budget: {budget or 'Not specified'}\n"
            f"IP: {ip_address}\n"
            f"Time: {timestamp}\n\n"
            f"Project Details:\n{message}"
        )
        payload = {
            'sender': {'email': app.config['MAIL_FROM']},
            'to': [{'email': app.config['MAIL_TO']}],
            'replyTo': {'email': email},
            'subject': f"Project Inquiry: {(project_type or 'General')[:80]}",
            'textContent': body,
        }
        attachment = enquiries_csv_attachment()
        if attachment:
            payload['attachment'] = [attachment]
        resp = requests.post(
            'https://api.brevo.com/v3/smtp/email',
            headers={'api-key': api_key, 'Content-Type': 'application/json'},
            json=payload,
            timeout=15,
        )
        if resp.ok:
            return True
        app.logger.error('Brevo contact email error %s: %s', resp.status_code, resp.text)
        return False
    except Exception as exc:
        app.logger.exception('Contact email failed: %s', exc)
        return False

def send_sms_notification(name, email, business, project_type, budget, message):
    """SMS the studio when a project inquiry is submitted.

    NOT CALLED. The contact route now sends an email with a cumulative enquiry
    CSV attached (see `enquiries_csv_attachment`) instead. Retained so SMS can be
    restored by re-adding a single call in `contact()`. While unused, the
    SMS_NOTIFY_TO / SMS_SENDER config has no effect.

    Uses Brevo transactional SMS (same BREVO_API_KEY as email). Pay-per-SMS
    via Brevo SMS credits; SMS credits must be enabled on the account. Fails
    soft (logs only) so a failure never blocks the inquiry. `sender` is the
    alphanumeric sender name shown to the recipient (max 11 chars),
    `recipient` must be in international format with country code, digits only.
    """
    api_key = app.config['BREVO_API_KEY']
    recipient = app.config.get('SMS_NOTIFY_TO', '')
    sender = app.config.get('SMS_SENDER', 'RETEC')
    if not api_key or not recipient:
        app.logger.warning('SMS notification skipped: set SMS_NOTIFY_TO.')
        return False
    try:
        content = (
            f"New RETEC inquiry\n"
            f"{name} | {business or 'N/A'}\n"
            f"{email}\n"
            f"{project_type or 'General'} | {budget or 'N/A'}\n"
            f"Msg: {message[:80]}"
        )
        resp = requests.post(
            'https://api.brevo.com/v3/transactionalSMS/send',
            headers={'api-key': api_key, 'Content-Type': 'application/json', 'Accept': 'application/json'},
            json={
                'sender': sender,
                'recipient': recipient,
                'content': content,
                'type': 'transactional',
                'unicodeEnabled': False,
                'tag': 'inquiry',
            },
            timeout=15,
        )
        if resp.ok:
            app.logger.info('SMS inquiry notification sent (messageId %s)', resp.json().get('messageId', '?'))
            return True
        app.logger.error('Brevo SMS API error %s: %s', resp.status_code, resp.text[:500])
        return False
    except Exception as exc:
        app.logger.exception('SMS notification failed: %s', exc)
        return False

def send_partner_application(application):
    """Email a partner application to the studio.

    Mirrors send_email() so both public forms use the same Brevo transport.
    `application` is a persisted PartnerApplication row, which is written
    before this is called: the database is the record of truth and the email is
    only the alert, so a mail failure never loses an application.
    """
    api_key = app.config['BREVO_API_KEY']
    if not api_key or not app.config['MAIL_FROM'] or not app.config['MAIL_TO']:
        app.logger.warning('Partner email skipped: BREVO_API_KEY or sender/recipient not configured.')
        return False
    try:
        body = (
            f"New RETEC partner application\n\n"
            f"Name: {application.name}\n"
            f"Email: {application.email}\n"
            f"Company / Studio: {application.company or 'N/A'}\n"
            f"Role / Specialty: {application.role or 'N/A'}\n"
            f"Collaboration Type: {application.collaboration_type or 'Not specified'}\n"
            f"Website / Portfolio: {application.portfolio or 'N/A'}\n"
            f"Areas of Expertise: {application.expertise or 'N/A'}\n"
            f"Received: {application.created_at.strftime('%Y-%m-%d %H:%M UTC')}\n\n"
            f"About them:\n{application.message}"
        )
        resp = requests.post(
            'https://api.brevo.com/v3/smtp/email',
            headers={'api-key': api_key, 'Content-Type': 'application/json'},
            json={
                'sender': {'email': app.config['MAIL_FROM']},
                'to': [{'email': app.config['MAIL_TO']}],
                'replyTo': {'email': application.email},
                'subject': f"Partner Application: {(application.collaboration_type or 'General')[:80]}",
                'textContent': body,
            },
            timeout=15,
        )
        if resp.ok:
            return True
        app.logger.error('Brevo partner email error %s: %s', resp.status_code, resp.text)
        return False
    except Exception as exc:
        app.logger.exception('Partner email failed: %s', exc)
        return False

def send_verification_code(email, code):
    if not email:
        app.logger.warning('Verification email skipped: no recipient email.')
        return False
    api_key = app.config['BREVO_API_KEY']
    if not api_key:
        app.logger.warning('Verification email skipped: BREVO_API_KEY not configured.')
        return False
    try:
        resp = requests.post(
            'https://api.brevo.com/v3/smtp/email',
            headers={
                'api-key': api_key,
                'Content-Type': 'application/json',
            },
            json={
                'sender': {'email': app.config['MAIL_FROM'] or email},
                'to': [{'email': email}],
                'subject': 'Your Retec Admin Verification Code',
                'textContent': (
                    f"Your Retec admin verification code is: {code}\n\n"
                    f"This code will expire in 10 minutes.\n\n"
                    f"If you did not request this, please ignore this email."
                ),
            },
            timeout=15,
        )
        if resp.ok:
            return True
        app.logger.error('Brevo API error %s: %s', resp.status_code, resp.text)
        return False
    except Exception as exc:
        app.logger.exception('Verification email failed: %s', exc)
        return False

def send_broadcast(subject, html_content, test_email=None):
    """Send a broadcast through Brevo's transactional API.

    This runs inside an admin request, one synchronous HTTP POST per subscriber
    with a 15s timeout each. Against a list of a few hundred, that is several
    minutes of work in a request thread -- past Render's 30s request timeout,
    which means gunicorn kills the worker mid-send and the list is delivered
    part-way with no record of where it stopped.

    Two changes bound that. Recipients go out in parallel with a thread pool
    rather than one after another, and the whole thing stops at a wall-clock
    budget (BREVO_BROADCAST_BUDGET_SECONDS, 25s by default, deliberately under
    the platform request limit) so the worker is always released cleanly.
    Whatever was not attempted is reported back explicitly rather than silently
    dropped, so the admin knows to send the remainder.
    """
    api_key = app.config['BREVO_API_KEY']
    broadcast_from = app.config.get('MAIL_FROM', 'contact.retec@gmail.com')
    if not api_key:
        return False, "BREVO_API_KEY not configured."

    if test_email:
        # Validate the test recipient rather than forwarding whatever was typed
        # into the form straight to the API.
        candidate = str(test_email).strip().lower()
        if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]{2,}$', candidate):
            return False, "That test email address is not valid."
        targets = [{'email': candidate, 'name': 'Test'}]
    else:
        targets = Subscriber.query.filter_by(active=True).all()
        if not targets:
            return False, "No active subscribers."

    budget = clean_env_int(os.environ.get('BREVO_BROADCAST_BUDGET_SECONDS'), 25, low=5, high=120)
    deadline = time.monotonic() + budget
    totals = {'sent': 0, 'failed': 0, 'skipped': 0}
    lock = threading.Lock()

    def deliver(target):
        email = target['email'] if isinstance(target, dict) else target.email
        name = ((target.get('name', '') if isinstance(target, dict) else (target.name or '')) or '')
        if time.monotonic() >= deadline:
            with lock:
                totals['skipped'] += 1
            return
        try:
            greeting = "Hi %s," % (name or 'there')
            unsub = url_for('unsubscribe', email=email, _external=True)
            html = render_template(
                'email/broadcast.html',
                content="<p>%s</p>%s" % (escape(greeting), html_content),
                unsubscribe_url=unsub)

            resp = requests.post(
                'https://api.brevo.com/v3/smtp/email',
                headers={'api-key': api_key, 'Content-Type': 'application/json'},
                json={
                    'sender': {'email': broadcast_from, 'name': 'RETEC'},
                    'to': [{'email': email}],
                    'subject': subject,
                    'htmlContent': html,
                    'textContent': f"View this email in a browser that supports HTML.\n\nSubject: {subject}",
                },
                timeout=10,
            )
            with lock:
                if resp.ok:
                    totals['sent'] += 1
                else:
                    totals['failed'] += 1
                    app.logger.error('Brevo broadcast error %s to %s: %s',
                                     resp.status_code, email, resp.text)
        except Exception:
            with lock:
                totals['failed'] += 1
            app.logger.exception('Broadcast email failed to %s', email)

    workers = clean_env_int(os.environ.get('BREVO_BROADCAST_WORKERS'), 8, low=1, high=32)
    with ThreadPoolExecutor(max_workers=workers,
                            thread_name_prefix='retec-broadcast') as pool:
        # Submit everything, but each task re-checks the deadline before doing
        # any network work, so queued recipients are skipped rather than started
        # and abandoned when the budget runs out.
        list(pool.map(deliver, targets))

    summary = "Sent: %d, Failed: %d" % (totals['sent'], totals['failed'])
    if totals['skipped']:
        summary += ", Not sent (time limit): %d" % totals['skipped']
        app.logger.warning('Broadcast stopped at the %ds budget with %d recipient(s) '
                           'unsent', budget, totals['skipped'])
    return True, summary

@app.route('/unsubscribe')
def unsubscribe():
    email = request.args.get('email', '').strip().lower()
    if email:
        sub = Subscriber.query.filter_by(email=email).first()
        if sub:
            sub.active = False
            db.session.commit()
            flash('You have been unsubscribed.', 'info')
    return redirect(url_for('home'))

@app.route('/admin/broadcast', methods=['GET', 'POST'])
@admin_required
def admin_broadcast():
    result = None
    if request.method == 'POST':
        subject = request.form.get('subject', '').strip()
        content = request.form.get('content', '').strip()
        test = request.form.get('test_email', '').strip()
        if not subject or not content:
            flash('Subject and content are required.', 'error')
        else:
            ok, msg = send_broadcast(subject, content, test_email=test or None)
            if ok:
                flash(f'Broadcast sent. {msg}', 'success')
            else:
                flash(f'Failed: {msg}', 'error')
        return redirect(url_for('admin_broadcast'))
    subscriber_count = Subscriber.query.filter_by(active=True).count()
    return render_template('admin/broadcast.html', subscriber_count=subscriber_count)

def get_email_domain(email: str) -> str | None:
    email = email.strip().lower()

    if not email or "@" not in email:
        return None

    local, domain = email.rsplit("@", 1)

    if not local or not domain:
        return None

    return domain.rstrip(".")


def is_disposable_email(email: str) -> bool:
    domain = get_email_domain(email)
    return domain is not None and domain in DISPOSABLE_DOMAINS

def check_mx_record(domain):
    try:
        import socket
        socket.getaddrinfo(domain, 25, socket.AF_INET, socket.SOCK_STREAM)
        return True
    except Exception:
        return False

BIG_PROVIDERS = {'gmail.com', 'yahoo.com', 'outlook.com', 'hotmail.com', 'aol.com', 'icloud.com', 'protonmail.com', 'mail.com'}

def smtp_verify(email, timeout=5):
    domain = get_email_domain(email)
    if domain is None:
        return None
    if domain in BIG_PROVIDERS:
        return None
    try:
        import dns.resolver
        answers = dns.resolver.resolve(domain, 'MX')
        mx_host = str(sorted(answers, key=lambda r: r.preference)[0].exchange).rstrip('.')
    except Exception:
        return None
    try:
        import smtplib
        sock = smtplib.SMTP(timeout=timeout)
        sock.connect(mx_host, 25)
        sock.ehlo_or_helo_if_needed()
        sock.mail('check@example.com')
        code, _ = sock.rcpt(email)
        sock.quit()
        return code == 250
    except Exception:
        return None

def verify_email_api(email):
    api_key = app.config['ZEROBOUNCE_API_KEY']
    if not api_key:
        return None
    try:
        resp = requests.get(
            'https://api.zerobounce.net/v2/validate',
            params={'api_key': api_key, 'email': email},
            timeout=10
        )
        data = resp.json()
        status = data.get('status', '')  # Valid, Invalid, Catch-All, Unknown, do_not_mail
        sub_status = data.get('sub_status', '')
        if status == 'Valid':
            return True
        if status == 'do_not_mail' and sub_status in ('role_based', 'disposable'):
            return False
        if status == 'Invalid':
            return False
        return None
    except Exception:
        return None

def is_valid_email(email):
    if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email or ''):
        return False
    if is_disposable_email(email):
        return False
    return True

def sync_brevo_contact(email, name=''):
    api_key = app.config['BREVO_API_KEY']
    list_id = app.config['BREVO_LIST_ID']
    if not api_key or not list_id:
        app.logger.info('Brevo sync skipped: BREVO_API_KEY or BREVO_LIST_ID is missing.')
        return False
    try:
        payload = {
            'email': email,
            'attributes': {'FIRSTNAME': name} if name else {},
            'listIds': [int(list_id)],
            'updateEnabled': True
        }
        response = requests.post(
            'https://api.brevo.com/v3/contacts',
            headers={
                'accept': 'application/json',
                'api-key': api_key,
                'content-type': 'application/json'
            },
            json=payload,
            timeout=15
        )
        if response.status_code in (200, 201, 204):
            return True
        app.logger.warning('Brevo sync failed with status %s: %s', response.status_code, response.text[:500])
    except Exception as exc:
        app.logger.exception('Brevo sync failed: %s', exc)
    return False

def save_subscriber(email, name='', source='website'):
    email = (email or '').strip().lower()
    name = (name or '').strip()
    if not is_valid_email(email):
        return None, False

    subscriber = Subscriber.query.filter_by(email=email).first()
    created = subscriber is None
    if created:
        subscriber = Subscriber(email=email, name=name, source=source)
        db.session.add(subscriber)
    else:
        if name and not subscriber.name:
            subscriber.name = name
        subscriber.active = True

    if not subscriber.validated:
        api_result = verify_email_api(email)
        if api_result is True:
            subscriber.validated = True
        elif api_result is None:
            smtp_result = smtp_verify(email)
            if smtp_result is True:
                subscriber.validated = True
            elif smtp_result is None:
                domain = get_email_domain(email)
                if domain and check_mx_record(domain):
                    subscriber.validated = True

    synced = sync_brevo_contact(email, name or subscriber.name)
    subscriber.brevo_synced = subscriber.brevo_synced or synced
    db.session.commit()
    return subscriber, created

def slugify(text):
    text = (text or '').lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[-\s]+', '-', text).strip('-')
    return text[:180]


def unique_slug(title, exclude_id=None):
    """A slug that is unique across the Journal.

    Collisions are common here: syndicated headlines repeat, and an admin can
    easily reuse a wordmark. The numeric suffix keeps the URL stable and
    readable instead of failing the save.
    """
    base = slugify(title) or 'journal-article'
    candidate, suffix = base, 2
    while True:
        query = JournalArticle.query.filter_by(slug=candidate)
        if exclude_id is not None:
            query = query.filter(JournalArticle.id != exclude_id)
        if query.first() is None:
            return candidate
        candidate = '%s-%d' % (base, suffix)
        suffix += 1


# ===== JOURNAL: NEWS INGESTION PIPELINE =====
#
#   fetch -> validate -> normalise -> deduplicate -> DRAFT -> admin review
#
# The hard rule this section exists to enforce: nothing here can set an
# article's status to `published`. `run_journal_ingestion` writes `new` and
# returns; promoting a story is an explicit, authenticated admin action.


def _dedupe_reason_for(item):
    """Why ``item`` is already in the Journal, or '' when it is new.

    Checked strongest-first: the source's own identifier, then the canonical
    URL, then the headline. The title scan is bounded to recent fetches so the
    cost per item stays flat as the archive grows.
    """
    if item.external_id:
        row = JournalArticle.query.filter(
            JournalArticle.external_id == item.external_id,
            JournalArticle.source_record_id.isnot(None),
        ).first()
        if row is not None:
            return 'external id %s' % item.external_id

    fingerprint = journal.url_fingerprint(item.url)
    if fingerprint:
        row = JournalArticle.query.filter_by(url_fingerprint=fingerprint).first()
        if row is not None:
            return 'already fetched from %s' % (row.source_name or 'another source')
        row = JournalArticle.query.filter(
            JournalArticle.canonical_url == journal.normalise_url(item.url)
        ).first()
        if row is not None:
            return 'already fetched from %s' % (row.source_name or 'another source')

    title_key = journal.title_fingerprint(item.title)
    if title_key:
        row = JournalArticle.query.filter_by(title_fingerprint=title_key).first()
        if row is not None:
            return 'matching headline already fetched (%s)' % (row.source_name or 'another source')
        since = datetime.utcnow() - timedelta(days=journal.DEDUPE_WINDOW_DAYS)
        candidates = JournalArticle.query.filter(
            JournalArticle.original_title != '',
            JournalArticle.fetched_at >= since,
        ).order_by(JournalArticle.fetched_at.desc()).limit(
            journal.DEDUPE_TITLE_CANDIDATES).all()
        for candidate in candidates:
            if journal.titles_match(candidate.original_title or '', item.title):
                return 'near-identical headline already fetched (%s)' % (
                    candidate.source_name or 'another source')
    return ''


def _build_draft_from_item(item, source, ai_editor=None):
    """Create one unpublished Brief draft, or return ``(None, reason)``.

    Nothing from the source body is copied: the draft starts from the
    normalised metadata, and if AI drafting is configured and succeeds it is
    the model's own analysis of that metadata, not the publisher's article.
    """
    reason = _dedupe_reason_for(item)
    if reason:
        return None, reason

    now = datetime.utcnow()
    draft_body = ''
    headline = item.title
    excerpt = item.excerpt
    ai_used = False

    if ai_editor is not None and ai_editor.enabled:
        proposal = ai_editor.draft(item, source_name=source.name)
        if proposal:
            draft_body = journal.compose_brief_body(proposal['sections'], fallback_excerpt=item.excerpt)
            headline = proposal['headline'] or item.title
            excerpt = proposal['excerpt'] or item.excerpt
            ai_used = True

    if not draft_body:
        # No AI configured, or the call failed. The draft still exists so the
        # story is in the queue rather than lost; the admin writes it up.
        draft_body = (
            '<p><em>Awaiting editorial drafting. RETEC has not yet written '
            'this story up — read the original source, then replace this '
            'placeholder with the Brief.</em></p>'
        )

    article = JournalArticle(
        title=headline[:200],
        slug=unique_slug(headline),
        summary=excerpt[:500],
        content=draft_body,
        content_type='brief',
        category=_journal_category_from_source(source.category),
        status='new',
        published=False,
        published_at=None,
        # Source attribution. Required for any Brief we publish.
        source_name=source.name,
        source_url=item.url,
        source_published_at=item.published_at,
        # Ingestion bookkeeping for de-duplication and provenance.
        external_id=item.external_id or None,
        canonical_url=journal.normalise_url(item.url) or None,
        url_fingerprint=journal.url_fingerprint(item.url) or None,
        title_fingerprint=journal.title_fingerprint(item.title) or None,
        original_title=item.title,
        original_excerpt=item.excerpt,
        image_url=item.image_url or '',
        fetched_at=now,
        source_record_id=source.id,
        ai_generated=ai_used,
        reading_time=journal.estimate_reading_time(draft_body),
    )
    db.session.add(article)
    return article, ''


def _fetch_one_source(source, trigger='schedule', ai_editor=None,
                      max_drafts=JOURNAL_MAX_DRAFTS_PER_SOURCE):
    """Fetch a single source and turn its new stories into drafts.

    Never raises: a broken feed is recorded against the source and the run
    moves on, so one bad URL cannot stop the other fifteen.
    """
    run = NewsFetchRun(source_id=source.id, trigger=trigger, started_at=datetime.utcnow())
    db.session.add(run)
    source.last_fetched_at = run.started_at
    created, duplicates, generated = 0, 0, 0

    try:
        payload = journal.fetch_feed(source.feed_url)
        items = journal.parse_feed(payload, source_url=source.feed_url)
        run.entries_seen = len(items)
    except journal.FeedError as exc:
        run.ok = False
        run.error = str(exc)[:1000]
        run.finished_at = datetime.utcnow()
        source.last_status = 'error'
        source.last_error = run.error
        source.consecutive_failures = (source.consecutive_failures or 0) + 1
        db.session.commit()
        app.logger.warning('JOURNAL source %r failed: %s', source.name, run.error)
        return run
    except Exception as exc:  # unexpected: still must not kill the pipeline
        run.ok = False
        run.error = 'unexpected %s: %s' % (type(exc).__name__, str(exc)[:200])
        run.finished_at = datetime.utcnow()
        source.last_status = 'error'
        source.last_error = run.error
        source.consecutive_failures = (source.consecutive_failures or 0) + 1
        db.session.commit()
        app.logger.exception('JOURNAL source %r raised', source.name)
        return run

    for item in items:
        if created >= max_drafts:
            break
        try:
            article, reason = _build_draft_from_item(item, source, ai_editor)
            if article is None:
                duplicates += 1
                continue
            created += 1
            if article.ai_generated:
                generated += 1
        except Exception as exc:
            # Roll back just this item so a bad entry cannot poison the rest.
            db.session.rollback()
            duplicates += 1
            app.logger.warning('JOURNAL skipping entry from %r: %s: %s',
                               source.name, type(exc).__name__, exc)

    source.last_status = 'ok'
    source.last_error = ''
    source.last_success_at = datetime.utcnow()
    source.consecutive_failures = 0
    source.articles_created = (source.articles_created or 0) + created
    run.ok = True
    run.drafts_created = created
    run.duplicates_skipped = duplicates
    run.drafts_generated = generated
    run.finished_at = datetime.utcnow()
    db.session.commit()
    app.logger.info('JOURNAL %s: %d entries, %d drafts, %d duplicates, %d AI-written',
                    source.name, run.entries_seen, created, duplicates, generated)
    return run


def run_journal_ingestion(source_ids=None, trigger='manual', generate_ai=True):
    """Fetch every active source (or the given ones) and create drafts.

    Returns a summary dict. The return value is for the admin UI and the log;
    it is never used to publish anything.
    """
    query = NewsSource.query.filter_by(is_active=True)
    if source_ids:
        query = query.filter(NewsSource.id.in_(source_ids))
    sources = query.order_by(NewsSource.category, NewsSource.name).all()

    ai_editor = journal.AiEditor() if (generate_ai and JOURNAL_AI_ENABLED) else None
    if generate_ai and JOURNAL_AI_ENABLED and not (ai_editor and ai_editor.enabled):
        ai_editor = None

    summary = {
        'sources': len(sources), 'entries': 0, 'created': 0, 'duplicates': 0,
        'generated': 0, 'failures': [],
    }
    for source in sources:
        try:
            run = _fetch_one_source(source, trigger=trigger, ai_editor=ai_editor)
        except Exception as exc:
            # Belt and braces: _fetch_one_source already contains its own
            # failures, so reaching here means a database-level problem.
            db.session.rollback()
            summary['failures'].append('%s: %s' % (source.name, type(exc).__name__))
            continue
        summary['entries'] += run.entries_seen or 0
        summary['created'] += run.drafts_created or 0
        summary['duplicates'] += run.duplicates_skipped or 0
        summary['generated'] += run.drafts_generated or 0
        if not run.ok and run.error:
            summary['failures'].append('%s: %s' % (source.name, run.error))
    return summary


def regenerate_article_draft(article):
    """Re-run AI drafting for one article, in place.

    Only ever rewrites the body of a draft. An article that has already been
    published, rejected or archived is left alone unless an admin explicitly
    moves it back to `draft` first, so published copy is never rewritten
    underneath readers.
    """
    if article.status not in ('new', 'draft', 'review', 'rejected'):
        return False, 'Only an unapproved draft can be rewritten automatically.'
    editor = journal.AiEditor()
    if not editor.enabled:
        return False, 'No AI drafting key is configured on this server.'
    if not article.source_url:
        return False, 'This article has no external source to draft from.'

    item = journal.FeedItem(
        external_id=article.external_id or '',
        url=article.source_url,
        title=article.original_title or article.title,
        excerpt=article.original_excerpt or article.summary,
        published_at=article.source_published_at,
    )
    proposal = editor.draft(item, source_name=article.source_name or '')
    if not proposal:
        return False, 'The drafting request did not return a usable draft.'

    body = journal.compose_brief_body(proposal['sections'], fallback_excerpt=item.excerpt)
    article.content = body
    article.title = (proposal['headline'] or article.title)[:200]
    article.summary = (proposal['excerpt'] or article.summary)[:500]
    article.reading_time = journal.estimate_reading_time(body)
    article.ai_generated = True
    # Re-drafting returns the article to the queue. It is never published.
    if article.status in ('rejected', 'review'):
        article.status = 'new'
        article.published = False
    article.updated_at = datetime.utcnow()
    db.session.commit()
    return True, 'Editorial draft regenerated. Review it before publishing.'


# ===== JOURNAL: SCHEDULING =====
#
# There is no scheduler process in this project and none is being added. The
# Journal piggybacks on the web app: a request that arrives after the interval
# has elapsed claims the current time bucket with a uniquely-indexed row and
# does the fetch on a background thread. That means:
#
#   * no new dependency, no new service, no cron to keep alive;
#   * on a sleeping host the Journal simply catches up on the first request;
#   * two workers waking together cannot both fetch, because the second one's
#     slot insert violates the unique index;
#   * a run that raises rolls its slot back, so it is retried next time.
#
# `flask fetch-journal` runs the same code path for anyone who would rather
# drive it from cron.

_journal_tick_lock = threading.Lock()


def _journal_due():
    """The current interval bucket if a fetch is due, else ``None``."""
    if not JOURNAL_SCHEDULER_ENABLED or app.config.get('TESTING'):
        return None
    if JOURNAL_FETCH_INTERVAL_MINUTES <= 0:
        return None
    slot = journal.due_slot(interval_minutes=JOURNAL_FETCH_INTERVAL_MINUTES)
    if slot is None:
        return None
    try:
        # Slot first, on purpose. This runs on the before_request path of every
        # uncached page view for anonymous visitors, and this was the only thing
        # keeping it to a query. Ordering it the other way round meant the
        # source check ran first, so every visit paid two round trips to find
        # out that no fetch was due. The source check is the cheaper thing to
        # skip when the slot has already been claimed.
        if NewsFetchRun.query.filter_by(slot=slot).first() is not None:
            return None
        if not NewsSource.query.filter_by(is_active=True).first():
            return None
    except Exception:
        db.session.rollback()
        return None
    return slot


def _run_scheduled_fetch(slot):
    """Claim the slot, fetch, then record the run. Runs in its own app context.

    The claim is committed on its own so concurrent workers cannot both run the
    same slot, then released again if the pass aborts, so a crash is retried on
    the next request instead of silently skipping the interval.
    """
    with app.app_context():
        try:
            run = NewsFetchRun(slot=slot, trigger='schedule', started_at=datetime.utcnow())
            db.session.add(run)
            db.session.commit()
        except Exception:
            # Slot already claimed by another worker. Nothing to do.
            db.session.rollback()
            return
        try:
            summary = run_journal_ingestion(trigger='schedule')
        except Exception as exc:
            db.session.rollback()
            app.logger.warning('JOURNAL scheduled fetch aborted: %s: %s', type(exc).__name__, exc)
            _release_fetch_slot(slot)
            return
        run.finished_at = datetime.utcnow()
        run.ok = not summary['failures']
        run.entries_seen = summary['entries']
        run.drafts_created = summary['created']
        run.duplicates_skipped = summary['duplicates']
        run.source_id = None
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()


def _release_fetch_slot(slot):
    """Drop a scheduler claim so the interval is retried rather than skipped."""
    with app.app_context():
        try:
            NewsFetchRun.query.filter_by(slot=slot).delete()
            db.session.commit()
        except Exception:
            db.session.rollback()


def journal_scheduler_tick():
    """``before_request`` hook. Cheap when not due; never raises."""
    if not _journal_tick_lock.acquire(blocking=False):
        return
    try:
        slot = _journal_due()
        if not slot:
            return
        if JOURNAL_FETCH_IN_BACKGROUND:
            threading.Thread(
                target=_run_scheduled_fetch, args=(slot,),
                name='retec-journal-fetch', daemon=True,
            ).start()
        else:
            _run_scheduled_fetch(slot)
    except Exception as exc:
        app.logger.warning('JOURNAL scheduler tick failed: %s: %s', type(exc).__name__, exc)
        try:
            db.session.rollback()
        except Exception:
            pass
    finally:
        _journal_tick_lock.release()

services = [
    {
        'name': 'Website Development',
        'icon': 'webdev.png',
        'desc': 'Modern, responsive websites designed around your brand, audience, and business goals.',
        'price': 'From KSh 15,000'
    },
    {
        'name': 'Web Applications',
        'icon': 'webapp.png',
        'desc': 'Custom applications for bookings, dashboards, customer portals, management systems, and other business workflows.',
        'price': 'Custom quote'
    },
    {
        'name': 'Custom Software',
        'icon': 'build.png',
        'desc': 'Python-powered software built around specific business requirements and processes.',
        'price': 'Custom quote'
    },
    {
        'name': 'API & Backend Development',
        'icon': 'python.png',
        'desc': 'Reliable backend systems and APIs that connect applications, services, and data.',
        'price': 'Custom quote'
    },
    {
        'name': 'Website Maintenance',
        'icon': 'shield.png',
        'desc': 'Ongoing updates, fixes, improvements, and technical support for existing websites.',
        'price': 'Quoted per project'
    },
    {
        'name': 'Digital Consulting',
        'icon': 'focus.png',
        'desc': 'Practical guidance on choosing and planning technology before investing in development.',
        'price': 'Quoted per project'
    },
]

process = [
    {'title': 'Discover', 'desc': 'We understand your business, goals, audience, requirements, and the problem you are trying to solve.'},
    {'title': 'Plan', 'desc': 'We define the project scope, functionality, technology, and delivery approach.'},
    {'title': 'Build', 'desc': 'We design and develop the solution while keeping the project practical, maintainable, and focused on its goals.'},
    {'title': 'Launch', 'desc': 'We test, deploy, and prepare the product for real users.'},
    {'title': 'Support', 'desc': 'We can continue improving, maintaining, and supporting the solution after launch.'},
]

# ===== BECOME A PARTNER PAGE CONTENT =====
# Editorial copy for the collaboration page. Held here alongside `services` and
# `process` so the template stays presentational, mirroring how the homepage
# sections are sourced. Deliberately free of invented scale, client counts,
# partner logos or testimonials.

partner_collaborator_types = [
    {
        'name': 'Designers',
        'desc': 'UI/UX, product and visual designers who want serious technical execution for their concepts.',
    },
    {
        'name': 'Developers',
        'desc': 'Frontend, backend, mobile and specialised developers who can contribute to larger builds.',
    },
    {
        'name': 'Creative Studios',
        'desc': 'Branding, creative and production studios that need a technical development partner.',
    },
    {
        'name': 'Marketing Agencies',
        'desc': 'Agencies that need websites, landing pages, applications or custom digital systems for their clients.',
    },
    {
        'name': 'Specialists',
        'desc': 'Photographers, videographers, copywriters, SEO specialists and other professionals who complement digital work.',
    },
    {
        'name': 'Technology Partners',
        'desc': 'People or companies offering services, integrations or technical expertise that extend what RETEC can deliver.',
    },
]

partner_process = [
    {'title': 'Introduce', 'desc': 'Tell us who you are, what you specialise in and the kind of projects you work on.'},
    {'title': 'Align', 'desc': 'We discuss the project, responsibilities, scope, timelines and expectations.'},
    {'title': 'Build', 'desc': 'Each collaborator contributes within their area of expertise while RETEC coordinates the technical and product direction where appropriate.'},
    {'title': 'Deliver', 'desc': 'We work together to deliver a cohesive, professional result for the client.'},
]

partner_reasons = [
    {'title': 'Complementary Skills', 'desc': 'Bring your expertise together with RETEC’s design and development capabilities.'},
    {'title': 'Flexible Collaboration', 'desc': 'Work together on individual projects without requiring a permanent employment relationship.'},
    {'title': 'Clear Responsibilities', 'desc': 'Define scope, deliverables and responsibilities before any work begins.'},
    {'title': 'Quality First', 'desc': 'Maintain a high standard across design, development and delivery.'},
    {'title': 'Long-Term Relationships', 'desc': 'Strong collaborations can develop into recurring project partnerships.'},
]

# ===== CONTEXT PROCESSORS =====

@app.context_processor
def inject_globals():
    fun_facts = FunFact.query.filter_by(active=True).order_by(FunFact.sort_order).all()
    settings = {
        setting.key: setting.value
        for setting in SiteSetting.query.filter(SiteSetting.key.in_([
            'hero_bg_type', 'hero_video', 'hero_image', 'hero_poster',
            'hero_quote_interval', 'cube_positioner_enabled', 'cube_positions',
        ])).all()
    }
    try:
        # request.url carries the query string, so /blog?page=2 and
        # /blog?page=2&category=Foo each declared themselves canonical. Search
        # engines read that as several URLs competing for the same content and
        # pick one arbitrarily. request.base_url is the same URL with the query
        # and fragment stripped, so only parameters that select a genuinely
        # different view are added back.
        meta_url = request.base_url
        keep = {}
        if request.path.rstrip('/') == '/blog':
            # Empty values and page=1 describe the same view as the bare URL, so
            # they are dropped rather than echoed back into the canonical.
            content_type = request.args.get('type', '').strip()
            category = request.args.get('category', '').strip()
            page = request.args.get('page', '').strip()
            if content_type:
                keep['type'] = content_type
            if category:
                keep['category'] = category
            if page and page != '1':
                keep['page'] = page
        if keep:
            meta_url = f"{meta_url}?{urlencode(keep)}"
        meta_image = url_for('static', filename='images/og-default.png', _external=True)
    except RuntimeError:
        meta_url = '/'
        meta_image = ''
    return {
        'year': datetime.now().year,
        'css_version': ASSET_VERSION,
        'fun_facts': fun_facts,
        'fun_fact': fun_facts[0].text if fun_facts else None,
        'meta_title': 'Retec-Biz Yako.Tech Yetu',
        'meta_desc': 'RETEC builds modern websites, web applications, custom software, and digital solutions for businesses, creators, and organizations.',
        'meta_url': meta_url,
        'meta_image': meta_image,
        'get_image_url': get_image_url,
        'hero_bg_type': settings.get('hero_bg_type', 'video'),
        'hero_video_url': get_image_url(settings['hero_video']) if 'hero_video' in settings else url_for('static', filename='hero-bg.mp4'),
        'hero_image_url': get_image_url(settings['hero_image']) if 'hero_image' in settings else 'https://images.unsplash.com/photo-1581091226825-a6a2a5aee158?q=80&w=2670&auto=format&fit=crop',
        'hero_poster_url': get_image_url(settings['hero_poster']) if 'hero_poster' in settings else url_for('static', filename='images/hero-bg.svg'),
        'hero_quote_interval': settings.get('hero_quote_interval', '6000'),
        'cube_positioner_enabled': settings.get('cube_positioner_enabled') == '1' and 'admin_id' in session,
        'cube_positions': _load_cube_positions(settings.get('cube_positions'))
    }


def _load_cube_positions(raw):
    """Parse the stored cube-position JSON, treating anything invalid as absent.

    This setting is read on every homepage render. One bad value -- a truncated
    write, a hand-edited row -- raised out of the context processor and took the
    whole homepage down with a 500, rather than just losing the cube layout.
    """
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        app.logger.warning('Ignoring malformed cube_positions setting (%d bytes)', len(raw))
        return None
    return data if isinstance(data, list) and data else None

def _asset_version():
    """A cache-busting stamp for `?v=` on CSS and JS that only changes on deploy.

    This used to be ``int(datetime.now().timestamp())``, which produced a
    different value on every single render. Every stylesheet and script URL was
    therefore unique per page view, so none of them could ever come out of the
    browser cache. Taking the newest mtime under static/css and static/js means
    the stamp is stable for the life of a deploy and changes exactly when the
    assets do.
    """
    try:
        newest = 0
        for folder in ('css', 'js'):
            root = Path(app.static_folder) / folder
            if root.is_dir():
                for entry in root.rglob('*'):
                    if entry.is_file():
                        newest = max(newest, entry.stat().st_mtime)
        return str(int(newest) or 1)
    except OSError:
        return '1'


ASSET_VERSION = _asset_version()

# Only the hosts RETEC actually loads from are allow-listed. `script-src` needs
# `'unsafe-inline'` because base.html, index.html and most admin templates carry
# inline <script> blocks; that part of the policy is therefore advisory rather
# than enforcing, and it is called out here so nobody mistakes this CSP for XSS
# protection. What it does enforce is the rest of the attack surface: no plugin
# objects, no framing by anyone else, no form posts off-origin, and no script,
# style, font, image or XHR from a host that is not listed here.
CSP_DIRECTIVES = (
    "default-src 'self'",
    "base-uri 'self'",
    "object-src 'none'",
    "frame-ancestors 'self'",
    "form-action 'self'",
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://unpkg.com",
    "style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://fonts.googleapis.com",
    "font-src 'self' data: https://fonts.gstatic.com https://cdnjs.cloudflare.com",
    # External images are part of the design (Unsplash hero, Simple Icons,
    # Pinterest avatar) and Journal article covers come from arbitrary feeds, so
    # https: is required here. Cloudinary delivery is covered by it too.
    "img-src 'self' data: blob: https:",
    "media-src 'self' blob: https:",
    "connect-src 'self'",
    "manifest-src 'self'",
    "worker-src 'self' blob:",
)
CSP = '; '.join(CSP_DIRECTIVES)
# Applied on top of the policy when TLS is actually in play, so a stray http://
# asset or link cannot downgrade a visitor.
CSP_PRODUCTION = CSP + '; upgrade-insecure-requests'

PERMISSIONS_POLICY = (
    'accelerometer=(), camera=(), geolocation=(), gyroscope=(), '
    'magnetometer=(), microphone=(), payment=(), usb=()'
)

# Uploaded media is user content served from RETEC's own origin. Without this,
# an uploaded `.svg` opened directly would run its embedded script with access
# to the session cookie. A CSP delivered with a subresource is ignored by
# browsers, so this only takes effect when the file is navigated to directly or
# framed -- which is exactly the case that needs it, and it leaves the same
# files working as ordinary <img>/<video> sources.
UPLOADS_CSP = "default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'; sandbox"


def _cache_static(response):
    """Cache policy for /static/, chosen by how the URL is versioned.

    A `?v=` stamp means the URL changes whenever the bytes do, so it can be
    cached immutably. Everything else (fonts, images, the hero video) keeps a
    short lifetime so replacing a file is picked up without a redeploy.
    """
    if request.path.startswith('/static/uploads/'):
        response.headers['Content-Security-Policy'] = UPLOADS_CSP
        response.headers['Cache-Control'] = 'public, max-age=3600'
    elif 'v=' in request.query_string.decode('latin-1'):
        response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
    else:
        response.headers['Cache-Control'] = 'public, max-age=%d' % app.config[
            'SEND_FILE_MAX_AGE_DEFAULT']
    return response


# ===== AFTER REQUEST =====

@app.after_request
def apply_response_headers(response):
    response.headers.setdefault('X-Content-Type-Options', 'nosniff')
    response.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
    response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
    response.headers.setdefault('Permissions-Policy', PERMISSIONS_POLICY)
    response.headers['Content-Security-Policy'] = (
        CSP_PRODUCTION if _is_production else CSP)
    if _is_production and request.is_secure:
        response.headers.setdefault(
            'Strict-Transport-Security', 'max-age=31536000')

    if request.path.startswith('/static/'):
        return _cache_static(response)

    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

def _track_pageview_worker(page, ip, user_agent):
    with app.app_context():
        try:
            db.session.add(PageView(
                page=page, ip_address=ip, user_agent=user_agent))
            db.session.commit()
        except Exception:
            db.session.rollback()
            return
        record_visitor_location(ip)


@app.before_request
def track_pageview():
    if 'admin_id' in session:
        return
    if request.path.startswith('/static') or request.path.startswith('/track') or request.path.startswith('/admin') or request.path == '/favicon.ico':
        return
    page = request.path[:200]
    ip = get_client_ip()
    user_agent = request.headers.get('User-Agent', '')[:500]
    try:
        threading.Thread(
            target=_track_pageview_worker,
            args=(page, ip, user_agent),
            name='retec-pageview',
            daemon=True,
        ).start()
    except Exception:
        # Analytics must never block or break a page render.
        pass


def record_visitor_location(ip):
    """Attribute a visitor to a country/city without holding up the response.

    Geolocation is an analytics nicety, so it must never be able to add its
    network latency to a page view. The lookup is handed to a short-lived
    daemon thread, exactly as the Journal scheduler hands off its fetch. If the
    thread cannot start, or the third party is slow or down, nothing is lost:
    the view is still counted and the location is simply never recorded.
    """
    try:
        if not ip or LocationLog.query.filter_by(ip_address=ip).first() is not None:
            return
    except Exception:
        db.session.rollback()
        return
    threading.Thread(target=_record_visitor_location_worker, args=(ip,),
                     name='retec-geo-lookup', daemon=True).start()


def _record_visitor_location_worker(ip):
    with app.app_context():
        geo = lookup_location(ip)
        if not geo:
            return
        try:
            if LocationLog.query.filter_by(ip_address=ip).first() is not None:
                return
            db.session.add(LocationLog(ip_address=ip, country=geo['country'],
                                       city=geo['city']))
            db.session.commit()
        except Exception:
            db.session.rollback()

@app.before_request
def journal_scheduler_hook():
    """Give the fetch pipeline a chance to run, once per interval.

    Registered before pageview tracking so it never inflates analytics. The
    work itself happens off-thread and is claimed by a uniquely-indexed slot,
    so the common path here is a single indexed SELECT and a thread that does
    not start.
    """
    if request.path.startswith('/static') or request.path.startswith('/track'):
        return
    journal_scheduler_tick()

@app.cli.command('fetch-journal')
def fetch_journal_command():
    """Fetch configured news sources and create Brief drafts. Never publishes.

    Drive this from cron on a host where you would rather not piggyback on web
    requests:  flask fetch-journal
    """
    summary = run_journal_ingestion(trigger='cli')
    # A CLI command's output is the whole point, so this stays on stdout.
    click.echo('sources: %d | entries: %d | drafts: %d (ai: %d) | duplicates: %d'
               % (summary['sources'], summary['entries'], summary['created'],
                  summary['generated'], summary['duplicates']))
    for failure in summary['failures']:
        click.echo('  FAILED %s' % failure)
    click.echo('All created articles are drafts awaiting admin review.')

# ===== ERROR HANDLERS =====

def _error_is_json():
    """True when the client expects JSON, not a rendered page."""
    return (
        request.path.startswith('/admin/api/')
        or request.path.startswith('/track/')
        or request.accept_mimetypes.best_match(['application/json', 'text/html'])
           == 'application/json'
    )


def _error_response(message, status):
    if _error_is_json():
        return jsonify({'error': message}), status
    template = '500.html' if status >= 500 else '404.html'
    try:
        return render_template(template), status
    except Exception:
        return make_response(message, status)


@app.errorhandler(404)
def not_found(e):
    if _error_is_json():
        return jsonify({'error': 'Not found'}), 404
    return render_template('404.html'), 404

@app.errorhandler(405)
def method_not_allowed(e):
    # A POST to a GET-only route previously produced the default Werkzeug HTML
    # page. This keeps the site's own styling and stays JSON for API clients.
    if _error_is_json():
        return jsonify({'error': 'Method not allowed'}), 405
    return render_template('404.html'), 405

@app.errorhandler(413)
def request_too_large(e):
    # MAX_CONTENT_LENGTH is 16MB. Uploading over it used to surface as a raw
    # Werkzeug page; the admin forms now show a specific message on 413 too.
    if _error_is_json():
        return jsonify({'error': 'File too large (16MB maximum)'}), 413
    if request.path.startswith('/admin'):
        flash('That file is over the 16MB limit. Please upload something smaller.', 'error')
        return redirect(url_for(request.endpoint) if request.endpoint in app.view_functions
                        else url_for('admin_dashboard'))
    flash('That file is over the 16MB limit.', 'error')
    return redirect(url_for('home') + '#contact')

@app.errorhandler(500)
def internal_error(e):
    # The exception is logged, never rendered: Werkzeug's default 500 page in
    # debug mode is where tracebacks and local variables leak out.
    db.session.rollback()
    app.logger.exception('Unhandled error on %s %s', request.method, request.path)
    if _error_is_json():
        return jsonify({'error': 'Internal server error'}), 500
    try:
        return render_template('500.html'), 500
    except Exception:
        return make_response('Internal server error', 500)

@app.errorhandler(429)
def rate_limited(e):
    if request.path.startswith('/admin'):
        flash('Too many attempts. Please try again in a minute.', 'error')
        return redirect(url_for('admin_login'))
    flash('Too many messages. Please try again later.', 'error')
    return redirect(url_for('home') + '#contact')


@app.route('/healthz')
def healthz():
    """Liveness/readiness probe.

    Checks that the database actually answers, not just that the process is
    alive. Render's health check pointed at `/` before, which rendered the whole
    homepage -- including a GitHub API call on every request -- and returned 200
    even with the database down.
    """
    checks = {'app': 'ok'}
    status = 200
    try:
        db.session.execute(db.text('SELECT 1'))
        checks['database'] = 'ok'
    except Exception as exc:
        db.session.rollback()
        checks['database'] = 'error'
        checks['detail'] = type(exc).__name__
        status = 503
    return jsonify({'status': 'ok' if status == 200 else 'degraded',
                    'checks': checks}), status

# ===== PUBLIC ROUTES =====

def get_homepage_data():
    return {
        'projects': get_projects(),
        'testimonials': Testimonial.query.filter_by(active=True).order_by(Testimonial.sort_order).all(),
        'blog_posts': JournalArticle.query.filter_by(status='published').order_by(
            JournalArticle.published_at.desc().nullslast()).limit(3).all(),
        'services': services,
        'process': process,
        'project_types': PROJECT_TYPES,
        'budget_options': BUDGET_OPTIONS
    }

@app.route('/')
def home():
    return render_template('index.html', active='home', form=ContactForm(), **get_homepage_data())

@app.route('/contact', methods=['GET', 'POST'])
# POST only. Unscoped, the limit also counted GETs, so the sixth visitor to load
# the contact section at all was refused a 429 page -- even though the form was
# never submitted and no email was ever sent.
@limiter.limit("5 per hour", methods=["POST"])
def contact():
    form = ContactForm()
    honeypot = request.form.get('website', '')
    if form.validate_on_submit() and not honeypot:
        ip = get_client_ip() or '0.0.0.0'
        try:
            db.session.add(Enquiry(
                name=form.name.data,
                business=form.business.data or '',
                email=form.email.data,
                project_type=form.project_type.data or '',
                budget=form.budget.data or '',
                message=form.message.data,
                ip_address=ip,
            ))
            db.session.commit()
        except Exception:
            db.session.rollback()
            app.logger.exception('Failed to store enquiry: %s', form.email.data)
        if send_email(form.name.data, form.email.data, form.business.data, form.project_type.data, form.budget.data, form.message.data, ip):
            flash('Thank you for your project inquiry. We will get back to you soon.', 'success')
        else:
            flash('Your inquiry could not be sent right now. Please email us directly.', 'error')
        save_subscriber(form.email.data, form.name.data, source='contact')
        return redirect(url_for('home') + '#contact')
    context = get_homepage_data()
    context['form'] = form
    context['active'] = 'home'
    return render_template('index.html', **context)

@app.route('/subscribe', methods=['POST'])
# POST only, CSRF-protected via the hidden token in the subscribe form. Each
# signup can touch subscriber storage and optional third-party list sync, so
# the limit is scoped to POST like the contact and partner forms.
@limiter.limit("5 per hour", methods=["POST"])
def subscribe():
    honeypot = request.form.get('website', '')
    if honeypot:
        return redirect(url_for('home') + '#contact')
    email = request.form.get('email', '').strip()
    name = request.form.get('name', '').strip()
    if not email:
        flash('Please enter your email address.', 'error')
        return redirect(url_for('home') + '#contact')
    subscriber, created = save_subscriber(email, name, source='newsletter')
    if subscriber:
        if created:
            flash('Thanks for subscribing! Stay tuned for updates.', 'success')
        else:
            flash('You are already subscribed!', 'info')
    else:
        flash('That email address does not look valid.', 'error')
    return redirect(url_for('home') + '#contact')

@app.route('/verify-email', methods=['POST'])
@limiter.limit("20 per minute", methods=["POST"])
@csrf.exempt
def verify_email():
    data = request.get_json(silent=True) or {}
    email = (data.get('email', '') or '').strip().lower()
    if not email:
        return jsonify({'valid': False, 'message': 'Enter an email address.'})
    if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
        return jsonify({'valid': False, 'message': 'Invalid email format.'})
    if is_disposable_email(email):
        return jsonify({'valid': False, 'message': 'Disposable email not allowed.'})
    api_result = verify_email_api(email)
    if api_result is True:
        return jsonify({'valid': True, 'message': 'Email verified.'})
    if api_result is False:
        return jsonify({'valid': False, 'message': 'Email does not appear to exist.'})
    smtp_result = smtp_verify(email)
    if smtp_result is True:
        return jsonify({'valid': True, 'message': 'Email exists.'})
    if smtp_result is False:
        return jsonify({'valid': False, 'message': 'Email does not appear to exist.'})
    domain = get_email_domain(email)
    if domain and check_mx_record(domain):
        return jsonify({'valid': True, 'message': 'Email looks good.'})
    return jsonify({'valid': False, 'message': 'Could not verify this email.'})

# `/partner` is the canonical URL (footer link, form target, url_for output) and
# `/become-a-partner` is a readable alias. Both are registered on the same view
# and neither redirects, so no incoming link can go stale. Declared alias-first
# because werkzeug builds the last-registered matching rule, which is what
# url_for() emits.
@app.route('/become-a-partner', methods=['GET', 'POST'])
@app.route('/partner', methods=['GET', 'POST'])
# POST only, for the same reason as /contact: counting page loads here locked
# out ordinary readers of the partner page, not submitters.
@limiter.limit("5 per hour", methods=["POST"])
def partner():
    """Become a Partner / collaboration page and application form.

    Both routes render the same template: `/become-a-partner` is the readable
    alias people tend to link to, `/partner` is the short one used in the
    footer. No redirect between them so neither URL can go stale.
    """
    form = PartnerForm()
    honeypot = request.form.get('website', '')
    if form.validate_on_submit() and not honeypot:
        # SelectField.pre_validate already rejects anything outside the
        # COLLABORATION_TYPES choices server-side, so reaching here means the
        # submitted type came from the whitelist.
        application = PartnerApplication(
            name=form.name.data.strip(),
            email=form.email.data.strip(),
            company=form.company.data.strip(),
            role=form.role.data.strip(),
            portfolio=form.portfolio.data.strip(),
            collaboration_type=form.collaboration_type.data,
            expertise=form.expertise.data.strip(),
            message=form.message.data.strip(),
        )
        db.session.add(application)
        db.session.commit()
        send_partner_application(application)
        flash('Thank you for reaching out. We read every application and will reply if there is a fit.', 'success')
        return redirect(url_for('partner'))
    return render_template('partner.html', **_partner_context(form))

def _partner_context(form):
    """Template context for the partner page, shared by the GET and the
    re-render-after-invalid paths so both always see identical data."""
    return {
        'active': 'partner',
        'form': form,
        'collaboration_types': COLLABORATION_TYPES,
        'collaborator_types': partner_collaborator_types,
        'partner_process': partner_process,
        'partner_reasons': partner_reasons,
        'meta_title': 'Become a Partner — RETEC',
        'meta_desc': 'RETEC collaborates with designers, developers, agencies and '
                     'specialists on digital projects. Tell us what you do and how you '
                     'would like to work together.',
    }

@app.route('/cv')
def cv():
    return render_template('cv.html', active='cv', github_stats=get_github_stats())

# ===== LEGAL PAGES =====
#
# /privacy, /terms, /security. All three render templates/legal_base.html and
# differ only in which descriptor from legal.py they pass plus their metadata.
# The wording is in legal.py rather than in the routes or the templates so a
# legal review never means touching a view.
#
# Nothing here invents a fact. Every claim on these pages is traceable to this
# module or to legal.py, and the handful of values that genuinely are unknown —
# retention periods, the backup schedule, a dedicated security mailbox — are
# rendered as visible [TODO: ...] markers rather than plausible fiction.

LEGAL_LAST_UPDATED = legal.LAST_UPDATED
LEGAL_LAST_UPDATED_ISO = '2026-02-02'

# Mailboxes are configuration, never copy. `contact_email` is the address this
# application actually sends from, which is also the one published in the
# structured data in base.html. `security_email` prefers a dedicated
# SECURITY_CONTACT_EMAIL when one exists and otherwise falls back to MAIL_TO --
# the inbox this studio's own notifications are delivered to, so a report always
# reaches a monitored mailbox. The Security page says exactly that.
LEGAL_EMAILS = {
    'contact_email': app.config['MAIL_FROM'],
    'security_email': os.environ.get('SECURITY_CONTACT_EMAIL') or app.config['MAIL_TO'],
}


def _legal_page(slug, meta_desc):
    """Shared render for the three legal pages.

    The canonical URL is built from url_for rather than left to the context
    processor's `request.url`, so a stray query string can never end up in the
    canonical link for a page that has no query string.
    """
    page = legal.PAGES[slug]
    return render_template(
        '%s.html' % slug,
        legal_page=page,
        legal_emails=LEGAL_EMAILS,
        legal_updated=LEGAL_LAST_UPDATED,
        legal_updated_iso=LEGAL_LAST_UPDATED_ISO,
        active='legal',
        meta_title='%s — RETEC' % page['title'],
        meta_desc=meta_desc,
        meta_url=url_for(slug, _external=True),
    )


@app.route('/privacy')
def privacy():
    return _legal_page(
        'privacy',
        'How RETEC collects, uses, protects and manages information when you use '
        'our website and services — forms, analytics, cookies, retention and '
        'your rights.'
    )


@app.route('/terms')
def terms():
    return _legal_page(
        'terms',
        'The terms for using RETEC’s public website: what you may and may not '
        'do with it, and how it relates to actual client engagements.'
    )


@app.route('/security')
def security():
    return _legal_page(
        'security',
        'The security practices RETEC actually implements on its website and the '
        'applications it builds — and, just as importantly, the ones it does not '
        'claim.'
    )

# ===== RETEC JOURNAL (PUBLIC) =====
#
# `/blog` stays the canonical URL. It is linked from the navbar, the footer,
# the sitemap and any article that has been shared, and a Journal rename is not
# a reason to break those. `/journal` is a permanent redirect to it so the new
# name resolves for anyone who types or links it.

JOURNAL_PER_PAGE = 9
JOURNAL_RELATED_COUNT = 3
JOURNAL_FEATURED_FALLBACK_WINDOW = 60  # days a featured article stays lead


def _published_articles():
    return JournalArticle.query.filter_by(status='published')


def _journal_article_query(content_type='', category=''):
    query = _published_articles()
    if content_type:
        query = query.filter_by(content_type=content_type)
    if category:
        query = query.filter_by(category=category)
    return query


def _journal_category_from_source(source_category):
    """Map a source's uppercase category onto an article category.

    Sources are grouped with values like 'KENYA / BUSINESS' and 'GLOBAL
    TECHNOLOGY'; articles use title-case topics like 'Technology'. Writing the
    raw source value into `category` would create filters the public pages can
    never reach, since the category chips come from published articles.
    """
    if not source_category:
        return ''
    cleaned = source_category.replace('/', ' ').strip().title()
    for candidate in journal.JOURNAL_CATEGORIES:
        if candidate.lower() == cleaned.lower():
            return candidate
    # 'Kenya Business' and 'Global Technology' have no exact article topic; fall
    # back to the closest single word that is one.
    for word in cleaned.split():
        for candidate in journal.JOURNAL_CATEGORIES:
            if candidate.lower() == word.lower():
                return candidate
    return ''


def _journal_categories():
    """Categories that actually have published articles, alphabetically."""
    return [row[0] for row in db.session.query(JournalArticle.category)
            .filter(JournalArticle.status == 'published', JournalArticle.category != '')
            .distinct().order_by(JournalArticle.category).all()]


def _journal_featured(exclude_ids=()):
    """The featured article, chosen from the database.

    An explicit `is_featured` article wins. Otherwise the most recent
    publication takes the lead, so a brand new post is never buried — but only
    within a recent window, after which a stale manual pick is respected.
    """
    exclude = list(exclude_ids or ())
    query = JournalArticle.query.filter(JournalArticle.status == 'published')
    if exclude:
        query = query.filter(JournalArticle.id.notin_(exclude))
    manual = query.filter(JournalArticle.is_featured == True).order_by(
        JournalArticle.published_at.desc().nullslast(),
        JournalArticle.updated_at.desc()).first()
    if manual is not None:
        return manual
    cutoff = datetime.utcnow() - timedelta(days=JOURNAL_FEATURED_FALLBACK_WINDOW)
    return query.filter(JournalArticle.published_at >= cutoff).order_by(
        JournalArticle.published_at.desc()).first()


@app.route('/journal')
def journal_redirect():
    return redirect(url_for('blog'), code=301)


@app.route('/blog')
def blog():
    content_type = request.args.get('type', '').strip().lower()
    if content_type not in JOURNAL_CONTENT_TYPE_VALUES:
        content_type = ''
    category = request.args.get('category', '').strip()
    page = max(1, request.args.get('page', 1, type=int))

    # The lead article is picked from the unfiltered archive so filtering the
    # grid never produces an empty page with a stranger sitting above it.
    featured = _journal_featured()
    exclude = [featured.id] if featured is not None else []

    query = _journal_article_query(content_type, category)
    if exclude:
        query = query.filter(JournalArticle.id.notin_(exclude))
    pagination = query.order_by(
        JournalArticle.published_at.desc().nullslast(),
        JournalArticle.id.desc(),
    ).paginate(page=page, per_page=JOURNAL_PER_PAGE, error_out=False)

    meta_title = 'RETEC Journal'
    if content_type:
        meta_title = '%s — RETEC Journal' % JOURNAL_CONTENT_TYPE_PLURALS.get(content_type, 'Journal')
    if category:
        meta_title = '%s — RETEC Journal' % category
    return render_template(
        'blog.html', active='blog', posts=pagination.items,
        pagination=pagination, featured_post=featured,
        categories=_journal_categories(),
        active_content_type=content_type, active_category=category,
        journal_content_types=JOURNAL_CONTENT_TYPES,
        meta_title=meta_title,
        meta_desc='RETEC insights on business and technology, briefings on the '
                  'developments that matter to Kenyan businesses, and stories '
                  'from the projects we build.',
    )


@app.route('/journal/<slug>')
def journal_post_redirect(slug):
    return redirect(url_for('blog_post', slug=slug), code=301)


@app.route('/blog/<slug>')
def blog_post(slug):
    post = JournalArticle.query.filter_by(slug=slug, status='published').first_or_404()

    published = JournalArticle.query.filter(
        JournalArticle.status == 'published', JournalArticle.id != post.id,
    )
    prev_post = published.filter(JournalArticle.published_at <= post.display_date).order_by(
        JournalArticle.published_at.desc()).first()
    next_post = published.filter(JournalArticle.published_at > post.display_date).order_by(
        JournalArticle.published_at.asc()).first()

    # Related: same category first, then same content type, then recency.
    # Purely database-driven -- nothing here is hand-picked.
    related = published.order_by(
        db.case((JournalArticle.category == post.category, 0), else_=1),
        db.case((JournalArticle.content_type == post.content_type, 0), else_=1),
        JournalArticle.published_at.desc().nullslast(),
    ).limit(JOURNAL_RELATED_COUNT).all()

    canonical = url_for('blog_post', slug=post.slug, _external=True)
    meta_title = '%s — RETEC Journal' % post.title
    meta_desc = journal.truncate(post.summary or journal.strip_html(post.content)[:180], 200)
    meta_image = post.hero_image or url_for('static', filename='images/favicon.svg', _external=True)

    return render_template(
        'blog_post.html', post=post, prev_post=prev_post, next_post=next_post,
        related=related, canonical_url=canonical,
        meta_title=meta_title, meta_desc=meta_desc, meta_image=meta_image,
        meta_url=canonical, meta_og_type='article',
        structured_data=_journal_structured_data(post, canonical, meta_desc, meta_image),
        publisher=JOURNAL_PUBLISHER,
    )


def _journal_structured_data(post, canonical, description, image):
    """Schema.org payload describing the article actually on screen.

    The type follows the nature of the content, not its label:

      * INSIGHT     -> BlogPosting: RETEC's own editorial.
      * CASE_STUDY  -> Article: a write-up of a project we delivered.
      * BRIEF       -> Article, cited. A Brief is RETEC *commentary* on someone
        else's reporting, so declaring it NewsArticle would be claiming the
        original news report, which it is not. `citation` points at the source
        so the relationship stays explicit for readers and for search engines.
    """
    schema_type = {
        'insight': 'BlogPosting',
        'case_study': 'Article',
        'brief': 'Article',
    }.get(post.content_type, 'Article')

    publisher = JOURNAL_PUBLISHER
    data = {
        '@context': 'https://schema.org',
        '@type': schema_type,
        'headline': post.title,
        'description': description,
        'url': canonical,
        'mainEntityOfPage': {'@type': 'WebPage', '@id': canonical},
        'publisher': {
            '@type': 'Organization',
            'name': publisher['name'],
            'url': publisher['url'],
            'logo': {
                '@type': 'ImageObject',
                'url': url_for('static', filename='images/logo.svg', _external=True),
            },
            'sameAs': publisher['same_as'],
        },
        'isPartOf': {
            '@type': 'Blog',
            'name': 'RETEC Journal',
            'url': url_for('blog', _external=True),
        },
    }
    if image:
        data['image'] = image
    data['author'] = (
        {'@type': 'Person', 'name': post.author} if post.author
        else {'@type': 'Organization', 'name': publisher['name']}
    )
    if post.display_date:
        data['datePublished'] = post.display_date.isoformat()
    if post.updated_at:
        data['dateModified'] = post.updated_at.isoformat()
    if post.category:
        data['articleSection'] = post.category
    if post.source_url:
        # Attribution, not ownership: the third-party report is the origin of
        # the story, RETEC is the publisher of the analysis.
        data['citation'] = {
            '@type': 'CreativeWork',
            'name': post.original_title or post.title,
            'url': post.source_url,
            'publisher': {'@type': 'Organization', 'name': post.source_name or 'Source'},
        }
    return data

# ===== TRACKING ROUTES =====

def _tracking_payload():
    """Read a tracking beacon body as a small dict of clipped strings.

    `silent=True` means a malformed body yields `None` instead of raising, and
    the fallback used to then trust whatever `data.get()` returned: sending
    `{"page": 12345}` put an int into a `String(200)` column, `{"page": {...}}`
    put a dict there, and both ended as an unhandled exception and a 500 on a
    fire-and-forget endpoint. Anything that is not a string is replaced, never
    passed through, and each field is length-capped to its column.
    """
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return {}
    return data


def _track_value(data, key, default, limit):
    value = data.get(key, default)
    if not isinstance(value, str):
        # Numbers, bools, nulls and nested objects are not meaningful for any of
        # these fields; fall back to the default rather than coerce.
        return default
    value = value.strip()
    return value[:limit] if value else default


@app.route('/track/pageview', methods=['POST'])
@csrf.exempt
@limiter.limit("120 per minute", methods=["POST"])
def track_pageview_ajax():
    if 'admin_id' in session:
        return '', 204
    ip = get_client_ip()
    data = _tracking_payload()
    view = PageView(
        page=_track_value(data, 'page', '/', 200),
        ip_address=ip,
        user_agent=request.headers.get('User-Agent', '')[:500]
    )
    db.session.add(view)
    db.session.commit()
    record_visitor_location(ip)
    return '', 204


@app.route('/track/interest', methods=['POST'])
@csrf.exempt
@limiter.limit("120 per minute", methods=["POST"])
def track_interest():
    if 'admin_id' in session:
        return '', 204
    ip = get_client_ip()
    data = _tracking_payload()
    interest = Interest(
        section=_track_value(data, 'section', 'unknown', 100),
        action=_track_value(data, 'action', 'view', 100),
        ip_address=ip
    )
    db.session.add(interest)
    db.session.commit()
    record_visitor_location(ip)
    return '', 204

# A valid bcrypt hash of a value nobody knows, used to keep the failed-login
# path the same cost whether or not the username exists. Generated once at
# import; it is not a credential for anything.
_DUMMY_HASH = bcrypt.generate_password_hash(secrets.token_urlsafe(32)).decode('utf-8')

# ===== ADMIN ROUTES =====

@app.route('/admin/login', methods=['GET', 'POST'])
@limiter.limit("5 per minute", methods=["POST"])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        # Compare against a real bcrypt hash even when the username does not
        # exist. Returning early on an unknown user made the "no such user" path
        # measurably faster than the wrong-password path, which is a timing
        # oracle for enumerating admin usernames.
        stored_hash = user.password_hash if user else _DUMMY_HASH
        password_ok = bcrypt.check_password_hash(stored_hash, password or '')
        if user and password_ok:
            session.clear()
            session['admin_id'] = user.id
            session['admin_username'] = user.username
            flash('Welcome back, admin.', 'success')
            return redirect(url_for('admin_dashboard'))
        flash('Invalid credentials.', 'error')
        return redirect(url_for('admin_login'))
    return render_template('admin/login.html')

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_id', None)
    session.pop('admin_username', None)
    flash('Logged out.', 'success')
    return redirect(url_for('admin_login'))

@app.route('/admin/hero-settings', methods=['GET', 'POST'])
@admin_required
def admin_hero_settings():
    if request.method == 'POST':
        if 'clear_cube_positions' in request.form:
            setting = SiteSetting.query.filter_by(key='cube_positions').first()
            if setting:
                setting.value = ''
                db.session.commit()
            flash('Saved cube positions cleared.', 'success')
            return redirect(url_for('admin_hero_settings'))
        bg_type = request.form.get('hero_bg_type', 'video')
        setting = SiteSetting.query.filter_by(key='hero_bg_type').first()
        if setting:
            setting.value = bg_type
        else:
            db.session.add(SiteSetting(key='hero_bg_type', value=bg_type))
        db.session.commit()
        cube_enabled = '1' if request.form.get('cube_positioner_enabled') else '0'
        setting = SiteSetting.query.filter_by(key='cube_positioner_enabled').first()
        if setting:
            setting.value = cube_enabled
        else:
            db.session.add(SiteSetting(key='cube_positioner_enabled', value=cube_enabled))
        db.session.commit()
        quote_interval = request.form.get('hero_quote_interval', '6000')
        setting = SiteSetting.query.filter_by(key='hero_quote_interval').first()
        if setting:
            setting.value = quote_interval
        else:
            db.session.add(SiteSetting(key='hero_quote_interval', value=quote_interval))
        db.session.commit()
        if bg_type == 'video':
            if request.files.get('video') and request.files['video'].filename:
                url = upload_image(request.files['video'])
                if url:
                    setting = SiteSetting.query.filter_by(key='hero_video').first()
                    if setting:
                        setting.value = url
                    else:
                        db.session.add(SiteSetting(key='hero_video', value=url))
                    db.session.commit()
                    flash('Hero video updated.', 'success')
                else:
                    flash('Hero video upload failed — check the file type and that it is under 16MB.', 'error')
            if request.files.get('poster') and request.files['poster'].filename:
                url = upload_image(request.files['poster'])
                if url:
                    setting = SiteSetting.query.filter_by(key='hero_poster').first()
                    if setting:
                        setting.value = url
                    else:
                        db.session.add(SiteSetting(key='hero_poster', value=url))
                    db.session.commit()
                    flash('Hero poster updated.', 'success')
                else:
                    flash('Hero poster upload failed — check the file type and that it is under 16MB.', 'error')
        else:
            if request.files.get('hero_image') and request.files['hero_image'].filename:
                url = upload_image(request.files['hero_image'])
                if url:
                    setting = SiteSetting.query.filter_by(key='hero_image').first()
                    if setting:
                        setting.value = url
                    else:
                        db.session.add(SiteSetting(key='hero_image', value=url))
                    db.session.commit()
                    flash('Hero image updated.', 'success')
                else:
                    flash('Hero image upload failed — check the file type and that it is under 16MB.', 'error')
        return redirect(url_for('admin_hero_settings'))
    hero_bg_type = SiteSetting.query.filter_by(key='hero_bg_type').first()
    hero_video = SiteSetting.query.filter_by(key='hero_video').first()
    hero_image = SiteSetting.query.filter_by(key='hero_image').first()
    hero_poster = SiteSetting.query.filter_by(key='hero_poster').first()
    hero_quote_interval = SiteSetting.query.filter_by(key='hero_quote_interval').first()
    cube_positioner_enabled = SiteSetting.query.filter_by(key='cube_positioner_enabled').first()
    cube_positions_setting = SiteSetting.query.filter_by(key='cube_positions').first()
    cube_positions = _load_cube_positions(
        cube_positions_setting.value if cube_positions_setting else None)
    return render_template('admin/hero_settings.html',
        hero_bg_type=hero_bg_type.value if hero_bg_type else 'video',
        hero_video=hero_video.value if hero_video else '',
        hero_image=hero_image.value if hero_image else '',
        hero_poster=hero_poster.value if hero_poster else '',
        hero_quote_interval=hero_quote_interval.value if hero_quote_interval else '6000',
        cube_positioner_enabled=(cube_positioner_enabled.value == '1') if cube_positioner_enabled else False,
        cube_positions=cube_positions)

@app.route('/admin/change-password', methods=['GET', 'POST'])
@admin_required
@limiter.limit("10 per 10 minutes", methods=["POST"])
def admin_change_password():
    user = db.session.get(User, session['admin_id'])
    if not user:
        flash('User not found.', 'error')
        return redirect(url_for('admin_logout'))

    if request.method == 'POST' and 'verification_code' in request.form:
        code = request.form.get('verification_code', '').strip()
        new_password = request.form.get('new_password', '')
        confirm = request.form.get('confirm_password', '')

        stored_code = session.get('pwd_change_code')
        expiry = session.get('pwd_change_expiry', 0)

        if not stored_code or not expiry:
            flash('No verification code was sent. Please start again.', 'error')
            session.pop('pwd_change_code', None)
            session.pop('pwd_change_expiry', None)
            return redirect(url_for('admin_change_password'))

        if time.time() > expiry:
            flash('Verification code has expired. Please request a new one.', 'error')
            session.pop('pwd_change_code', None)
            session.pop('pwd_change_expiry', None)
            return redirect(url_for('admin_change_password'))

        if code != stored_code:
            flash('Invalid verification code.', 'error')
            return render_template('admin/change_password.html', step=2)

        if len(new_password) < 12:
            flash('New password must be at least 12 characters.', 'error')
            return render_template('admin/change_password.html', step=2)

        if new_password != confirm:
            flash('New passwords do not match.', 'error')
            return render_template('admin/change_password.html', step=2)

        user.password_hash = bcrypt.generate_password_hash(new_password).decode('utf-8')
        db.session.commit()

        session.pop('pwd_change_code', None)
        session.pop('pwd_change_expiry', None)

        flash('Password changed successfully.', 'success')
        return redirect(url_for('admin_dashboard'))

    if request.method == 'POST' and 'current_password' in request.form:
        current = request.form.get('current_password', '')

        if not bcrypt.check_password_hash(user.password_hash, current):
            flash('Current password is incorrect.', 'error')
            return redirect(url_for('admin_change_password'))

        code = str(secrets.randbelow(900000) + 100000)
        email_to = app.config['MAIL_TO']

        if send_verification_code(email_to, code):
            session['pwd_change_code'] = code
            session['pwd_change_expiry'] = time.time() + 600
            flash(f'A verification code has been sent to {email_to}.', 'success')
            return render_template('admin/change_password.html', step=2)
        else:
            flash('Failed to send verification email. Please check SMTP settings.', 'error')
            return redirect(url_for('admin_change_password'))

    code = session.get('pwd_change_code')
    expiry = session.get('pwd_change_expiry', 0)
    if code and expiry and time.time() < expiry:
        return render_template('admin/change_password.html', step=2)

    session.pop('pwd_change_code', None)
    session.pop('pwd_change_expiry', None)
    return render_template('admin/change_password.html', step=1)

@app.route('/admin')
@admin_required
def admin_dashboard():
    total_views = PageView.query.count()
    unique_visitors = db.session.query(PageView.ip_address).distinct().count()
    project_count = Project.query.count()
    testimonial_count = Testimonial.query.count()
    blog_count = JournalArticle.query.count()
    top_pages = db.session.query(
        PageView.page, db.func.count(PageView.id).label('count')
    ).group_by(PageView.page).order_by(db.desc('count')).limit(10).all()
    recent_views = PageView.query.order_by(PageView.timestamp.desc()).limit(20).all()
    total_interests = Interest.query.count()
    top_sections = db.session.query(
        Interest.section, db.func.count(Interest.id).label('count')
    ).group_by(Interest.section).order_by(db.desc('count')).limit(10).all()
    subscriber_count = Subscriber.query.count()
    enquiry_count = Enquiry.query.count()
    countries_count = db.session.query(LocationLog.country).distinct().count()
    import sqlalchemy as sa
    top_locations = db.session.query(
        LocationLog.country, LocationLog.city, sa.func.count(LocationLog.id).label('count')
    ).group_by(LocationLog.country, LocationLog.city
    ).order_by(sa.desc('count')).limit(10).all()
    return render_template('admin/dashboard.html',
        total_views=total_views, unique_visitors=unique_visitors,
        project_count=project_count, testimonial_count=testimonial_count,
        blog_count=blog_count, top_pages=top_pages,
        recent_views=recent_views, total_interests=total_interests,
        top_sections=top_sections, subscriber_count=subscriber_count,
        enquiry_count=enquiry_count,
        countries_count=countries_count, top_locations=top_locations)

# ----- Projects -----

@app.route('/admin/projects')
@admin_required
def admin_projects():
    projects = Project.query.order_by(Project.sort_order, Project.created_at.desc()).all()
    github_repos = []
    try:
        r = requests.get('https://api.github.com/users/echoesrule/repos?sort=updated&per_page=30', timeout=5)
        if r.status_code == 200:
            for repo in r.json():
                if not repo.get('fork') and isinstance(repo, dict):
                    github_repos.append(repo)
    except Exception:
        pass
    imported_urls = {p.github_url for p in projects if p.github_url}
    return render_template('admin/projects.html', projects=projects, github_repos=github_repos,
        imported_urls=imported_urls, project_status_values=PROJECT_STATUS_VALUES,
        project_status_labels=PROJECT_STATUS_LABELS)

@app.route('/admin/projects/add', methods=['GET', 'POST'])
@admin_required
def admin_project_add():
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        if not title:
            flash('Title is required.', 'error')
            return redirect(url_for('admin_project_add'))
        image_filename = upload_image(request.files.get('image'))
        project = Project(
            title=title,
            description=request.form.get('description', ''),
            category=request.form.get('category', ''),
            tags=request.form.get('tags', ''),
            image_filename=image_filename,
            github_url=request.form.get('github_url', ''),
            demo_url=request.form.get('demo_url', ''),
            featured=bool(request.form.get('featured')),
            visible=bool(request.form.get('visible')),
            status=clean_project_status(request.form.get('status')),
            sort_order=form_int(request.form.get('sort_order', 0))
        )
        db.session.add(project)
        db.session.commit()
        flash('Project added.', 'success')
        return redirect(url_for('admin_projects'))
    categories = db.session.query(Project.category).distinct().order_by(Project.category).all()
    categories = [c[0] for c in categories if c[0]]
    prefill = {
        'title': request.args.get('title', ''),
        'description': request.args.get('description', ''),
        'github_url': request.args.get('github_url', '')
    }
    return render_template('admin/project_form.html', project=None, prefill=prefill,
        categories=categories, project_statuses=PROJECT_STATUSES)

@app.route('/admin/projects/edit/<int:id>', methods=['GET', 'POST'])
@admin_required
def admin_project_edit(id):
    project = Project.query.get_or_404(id)
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        if not title:
            flash('Title is required.', 'error')
            return redirect(url_for('admin_project_edit', id=id))
        project.title = title
        project.description = request.form.get('description', '')
        project.category = request.form.get('category', '')
        project.tags = request.form.get('tags', '')
        project.github_url = request.form.get('github_url', '')
        project.demo_url = request.form.get('demo_url', '')
        project.featured = bool(request.form.get('featured'))
        project.visible = bool(request.form.get('visible'))
        project.status = clean_project_status(request.form.get('status'))
        project.sort_order = form_int(request.form.get('sort_order', 0))
        if request.files.get('image') and request.files['image'].filename:
            delete_image(project.image_filename)
            project.image_filename = upload_image(request.files['image'])
        db.session.commit()
        flash('Project updated.', 'success')
        return redirect(url_for('admin_projects'))
    categories = db.session.query(Project.category).distinct().order_by(Project.category).all()
    categories = [c[0] for c in categories if c[0]]
    return render_template('admin/project_form.html', project=project, prefill={},
        categories=categories, project_statuses=PROJECT_STATUSES)

@app.route('/admin/projects/github-sync', methods=['POST'])
@admin_required
def admin_project_github_sync():
    repo_url = request.form.get('repo_url', '').strip()
    if not repo_url:
        flash('GitHub URL is required.', 'error')
        return redirect(url_for('admin_project_add'))
    import re
    match = re.match(r'https?://github\.com/([^/]+)/([^/]+)', repo_url)
    if not match:
        flash('Invalid GitHub URL.', 'error')
        return redirect(url_for('admin_project_add'))
    owner, repo = match.group(1), match.group(2).rstrip('/')
    try:
        r = requests.get(f'https://api.github.com/repos/{owner}/{repo}', timeout=5)
        if r.status_code == 200:
            data = r.json()
            tags = [data.get('language') or ''] + data.get('topics', [])
            tags = [t for t in tags if t]
            return jsonify({
                'description': data.get('description') or '',
                'tags': ', '.join(tags[:6])
            })
    except Exception:
        pass
    return jsonify({'error': 'Could not fetch repo data'}), 400

@app.route('/admin/projects/delete/<int:id>', methods=['POST'])
@admin_required
def admin_project_delete(id):
    project = Project.query.get_or_404(id)
    delete_image(project.image_filename)
    db.session.delete(project)
    db.session.commit()
    flash('Project deleted.', 'success')
    return redirect(url_for('admin_projects'))

@app.route('/admin/projects/sync-github', methods=['POST'])
@admin_required
def sync_github_projects():
    try:
        r = requests.get('https://api.github.com/users/echoesrule/repos?sort=updated&per_page=30', timeout=10)
        if r.status_code != 200:
            flash('Could not fetch GitHub repos.', 'error')
            return redirect(url_for('admin_projects'))
        repos = r.json()
        if not isinstance(repos, list):
            flash('Unexpected response from GitHub.', 'error')
            return redirect(url_for('admin_projects'))
        added = 0
        for repo in repos:
            if repo.get('fork'):
                continue
            github_url = repo['html_url']
            exists = Project.query.filter_by(github_url=github_url).first()
            if exists:
                continue
            tags = []
            if repo.get('language'):
                tags.append(repo['language'])
            tags.extend(repo.get('topics', [])[:4])
            project = Project(
                title=repo['name'].replace('-', ' ').replace('_', ' ').title(),
                description=repo.get('description') or '',
                tags=', '.join(tags) if tags else '',
                github_url=github_url,
                visible=True
            )
            db.session.add(project)
            added += 1
        db.session.commit()
        flash(f'Synced {added} new project(s) from GitHub.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Sync failed: {str(e)}', 'error')
    return redirect(url_for('admin_projects'))

@app.route('/admin/projects/toggle-visibility/<int:id>', methods=['POST'])
@admin_required
def toggle_project_visibility(id):
    project = Project.query.get_or_404(id)
    project.visible = not project.visible
    db.session.commit()
    return jsonify({'visible': project.visible})

# ----- Cube positioner -----

def _sanitize_cube_positions(positions):
    cleaned = []
    for p in positions:
        if not isinstance(p, dict):
            continue
        try:
            x = min(100.0, max(0.0, float(p.get('x', 0))))
            y = min(100.0, max(0.0, float(p.get('y', 0))))
        except (TypeError, ValueError):
            continue
        entry = {'x': round(x, 1), 'y': round(y, 1)}
        try:
            if p.get('w') is not None:
                entry['w'] = max(40, min(600, int(p['w'])))
            if p.get('o') is not None:
                entry['o'] = min(1.0, max(0.0, float(p['o'])))
        except (TypeError, ValueError):
            pass
        cleaned.append(entry)
    return cleaned

@app.route('/admin/api/cube-positions', methods=['POST'])
@admin_required
@limiter.exempt
def admin_save_cube_positions():
    data = request.get_json(silent=True) or {}
    if data.get('clear'):
        setting = SiteSetting.query.filter_by(key='cube_positions').first()
        if setting:
            setting.value = ''
            db.session.commit()
        return jsonify({'ok': True, 'cleared': True})
    positions = data.get('positions')
    if not isinstance(positions, list):
        return jsonify({'ok': False, 'error': 'positions must be a list'}), 400
    cleaned = _sanitize_cube_positions(positions)
    if not cleaned:
        return jsonify({'ok': False, 'error': 'no valid positions'}), 400
    setting = SiteSetting.query.filter_by(key='cube_positions').first()
    if setting:
        setting.value = json.dumps(cleaned)
    else:
        db.session.add(SiteSetting(key='cube_positions', value=json.dumps(cleaned)))
    db.session.commit()
    return jsonify({'ok': True, 'count': len(cleaned)})

# ----- Analytics + CSV Export -----

@app.route('/admin/analytics')
@admin_required
def admin_analytics():
    return render_template('admin/analytics.html')

@app.route('/admin/api/analytics/summary')
@admin_required
def admin_analytics_summary():
    from datetime import datetime, timedelta
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    total_views = PageView.query.count()
    unique_visitors = db.session.query(PageView.ip_address).distinct().count()
    total_interests = Interest.query.count()
    recent_views = PageView.query.filter(PageView.timestamp >= thirty_days_ago).count()
    countries_count = db.session.query(LocationLog.country).distinct().count()
    return jsonify({
        'total_views': total_views,
        'unique_visitors': unique_visitors,
        'total_interests': total_interests,
        'recent_views': recent_views,
        'countries_count': countries_count
    })

@app.route('/admin/api/analytics/views-over-time')
@admin_required
def admin_analytics_views_over_time():
    from datetime import datetime, timedelta
    import sqlalchemy as sa
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    rows = db.session.query(
        sa.func.date(PageView.timestamp).label('date'),
        sa.func.count(PageView.id).label('count')
    ).filter(PageView.timestamp >= thirty_days_ago
    ).group_by(sa.func.date(PageView.timestamp)
    ).order_by('date').all()
    labels = [(datetime.utcnow() - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(29, -1, -1)]
    counts = {str(r.date): r.count for r in rows}
    data = [counts.get(d, 0) for d in labels]
    return jsonify({'labels': labels, 'data': data})

@app.route('/admin/api/analytics/top-pages')
@admin_required
def admin_analytics_top_pages():
    import sqlalchemy as sa
    rows = db.session.query(
        PageView.page, sa.func.count(PageView.id).label('count')
    ).group_by(PageView.page).order_by(sa.desc('count')).limit(10).all()
    return jsonify({
        'labels': [r.page for r in rows],
        'data': [r.count for r in rows]
    })

@app.route('/admin/api/analytics/section-interests')
@admin_required
def admin_analytics_section_interests():
    import sqlalchemy as sa
    rows = db.session.query(
        Interest.section, sa.func.count(Interest.id).label('count')
    ).group_by(Interest.section).order_by(sa.desc('count')).all()
    return jsonify({
        'labels': [r.section for r in rows],
        'data': [r.count for r in rows]
    })

@app.route('/admin/api/analytics/interests-over-time')
@admin_required
def admin_analytics_interests_over_time():
    from datetime import datetime, timedelta
    import sqlalchemy as sa
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    rows = db.session.query(
        sa.func.date(Interest.timestamp).label('date'),
        sa.func.count(Interest.id).label('count')
    ).filter(Interest.timestamp >= thirty_days_ago
    ).group_by(sa.func.date(Interest.timestamp)
    ).order_by('date').all()
    labels = [(datetime.utcnow() - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(29, -1, -1)]
    counts = {str(r.date): r.count for r in rows}
    data = [counts.get(d, 0) for d in labels]
    return jsonify({'labels': labels, 'data': data})

@app.route('/admin/api/analytics/locations')
@admin_required
def admin_analytics_locations():
    import sqlalchemy as sa
    rows = db.session.query(
        LocationLog.country, sa.func.count(LocationLog.id).label('count')
    ).group_by(LocationLog.country).order_by(sa.desc('count')).all()
    total = sum(r.count for r in rows)
    return jsonify({
        'labels': [r.country for r in rows],
        'data': [r.count for r in rows],
        'total': total
    })

@app.route('/admin/api/analytics/cities')
@admin_required
def admin_analytics_cities():
    import sqlalchemy as sa
    rows = db.session.query(
        LocationLog.country, LocationLog.city, sa.func.count(LocationLog.id).label('count')
    ).group_by(LocationLog.country, LocationLog.city
    ).order_by(sa.desc('count')).limit(15).all()
    return jsonify({
        'labels': [f"{r.city}, {r.country}" if r.city else r.country for r in rows],
        'cities': [r.city or 'Unknown' for r in rows],
        'countries': [r.country for r in rows],
        'data': [r.count for r in rows]
    })

@app.route('/admin/analytics/clear', methods=['POST'])
@admin_required
def admin_analytics_clear():
    try:
        PageView.query.delete()
        Interest.query.delete()
        LocationLog.query.delete()
        db.session.commit()
        flash('All analytics data cleared.', 'success')
    except Exception as exc:
        db.session.rollback()
        # Log the detail, show a generic message. The old text rendered
        # str(exc) into the page, so a database failure showed the driver
        # message and table names to whoever triggered it.
        app.logger.exception('Failed to clear analytics')
        flash('Could not clear analytics. Please try again.', 'error')
    return redirect(url_for('admin_analytics'))

@app.route('/admin/analytics/export.csv')
@admin_required
def admin_analytics_export():
    output = io.StringIO()
    writer = _csv_writer(output)
    writer.writerow(['Type', 'Page/Section', 'IP', 'User Agent', 'Timestamp'])
    for v in PageView.query.order_by(PageView.timestamp.desc()).limit(5000):
        writer.writerow(['pageview', _csv_cell(v.page), _csv_cell(v.ip_address),
                         _csv_cell(v.user_agent), _csv_cell(v.timestamp)])
    for i in Interest.query.order_by(Interest.timestamp.desc()).limit(5000):
        writer.writerow(['interest', _csv_cell(f"{i.section}/{i.action}"),
                         _csv_cell(i.ip_address), '',
                         _csv_cell(i.timestamp)])
    output.seek(0)
    return Response(output.getvalue(), mimetype='text/csv',
        headers={'Content-Disposition': 'attachment;filename=analytics.csv'})

# ----- Fun Facts -----

@app.route('/admin/fun-facts')
@admin_required
def admin_fun_facts():
    facts = FunFact.query.order_by(FunFact.updated_at.desc()).all()
    return render_template('admin/fun_facts.html', facts=facts)

@app.route('/admin/fun-facts/add', methods=['GET', 'POST'])
@admin_required
def admin_fun_fact_add():
    if request.method == 'POST':
        text = request.form.get('text', '').strip()
        if not text:
            flash('Fun fact text is required.', 'error')
            return redirect(url_for('admin_fun_fact_add'))
        duration = form_int(request.form.get('duration_seconds', 6), 6, low=1, high=600)
        fact = FunFact(text=text, active=bool(request.form.get('active')), duration_seconds=duration)
        db.session.add(fact)
        db.session.commit()
        flash('Fun fact added.', 'success')
        return redirect(url_for('admin_fun_facts'))
    return render_template('admin/fun_fact_form.html', fact=None)

@app.route('/admin/fun-facts/edit/<int:id>', methods=['GET', 'POST'])
@admin_required
def admin_fun_fact_edit(id):
    fact = FunFact.query.get_or_404(id)
    if request.method == 'POST':
        text = request.form.get('text', '').strip()
        if not text:
            flash('Fun fact text is required.', 'error')
            return redirect(url_for('admin_fun_fact_edit', id=id))
        fact.text = text
        fact.active = bool(request.form.get('active'))
        fact.duration_seconds = form_int(request.form.get('duration_seconds', 6), 6, low=1, high=600)
        db.session.commit()
        flash('Fun fact updated.', 'success')
        return redirect(url_for('admin_fun_facts'))
    return render_template('admin/fun_fact_form.html', fact=fact)

@app.route('/admin/fun-facts/delete/<int:id>', methods=['POST'])
@admin_required
def admin_fun_fact_delete(id):
    fact = FunFact.query.get_or_404(id)
    db.session.delete(fact)
    db.session.commit()
    flash('Fun fact deleted.', 'success')
    return redirect(url_for('admin_fun_facts'))

# ----- Testimonials -----

@app.route('/admin/testimonials')
@admin_required
def admin_testimonials():
    testimonials = Testimonial.query.order_by(Testimonial.sort_order).all()
    return render_template('admin/testimonials.html', testimonials=testimonials)

@app.route('/admin/testimonials/add', methods=['GET', 'POST'])
@admin_required
def admin_testimonial_add():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        text = request.form.get('text', '').strip()
        if not name or not text:
            flash('Name and text are required.', 'error')
            return redirect(url_for('admin_testimonial_add'))
        avatar = upload_image(request.files.get('avatar'))
        testimonial = Testimonial(name=name, role=request.form.get('role', ''),
            text=text, avatar_filename=avatar,
            active=bool(request.form.get('active')),
            sort_order=form_int(request.form.get('sort_order', 0)))
        db.session.add(testimonial)
        db.session.commit()
        flash('Testimonial added.', 'success')
        return redirect(url_for('admin_testimonials'))
    return render_template('admin/testimonial_form.html', testimonial=None)

@app.route('/admin/testimonials/edit/<int:id>', methods=['GET', 'POST'])
@admin_required
def admin_testimonial_edit(id):
    testimonial = Testimonial.query.get_or_404(id)
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        text = request.form.get('text', '').strip()
        if not name or not text:
            flash('Name and text are required.', 'error')
            return redirect(url_for('admin_testimonial_edit', id=id))
        testimonial.name = name
        testimonial.role = request.form.get('role', '')
        testimonial.text = text
        testimonial.active = bool(request.form.get('active'))
        testimonial.sort_order = form_int(request.form.get('sort_order', 0))
        if request.files.get('avatar') and request.files['avatar'].filename:
            delete_image(testimonial.avatar_filename)
            testimonial.avatar_filename = upload_image(request.files['avatar'])
        db.session.commit()
        flash('Testimonial updated.', 'success')
        return redirect(url_for('admin_testimonials'))
    return render_template('admin/testimonial_form.html', testimonial=testimonial)

@app.route('/admin/testimonials/delete/<int:id>', methods=['POST'])
@admin_required
def admin_testimonial_delete(id):
    testimonial = Testimonial.query.get_or_404(id)
    delete_image(testimonial.avatar_filename)
    db.session.delete(testimonial)
    db.session.commit()
    flash('Testimonial deleted.', 'success')
    return redirect(url_for('admin_testimonials'))

# ----- RETEC Journal: moderation -----
#
# The Journal is one CMS. Everything below -- original Insights, reviewed
# Briefs, Case Studies, and the fetch pipeline that produces new Brief drafts
# -- is edited, approved and retired from this one place, with the same
# session-gated `admin_required` decorator the rest of the dashboard uses.

JOURNAL_ADMIN_PER_PAGE = 25


def _admin_article_or_404(id):
    return JournalArticle.query.get_or_404(id)


def _redirect_back_to_queue(fallback_endpoint='admin_blog'):
    """Return to the queue tab the admin came from, so filters survive an action."""
    status = request.args.get('status', '').strip()
    if status in JOURNAL_STATUS_VALUES:
        return redirect(url_for(fallback_endpoint, status=status))
    return redirect(url_for(fallback_endpoint))


def _apply_article_form(article, form, is_new=False):
    """Write an admin's submitted article fields onto the model.

    Shared by create and edit so the two cannot drift apart. Content and any
    external HTML always go through the sanitiser: feed text and model output
    are untrusted input and this is the boundary that makes them safe to render.
    """
    title = form.get('title', '').strip()
    content = form.get('content', '').strip()
    if not title:
        raise ValueError('A headline is required.')
    if not content:
        raise ValueError('Article body is required.')

    content_type = clean_journal_content_type(form.get('content_type'))
    source_url = form.get('source_url', '').strip()
    if source_url and not journal.is_safe_http_url(source_url):
        raise ValueError('The source URL must be a valid http(s) address.')

    article.title = title[:200]
    article.slug = unique_slug(title, exclude_id=None if is_new else article.id)
    # Keep the dedupe fingerprint in step with the headline. Without this an
    # admin-written article is invisible to the fetcher's title check, and the
    # same story can come back as a "new" draft.
    article.title_fingerprint = journal.title_fingerprint(title) or None
    article.summary = form.get('summary', '').strip()[:500]
    article.content = journal.sanitize_html(content)
    article.content_type = content_type
    article.category = form.get('category', '').strip()[:100]
    article.author = form.get('author', '').strip()[:120]
    article.reading_time = clean_optional_int(form.get('reading_time'))

    # Source attribution only exists for externally-based content. Switching an
    # article back to an Insight clears it rather than leaving a stale credit.
    if content_type == 'brief':
        article.source_name = form.get('source_name', '').strip()[:200]
        article.source_url = source_url[:500]
        article.source_published_at = clean_optional_date(form.get('source_published_at'))
    else:
        article.source_name = ''
        article.source_url = ''
        article.source_published_at = None

    published_at = clean_optional_date(form.get('published_at'))
    if published_at is not None:
        article.published_at = published_at

    article.is_featured = bool(form.get('is_featured'))
    if article.is_featured:
        # Exactly one lead story: clear any other manual pick so the landing
        # page never has to choose between two.
        JournalArticle.query.filter(
            JournalArticle.id != (article.id or -1),
            JournalArticle.is_featured == True,
        ).update({'is_featured': False}, synchronize_session=False)
    article.updated_at = datetime.utcnow()
    return article


@app.route('/admin/blog')
@admin_required
def admin_blog():
    """Moderation queue. Defaults to the inbox so new fetches are seen first."""
    status = request.args.get('status', '').strip()
    if status not in JOURNAL_STATUS_VALUES:
        status = ''
    content_type = request.args.get('type', '').strip()
    if content_type not in JOURNAL_CONTENT_TYPE_VALUES:
        content_type = ''
    page = max(1, request.args.get('page', 1, type=int))

    query = JournalArticle.query
    if status:
        query = query.filter_by(status=status)
    if content_type:
        query = query.filter_by(content_type=content_type)

    pagination = query.order_by(
        JournalArticle.fetched_at.desc().nullslast(),
        JournalArticle.created_at.desc(),
        JournalArticle.id.desc(),
    ).paginate(page=page, per_page=JOURNAL_ADMIN_PER_PAGE, error_out=False)

    counts = {row[0]: row[1] for row in db.session.query(
        JournalArticle.status, db.func.count(JournalArticle.id)
    ).group_by(JournalArticle.status).all()}
    counts['all'] = sum(counts.values())

    active_sources = NewsSource.query.filter_by(is_active=True).count()
    failed_sources = NewsSource.query.filter(NewsSource.is_active == True,
                                             NewsSource.last_error != '').count()

    return render_template(
        'admin/blog.html', articles=pagination.items, pagination=pagination,
        status_counts=counts, active_status=status, active_content_type=content_type,
        journal_content_types=JOURNAL_CONTENT_TYPES,
        journal_statuses=JOURNAL_STATUSES,
        content_type_labels=JOURNAL_CONTENT_TYPE_LABELS,
        active_sources=active_sources, failed_sources=failed_sources,
        source_count=NewsSource.query.count(),
        scheduler_on=JOURNAL_SCHEDULER_ENABLED,
        interval_minutes=JOURNAL_FETCH_INTERVAL_MINUTES,
        ai_ready=JOURNAL_AI_ENABLED and journal.AiEditor().enabled,
    )


@app.route('/admin/blog/add', methods=['GET', 'POST'])
@app.route('/admin/blog/new', methods=['GET', 'POST'])
@admin_required
def admin_blog_add():
    if request.method == 'POST':
        form = request.form
        try:
            article = _apply_article_form(JournalArticle(), form, is_new=True)
        except ValueError as exc:
            flash(str(exc), 'error')
            return redirect(url_for('admin_blog_add'))
        requested = clean_journal_status(form.get('status'))
        # A brand new article can be created directly in a reviewable state,
        # but never "published" straight from an empty form: it lands in the
        # queue like any other draft and is promoted by an explicit action.
        article.status = 'draft' if requested in ('new', 'draft', 'review') else 'draft'
        article.published = False
        article.created_at = datetime.utcnow()
        db.session.add(article)
        image = upload_image(request.files.get('image'))
        article.image_filename = image or ''
        db.session.commit()
        flash('Journal article created as a draft.', 'success')
        return redirect(url_for('admin_blog_edit', id=article.id))
    return render_template('admin/blog_form.html', article=None, post=None,
                           journal_content_types=JOURNAL_CONTENT_TYPES,
                           journal_statuses=JOURNAL_STATUSES,
                           categories=journal.JOURNAL_CATEGORIES)


@app.route('/admin/blog/edit/<int:id>', methods=['GET', 'POST'])
@admin_required
def admin_blog_edit(id):
    article = _admin_article_or_404(id)
    if request.method == 'POST':
        form = request.form
        try:
            _apply_article_form(article, form)
        except ValueError as exc:
            flash(str(exc), 'error')
            return redirect(url_for('admin_blog_edit', id=id))
        if request.files.get('image') and request.files['image'].filename:
            delete_image(article.image_filename)
            article.image_filename = upload_image(request.files['image'])
        elif form.get('remove_image'):
            delete_image(article.image_filename)
            article.image_filename = ''
        requested = clean_journal_status(form.get('status'))
        if requested and requested != article.status and article.can_transition_to(requested):
            article.apply_status(requested)
        elif requested == 'published' and not article.can_transition_to('published'):
            flash('That status change is not allowed from the current state.', 'error')
        db.session.commit()
        flash('Journal article updated.', 'success')
        return _redirect_back_to_queue()
    return render_template('admin/blog_form.html', article=article, post=article,
                           journal_content_types=JOURNAL_CONTENT_TYPES,
                           journal_statuses=JOURNAL_STATUSES,
                           categories=journal.JOURNAL_CATEGORIES)


@app.route('/admin/blog/view/<int:id>')
@admin_required
def admin_blog_view(id):
    """Read-only preview of an article in any state, including drafts.

    Served from the same template as the public page so what an admin approves
    is what a reader sees. Never reachable without a session, and never
    indexed: the response carries a noindex header and the page is not linked
    from the site.
    """
    article = _admin_article_or_404(id)
    related = _published_articles().filter(JournalArticle.id != article.id).order_by(
        JournalArticle.published_at.desc().nullslast()).limit(JOURNAL_RELATED_COUNT).all()
    canonical = url_for('blog_post', slug=article.slug, _external=True)
    response = make_response(render_template(
        'blog_post.html', post=article, prev_post=None, next_post=None,
        related=related, canonical_url=canonical,
        meta_title='[Preview] %s' % article.title,
        meta_desc=journal.truncate(article.summary or '', 200),
        meta_image=article.hero_image or url_for('static', filename='images/favicon.svg', _external=True),
        meta_url=canonical, meta_og_type='article',
        structured_data=_journal_structured_data(
            article, canonical, journal.truncate(article.summary or '', 200),
            article.hero_image),
        publisher=JOURNAL_PUBLISHER, is_preview=True,
    ))
    response.headers['X-Robots-Tag'] = 'noindex, nofollow'
    return response


@app.route('/admin/blog/status/<int:id>', methods=['POST'])
@admin_required
def admin_blog_status(id):
    """Move an article between editorial states.

    This is the only path to `published`, and it sits behind `admin_required`
    plus the transition table in `JOURNAL_STATUS_TRANSITIONS`. An unrecognised
    or illegal target leaves the article exactly as it was.
    """
    article = _admin_article_or_404(id)
    target = clean_journal_status(request.form.get('status'))
    if not target:
        flash('Unknown status.', 'error')
        return _redirect_back_to_queue()
    if target == article.status:
        return _redirect_back_to_queue()
    if not article.can_transition_to(target):
        flash('An article cannot move from %s to %s.'
              % (article.status_label, JOURNAL_STATUS_LABELS.get(target, target)), 'error')
        return _redirect_back_to_queue()
    article.apply_status(target)
    db.session.commit()
    flash('%s is now %s.' % (article.title[:60], article.status_label.lower()), 'success')
    return _redirect_back_to_queue()


@app.route('/admin/blog/publish/<int:id>', methods=['POST'])
@admin_required
def admin_blog_publish(id):
    """Approve & publish.

    Same checks as the generic status route, spelled out because this is the
    button an admin actually clicks. A Brief cannot go out without its source
    link, so third-party reporting is never published unattributed.
    """
    article = _admin_article_or_404(id)
    if article.status == 'published':
        return _redirect_back_to_queue()
    if not article.can_transition_to('published'):
        flash('This article cannot be published from its current state.', 'error')
        return _redirect_back_to_queue()
    if article.content_type == 'brief' and not article.source_url:
        flash('A Brief needs a source URL before it can be published.', 'error')
        return _redirect_back_to_queue()
    article.apply_status('published')
    article.updated_at = datetime.utcnow()
    db.session.commit()
    flash('Published: %s' % article.title[:70], 'success')
    return _redirect_back_to_queue()


@app.route('/admin/blog/reject/<int:id>', methods=['POST'])
@admin_required
def admin_blog_reject(id):
    article = _admin_article_or_404(id)
    if not article.can_transition_to('rejected'):
        flash('This article cannot be rejected from its current state.', 'error')
        return _redirect_back_to_queue()
    article.apply_status('rejected')
    if article.is_featured:
        article.is_featured = False
    db.session.commit()
    flash('Rejected: %s' % article.title[:70], 'success')
    return _redirect_back_to_queue()


@app.route('/admin/blog/archive/<int:id>', methods=['POST'])
@admin_required
def admin_blog_archive(id):
    article = _admin_article_or_404(id)
    if not article.can_transition_to('archived'):
        flash('This article cannot be archived from its current state.', 'error')
        return _redirect_back_to_queue()
    article.apply_status('archived')
    if article.is_featured:
        article.is_featured = False
    db.session.commit()
    flash('Archived: %s' % article.title[:70], 'success')
    return _redirect_back_to_queue()


@app.route('/admin/blog/redraft/<int:id>', methods=['POST'])
@admin_required
def admin_blog_redraft(id):
    article = _admin_article_or_404(id)
    ok, message = regenerate_article_draft(article)
    flash(message, 'success' if ok else 'error')
    return _redirect_back_to_queue()


@app.route('/admin/blog/delete/<int:id>', methods=['POST'])
@admin_required
def admin_blog_delete(id):
    article = _admin_article_or_404(id)
    if article.status == 'published':
        flash('Archive a published article instead of deleting it — the URL stays alive.',
              'error')
        return _redirect_back_to_queue()
    delete_image(article.image_filename)
    db.session.delete(article)
    db.session.commit()
    flash('Draft deleted.', 'success')
    return _redirect_back_to_queue()


@app.route('/admin/blog/fetch', methods=['POST'])
@admin_required
def admin_blog_fetch():
    """Run the ingestion pipeline now, on demand."""
    source_ids = clean_optional_int(request.form.get('source_id'))
    summary = run_journal_ingestion(
        source_ids=[source_ids] if source_ids else None, trigger='manual')
    if summary['failures']:
        flash('%d source(s) failed: %s' % (len(summary['failures']),
                                           '; '.join(summary['failures'][:3])), 'error')
    flash('Fetched %d sources: %d entries, %d new drafts (%d AI-written), %d duplicates skipped.'
          % (summary['sources'], summary['entries'], summary['created'],
             summary['generated'], summary['duplicates']), 'success')
    return _redirect_back_to_queue()


@app.route('/admin/upload-image', methods=['POST'])
@admin_required
def admin_upload_image():
    file = request.files.get('image')
    if not file or not file.filename:
        return jsonify({'error': 'No image provided'}), 400
    url = upload_image(file)
    if not url:
        return jsonify({'error': 'Upload failed'}), 400
    return jsonify({'url': get_image_url(url)})


# ----- RETEC Journal: sources -----

@app.route('/admin/blog/sources')
@admin_required
def admin_blog_sources():
    sources = NewsSource.query.order_by(
        NewsSource.is_active.desc(), NewsSource.category, NewsSource.name).all()
    runs = NewsFetchRun.query.order_by(
        NewsFetchRun.started_at.desc()).limit(15).all()
    counts = {row[0]: row[1] for row in db.session.query(
        JournalArticle.content_type, db.func.count(JournalArticle.id)
    ).filter(JournalArticle.source_record_id.isnot(None)).group_by(
        JournalArticle.content_type).all()}
    return render_template(
        'admin/blog_sources.html', sources=sources, recent_runs=runs,
        draft_counts=counts, source_categories=journal.SOURCE_CATEGORIES,
        status_labels=JOURNAL_STATUSES, content_type_labels=JOURNAL_CONTENT_TYPE_LABELS,
        scheduler_on=JOURNAL_SCHEDULER_ENABLED, interval_minutes=JOURNAL_FETCH_INTERVAL_MINUTES,
        ai_ready=JOURNAL_AI_ENABLED and journal.AiEditor().enabled,
        ai_enabled=JOURNAL_AI_ENABLED,
        max_drafts=JOURNAL_MAX_DRAFTS_PER_SOURCE,
    )


def _apply_source_form(source):
    """Validate and write the source fields an admin submitted."""
    name = request.form.get('name', '').strip()
    feed_url = request.form.get('feed_url', '').strip()
    website_url = request.form.get('website_url', '').strip()
    if not name:
        raise ValueError('A source name is required.')
    if not journal.is_safe_http_url(feed_url):
        raise ValueError('The feed URL must be a valid http(s) address.')
    if website_url and not journal.is_safe_http_url(website_url):
        raise ValueError('The website URL must be a valid http(s) address.')
    clash = NewsSource.query.filter(
        NewsSource.feed_url == feed_url, NewsSource.id != (source.id or -1)).first()
    if clash is not None:
        raise ValueError('That feed URL is already configured as "%s".' % clash.name)
    source.name = name[:160]
    source.feed_url = feed_url[:500]
    source.website_url = website_url[:500]
    # Match the category case-insensitively and store the canonical spelling.
    # Source categories are stored uppercase ("TECHNOLOGY") while article
    # categories are title case, so a hand-typed value would otherwise be
    # silently discarded.
    category = request.form.get('category', '').strip()
    canonical = next((c for c in journal.SOURCE_CATEGORIES
                      if c.lower() == category.lower()), '')
    source.category = canonical
    source.is_active = bool(request.form.get('is_active'))
    source.updated_at = datetime.utcnow()
    return source


@app.route('/admin/blog/sources/add', methods=['POST'])
@admin_required
def admin_blog_source_add():
    source = NewsSource(is_active=True)
    try:
        _apply_source_form(source)
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), 'error')
        return redirect(url_for('admin_blog_sources'))
    db.session.add(source)
    db.session.commit()
    flash('Source added. It will be picked up on the next fetch.', 'success')
    return redirect(url_for('admin_blog_sources'))


@app.route('/admin/blog/sources/edit/<int:id>', methods=['POST'])
@admin_required
def admin_blog_source_edit(id):
    source = NewsSource.query.get_or_404(id)
    try:
        _apply_source_form(source)
    except ValueError as exc:
        flash(str(exc), 'error')
        return redirect(url_for('admin_blog_sources'))
    db.session.commit()
    flash('Source updated.', 'success')
    return redirect(url_for('admin_blog_sources'))


@app.route('/admin/blog/sources/toggle/<int:id>', methods=['POST'])
@admin_required
def admin_blog_source_toggle(id):
    source = NewsSource.query.get_or_404(id)
    source.is_active = not source.is_active
    source.updated_at = datetime.utcnow()
    db.session.commit()
    flash('%s is now %s.' % (source.name, 'active' if source.is_active else 'disabled'), 'success')
    return redirect(url_for('admin_blog_sources'))


@app.route('/admin/blog/sources/delete/<int:id>', methods=['POST'])
@admin_required
def admin_blog_source_delete(id):
    source = NewsSource.query.get_or_404(id)
    # Drafts already created keep their source name and URL -- removing a feed
    # must not strip attribution from an article that cites it.
    db.session.delete(source)
    db.session.commit()
    flash('Source removed. Existing Briefs keep their attribution.', 'success')
    return redirect(url_for('admin_blog_sources'))


# ----- Content Studio -----

@app.route('/admin/content-studio')
@admin_required
def admin_content_studio():
    posts = JournalArticle.query.filter_by(status='published').order_by(
        JournalArticle.published_at.desc().nullslast()).all()
    return render_template('admin/content_studio.html', posts=posts)

@app.route('/admin/content-studio/<int:id>')
@admin_required
def admin_content_studio_post(id):
    post = JournalArticle.query.get_or_404(id)
    hero_url = get_image_url(post.image_filename) if post.image_filename else ''
    return render_template('admin/content_studio_post.html', post=post, hero_url=hero_url,
        site_url=request.host_url.rstrip('/'))

# ----- Partner applications -----

@app.route('/admin/partner-applications')
@admin_required
def admin_partner_applications():
    page = request.args.get('page', 1, type=int)
    per_page = 25
    applications = PartnerApplication.query.order_by(PartnerApplication.created_at.desc()).paginate(
        page=page, per_page=per_page)
    counts = {row[0]: row[1] for row in db.session.query(
        PartnerApplication.status, db.func.count(PartnerApplication.id)
    ).group_by(PartnerApplication.status).all()}
    return render_template('admin/partner_applications.html',
        applications=applications, counts=counts,
        status_labels=PARTNER_APPLICATION_STATUSES)

@app.route('/admin/partner-applications/status/<int:id>', methods=['POST'])
@admin_required
def admin_partner_application_status(id):
    application = PartnerApplication.query.get_or_404(id)
    status = request.form.get('status', '').strip()
    # An unrecognised value leaves the stored status untouched rather than
    # resetting it, so a malformed request cannot silently clear a decision.
    if status in PARTNER_APPLICATION_STATUS_VALUES:
        application.status = status
        db.session.commit()
        flash('Application marked as %s.' % application.status, 'success')
    return redirect(url_for('admin_partner_applications'))

@app.route('/admin/partner-applications/delete/<int:id>', methods=['POST'])
@admin_required
def admin_partner_application_delete(id):
    db.session.delete(PartnerApplication.query.get_or_404(id))
    db.session.commit()
    flash('Application deleted.', 'success')
    return redirect(url_for('admin_partner_applications'))

@app.route('/admin/partner-applications/export.csv')
@admin_required
def admin_partner_applications_export():
    output = io.StringIO()
    writer = _csv_writer(output)
    writer.writerow(['Received', 'Name', 'Email', 'Company', 'Role',
                     'Collaboration Type', 'Portfolio', 'Expertise', 'Status', 'Message'])
    for a in PartnerApplication.query.order_by(PartnerApplication.created_at.desc()).all():
        writer.writerow([_csv_cell(a.created_at), _csv_cell(a.name), _csv_cell(a.email),
                         _csv_cell(a.company), _csv_cell(a.role), _csv_cell(a.collaboration_type),
                         _csv_cell(a.portfolio), _csv_cell(a.expertise), _csv_cell(a.status),
                         _csv_cell(a.message)])
    output.seek(0)
    return Response(output.getvalue(), mimetype='text/csv',
        headers={'Content-Disposition': 'attachment;filename=partner-applications.csv'})

# ----- Enquiries -----

@app.route('/admin/enquiries')
@admin_required
def admin_enquiries():
    page = request.args.get('page', 1, type=int)
    per_page = 50
    enquiries = Enquiry.query.order_by(Enquiry.created_at.desc()).paginate(page=page, per_page=per_page)
    return render_template('admin/enquiries.html', enquiries=enquiries)

@app.route('/admin/enquiries/export.csv')
@admin_required
def admin_enquiries_export():
    csv_data = build_enquiries_csv()
    filename = f"retec-enquiries-{datetime.utcnow().strftime('%Y-%m-%d')}.csv"
    return Response(csv_data, mimetype='text/csv',
        headers={'Content-Disposition': f'attachment;filename={filename}'})

# ----- Subscribers -----

@app.route('/admin/subscribers')
@admin_required
def admin_subscribers():
    page = request.args.get('page', 1, type=int)
    per_page = 50
    subscribers = Subscriber.query.order_by(Subscriber.created_at.desc()).paginate(page=page, per_page=per_page)
    return render_template('admin/subscribers.html', subscribers=subscribers)

@app.route('/admin/subscribers/export.csv')
@admin_required
def admin_subscribers_export():
    output = io.StringIO()
    writer = _csv_writer(output)
    writer.writerow(['Email', 'Name', 'Source', 'Brevo Synced', 'Active', 'Subscribed At'])
    for s in Subscriber.query.order_by(Subscriber.created_at.desc()).all():
        writer.writerow([_csv_cell(s.email), _csv_cell(s.name), _csv_cell(s.source),
                         'Yes' if s.brevo_synced else 'No',
                         'Yes' if s.active else 'No', _csv_cell(s.created_at)])
    output.seek(0)
    return Response(output.getvalue(), mimetype='text/csv',
        headers={'Content-Disposition': 'attachment;filename=subscribers.csv'})

with app.app_context():
    try:
        db.create_all()
    except Exception as exc:
        app.logger.error(
            'STARTUP database connection failed (%s: %s). The app will run without a '
            'database; check if the Render DB is sleeping.', type(exc).__name__, exc)
    try:
        import sqlalchemy as sa
        inspector = sa.inspect(db.engine)
        for table, col, col_def in [
            ('subscriber', 'validated', 'BOOLEAN DEFAULT false'),
            ('project', 'demo_url', 'VARCHAR(500) DEFAULT \'\''),
            ('project', 'visible', 'BOOLEAN DEFAULT true'),
            ('project', 'status', 'VARCHAR(50) DEFAULT \'\''),
            ('blog_post', 'category', 'VARCHAR(100) DEFAULT \'\''),
            ('blog_post', 'content_type', 'VARCHAR(30) DEFAULT \'insight\''),
            ('blog_post', 'author', 'VARCHAR(120) DEFAULT \'\''),
            ('blog_post', 'is_featured', 'BOOLEAN DEFAULT false'),
            ('blog_post', 'reading_time', 'INTEGER'),
            ('blog_post', 'source_name', 'VARCHAR(200) DEFAULT \'\''),
            ('blog_post', 'source_url', 'VARCHAR(500) DEFAULT \'\''),
            ('blog_post', 'source_published_at', 'TIMESTAMP'),
            ('blog_post', 'published_at', 'TIMESTAMP'),
            # Journal lifecycle + ingestion bookkeeping. All additive and
            # nullable/defaulted, so existing articles survive untouched.
            ('blog_post', 'status', 'VARCHAR(20) DEFAULT \'draft\''),
            ('blog_post', 'external_id', 'VARCHAR(255)'),
            ('blog_post', 'canonical_url', 'VARCHAR(500)'),
            ('blog_post', 'url_fingerprint', 'VARCHAR(40)'),
            ('blog_post', 'title_fingerprint', 'VARCHAR(40)'),
            ('blog_post', 'original_title', 'VARCHAR(300) DEFAULT \'\''),
            ('blog_post', 'original_excerpt', 'TEXT'),
            ('blog_post', 'image_url', 'VARCHAR(500) DEFAULT \'\''),
            ('blog_post', 'fetched_at', 'TIMESTAMP'),
            ('blog_post', 'source_record_id', 'INTEGER'),
            ('blog_post', 'ai_generated', 'BOOLEAN DEFAULT false'),
            ('fun_fact', 'duration_seconds', 'INTEGER DEFAULT 6'),
            ('fun_fact', 'text', 'TEXT DEFAULT \'\''),
            ('fun_fact', 'active', 'BOOLEAN DEFAULT true'),
            ('fun_fact', 'sort_order', 'INTEGER DEFAULT 0'),
            ('fun_fact', 'created_at', 'TIMESTAMP'),
            ('fun_fact', 'updated_at', 'TIMESTAMP')
        ]:
            try:
                cols = [c['name'] for c in inspector.get_columns(table)]
                if col not in cols:
                    db.session.execute(sa.text(f'ALTER TABLE {table} ADD COLUMN {col} {col_def}'))
                    db.session.commit()
                    app.logger.info('Migration: added %s column to %s', col, table)
            except Exception:
                db.session.rollback()
    except Exception as e:
        app.logger.warning('Startup migration note: %s', e)
        db.session.rollback()
    try:
        # Indexes for the Journal's query patterns. create_all() only builds
        # indexes on tables it creates, so an existing blog_post needs these
        # added explicitly.
        import sqlalchemy as sa
        for statement in [
            'CREATE INDEX IF NOT EXISTS ix_blog_post_slug ON blog_post (slug)',
            'CREATE INDEX IF NOT EXISTS ix_blog_post_status ON blog_post (status)',
            'CREATE INDEX IF NOT EXISTS ix_blog_post_content_type ON blog_post (content_type)',
            'CREATE INDEX IF NOT EXISTS ix_blog_post_category ON blog_post (category)',
            'CREATE INDEX IF NOT EXISTS ix_blog_post_published_at ON blog_post (published_at)',
            'CREATE INDEX IF NOT EXISTS ix_blog_post_status_published_at ON blog_post (status, published_at)',
            'CREATE INDEX IF NOT EXISTS ix_blog_post_canonical_url ON blog_post (canonical_url)',
            'CREATE INDEX IF NOT EXISTS ix_blog_post_external_id ON blog_post (external_id)',
            'CREATE INDEX IF NOT EXISTS ix_blog_post_fetched_at ON blog_post (fetched_at)',
        ]:
            db.session.execute(sa.text(statement))
        db.session.commit()
    except Exception as e:
        app.logger.warning('Journal index setup failed: %s', e)
        db.session.rollback()
    try:
        # Analytics indexes. Every admin analytics endpoint groups or filters on
        # these columns with no index at all, so the admin dashboard ran a full
        # table scan plus a sort on tables that grow by a row per page view. The
        # composite (timestamp, page) index serves both the date-bucketed chart
        # and the "top pages" group-by from one structure.
        import sqlalchemy as sa
        for statement in [
            'CREATE INDEX IF NOT EXISTS ix_page_view_timestamp ON page_view (timestamp)',
            'CREATE INDEX IF NOT EXISTS ix_page_view_page ON page_view (page)',
            'CREATE INDEX IF NOT EXISTS ix_page_view_timestamp_page ON page_view (timestamp, page)',
            'CREATE INDEX IF NOT EXISTS ix_interest_timestamp ON interest (timestamp)',
            'CREATE INDEX IF NOT EXISTS ix_interest_section ON interest (section)',
            'CREATE INDEX IF NOT EXISTS ix_interest_timestamp_section ON interest (timestamp, section)',
            'CREATE INDEX IF NOT EXISTS ix_location_log_ip ON location_log (ip_address)',
            'CREATE INDEX IF NOT EXISTS ix_location_log_country ON location_log (country)',
        ]:
            db.session.execute(sa.text(statement))
        db.session.commit()
    except Exception as e:
        app.logger.warning('Analytics index setup failed: %s', e)
        db.session.rollback()
    try:
        # Backfill: articles that existed before the Journal have a `published`
        # flag but no `status`. Derive it once, then the status column is the
        # single source of truth from here on.
        updated = db.session.execute(sa.text(
            "UPDATE blog_post SET status = 'published' "
            "WHERE (status IS NULL OR status = '') AND published = true"))
        db.session.execute(sa.text(
            "UPDATE blog_post SET status = 'draft' WHERE status IS NULL OR status = ''"))
        db.session.commit()
        if updated.rowcount:
            app.logger.info('Journal: backfilled %d published article(s).',
                            updated.rowcount)
    except Exception as e:
        app.logger.warning('Startup journal backfill note: %s', e)
        db.session.rollback()
    try:
        # Starter sources, written once so the feed list is admin data from
        # then on. Seeding is skipped entirely if any source already exists, so
        # this can never resurrect a source an admin deleted.
        if NewsSource.query.count() == 0:
            for name, feed_url, website_url, category in journal.DEFAULT_NEWS_SOURCES:
                db.session.add(NewsSource(
                    name=name, feed_url=feed_url, website_url=website_url,
                    category=category, is_active=True))
            db.session.commit()
            app.logger.info('Journal: seeded %d starter news sources.', len(journal.DEFAULT_NEWS_SOURCES))
    except Exception as e:
        app.logger.warning('Startup journal source note: %s', e)
        db.session.rollback()
    try:
        if not User.query.first():
            initial_username = os.environ.get('INITIAL_ADMIN_USERNAME', '').strip()
            initial_password = os.environ.get('INITIAL_ADMIN_PASSWORD', '')
            if initial_username and len(initial_password) >= 12:
                hashed = bcrypt.generate_password_hash(initial_password).decode('utf-8')
                db.session.add(User(username=initial_username, password_hash=hashed))
                db.session.commit()
                app.logger.info('Initial admin user created from environment configuration.')
            else:
                app.logger.warning(
                'No admin user created. Set INITIAL_ADMIN_USERNAME and a 12+ character '
                'INITIAL_ADMIN_PASSWORD before first startup.')
    except Exception as e:
        app.logger.warning('Startup admin bootstrap note: %s', e)
        db.session.rollback()

if __name__ == '__main__':
    app.run(debug=not _is_production, host='0.0.0.0', port=5000)
