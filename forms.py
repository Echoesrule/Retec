from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, SubmitField
from wtforms.validators import DataRequired, Length, Email

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