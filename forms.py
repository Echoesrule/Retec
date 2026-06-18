from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SubmitField
from wtforms.validators import DataRequired, Length, Email

class ContactForm(FlaskForm):
    name = StringField('Name', validators=[
        DataRequired(message='Please enter your name.'),
        Length(min=2, max=100, message='Name must be 2-100 characters.')
    ])
    email = StringField('Email', validators=[
        DataRequired(message='Please enter your email.'),
        Email(message='Please enter a valid email address.')
    ])
    subject = StringField('Subject', validators=[
        DataRequired(message='Please enter a subject.'),
        Length(min=3, max=200, message='Subject must be 3-200 characters.')
    ])
    message = TextAreaField('Message', validators=[
        DataRequired(message='Please enter your message.'),
        Length(min=10, max=5000, message='Message must be 10-5000 characters.')
    ])
    submit = SubmitField('Send Message')
