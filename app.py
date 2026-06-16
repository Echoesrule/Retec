from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, send_from_directory, abort, Response
from datetime import datetime
import os, requests, csv, io, re, time
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from functools import wraps
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'retec-dev-key-2026')
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///portfolio.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', '')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME', '')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD', '')
app.config['MAIL_TO'] = os.environ.get('MAIL_TO', 'hello@retec.dev')

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'}

# Track contact submissions per IP for rate limiting
_contact_log = {}

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
    featured = db.Column(db.Boolean, default=False)
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def tag_list(self):
        return [t.strip() for t in self.tags.split(',') if t.strip()] or ['N/A']

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

class FunFact(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.String(500), nullable=False)
    active = db.Column(db.Boolean, default=True)
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

class BlogPost(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(200), unique=True, nullable=False)
    content = db.Column(db.Text, nullable=False)
    summary = db.Column(db.String(500), default='')
    image_filename = db.Column(db.String(200), default='')
    published = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# ===== HELPERS =====

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'admin_id' not in session:
            flash('Please log in first.', 'error')
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated

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
    q = Project.query.order_by(Project.sort_order, Project.created_at.desc())
    if category:
        q = q.filter_by(category=category)
    db_projects = q.all()
    if db_projects:
        return [{
            'title': p.title,
            'description': p.description or 'No description provided.',
            'tags': p.tag_list(),
            'github': p.github_url or '#',
            'image': url_for('static', filename='uploads/' + p.image_filename) if p.image_filename else '',
            'id': p.id,
            'category': p.category
        } for p in db_projects]
    return get_github_projects()

def get_github_stats():
    try:
        r = requests.get('https://api.github.com/users/echoesrule', timeout=5)
        if r.status_code != 200:
            return None
        data = r.json()
        return {'public_repos': data.get('public_repos', 0), 'followers': data.get('followers', 0)}
    except Exception:
        return None

def send_email(name, email, message):
    if not app.config['MAIL_SERVER']:
        return False
    try:
        import smtplib
        from email.message import EmailMessage
        msg = EmailMessage()
        msg.set_content(f"From: {name} ({email})\n\n{message}")
        msg['Subject'] = f"Portfolio Contact: {name}"
        msg['From'] = app.config['MAIL_USERNAME']
        msg['To'] = app.config['MAIL_TO']
        with smtplib.SMTP(app.config['MAIL_SERVER'], app.config['MAIL_PORT']) as server:
            server.starttls()
            server.login(app.config['MAIL_USERNAME'], app.config['MAIL_PASSWORD'])
            server.send_message(msg)
        return True
    except Exception:
        return False

def rate_limit_check(ip):
    now = time.time()
    _contact_log[ip] = [t for t in _contact_log.get(ip, []) if now - t < 3600]
    if len(_contact_log[ip]) >= 3:
        return False
    _contact_log[ip].append(now)
    return True

def slugify(text):
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[-\s]+', '-', text)
    return text

services = [
    'Website Development',
    'Portfolio Websites',
    'Web Applications',
    'Python Solutions',
    'Website Maintenance'
]

# ===== CONTEXT PROCESSORS =====

@app.context_processor
def inject_globals():
    fun_fact = FunFact.query.filter_by(active=True).order_by(FunFact.updated_at.desc()).first()
    github_stats = get_github_stats()
    try:
        meta_url = request.url
        meta_image = url_for('static', filename='uploads/default-og.png', _external=True)
    except RuntimeError:
        meta_url = '/'
        meta_image = ''
    return {
        'year': datetime.now().year,
        'css_version': int(datetime.now().timestamp()),
        'fun_fact': fun_fact.text if fun_fact else None,
        'github_stats': github_stats,
        'meta_title': 'RETEC — Retro Spirit. Modern Solutions.',
        'meta_desc': 'RETEC is a software developer building modern websites, web applications, and digital experiences.',
        'meta_url': meta_url,
        'meta_image': meta_image
    }

# ===== AFTER REQUEST =====

@app.after_request
def no_cache(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.before_request
def track_pageview():
    if request.path.startswith('/static') or request.path.startswith('/track') or request.path.startswith('/admin'):
        return
    view = PageView(
        page=request.path,
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent', '')[:500]
    )
    db.session.add(view)
    db.session.commit()

# ===== ERROR HANDLERS =====

@app.errorhandler(404)
def not_found(e):
    return render_template('404.html'), 404

# ===== PUBLIC ROUTES =====

@app.route('/')
def home():
    projects = get_projects()
    testimonials = Testimonial.query.filter_by(active=True).order_by(Testimonial.sort_order).all()
    blog_posts = BlogPost.query.filter_by(published=True).order_by(BlogPost.created_at.desc()).limit(3).all()
    return render_template('index.html', active='home', projects=projects,
        services=services, testimonials=testimonials, blog_posts=blog_posts)

@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        honeypot = request.form.get('website', '')
        if honeypot:
            return redirect(url_for('home') + '#contact')
        if not rate_limit_check(request.remote_addr or '0.0.0.0'):
            flash('Too many messages. Please try again later.', 'error')
            return redirect(url_for('home') + '#contact')
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        message = request.form.get('message', '').strip()
        if not name or not email or not message:
            flash('All fields are required.', 'error')
            return redirect(url_for('home') + '#contact')
        sent = send_email(name, email, message)
        flash('Thank you for your message. I will get back to you soon.', 'success')
        return redirect(url_for('home') + '#contact')
    return redirect(url_for('home') + '#contact')

@app.route('/cv')
def cv():
    return render_template('cv.html', active='cv')

@app.route('/blog')
def blog():
    posts = BlogPost.query.filter_by(published=True).order_by(BlogPost.created_at.desc()).all()
    return render_template('blog.html', active='blog', posts=posts)

@app.route('/blog/<slug>')
def blog_post(slug):
    post = BlogPost.query.filter_by(slug=slug, published=True).first_or_404()
    return render_template('blog_post.html', post=post)

# ===== TRACKING ROUTES =====

@app.route('/track/pageview', methods=['POST'])
def track_pageview_ajax():
    data = request.get_json(silent=True) or {}
    view = PageView(
        page=data.get('page', '/'),
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent', '')[:500]
    )
    db.session.add(view)
    db.session.commit()
    return '', 204

@app.route('/track/interest', methods=['POST'])
def track_interest():
    data = request.get_json(silent=True) or {}
    interest = Interest(
        section=data.get('section', 'unknown'),
        action=data.get('action', 'view'),
        ip_address=request.remote_addr
    )
    db.session.add(interest)
    db.session.commit()
    return '', 204

# ===== ADMIN ROUTES =====

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and bcrypt.check_password_hash(user.password_hash, password):
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

@app.route('/admin')
@admin_required
def admin_dashboard():
    total_views = PageView.query.count()
    unique_visitors = db.session.query(PageView.ip_address).distinct().count()
    project_count = Project.query.count()
    testimonial_count = Testimonial.query.count()
    blog_count = BlogPost.query.count()
    top_pages = db.session.query(
        PageView.page, db.func.count(PageView.id).label('count')
    ).group_by(PageView.page).order_by(db.desc('count')).limit(10).all()
    recent_views = PageView.query.order_by(PageView.timestamp.desc()).limit(20).all()
    total_interests = Interest.query.count()
    top_sections = db.session.query(
        Interest.section, db.func.count(Interest.id).label('count')
    ).group_by(Interest.section).order_by(db.desc('count')).limit(10).all()
    return render_template('admin/dashboard.html',
        total_views=total_views, unique_visitors=unique_visitors,
        project_count=project_count, testimonial_count=testimonial_count,
        blog_count=blog_count, top_pages=top_pages,
        recent_views=recent_views, total_interests=total_interests,
        top_sections=top_sections)

# ----- Projects -----

@app.route('/admin/projects')
@admin_required
def admin_projects():
    projects = Project.query.order_by(Project.sort_order, Project.created_at.desc()).all()
    return render_template('admin/projects.html', projects=projects)

@app.route('/admin/projects/add', methods=['GET', 'POST'])
@admin_required
def admin_project_add():
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        if not title:
            flash('Title is required.', 'error')
            return redirect(url_for('admin_project_add'))
        image_filename = ''
        if request.files.get('image'):
            file = request.files['image']
            if file and allowed_file(file.filename):
                filename = secure_filename(f"{datetime.now().timestamp()}_{file.filename}")
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                image_filename = filename
        project = Project(
            title=title,
            description=request.form.get('description', ''),
            category=request.form.get('category', ''),
            tags=request.form.get('tags', ''),
            image_filename=image_filename,
            github_url=request.form.get('github_url', ''),
            featured=bool(request.form.get('featured')),
            sort_order=int(request.form.get('sort_order', 0))
        )
        db.session.add(project)
        db.session.commit()
        flash('Project added.', 'success')
        return redirect(url_for('admin_projects'))
    return render_template('admin/project_form.html', project=None)

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
        project.featured = bool(request.form.get('featured'))
        project.sort_order = int(request.form.get('sort_order', 0))
        if request.files.get('image') and request.files['image'].filename:
            file = request.files['image']
            if allowed_file(file.filename):
                if project.image_filename:
                    old_path = os.path.join(app.config['UPLOAD_FOLDER'], project.image_filename)
                    if os.path.exists(old_path):
                        os.remove(old_path)
                filename = secure_filename(f"{datetime.now().timestamp()}_{file.filename}")
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                project.image_filename = filename
        db.session.commit()
        flash('Project updated.', 'success')
        return redirect(url_for('admin_projects'))
    return render_template('admin/project_form.html', project=project)

@app.route('/admin/projects/delete/<int:id>', methods=['POST'])
@admin_required
def admin_project_delete(id):
    project = Project.query.get_or_404(id)
    if project.image_filename:
        path = os.path.join(app.config['UPLOAD_FOLDER'], project.image_filename)
        if os.path.exists(path):
            os.remove(path)
    db.session.delete(project)
    db.session.commit()
    flash('Project deleted.', 'success')
    return redirect(url_for('admin_projects'))

# ----- Analytics + CSV Export -----

@app.route('/admin/analytics')
@admin_required
def admin_analytics():
    page = request.args.get('page', 1, type=int)
    per_page = 50
    views = PageView.query.order_by(PageView.timestamp.desc()).paginate(page=page, per_page=per_page)
    interests = Interest.query.order_by(Interest.timestamp.desc()).paginate(page=page, per_page=per_page)
    return render_template('admin/analytics.html', views=views, interests=interests)

@app.route('/admin/analytics/export.csv')
@admin_required
def admin_analytics_export():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Type', 'Page/Section', 'IP', 'User Agent', 'Timestamp'])
    for v in PageView.query.order_by(PageView.timestamp.desc()).limit(5000):
        writer.writerow(['pageview', v.page, v.ip_address or '', v.user_agent or '', v.timestamp])
    for i in Interest.query.order_by(Interest.timestamp.desc()).limit(5000):
        writer.writerow(['interest', f"{i.section}/{i.action}", i.ip_address or '', '', i.timestamp])
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
        fact = FunFact(text=text, active=bool(request.form.get('active')))
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
        avatar = ''
        if request.files.get('avatar'):
            file = request.files['avatar']
            if file and allowed_file(file.filename):
                filename = secure_filename(f"{datetime.now().timestamp()}_{file.filename}")
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                avatar = filename
        testimonial = Testimonial(name=name, role=request.form.get('role', ''),
            text=text, avatar_filename=avatar,
            active=bool(request.form.get('active')),
            sort_order=int(request.form.get('sort_order', 0)))
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
        testimonial.sort_order = int(request.form.get('sort_order', 0))
        if request.files.get('avatar') and request.files['avatar'].filename:
            file = request.files['avatar']
            if allowed_file(file.filename):
                if testimonial.avatar_filename:
                    old_path = os.path.join(app.config['UPLOAD_FOLDER'], testimonial.avatar_filename)
                    if os.path.exists(old_path):
                        os.remove(old_path)
                filename = secure_filename(f"{datetime.now().timestamp()}_{file.filename}")
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                testimonial.avatar_filename = filename
        db.session.commit()
        flash('Testimonial updated.', 'success')
        return redirect(url_for('admin_testimonials'))
    return render_template('admin/testimonial_form.html', testimonial=testimonial)

@app.route('/admin/testimonials/delete/<int:id>', methods=['POST'])
@admin_required
def admin_testimonial_delete(id):
    testimonial = Testimonial.query.get_or_404(id)
    if testimonial.avatar_filename:
        path = os.path.join(app.config['UPLOAD_FOLDER'], testimonial.avatar_filename)
        if os.path.exists(path):
            os.remove(path)
    db.session.delete(testimonial)
    db.session.commit()
    flash('Testimonial deleted.', 'success')
    return redirect(url_for('admin_testimonials'))

# ----- Blog -----

@app.route('/admin/blog')
@admin_required
def admin_blog():
    posts = BlogPost.query.order_by(BlogPost.created_at.desc()).all()
    return render_template('admin/blog.html', posts=posts)

@app.route('/admin/blog/add', methods=['GET', 'POST'])
@admin_required
def admin_blog_add():
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        content = request.form.get('content', '').strip()
        if not title or not content:
            flash('Title and content are required.', 'error')
            return redirect(url_for('admin_blog_add'))
        slug = slugify(title)
        existing = BlogPost.query.filter_by(slug=slug).first()
        if existing:
            slug = f"{slug}-{int(datetime.now().timestamp())}"
        image = ''
        if request.files.get('image'):
            file = request.files['image']
            if file and allowed_file(file.filename):
                filename = secure_filename(f"{datetime.now().timestamp()}_{file.filename}")
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                image = filename
        post = BlogPost(title=title, slug=slug, content=content,
            summary=request.form.get('summary', ''),
            image_filename=image,
            published=bool(request.form.get('published')))
        db.session.add(post)
        db.session.commit()
        flash('Blog post created.', 'success')
        return redirect(url_for('admin_blog'))
    return render_template('admin/blog_form.html', post=None)

@app.route('/admin/blog/edit/<int:id>', methods=['GET', 'POST'])
@admin_required
def admin_blog_edit(id):
    post = BlogPost.query.get_or_404(id)
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        content = request.form.get('content', '').strip()
        if not title or not content:
            flash('Title and content are required.', 'error')
            return redirect(url_for('admin_blog_edit', id=id))
        post.title = title
        post.content = content
        post.summary = request.form.get('summary', '')
        post.published = bool(request.form.get('published'))
        if request.files.get('image') and request.files['image'].filename:
            file = request.files['image']
            if allowed_file(file.filename):
                if post.image_filename:
                    old_path = os.path.join(app.config['UPLOAD_FOLDER'], post.image_filename)
                    if os.path.exists(old_path):
                        os.remove(old_path)
                filename = secure_filename(f"{datetime.now().timestamp()}_{file.filename}")
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                post.image_filename = filename
        db.session.commit()
        flash('Blog post updated.', 'success')
        return redirect(url_for('admin_blog'))
    return render_template('admin/blog_form.html', post=post)

@app.route('/admin/blog/delete/<int:id>', methods=['POST'])
@admin_required
def admin_blog_delete(id):
    post = BlogPost.query.get_or_404(id)
    if post.image_filename:
        path = os.path.join(app.config['UPLOAD_FOLDER'], post.image_filename)
        if os.path.exists(path):
            os.remove(path)
    db.session.delete(post)
    db.session.commit()
    flash('Blog post deleted.', 'success')
    return redirect(url_for('admin_blog'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        if not User.query.first():
            hashed = bcrypt.generate_password_hash('admin123').decode('utf-8')
            db.session.add(User(username='admin', password_hash=hashed))
            db.session.commit()
            print('Default admin user created: admin / admin123')
    app.run(debug=True, host='0.0.0.0', port=5000)
