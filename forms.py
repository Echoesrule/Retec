import re
from urllib.parse import urlsplit

from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, SubmitField
from wtforms.validators import DataRequired, Length, Email, Optional, ValidationError

PROJECT_TYPES = [
    ('', 'Select a project type'),
    ('Business Website', 'Business Website'),
    ('Web Application', 'Web Application'),
    ('Custom Software', 'Custom Software'),
    ('API / Backend', 'API / Backend'),
    ('Website Maintenance', 'Website Maintenance'),
    ('Other', 'Other'),
]

BUDGET_OPTIONS = [
    ('', 'Select a budget range'),
    ('Under KSh 15,000', 'Under KSh 15,000'),
    ('KSh 15,000-30,000', 'KSh 15,000-30,000'),
    ('KSh 30,000-50,000', 'KSh 30,000-50,000'),
    ('KSh 50,000+', 'KSh 50,000+'),
    ('Not sure yet', 'Not sure yet'),
]

COLLABORATION_TYPES = [
    ('', 'Select a collaboration type'),
    ('Designer', 'Designer'),
    ('Developer', 'Developer'),
    ('Agency', 'Agency'),
    ('Creative Studio', 'Creative Studio'),
    ('Marketing', 'Marketing'),
    ('Specialist', 'Specialist'),
    ('Technology Partner', 'Technology Partner'),
    ('Other', 'Other'),
]


class OptionalHttpUrl:
    """Validates an optional website/portfolio field.

    People type bare domains ("studio.com") as often as full URLs, so a missing
    scheme is normalised to https:// rather than rejected. Two things are
    rejected outright rather than normalised:

      * any non-http(s) scheme, so `javascript:`, `data:` and `file:` never
        reach the database or the admin review screen as a live link;
      * embedded credentials, so the admin review screen cannot render a link
        that points somewhere other than the host it appears to.

    Requires `Optional()` to be declared first so a blank field is allowed.
    """

    message = 'Please enter a valid website address, or leave this blank.'
    # A scheme is only a scheme when `//` follows it; otherwise "localhost:3000"
    # would parse as a scheme named "localhost". Schemes that are conventionally
    # written without `//` (javascript:, mailto:, data:) are listed explicitly
    # so they cannot be smuggled through as a host:port pair.
    _SCHEME = re.compile(r'^([a-z][a-z0-9+.\-]*)://', re.I)
    _BARE_SCHEME = re.compile(r'^(javascript|data|vbscript|file|blob|about|mailto|tel|sms|ftp):', re.I)
    # A host is a dotted name, an IPv4 literal, or localhost. No path,
    # credentials, port or wildcard survives this.
    _HOST = re.compile(r'^(?:localhost|(?:[a-z0-9](?:[a-z0-9\-]*[a-z0-9])?\.)+[a-z]{2,}|\d{1,3}(?:\.\d{1,3}){3})$', re.I)

    def __call__(self, form, field):
        value = (field.data or '').strip()
        if not value:
            return
        if self._BARE_SCHEME.match(value):
            raise ValidationError(self.message)
        scheme = self._SCHEME.match(value)
        if scheme:
            if scheme.group(1).lower() not in ('http', 'https'):
                raise ValidationError(self.message)
        else:
            value = 'https://' + value
        parts = urlsplit(value)
        if parts.scheme.lower() not in ('http', 'https') or parts.username or parts.password:
            raise ValidationError(self.message)
        try:
            host = parts.hostname or ''
            parts.port  # raises ValueError on a malformed port
        except ValueError:
            raise ValidationError(self.message)
        if not self._HOST.match(host):
            raise ValidationError(self.message)
        field.data = value


class ContactForm(FlaskForm):
    name = StringField('Name', validators=[
        DataRequired(message='Please enter your name.'),
        Length(min=2, max=100, message='Name must be 2-100 characters.')
    ])
    business = StringField('Business / Organization', validators=[
        Length(max=200, message='Business name must be 200 characters or fewer.')
    ])
    email = StringField('Email', validators=[
        DataRequired(message='Please enter your email.'),
        Email(message='Please enter a valid email address.')
    ])
    project_type = SelectField('Project Type', choices=PROJECT_TYPES)
    budget = SelectField('Budget', choices=BUDGET_OPTIONS)
    message = TextAreaField('Project Details', validators=[
        DataRequired(message='Please tell us about your project.'),
        Length(min=10, max=5000, message='Project details must be 10-5000 characters.')
    ])
    submit = SubmitField('Send Project Inquiry')


class PartnerForm(FlaskForm):
    """Become a Partner / collaboration application.

    Mirrors ContactForm so both public forms validate, render and submit through
    the same FlaskForm + CSRF + honeypot + rate-limit path.
    """

    name = StringField('Full Name', validators=[
        DataRequired(message='Please enter your name.'),
        Length(min=2, max=100, message='Name must be 2-100 characters.')
    ])
    email = StringField('Email', validators=[
        DataRequired(message='Please enter your email.'),
        Email(message='Please enter a valid email address.')
    ])
    company = StringField('Company / Studio', validators=[
        Optional(),
        Length(max=200, message='Company name must be 200 characters or fewer.')
    ])
    role = StringField('Role / Specialty', validators=[
        DataRequired(message='Please tell us your role or specialty.'),
        Length(max=150, message='Role must be 150 characters or fewer.')
    ])
    portfolio = StringField('Website / Portfolio', validators=[
        Optional(), OptionalHttpUrl()
    ])
    collaboration_type = SelectField('Collaboration Type', choices=COLLABORATION_TYPES, validators=[
        DataRequired(message='Please choose a collaboration type.')
    ])
    expertise = StringField('Areas of Expertise', validators=[
        DataRequired(message='Please list your areas of expertise.'),
        Length(max=300, message='Expertise must be 300 characters or fewer.')
    ])
    message = TextAreaField('Tell Us About Yourself', validators=[
        DataRequired(message='Please tell us a little about yourself.'),
        Length(min=20, max=5000, message='Please write between 20 and 5000 characters.')
    ])
    submit = SubmitField('Submit Application')
