import re
from urllib.parse import urlsplit

from flask_wtf import FlaskForm
from wtforms import (
    BooleanField, DateField, RadioField, SelectField, StringField,
    SubmitField, TextAreaField,
)
from wtforms.validators import DataRequired, Email, Length, Optional, ValidationError

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


# ===== DISCOVERY QUESTIONNAIRE =====
#
# The public questionnaire at /start-a-project is spec-driven: one list of
# sections and fields drives the WTForms field construction, the template
# rendering and the stored response keys, so the three can never drift apart.

QUESTIONNAIRE_YES_NO = [
    ('yes', 'Yes'),
    ('no', 'No'),
    ('unsure', 'Not sure'),
]

QUESTIONNAIRE_CONTACT_METHODS = [
    ('email', 'Email'),
    ('phone', 'Phone call'),
    ('whatsapp', 'WhatsApp'),
    ('any', 'Any is fine'),
]

QUESTIONNAIRE_BUDGET_RANGES = [
    ('below_15000', 'Below KSh 15,000'),
    ('15000_25000', 'KSh 15,000–25,000'),
    ('25000_40000', 'KSh 25,000–40,000'),
    ('40000_75000', 'KSh 40,000–75,000'),
    ('75000_plus', 'KSh 75,000+'),
    ('not_sure', 'Not sure / Need guidance'),
]

QUESTIONNAIRE_BUDGET_LABELS = dict(QUESTIONNAIRE_BUDGET_RANGES)

QUESTIONNAIRE_REQUIREMENTS = [
    ('business_website', 'Business website'),
    ('portfolio', 'Portfolio'),
    ('web_application', 'Web application'),
    ('booking_system', 'Booking system'),
    ('ecommerce', 'Ecommerce'),
    ('payments', 'Payments'),
    ('user_accounts', 'User accounts'),
    ('admin_dashboard', 'Admin dashboard'),
    ('cms', 'CMS (content management)'),
    ('blog', 'Blog'),
    ('search', 'Search'),
    ('notifications', 'Notifications'),
    ('email', 'Email'),
    ('whatsapp', 'WhatsApp integration'),
    ('api_integration', 'API integration'),
    ('database', 'Database'),
    ('analytics', 'Analytics'),
    ('authentication', 'Authentication / login'),
    ('other', 'Other'),
]

QUESTIONNAIRE_REQUIREMENT_LABELS = dict(QUESTIONNAIRE_REQUIREMENTS)

QUESTIONNAIRE_SECTIONS = [
    {
        'key': 'client',
        'letter': 'A',
        'title': 'Client Information',
        'intro': 'Who we are dealing with and how to reach you.',
        'fields': [
            {'name': 'full_name', 'label': 'Full name', 'type': 'text',
             'required': True, 'max': 100, 'placeholder': 'Your full name'},
            {'name': 'business_name', 'label': 'Business / organization name', 'type': 'text',
             'max': 200, 'placeholder': 'Leave blank if you are enquiring as an individual'},
            {'name': 'email', 'label': 'Email', 'type': 'email',
             'required': True, 'max': 255, 'placeholder': 'you@example.com'},
            {'name': 'phone', 'label': 'Phone / WhatsApp', 'type': 'text',
             'max': 50, 'placeholder': 'e.g. 0712 345 678'},
            {'name': 'business_location', 'label': 'Business location', 'type': 'text',
             'max': 200, 'placeholder': 'Town / city / country'},
            {'name': 'role_position', 'label': 'Role / position', 'type': 'text',
             'max': 150, 'placeholder': 'e.g. Founder, Marketing Manager'},
            {'name': 'contact_method', 'label': 'Preferred contact method', 'type': 'select',
             'options': QUESTIONNAIRE_CONTACT_METHODS},
        ],
    },
    {
        'key': 'business',
        'letter': 'B',
        'title': 'Business Information',
        'intro': 'What the business does today, and what digital footprint already exists.',
        'fields': [
            {'name': 'what_business_does', 'label': 'What does the business do?', 'type': 'textarea',
             'max': 2000, 'rows': 3},
            {'name': 'products_services', 'label': 'What products / services does it offer?', 'type': 'textarea',
             'max': 2000, 'rows': 3},
            {'name': 'target_customers', 'label': 'Who are the target customers?', 'type': 'textarea',
             'max': 2000, 'rows': 3},
            {'name': 'differentiators', 'label': 'What makes the business different?', 'type': 'textarea',
             'max': 2000, 'rows': 3},
            {'name': 'current_presence', 'label': 'Current digital presence', 'type': 'textarea',
             'max': 2000, 'rows': 3,
             'help': 'Where the business shows up online today — social media, marketplaces, directories, nothing yet.'},
            {'name': 'existing_website', 'label': 'Existing website', 'type': 'url',
             'max': 300, 'placeholder': 'https:// or none yet'},
            {'name': 'existing_social', 'label': 'Existing social media', 'type': 'text',
             'max': 300, 'placeholder': 'e.g. @yourbusiness on Instagram, Facebook page link'},
            {'name': 'existing_domain', 'label': 'Existing domain', 'type': 'text',
             'max': 200, 'placeholder': 'e.g. yourbusiness.co.ke or none yet'},
            {'name': 'existing_hosting', 'label': 'Existing hosting', 'type': 'text',
             'max': 200, 'placeholder': 'Provider name, or none yet'},
            {'name': 'existing_systems', 'label': 'Existing systems / tools', 'type': 'textarea',
             'max': 1500, 'rows': 2,
             'help': 'Spreadsheets, accounting software, POS, booking tools, etc.'},
        ],
    },
    {
        'key': 'project',
        'letter': 'C',
        'title': 'Project Overview',
        'intro': 'What you want built, and why it matters now.',
        'fields': [
            {'name': 'looking_to_build', 'label': 'What are you looking to build?', 'type': 'textarea',
             'required': True, 'max': 3000, 'rows': 4,
             'placeholder': 'Describe the website, application or system you have in mind.'},
            {'name': 'problem_solving', 'label': 'What problem are you trying to solve?', 'type': 'textarea',
             'max': 3000, 'rows': 3},
            {'name': 'why_now', 'label': 'Why are you looking to solve it now?', 'type': 'textarea',
             'max': 2000, 'rows': 3},
            {'name': 'current_process', 'label': 'What currently happens without this solution?', 'type': 'textarea',
             'max': 2000, 'rows': 3},
            {'name': 'success_looks_like', 'label': 'What would success look like?', 'type': 'textarea',
             'max': 3000, 'rows': 3},
            {'name': 'finished_product_helps', 'label': 'What should the finished product help you accomplish?', 'type': 'textarea',
             'max': 2000, 'rows': 3},
        ],
    },
    {
        'key': 'requirements',
        'letter': 'D',
        'title': 'Functional Requirements',
        'intro': 'Tick everything that is relevant. Nothing here commits you to anything.',
        'fields': [
            {'name': 'requirements', 'label': 'Which of these do you need?', 'type': 'checkboxes',
             'options': QUESTIONNAIRE_REQUIREMENTS},
            {'name': 'requirements_other', 'label': 'Other requirements', 'type': 'textarea',
             'max': 1000, 'rows': 2,
             'help': 'Anything not covered above — integrations, workflows, or features specific to your business.'},
        ],
    },
    {
        'key': 'content',
        'letter': 'E',
        'title': 'Content',
        'intro': 'What material already exists, and who will supply the rest.',
        'fields': [
            {'name': 'has_logo', 'label': 'Do you already have a logo?', 'type': 'radio',
             'options': QUESTIONNAIRE_YES_NO},
            {'name': 'has_brand_guidelines', 'label': 'Do you have brand guidelines?', 'type': 'radio',
             'options': QUESTIONNAIRE_YES_NO},
            {'name': 'has_images', 'label': 'Do you have images / photography?', 'type': 'radio',
             'options': QUESTIONNAIRE_YES_NO},
            {'name': 'has_copy', 'label': 'Do you have text / copy for the pages?', 'type': 'radio',
             'options': QUESTIONNAIRE_YES_NO},
            {'name': 'has_product_info', 'label': 'Do you have product / service information?', 'type': 'radio',
             'options': QUESTIONNAIRE_YES_NO},
            {'name': 'has_documents', 'label': 'Are there existing documents we should see?', 'type': 'radio',
             'options': QUESTIONNAIRE_YES_NO},
            {'name': 'content_provider', 'label': 'Who will provide the content?', 'type': 'text',
             'max': 200, 'placeholder': 'e.g. our marketer, the founder, RETEC'},
            {'name': 'content_to_create', 'label': 'What content still needs to be created?', 'type': 'textarea',
             'max': 2000, 'rows': 3},
        ],
    },
    {
        'key': 'design',
        'letter': 'F',
        'title': 'Design',
        'intro': 'Direction, references and anything we should match or avoid.',
        'fields': [
            {'name': 'preferred_style', 'label': 'Preferred visual style', 'type': 'textarea',
             'max': 1500, 'rows': 2,
             'placeholder': 'e.g. minimal and modern, bold and colourful, corporate, playful'},
            {'name': 'preferred_colors', 'label': 'Preferred colors', 'type': 'text',
             'max': 300, 'placeholder': 'Any colors you like, or "no preference"'},
            {'name': 'brand_colors', 'label': 'Existing brand colors', 'type': 'text',
             'max': 300, 'placeholder': 'Hex codes, names, or a link to your brand file'},
            {'name': 'liked_websites', 'label': 'Websites you like', 'type': 'textarea',
             'max': 2000, 'rows': 2, 'help': 'One per line, with a word about what you like about each.'},
            {'name': 'disliked_websites', 'label': 'Websites you dislike', 'type': 'textarea',
             'max': 2000, 'rows': 2, 'help': 'One per line, with a word about what you would avoid.'},
            {'name': 'design_references', 'label': 'Other design references', 'type': 'textarea',
             'max': 2000, 'rows': 2, 'help': 'Screenshots, Pinterest boards, competitor sites — describe or link them.'},
            {'name': 'brand_assets', 'label': 'Existing brand assets', 'type': 'textarea',
             'max': 1500, 'rows': 2, 'help': 'Logo files, fonts, illustrations, templates you already own.'},
        ],
    },
    {
        'key': 'technical',
        'letter': 'G',
        'title': 'Technical / Integration Requirements',
        'intro': 'Anything the solution has to work with.',
        'fields': [
            {'name': 'existing_software', 'label': 'Existing software', 'type': 'textarea',
             'max': 1500, 'rows': 2},
            {'name': 'apis', 'label': 'APIs', 'type': 'text', 'max': 300,
             'placeholder': 'Any APIs you already use or need'},
            {'name': 'payment_providers', 'label': 'Payment providers', 'type': 'text',
             'max': 300, 'placeholder': 'e.g. M-Pesa, Stripe, bank transfer'},
            {'name': 'email_services', 'label': 'Email services', 'type': 'text',
             'max': 300, 'placeholder': 'e.g. Google Workspace, transactional email'},
            {'name': 'hosting_needs', 'label': 'Hosting', 'type': 'text', 'max': 300,
             'placeholder': 'Preferred host, or "no preference"'},
            {'name': 'domain_needs', 'label': 'Domain', 'type': 'text', 'max': 300,
             'placeholder': 'Domain you want, or "need help choosing"'},
            {'name': 'third_party_services', 'label': 'Third-party services', 'type': 'text',
             'max': 300, 'placeholder': 'Any other services involved'},
            {'name': 'required_integrations', 'label': 'Required integrations', 'type': 'textarea',
             'max': 1500, 'rows': 2,
             'help': 'What must connect to what (e.g. website → M-Pesa → SMS).'},
            {'name': 'existing_database', 'label': 'Existing database / system', 'type': 'textarea',
             'max': 1500, 'rows': 2,
             'help': 'Spreadsheets, legacy software or databases we would need to import from or connect to.'},
        ],
    },
    {
        'key': 'timeline',
        'letter': 'H',
        'title': 'Timeline',
        'intro': 'Dates that matter, and how flexible they are.',
        'fields': [
            {'name': 'desired_launch', 'label': 'Desired launch date', 'type': 'date'},
            {'name': 'important_deadline', 'label': 'Important deadline', 'type': 'text',
             'max': 300, 'placeholder': 'e.g. product launch, event, tender submission'},
            {'name': 'deadline_reason', 'label': 'Reason for the deadline', 'type': 'textarea',
             'max': 1000, 'rows': 2},
            {'name': 'timeline_flexible', 'label': 'Is the timeline flexible?', 'type': 'radio',
             'options': QUESTIONNAIRE_YES_NO},
        ],
    },
    {
        'key': 'budget',
        'letter': 'I',
        'title': 'Budget',
        'intro': 'A range is enough — final pricing always depends on the confirmed scope.',
        'fields': [
            {'name': 'budget_range', 'label': 'Budget range', 'type': 'select',
             'options': QUESTIONNAIRE_BUDGET_RANGES},
        ],
    },
    {
        'key': 'decisions',
        'letter': 'J',
        'title': 'Decision Making',
        'intro': 'Who we take instructions and approval from.',
        'fields': [
            {'name': 'decision_maker', 'label': 'Who makes the final decision?', 'type': 'text',
             'max': 200, 'placeholder': 'Name and role'},
            {'name': 'other_stakeholders', 'label': 'Are there other stakeholders?', 'type': 'text',
             'max': 300, 'placeholder': 'Who else is involved in the decision'},
            {'name': 'design_approver', 'label': 'Who should approve designs / content?', 'type': 'text',
             'max': 200},
            {'name': 'delivery_approver', 'label': 'Who should approve final delivery?', 'type': 'text',
             'max': 200},
        ],
    },
    {
        'key': 'success',
        'letter': 'K',
        'title': 'Success',
        'intro': 'The two questions that matter most.',
        'fields': [
            {'name': 'project_success', 'label': 'What would make you consider this project successful?',
             'type': 'textarea', 'required': True, 'max': 3000, 'rows': 4},
            {'name': 'anything_else', 'label': 'Is there anything important we have not asked about?',
             'type': 'textarea', 'max': 3000, 'rows': 4},
        ],
    },
]

# Flat field lookup: name -> spec, in document order.
QUESTIONNAIRE_FIELDS = [
    field
    for section in QUESTIONNAIRE_SECTIONS
    for field in section['fields']
]
QUESTIONNAIRE_FIELD_SPECS = {field['name']: field for field in QUESTIONNAIRE_FIELDS}

# Field names copied onto the internal client record when a questionnaire is
# submitted, so the record is readable without opening the full response set.
QUESTIONNAIRE_RECORD_FIELDS = (
    'full_name', 'business_name', 'email', 'phone', 'business_location',
    'role_position', 'contact_method', 'looking_to_build', 'problem_solving',
    'budget_range',
)

_DISCOVERY_FIELD_TYPES = ('text', 'email', 'url', 'textarea', 'select', 'radio', 'date', 'checkboxes')


def _discovery_validators(spec):
    label = spec['label']
    validators = []
    if spec.get('required'):
        validators.append(DataRequired(message='Please answer "%s".' % label))
    elif spec['type'] != 'checkboxes':
        # Optional() must precede any validator that would otherwise reject an
        # empty value (Length on an empty string is fine, Email is not).
        validators.append(Optional())
    if spec.get('max'):
        validators.append(Length(
            max=spec['max'],
            message='%s must be %d characters or fewer.' % (label, spec['max']),
        ))
    if spec['type'] == 'email' and spec.get('required'):
        validators.append(Email(message='Please enter a valid email address.'))
    return validators


def _build_discovery_form():
    """Construct the questionnaire form from QUESTIONNAIRE_SECTIONS.

    Built with type() rather than a class body so the spec stays the single
    source of truth for field names, labels, choices and validation.
    """
    field_map = {}
    for spec in QUESTIONNAIRE_FIELDS:
        ftype = spec['type']
        if ftype not in _DISCOVERY_FIELD_TYPES:
            raise ValueError('Unknown questionnaire field type: %s' % ftype)
        label = spec['label']
        validators = _discovery_validators(spec)
        if ftype == 'textarea':
            field_map[spec['name']] = TextAreaField(label, validators=validators)
        elif ftype == 'radio':
            field_map[spec['name']] = RadioField(
                label, choices=spec['options'], validators=validators)
        elif ftype == 'date':
            field_map[spec['name']] = DateField(
                label, format='%Y-%m-%d', validators=validators)
        elif ftype == 'select':
            choices = [('', 'Select an option')] + list(spec['options'])
            field_map[spec['name']] = SelectField(
                label, choices=choices, validators=validators)
        elif ftype == 'checkboxes':
            # One BooleanField per option, namespaced so every option is an
            # independent input the template can render and read back.
            for value, option_label in spec['options']:
                field_map['%s__%s' % (spec['name'], value)] = BooleanField(option_label)
        else:  # text / email / url
            field_map[spec['name']] = StringField(label, validators=validators)
    field_map['submit'] = SubmitField('Submit Questionnaire')
    return type('DiscoveryQuestionnaireForm', (FlaskForm,), field_map)


DiscoveryQuestionnaireForm = _build_discovery_form()


def questionnaire_responses(form):
    """Extract a plain dict of responses from a validated form.

    Checkbox groups come back as lists of selected values; dates are stored as
    ISO strings; every string is stripped. The keys match the spec, which is
    what the admin questionnaire view renders from.
    """
    responses = {}
    for spec in QUESTIONNAIRE_FIELDS:
        name = spec['name']
        if spec['type'] == 'checkboxes':
            responses[name] = [
                value for value, _ in spec['options']
                if getattr(form, '%s__%s' % (name, value)).data
            ]
            continue
        value = getattr(form, name).data
        if value is None:
            value = ''
        if hasattr(value, 'strftime'):
            value = value.strftime('%Y-%m-%d')
        elif isinstance(value, str):
            value = value.strip()
        responses[name] = value
    return responses
