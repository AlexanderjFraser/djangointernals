---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# `normalize`, and the patterns that cannot be reversed

`normalize`, a function of `django.utils.regex_helper`, reads a pattern's regular expression into the strings with gaps that `reverse` fills in, and what it cannot read can make a pattern that serves its paths fail to reverse.

Why should a pattern that serves every path meant for it refuse to reverse, or keep every other name of its URLconf from reversing? Because `reverse` never runs a regular expression backwards. When the tables for reversing are built, `normalize` reads each pattern's expression from left to right, and keeps what a text the expression matches would have to contain, one character standing for each class. What it returns are the pattern's **forms**, a list of pairs, each a string that Python's `%` operator fills in from a dictionary and the names of the parameters it has gaps for ([Reversing a name](reversing.md#the-tables)) (`django/utils/regex_helper.py:normalize`).

The museum's plan pattern has an optional part with a group inside it, and the figure follows `normalize` through it: at the optional part the reading forks, and each branch ends as one form.

```text figure=two-forms
^plans/(?P<floor>[0-9])(?:\.(?P<format>pdf|svg))?$, read from the left a piece at a time

^          plans/     (?P<floor>[0-9])     (?:\.(?P<format>pdf|svg))?               $
dropped    kept       a gap, %(floor)s     optional, and it holds a group:          the reading
                      parameter floor      two ways on                              ends here
                                             left out:    nothing
                                             kept once:   \.  kept as .
                                                          (?P<format>pdf|svg)  a gap, %(format)s
                                                                               parameter format

the forms, one for each way
  left out     plans/%(floor)s               parameters floor
  kept once    plans/%(floor)s.%(format)s    parameters floor, format
```

*The museum's plan pattern as `normalize` reads it, a piece at a time from the left, with what each piece becomes under it. At the optional part the reading forks, once leaving it out and once keeping it, and each branch ends as one of the two forms at the foot; the gaps are accented.*

## `normalize`: from an expression to its forms

`normalize` meets the constructs of an expression one at a time, and each gives it a piece of text, a gap, a fork, nothing, the end of the reading, or an error (`django/utils/regex_helper.py:normalize`):

| what the expression holds | what `normalize` makes of it |
|---|---|
| literal text, and a character escaped to mean itself, as the plan pattern's `\.` | the text as it stands, an escaped character without its backslash, but read as unescaped just after a greedy quantifier |
| an anchor: `^`, `\A`, `\Z`, `\b`, `\B` | nothing |
| an unescaped `$` | the end of the reading: nothing after it is read |
| a named group, `(?P<name>…)` | a gap, `%(name)s`, and a parameter of that name; what is inside the group is skipped by counting parentheses, so neither the expression a converter supplies nor an alternation there is read |
| an unnamed group, `(…)` | a gap, `%(_0)s`, then `%(_1)s` and so on, with a parameter of that name; its inside skipped in the same way |
| a reference back to a named group, `(?P=name)` | a second gap for the same parameter, which is listed once |
| a group that does not capture, `(?:…)` | what is inside it, read in place, and taken whole by a quantifier |
| a quantifier, and something optional that holds a capturing group | the fewest repetitions the quantifier allows: none for `*` and `?`, one for `+`, the lower bound for braces, and `ValueError` for braces without one, `{,3}`; where that is none and what it repeats is or holds a capturing group not made optional within it, the reading forks two ways, one without it and one with it once |
| a class, `\d`, `\w`, a dot | one character in its place: the first after the class's opening bracket, so `"[^/]"` gives `"^"`; `"0"` for `\d`, `"x"` for `\w`; a dot for a dot |
| a lookahead or a lookbehind | nothing, with what is inside it |
| an alternation, a `\|` not inside a capturing group or a lookaround | the end of the reading, and one empty form for the whole expression |
| any other construct that begins `(?`, a flag such as `(?i)` among them | `ValueError` |

*Constructs of a regular expression, and what `normalize` makes of each.*

For a route written with `path` the reading is simple. The expression `_route_to_regex` made of it is a `^`, escaped literal text, named groups and, for a pattern, a closing `\Z`, so there is one form, the route with each parameter replaced by a gap ([Routes, regular expressions and converters](patterns.md#a-route-is-expanded-into-a-regular-expression)). The rest of the table is for expressions written for `re_path`. The expressions below have a line for every row but the lookaround's, and several of them give what their writer did not mean:

```text recording=urls
normalize(): the forms a regular expression can be filled in as
    normalize('^tickets/(?P<year>[0-9]+)/(?P<month>[0-9]{2})/\\Z')  ->  [('tickets/%(year)s/%(month)s/', ['year', 'month'])]
    normalize('^plans/(?P<floor>[0-9])(?:\\.(?P<format>pdf|svg))?$')  ->  [('plans/%(floor)s', ['floor']), ('plans/%(floor)s.%(format)s', ['floor', 'format'])]
    normalize('^archive/([0-9]{4})/([0-9]{2})/$')  ->  [('archive/%(_0)s/%(_1)s/', ['_0', '_1'])]
    normalize('^pair/(?P<a>[0-9]+)/(?P=a)/$')  ->  [('pair/%(a)s/%(a)s/', ['a'])]
    normalize('^rooms?/$')  ->  [('room/', [])]
    normalize('^(?:wing/)?rooms/$')  ->  [('rooms/', [])]
    normalize('^room/\\d+/\\w+/$')  ->  [('room/0/x/', [])]
    normalize('^files/.+\\.[a-z]{3}$')  ->  [('files/..aaa', [])]
    normalize('^files/[^/]+/$')  ->  [('files/^/', [])]
    normalize('^(?:east|west)/lift/$')  ->  [('', [])]
    normalize('^lift/(?P<side>east|west)/$')  ->  [('lift/%(side)s/', ['side'])]
    normalize('^sale\\-50%/\\Z')  ->  [('sale-50%/', [])]
    normalize('(?i)^cafe/$')  ->  raises ValueError: Non-reversible reg-exp portion: '(?i'
    normalize('^a{,3}/$')  ->  raises ValueError
    ...
```

Read against the table, `"files/..aaa"` is three rows at once: the dot of `.+` kept once, the fewest that `+` allows, then the escaped dot, then the first letter of `[a-z]` three times. What comes of the empty form, the `%`, the flag and the quantifier without a lower bound is under [Patterns that cannot be reversed](#patterns-that-cannot-be-reversed).

## Patterns that cannot be reversed

A pattern can serve its paths and still defeat `normalize`, and how much is lost depends on where the failure happens.

> **Why.** `normalize` is not meant to read every regular expression, only enough of them for a large class of URLs (`django/utils/regex_helper.py`).

Small URLconfs each hold a plain pattern, *about*, beside one that serves its path and cannot be reversed, the last of them only through an include, under a namespace, of a URLconf whose one pattern sets a flag; look at what becomes of *about* beside each:

```text recording=urls
Patterns that resolve and cannot be reversed, and how far the failure reaches
    ALTERNATIVES is path("about/", views.entrance, name="about") and re_path(r"^(?:east|west)/lift/$", views.entrance, name="lift")
      resolve("/west/lift/", urlconf=ALTERNATIVES).url_name  ->  'lift'
      reverse("lift", urlconf=ALTERNATIVES)  ->  raises NoReverseMatch
      reverse("about", urlconf=ALTERNATIVES)  ->  '/about/'
    PERCENT is path("about/", views.entrance, name="about") and path("sale-50%/", views.shop, name="sale")
      resolve("/sale-50%/", urlconf=PERCENT).url_name  ->  'sale'
      reverse("sale", urlconf=PERCENT)  ->  raises ValueError
      reverse("about", urlconf=PERCENT)  ->  '/about/'
    FLAGGED is path("about/", views.entrance, name="about") and re_path(r"(?i)^cafe/$", views.entrance, name="cafe")
      resolve("/CAFE/", urlconf=FLAGGED).url_name  ->  'cafe'
      reverse("cafe", urlconf=FLAGGED)  ->  raises ValueError: Non-reversible reg-exp portion: '(?i'
      reverse("about", urlconf=FLAGGED)  ->  raises ValueError: Non-reversible reg-exp portion: '(?i'
    CAFE is [re_path(r"(?i)^cafe/$", views.entrance, name="cafe")], and INCLUDING is path("about/", views.entrance, name="about") and path("food/", include((CAFE, "food")))
      reverse("about", urlconf=INCLUDING)  ->  raises ValueError: Non-reversible reg-exp portion: '(?i'
```

Where each of the three fails decides what is lost.

| what the pattern holds | where reversing fails | what is lost |
|---|---|---|
| an alternation `normalize` reads, as in ALTERNATIVES | `normalize` gives one empty form, which fills in to the script prefix alone, and *lift*'s expression refuses that | that name, with `NoReverseMatch` |
| a literal `%`, as in PERCENT, whose pattern was written with `path` | the form keeps the `%`, and Python's `%` operator tries to read it as a gap when the form is filled in | that name, here with `ValueError` |
| a construct `normalize` raises for, such as a group that sets a flag, as in FLAGGED, or a quantifier written `{,3}` | inside `URLResolver._populate`, so the tables are never finished | every name of the URLconf |

*Three ways a pattern that resolves can fail to reverse, by the URLconfs of the recording above.*

> **Trap.** A failure in `_populate` does not stay in its URLconf. `_populate` of a resolver runs `_populate` of every resolver among its entries, whatever their namespaces, so the `ValueError` passes up through every include above the pattern, and every URLconf that includes the pattern's URLconf loses its names too, as INCLUDING loses *about*. The unfinished tables are dropped, so each later `reverse` with the URLconf tries again and fails again (`django/urls/resolvers.py:URLResolver._populate`). An expression that does not compile breaks every name in the same way ([Routes, regular expressions and converters](patterns.md#when-a-matchers-expression-is-compiled)).

Mixing named and unnamed groups in one expression is a trap of another kind. Resolving passes the view only the named one ([Routes, regular expressions and converters](patterns.md#which-groups-become-arguments)). `normalize` makes a gap of each, the unnamed one under the name `"_0"`, so the name can be reversed with a positional argument for each group and not with the keyword argument the view receives:

```text recording=urls
An expression with an unnamed group and a named one: what resolving passes on, and what reversing asks for
    MIXED is a URLconf of one pattern: re_path(r"^mixed/([0-9]{4})/(?P<month>[0-9]{2})/$", views.tickets, name="mixed")
...
      normalize(r"^mixed/([0-9]{4})/(?P<month>[0-9]{2})/$")  ->  [('mixed/%(_0)s/%(month)s/', ['_0', 'month'])]
      reverse("mixed", urlconf=MIXED, kwargs={"month": "03"})  ->  raises NoReverseMatch
      reverse("mixed", urlconf=MIXED, args=[2026, "03"])  ->  '/mixed/2026/03/'
```
