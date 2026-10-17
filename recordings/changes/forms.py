"""The habits of the section "What changed in forms and validators", release by release: the
transitional renderer a project may still name, what a field group draws for screen readers and
what the paragraph layout draws for a field whose widget asks for a fieldset, an error class that returns a
plain string, the scheme a URL field assumes, the blank choice's label and the deprecated
setting and constant beside it, and what `EmailValidator` reports and calls. A habit that returns HTML returns it with each line's
surrounding white space and its blank lines left out. Run by recordings/changes.py under each
release; _run.py says how a habit is written.
"""
from _run import configure, habit, main

configure()


def html(text):
    """Rendered HTML, each line stripped of its surrounding white space, the blank lines left out."""
    return "\n".join(line.strip() for line in str(text).splitlines() if line.strip())


@habit('FORM_RENDERER = "django.forms.renderers.DjangoDivFormRenderer": the class of a form\'s renderer')
def div_form_renderer():
    from django import forms
    from django.test.utils import override_settings

    class NoteForm(forms.Form):
        title = forms.CharField()

    with override_settings(FORM_RENDERER="django.forms.renderers.DjangoDivFormRenderer"):
        return type(NoteForm().renderer).__name__


@habit('form["title"].as_field_group(): a required field with help text, sent empty')
def field_group_with_help_and_error():
    from django import forms

    class TitleForm(forms.Form):
        title = forms.CharField(max_length=20, help_text="At most twenty characters.")

    return html(TitleForm({"title": ""})["title"].as_field_group())


def mood_form():
    """A form of one field whose widget, RadioSelect, asks for a fieldset."""
    from django import forms

    class MoodForm(forms.Form):
        mood = forms.ChoiceField(
            choices=[("calm", "Calm"), ("stormy", "Stormy")],
            widget=forms.RadioSelect,
            help_text="How the day went.",
        )

    return MoodForm({})


@habit('form["mood"].as_field_group(): a RadioSelect field with help text, sent empty')
def field_group_with_a_fieldset_widget():
    return html(mood_form()["mood"].as_field_group())


@habit("form.as_p(): a RadioSelect field with help text, sent empty")
def paragraphs_with_a_fieldset_widget():
    return html(mood_form().as_p())


@habit('form["heading"].as_field_group(): an error class whose __str__ returns "<b>" and the message, unmarked')
def error_list_as_a_plain_string():
    from django import forms
    from django.forms.utils import ErrorList

    class BoldErrorList(ErrorList):
        def __str__(self):
            return "".join(f"<b>{error}</b>" for error in self)

    class HeadingForm(forms.Form):
        heading = forms.CharField()

    return html(HeadingForm({}, error_class=BoldErrorList)["heading"].as_field_group())


@habit('forms.URLField().clean("journal.example.com")')
def url_field_scheme():
    from django import forms
    return repr(forms.URLField().clean("journal.example.com"))


@habit('models.URLField().formfield().clean("journal.example.com"): the form field a model\'s URL field makes')
def model_url_field_scheme():
    from django.db import models
    return repr(models.URLField().formfield().clean("journal.example.com"))


@habit("forms.ModelChoiceField(Entry.objects.all()).empty_label")
def model_choice_empty_label():
    from django import forms
    from journal.models import Entry
    return repr(str(forms.ModelChoiceField(Entry.objects.all()).empty_label))


@habit('forms.ModelChoiceField(Entry.objects.all(), empty_label="").empty_label')
def model_choice_empty_label_given_empty():
    from django import forms
    from journal.models import Entry
    return repr(str(forms.ModelChoiceField(Entry.objects.all(), empty_label="").empty_label))


@habit("USE_BLANK_CHOICE_DASH = True: forms.ModelChoiceField(Entry.objects.all()).empty_label")
def use_blank_choice_dash():
    from django import forms
    from django.test.utils import override_settings
    from journal.models import Entry

    with override_settings(USE_BLANK_CHOICE_DASH=True):
        return repr(str(forms.ModelChoiceField(Entry.objects.all()).empty_label))


@habit("from django.db.models.fields import BLANK_CHOICE_DASH")
def blank_choice_dash():
    from django.db.models.fields import BLANK_CHOICE_DASH
    return repr(BLANK_CHOICE_DASH)


@habit('validate_email("entry@journal..example"): the params of the ValidationError')
def email_error_params():
    from django.core.exceptions import ValidationError
    from django.core.validators import validate_email

    try:
        validate_email("entry@journal..example")
    except ValidationError as error:
        return repr(error.params)
    return "valid"


@habit('class LocalEmailValidator(EmailValidator) defining validate_domain_part, given "entry@journal": the domains it is asked about')
def email_validate_domain_part_override():
    from django.core.validators import EmailValidator

    asked = []

    class LocalEmailValidator(EmailValidator):
        def validate_domain_part(self, domain_part):
            asked.append(domain_part)
            return domain_part == "journal" or super().validate_domain_part(domain_part)

    LocalEmailValidator()("entry@journal")
    return repr(asked)


main()
