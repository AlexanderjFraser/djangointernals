"""The project the recording of chapter 7 sends its requests to: a town's newspaper.

`models.py` has one model, `Article`, with a slug, a headline and the moment it was published.
`views.py` has views of every kind the chapter describes: functions, plain and decorated, a
class of the project's own, and subclasses of Django's generic views that show an article,
list them, make, change and delete one, take a reader's letter through a form, and list a
month's articles. `urls.py` is the root URLconf. `stamp.py` has the one middleware of the
recording, which is turned into a decorator; `forms.py` the letter's form. `templates/` holds a
template for each view that renders one, and `files/` what the static file view is asked for.
"""
