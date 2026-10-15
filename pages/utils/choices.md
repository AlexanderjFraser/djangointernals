---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Choices: `normalize_choices` and the choice iterators

`normalize_choices` puts the choices of a model field, a form field or a choice widget into one shape, a list of value-and-label pairs with groups one level down. The **choice iterators**, `CallableChoiceIterator` and `BlankChoiceIterator` on their base `BaseChoiceIterator`, stand for choices read only when something goes through them.

Choices may be written as pairs, as groups (a label over pairs of its own), as a mapping, as an enumeration class built on `Choices`, or as a callable that returns any of these, and what reads them, from a field's validation to the widget, wants one shape. So each property that holds choices passes its value through `normalize_choices`: a model field's (`django/db/models/fields/__init__.py:Field.choices`), `ChoiceField.choices` and `ChoiceWidget.choices`.

## `normalize_choices`, case by case

`normalize_choices` is one `match` statement over the value, then a list comprehension that calls it again on each label, one level deeper (`django/utils/choices.py:normalize_choices`). At `depth=0` the value is the whole list of choices; at 1, a choice's label or a group's list; at 2, a label inside a group. The cases, in order:

1. A choice iterator, a lazy value (a `Promise`), bytes or a string is returned as given. The comment says why: an iterator meant to be lazy must not be read early, and a string, being iterable, must not reach the cases below. Below the top, it keeps a label, a lazy translation included, as it is.
2. An enumeration class, an instance of `ChoicesType`, gives its `ChoicesType.choices`.
3. A mapping is replaced by its items.
4. An iterator goes on untested: the next case's test would use it up, the comment says.
5. Any other iterable goes on if none of its items is a string, bytes or a lazy value. The test is why a list of strings comes back as given rather than unpacked letter by letter.
6. A callable at the top is wrapped in a `CallableChoiceIterator` and returned uncalled; below the top it is called at once.
7. Anything else is returned as given. The third to sixth cases require a depth below 2, so a mapping, an iterable or a callable deeper than a group is kept as it is.

What goes on is unpacked item by item into a value and a label. If an unpacking raises `TypeError` (an item that is not iterable) or `ValueError` (one of the wrong length), the value is returned as it then stands, for a callable what it returned, so that, the comment says, the system check reports it. `Field._check_choices` does, with `"fields.E005"` (and with `"fields.E004"` a string, a set or a value that is not iterable); but an iterator comes back used up, and the check finds nothing in it to report (`django/db/models/fields/__init__.py:Field._check_choices`).

The example's choices for a port's country:

```python
# harbour/fleet/choices.py
from django.db import models

from harbour.fleet.models import Port


class Country(models.TextChoices):
    MALTA = "MT", "Malta"
    GREECE = "GR", "Greece"


def port_countries():
    return [(c, c) for c in Port.objects.values_list("country", flat=True).order_by("country")]


def europe():
    return {"MT": "Malta", "GR": "Greece"}
```

```text
normalize_choices(Country)
    -> [('MT', 'Malta'), ('GR', 'Greece')]
normalize_choices({"Europe": {"MT": "Malta"}, "Africa": [("TN", "Tunisia")]})
    -> [('Europe', [('MT', 'Malta')]), ('Africa', [('TN', 'Tunisia')])]
normalize_choices({"Europe": {"South": {"MT": "Malta"}}})
    -> [('Europe', [('South', {'MT': 'Malta'})])]
normalize_choices(["MT", "GR"])
    -> ['MT', 'GR']
normalize_choices(c for c in ["MT", "GR"])
    -> [('M', 'T'), ('G', 'R')]
normalize_choices({"Europe": europe})
    -> [('Europe', [('M', 'T'), ('G', 'R')])]
```

> **Trap.** Two things skip the fifth case's test: an iterator, and what a callable in a group's place returns, which is unpacked as it stands, so a mapping is read by its keys. Two-character strings then become pairs of letters, as the last two lines show, and the system check passes them.

## The choice iterators

`BaseChoiceIterator` is the base of choices made at each iteration rather than kept; a subclass writes `BaseChoiceIterator.__iter__` (`django/utils/choices.py:BaseChoiceIterator`). The base gives them a list's equality and indexing, each going through the choices again: `BaseChoiceIterator.__eq__` compares item by item with any iterable, through `itertools.zip_longest`, so lengths must match too; `BaseChoiceIterator.__getitem__` takes one item through `itertools.islice`, and for a slice or a negative index builds the whole list, which its comment calls suboptimal.

`CallableChoiceIterator` keeps its callable; each iteration calls it afresh and passes the result through `normalize_choices` from the top, so it may return any form (`django/utils/choices.py:CallableChoiceIterator`). `Field.deconstruct` unwraps it, so a migration records the callable, not its choices (`django/db/models/fields/__init__.py:Field.deconstruct`); and the system check goes through the choices, so it calls the callable.

`BlankChoiceIterator` puts a blank choice before choices it reads only when gone through (`django/utils/choices.py:BlankChoiceIterator`). At each iteration `itertools.tee` splits one pass over the choices in two: one copy, flattened by `flatten_choices`, is searched for a value `""` or `None`, and only if there is none is the blank choice yielded before the other copy. So a callable behind them is called once per iteration. `flatten_choices` replaces each group by its pairs, one level down (`django/utils/choices.py:flatten_choices`); so a `""` inside a group counts, as does the `None` that an enumeration with `"__empty__"` puts first.

A model field given port_countries, and the number of SQL statements each line sent:

```text
field = models.CharField(max_length=40, choices=port_countries) 0 queries
list(field.choices)
    -> [('Greece', 'Greece'), ('Malta', 'Malta')]                   1 query
list(field.get_choices())
    -> [('', '- Select an option -'), ('Greece', 'Greece'), ('Malta', 'Malta')] 1 query
form_field = field.formfield()               0 queries
form_field.widget.render("country", "Malta") 1 query
```

## Where Django uses them

On a model field (`django/db/models/fields/__init__.py:Field.get_choices`), `Field.get_choices` wraps the choices in a `BlankChoiceIterator` when a blank choice is wanted, and `Field.formfield` hands that to a form field, a `TypedChoiceField` by default, whose setter's `normalize_choices` returns it as given; so a callable's choices are read not as the form field is made but as its widget draws them, in the last two lines. `Field.flatchoices`, `flatten_choices` made a list, serves the display method of a field with choices ([A field: the base class](../models/fields.md)) (`django/db/models/base.py:Model._get_FIELD_display`).

On a form, the first case lets a model choice field's `ModelChoiceIterator`, a `BaseChoiceIterator` too, reach its widget unread ([Choices: `ChoiceField`, `ModelChoiceField` and the choice widgets](../forms/choices.md)) (`django/forms/models.py:ModelChoiceIterator`).
