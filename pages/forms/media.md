---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Form assets: `Media`

A widget or a form that needs stylesheets and scripts declares them in an inner class named `Media`, which `MediaDefiningClass` turns into the class's media property. Its value, a `Media` object, gathers the assets of every widget of a form, merges them in an order that keeps each declaration's own where the declarations agree, and renders them as link and script elements.

A calendar widget is no use without its script, and a page of several widgets wants each script once, with a library before the code that uses it. So a form's **assets**, the stylesheets and scripts it needs, are declared on the classes that need them and summed upwards. The form's templates write none ([Rendering a form: renderers and templates](rendering.md)): the page's template prints `{{ form.media }}`.

## Declaring assets: `MediaDefiningClass` and `media_property`

A class declares its assets in an inner class named `Media`, as the berth form does here, with two widgets that need assets and a stylesheet of its own:

```python
# harbour/fleet/forms.py
from django import forms


class CalendarInput(forms.DateInput):
    class Media:
        css = {"all": ["fleet/calendar.css"]}
        js = ["fleet/vendor.js", "fleet/calendar.js"]


class ShipNameInput(forms.TextInput):
    class Media:
        js = ["fleet/vendor.js", "fleet/ship-lookup.js"]


class BerthForm(forms.Form):
    ship = forms.CharField(max_length=60, widget=ShipNameInput)
    tonnage = forms.IntegerField(min_value=1)
    arrives = forms.DateField(widget=CalendarInput)

    class Media:
        css = {"all": ["fleet/berths.css"]}
```

`Widget` is made by the metaclass `MediaDefiningClass`, and so are `Form`, `ModelForm` and their subclasses, whose metaclasses descend from it ([Declaring a form: `DeclarativeFieldsMetaclass` and `BaseForm`](declaring.md)). A class whose body defines no media attribute is given one, a property that `media_property` makes for it, as `Widget.media` is (`django/forms/widgets.py:MediaDefiningClass.__new__`). Read on an instance, the property takes the media inherited from the classes after it in the method resolution order, or an empty `Media`, and adds the class's inner `Media` if it has one. Its extend attribute says what of the inherited to keep: all of it by default, none with `extend = False`, only the types a list names with `extend = ("js",)` (`django/forms/widgets.py:media_property`). A class that defines media itself keeps it, and a subclass's inner `Media` adds to it: so a form's adds to what `BaseForm.media` gathers.

## What a `Media` holds, and adding

A `Media` is made from an inner class's css and js, or from arguments of those names: a dictionary of lists of paths keyed by medium, and a list of script paths (`django/forms/widgets.py:Media.__init__`). Each path that is a string becomes a `Script`, or a `Stylesheet` with its medium as its `"media"` attribute. An object with `__html__` is kept as it is: a `Script` or `Stylesheet` written in the declaration, which takes no medium from its key, or a safe string holding a whole element (`django/forms/widgets.py:Media._normalize_js`, `django/forms/widgets.py:Media._normalize_css`).

Adding merges nothing. A `Media` keeps the declarations it was made from, each apart, and `Media.__add__` makes a new one holding the left's declarations and then each of the right's that is not empty and not equal to one already there (`django/forms/widgets.py:Media.__add__`).

## Merging: `Media.merge`

`Media.merge` settles the order each time the assets are read, for the scripts and for each medium's stylesheets. It gives each declaration to `graphlib.TopologicalSorter` as a chain, each asset after the one before, so an asset in two lists is one node, placed after everything any list puts before it (`django/forms/widgets.py:Media.merge`); two assets are one when they share class, path and attributes (`django/forms/widgets.py:MediaAsset.__eq__`). With `STATIC_URL` set to `"/static/"`:

```python
>>> from harbour.fleet.forms import BerthForm
>>> print(BerthForm().media)
<link href="/static/fleet/calendar.css" media="all" rel="stylesheet">
<link href="/static/fleet/berths.css" media="all" rel="stylesheet">
<script src="/static/fleet/vendor.js"></script>
<script src="/static/fleet/ship-lookup.js"></script>
<script src="/static/fleet/calendar.js"></script>
```

The library both widgets declare comes once, and first. The sorter puts out every asset no list places after another, then those whose predecessors are all out, and so on, so assets no list relates are interleaved. Had the form declared `js = ["fleet/berths.js"]`, its script would come second, after the library and before the widgets' own; a script that needs the calendar's names it first in its own declaration, `["fleet/calendar.js", "fleet/berths.js"]`.

> **Why.** `merge`'s docstring: a script may refer to a global that another defines, and a stylesheet may be meant to override another's style.

When the declarations' orders cannot all be kept, as when two put the same assets in opposite order, `merge` issues a `MediaOrderConflictWarning`, a `RuntimeWarning` naming the lists, and falls back to the lists end to end with repeats dropped. It warns when the media is read, not when the two are added.

## Rendering: `Media.render` and the subsets

A `Media` drawn as a string is `Media.render`: the stylesheets, by medium in alphabetical order, then the scripts, one element to a line, marked safe (`django/forms/widgets.py:Media.render`). An asset is drawn by `MediaAsset.render` from its class's element template, its path and its attributes. `media["css"]` and `media["js"]` are new `Media` objects holding only the stylesheets or only the scripts, so a template can write `{{ form.media.css }}` in its head and the scripts at its end (`django/forms/widgets.py:Media.__getitem__`).

`Media.render`, `Media.render_css` and `Media.render_js` take attributes to put on every element. An asset that already has one raises `ValueError`; a safe string is written without them. So `{% csp_nonce_attr form.media %}`, new in 6.1, puts the Content Security Policy nonce on every element when the context holds one (`django/utils/csp.py:nonce_attr`) ([The built-in tags](../templates/tags.md), [Content Security Policy: `ContentSecurityPolicyMiddleware` and the nonce](../security/csp.md)).

## Paths and the static files: `MediaAsset`

A `Script` (new in 5.2) is a path and HTML attributes, drawn as a script element with the path as `"src"`, as in `Script("fleet/calendar.js", defer=True)`; a `Stylesheet` (new in 6.1), as a link element with the path as `"href"` and `"rel"` set to `"stylesheet"`. Both are `MediaAsset` subclasses, whose property `MediaAsset.path` resolves the path at each drawing: one beginning with `"http://"`, `"https://"` or `"/"` is kept, and any other goes to `static`, which asks the static files' storage for its URL when `django.contrib.staticfiles` is installed and otherwise joins it to `STATIC_URL` (`django/forms/widgets.py:MediaAsset.path`, `django/templatetags/static.py:StaticNode.handle_simple`). So a storage that hashes file names gives the hashed name ([Content types, static files and the other contrib apps](../contrib.md)). `Media.absolute_path` applies the same rule, and nothing in Django calls it.

## Who gathers media: forms, formsets and `MultiWidget`

`BaseForm.media` adds the media of each field's widget, hidden ones too, in the order of the instance's fields, so a widget a form puts in place in its `__init__` counts (`django/forms/forms.py:BaseForm.media`). `MultiWidget.media` is the sum of its subwidgets' (`django/forms/widgets.py:MultiWidget._get_media`). `BaseFormSet.media` is its first form's, or with no forms its empty form's: all its forms, its comment says, are the same. A formset class is not made by `MediaDefiningClass`, so an inner `Media` on one is never read (`django/forms/formsets.py:BaseFormSet.media`) ([Formsets: `BaseFormSet` and the management form](formsets.md)).

No widget of `django.forms` declares assets; some of the admin's do. `BaseModelAdmin` is made by `MediaDefiningClass` too, so a model admin's inner `Media` adds to its media ([The admin](../admin.md)).
