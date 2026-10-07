from django import forms


class LetterForm(forms.Form):
    name = forms.CharField(max_length=60)
    letter = forms.CharField(min_length=20)
