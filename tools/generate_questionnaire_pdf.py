"""Render the public Discovery Questionnaire to a printable PDF.

The sections and fields come straight from forms.QUESTIONNAIRE_SECTIONS, so the
PDF can never drift from the /start-a-project page. Branding (logo mark, slogan,
MADE Mirage display font) reuses the files already in static/.

Usage:
    .venv/bin/python tools/generate_questionnaire_pdf.py [output.pdf]

No database is touched; only forms.py is imported.
"""

import base64
import html
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from forms import QUESTIONNAIRE_SECTIONS  # noqa: E402

FONT_DIR = ROOT / 'static' / 'fonts'
DEFAULT_OUTPUT = ROOT / 'RETEC-Project-Questionnaire.pdf'

SLOGAN = 'Biz Yako. Tech Yetu.'
LEAD = ('The more you share, the sharper the proposal. Every answer goes straight '
        'to the RETEC team — scope, timeline and price are prepared from what '
        'you write here.')
META = 'About 10–15 minutes · Required fields are marked · Nothing is charged or committed.'


def _font_face(family, filename, weight, style='normal'):
    path = FONT_DIR / filename
    if not path.exists():
        return ''
    encoded = base64.b64encode(path.read_bytes()).decode('ascii')
    return (
        "@font-face{font-family:'%s';font-style:%s;font-weight:%s;"
        "src:url(data:font/otf;base64,%s) format('opentype');}" %
        (family, style, weight, encoded)
    )


def _logo_svg():
    path = ROOT / 'static' / 'images' / 'logo.svg'
    svg = path.read_text(encoding='utf-8')
    return svg.replace('currentColor', '#111111')


def _field_html(spec):
    label = html.escape(spec['label'])
    required = ' <span class="req">*</span>' if spec.get('required') else ''
    ftype = spec['type']
    parts = ['<div class="field">',
             '<div class="field__label">%s%s</div>' % (label, required)]
    if spec.get('help'):
        parts.append('<div class="field__help">%s</div>' % html.escape(spec['help']))

    if ftype in ('text', 'email', 'url', 'date'):
        parts.append('<div class="line"></div>')
    elif ftype == 'textarea':
        rows = max(2, min(int(spec.get('rows', 3)), 4))
        parts.append('<div class="lines">%s</div>' % ('<div class="line"></div>' * rows))
    elif ftype in ('radio', 'select'):
        choices = ''.join(
            '<span class="choice"><span class="circle"></span>%s</span>' % html.escape(text)
            for _, text in spec['options']
        )
        parts.append('<div class="choices">%s</div>' % choices)
    elif ftype == 'checkboxes':
        choices = ''.join(
            '<span class="choice"><span class="box"></span>%s</span>' % html.escape(text)
            for _, text in spec['options']
        )
        parts.append('<div class="choices choices--check">%s</div>' % choices)
    else:
        parts.append('<div class="line"></div>')

    parts.append('</div>')
    return ''.join(parts)


def _section_html(section):
    fields = ''.join(_field_html(f) for f in section['fields'])
    return (
        '<section class="section">'
        '<div class="section__head">'
        '<span class="section__letter">%s</span>'
        '<div><h2 class="section__title">%s</h2>'
        '<p class="section__intro">%s</p></div>'
        '</div>%s</section>' %
        (html.escape(section['letter']), html.escape(section['title']),
         html.escape(section['intro']), fields)
    )


def build_html():
    fonts = ''.join([
        _font_face('MADE Mirage', 'MADE Mirage Regular PERSONAL USE.otf', 400),
        _font_face('MADE Mirage', 'MADE Mirage Medium PERSONAL USE.otf', 500),
        _font_face('MADE Mirage', 'MADE Mirage Bold PERSONAL USE.otf', 700),
    ])
    sections = ''.join(_section_html(s) for s in QUESTIONNAIRE_SECTIONS)
    return """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>RETEC Project Discovery Questionnaire</title>
<style>
%(fonts)s
@page { size: A4; margin: 18mm 16mm 20mm; }
* { box-sizing: border-box; }
html, body { margin: 0; }
body {
  font-family: 'Inter', 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
  color: #1a1a1a; font-size: 10.5pt; line-height: 1.5;
  -webkit-print-color-adjust: exact; print-color-adjust: exact;
}
.cover { border-bottom: 2px solid #111; padding-bottom: 14px; margin-bottom: 20px; }
.cover__logo { height: 42px; }
.cover__slogan { margin: 10px 0 20px; font-family: 'MADE Mirage', Georgia, serif;
  font-style: italic; font-size: 13pt; color: #6a645c; letter-spacing: .3px; }
.cover__title { font-family: 'MADE Mirage', Georgia, serif; font-weight: 700;
  font-size: 26pt; line-height: 1.1; margin: 0 0 8px; }
.cover__title span { color: #6a645c; }
.cover__lead { margin: 0 0 6px; max-width: 150mm; }
.cover__meta { margin: 0; font-size: 9pt; color: #6a645c; }
.section { break-inside: auto; margin-bottom: 14px; }
.section__head { display: flex; gap: 10px; align-items: flex-start;
  border-top: 1px solid #111; padding-top: 10px; margin-bottom: 10px; break-after: avoid; }
.section__letter { flex: 0 0 auto; width: 22px; height: 22px; border: 1.4px solid #111;
  border-radius: 50%%; display: flex; align-items: center; justify-content: center;
  font-size: 10pt; font-weight: 700; }
.section__title { font-family: 'MADE Mirage', Georgia, serif; font-weight: 600;
  font-size: 14pt; margin: 0; }
.section__intro { margin: 1px 0 0; font-size: 9pt; color: #6a645c; }
.field { break-inside: avoid; margin: 9px 0; }
.field__label { font-weight: 600; font-size: 10pt; margin-bottom: 4px; }
.field__label .req { color: #c62828; }
.field__help { font-size: 8.5pt; color: #7a746c; margin: -1px 0 5px; }
.line { border-bottom: 1px solid #c9c4bc; height: 15px; }
.lines .line { height: 17px; }
.choices { display: flex; flex-wrap: wrap; gap: 6px 20px; padding: 3px 0; }
.choices--check { gap: 4px 18px; }
.choice { display: inline-flex; align-items: center; gap: 6px; font-size: 9.5pt; }
.circle, .box { display: inline-block; width: 11px; height: 11px; border: 1.3px solid #555; }
.circle { border-radius: 50%%; }
.box { border-radius: 2px; }
.footnote { margin-top: 16px; border-top: 1px solid #111; padding-top: 10px;
  font-size: 9pt; color: #6a645c; }
</style></head>
<body>
  <header class="cover">
    <div class="cover__logo">%(logo)s</div>
    <p class="cover__slogan">%(slogan)s</p>
    <h1 class="cover__title">Project Discovery<br><span>Questionnaire</span></h1>
    <p class="cover__lead">%(lead)s</p>
    <p class="cover__meta">%(meta)s</p>
  </header>
  %(sections)s
  <p class="footnote">Prefer to talk first? Email contact.retec@gmail.com or message
  us on WhatsApp at +254 114 581 500. Thank you — we will be in touch shortly.</p>
</body></html>""" % {
        'fonts': fonts,
        'logo': _logo_svg(),
        'slogan': html.escape(SLOGAN),
        'lead': html.escape(LEAD),
        'meta': html.escape(META),
        'sections': sections,
    }


def _launch_chromium(playwright):
    """Launch Chromium, preferring the full build when only that is installed.

    Playwright's default launch wants the separate `chromium-headless-shell`
    download; on machines that already have the full Chromium, `channel`
    selects it. Falls back to the default so either install works.
    """
    try:
        return playwright.chromium.launch(channel='chromium')
    except Exception:
        return playwright.chromium.launch()


def render_pdf(output_path, html_string):
    from playwright.sync_api import sync_playwright

    output_path.parent.mkdir(parents=True, exist_ok=True)
    footer = (
        '<div style="width:100%;font-family:Inter,Arial,sans-serif;font-size:8pt;'
        'color:#6a645c;padding:0 16mm;display:flex;justify-content:space-between;">'
        '<span>RETEC &middot; Biz Yako. Tech Yetu.</span>'
        '<span>Page <span class="pageNumber"></span> of <span class="totalPages"></span></span>'
        '</div>'
    )
    with sync_playwright() as playwright:
        browser = _launch_chromium(playwright)
        page = browser.new_page()
        page.set_content(html_string, wait_until='load')
        page.emulate_media(media='print')
        page.pdf(
            path=str(output_path),
            format='A4',
            print_background=True,
            display_header_footer=True,
            header_template='<div></div>',
            footer_template=footer,
            margin={'top': '16mm', 'bottom': '18mm', 'left': '16mm', 'right': '16mm'},
        )
        browser.close()


def main(argv):
    output = Path(argv[1]) if len(argv) > 1 else DEFAULT_OUTPUT
    render_pdf(output, build_html())
    print('Wrote %s' % output)


if __name__ == '__main__':
    main(sys.argv)
