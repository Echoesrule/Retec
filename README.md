# RETEC — Portfolio

Personal portfolio website for RETEC, built with Flask. Features an admin dashboard, project showcase, blog, testimonials, analytics, and a black-and-white editorial design.

## Stack

- **Backend:** Python, Flask, SQLAlchemy, SQLite (dev) / PostgreSQL (prod)
- **Frontend:** Jinja2 templates, vanilla CSS, vanilla JS
- **Icons:** Font Awesome 6
- **Typography:** Inter + DM Serif Display

## Features

- Portfolio project showcase with GitHub API fallback
- Blog with admin CRUD, slugs, and HTML content
- Testimonial management
- Analytics (page views, section interest tracking)
- Fun fact ticker (floating bottom-left)
- WhatsApp contact button (floating bottom-right)
- Contact form with spam protection (honeypot + rate limiting)
- SMTP email support
- CV page
- Category-based project filtering
- SEO meta tags + Open Graph
- Page transition animations
- Admin panel at `/admin`

## Local Setup

```bash
pip install -r requirements.txt
python app.py
```

The app runs on `http://localhost:5000`. Admin credentials: `admin` / `admin123`.

## Deploy (Render)

1. Push this repo to GitHub
2. On Render: New > Web Service → connect repo
3. **Build Command:** `pip install -r requirements.txt`
4. **Start Command:** `gunicorn app:app`
5. Add a Render PostgreSQL database and set `DATABASE_URL` env var
6. Set `SECRET_KEY` env var
7. Deploy

## Environment Variables

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string (Render) |
| `SECRET_KEY` | Flask session secret key |
| `MAIL_SERVER` | SMTP server (optional) |
| `MAIL_PORT` | SMTP port (default 587) |
| `MAIL_USERNAME` | SMTP username |
| `MAIL_PASSWORD` | SMTP password |
| `MAIL_TO` | Contact form recipient |
