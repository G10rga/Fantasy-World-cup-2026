from flask_wtf import FlaskForm
from wtforms import IntegerField, PasswordField, StringField
from wtforms.validators import DataRequired, Email, EqualTo, Length, Optional


class NullableIntegerField(IntegerField):
    """IntegerField that treats null/empty JSON values as unset (Optional)."""

    def process_formdata(self, valuelist):
        if not valuelist or valuelist[0] in (None, "", "null", "undefined"):
            self.data = None
            return
        super().process_formdata(valuelist)


class RegisterForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email()])
    username = StringField("Username", validators=[DataRequired(), Length(min=3, max=80)])
    password = PasswordField("Password", validators=[DataRequired(), Length(min=8)])
    password_confirm = PasswordField(
        "Confirm Password",
        validators=[DataRequired(), EqualTo("password", message="Passwords must match")],
    )
    supported_nation_id = NullableIntegerField("Supported Nation", validators=[Optional()])


class LoginForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired()])
