---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The built-in filters

The built-in filters are the functions of `django/template/defaultfilters.py`, from `|upper` and `|date` to `|default` and `|length`, which every template has without `{% load %}`. Each is a plain function of a value and at most one argument, most of them registered with flags that tell `FilterExpression.resolve` how to treat its input and its output.

The parser finds a filter by name when it compiles `{{ ship.name|upper }}`, and checks its arguments ([Variables and filters: `FilterExpression` and `Variable`](variables.md)); at render time `FilterExpression.resolve` passes the value through each filter in turn (`django/template/base.py:FilterExpression.resolve`).

## How the module registers its filters

`django/template/defaultfilters.py` makes one `Library`, `register`, and decorates each filter with `Library.filter`, which stores it under its own name or the one given, as `escape_filter` is stored as `|escape`, and sets the flags it is given as attributes on it and, for a decorator such as `stringfilter` to read, on the innermost function under it (`django/template/library.py:Library.filter`). The module is one of `Engine.default_builtins`, so every engine loads it ([Libraries: `Library`, custom tags and `{% load %}`](libraries.md)).

Most string filters also wear `stringfilter`, which calls `str` on the first argument, so that `|lower` works on a number's text, and marks the result safe when that argument was a `SafeData` and the function has `is_safe=True` (`django/template/defaultfilters.py:stringfilter`). What safety means is told in [Autoescaping and safe strings](autoescape.md).

## Strings

The string filters carry `is_safe=True`: a safe value in gives a safe value out, marked by `FilterExpression.resolve`. `|upper`, `|urlencode` and `|wordcount` carry `is_safe=False`, and `|cut` no flag: it keeps its input's safety unless the text removed was `";"` (`django/template/defaultfilters.py:cut`).

| filter | returns |
|---|---|
| `\|addslashes` | a backslash before each backslash and quote |
| `\|capfirst` | the first character upper-cased |
| `\|center`, `\|ljust`, `\|rjust` | the value padded to the width given |
| `\|cut` | the value without the argument |
| `\|iriencode` | `iri_to_uri` |
| `\|lower`, `\|upper` | `str.lower`, `str.upper` |
| `\|phone2numeric` | letters as keypad digits |
| `\|pprint` | `pprint.pformat`, or the error |
| `\|slugify` | `django.utils.text.slugify` |
| `\|stringformat` | Python's `%`, `"03d"` meaning `"%03d"` |
| `\|title` | `str.title`, less a capital after a lower-case ASCII letter and an apostrophe, or after a digit |
| `\|truncatechars`, `\|truncatewords`, `\|truncatechars_html`, `\|truncatewords_html` | `Truncator.chars`, `Truncator.words`; the HTML ones close open tags |
| `\|urlencode` | `urllib.parse.quote` |
| `\|wordcount` | the number of words |
| `\|wordwrap` | `django.utils.text.wrap` |

## HTML and escaping

`|linebreaks`, `|linebreaksbr`, `|linenumbers`, `|urlize`, `|urlizetrunc`, `|unordered_list` and `|join` carry `needs_autoescape=True`, so they are passed the context's autoescaping. When it is on, each escapes what of its input is not safe, adds its markup, numbers or separator and returns the whole through `mark_safe`; called from Python, they escape by default (`django/template/defaultfilters.py:linebreaksbr`).

| filter | returns |
|---|---|
| `\|escape`, `\|force_escape` | `conditional_escape`, unless safe; `escape`, even when safe |
| `\|safe` | `mark_safe` |
| `\|escapeseq`, `\|safeseq` | a list, each item through `conditional_escape` or `mark_safe` |
| `\|escapejs` | `django.utils.html.escapejs` |
| `\|json_script` | `django.utils.html.json_script` |
| `\|striptags` | `strip_tags` |
| `\|linebreaks`, `\|linebreaksbr` | newlines as `<br>`, blank lines as paragraphs; newlines only |
| `\|linenumbers` | each line numbered |
| `\|urlize`, `\|urlizetrunc` | URLs and email addresses as links; the second cuts their text to the length given |

`|urlize` and `|urlizetrunc` call `django.utils.html.urlize` with `nofollow=True`, which splits the text at white space, quotes and angle brackets, trims each word's wrapping and trailing punctuation, and links what is left if it is an `"http"` or `"https"` URL, a name beginning `"www."` or ending in one of the seven original top-level domains, or an email address, given `"mailto:"` and no `rel="nofollow"` (`django/utils/html.py:Urlizer`). With autoescaping on, an unsafe input is escaped word by word, links' text included.

> **Deprecated.** A name without a scheme gets `"http://"`, with a `RemovedInDjango2028Warning`, unless the setting `URLIZE_ASSUME_HTTPS` is true; Django 2028 makes it `"https://"`.

## Numbers

| filter | returns |
|---|---|
| `\|add` | the sum as integers; else the value `+` the argument; else `""` |
| `\|filesizeformat` | a size in bytes, KB, MB, GB, TB or PB, localized |
| `\|floatformat` | the value rounded to some decimal places, localized |
| `\|get_digit` | the digit at the place given, from the right |

`floatformat` reads the value as a `decimal.Decimal`, through `str` or else `float`, and gives `""` for what is not a number (`django/template/defaultfilters.py:floatformat`). Its argument, `-1` by default, counts places: a positive one gives that many, rounded half up; a negative one as many, or none for a whole value. So `34.0` prints `"34"` under `-1` and `"34.000"` under `3`; `34.23234`, `"34.2"` and `"34.232"`. A `"g"` suffix forces the thousands to be grouped. The active language's separators apply even inside `{% localize off %}`, unless a `"u"` suffix turns localization off.

## Lists and dictionaries

| filter | returns |
|---|---|
| `\|dictsort`, `\|dictsortreversed` | the list sorted by a key or attribute of its items |
| `\|first`, `\|last` | the first or the last item, or `""` |
| `\|join` | the items joined by the argument, each escaped when autoescaping |
| `\|length` | `len` of the value, or `0` |
| `\|make_list` | the value's characters as a list |
| `\|random` | a random item |
| `\|slice` | the value sliced by `"start:stop:step"`, or whole on a bad argument |
| `\|unordered_list` | nested lists as `<li>` items, without the outer `<ul>` |

`dictsort` and `dictsortreversed` sort by a key that `_property_resolver` makes (`django/template/defaultfilters.py:_property_resolver`). An argument `float` accepts becomes `operator.itemgetter` of itself: `|dictsort:0` sorts pairs by their first item. Any other is a dotted path, each part tried as a key and then an attribute, never as an index and never called; a method's name gives bound methods, which do not compare, so a list of two or more gives `""`, as does a part that begins with an underscore.

`length` is `len`, or `0` (`django/template/defaultfilters.py:length`). A `QuerySet` meets the list filters as it meets Python ([Evaluation and the result cache](../querysets/evaluation.md)). `|length` calls `QuerySet.__len__`, which fills the result cache, so a `{% for %}` over the same `QuerySet` sends no second query; a variable that ends in a method, as `{{ port.ship_set.all }}` does, gives a new `QuerySet`, and a new query, each time it is resolved (`django/template/base.py:Variable._resolve_lookup`). `|last` asks for index -1, which `QuerySet.__getitem__` refuses with `ValueError`, and as `last` catches only `IndexError`, the render fails (`django/db/models/query.py:QuerySet.__getitem__`).

## Dates and times

`date` and `time` format with the letters of PHP's date function (`django/utils/dateformat.py`). Their `expects_localtime=True` has `FilterExpression.resolve` first convert an aware datetime to the current time zone, unless `Context.use_tz`, or `USE_TZ` when that is unset, is false, as inside `{% localtime off %}`, or a filter of `{% load tz %}` such as `|utc` has converted it already (`django/utils/timezone.py:template_localtime`, `django/templatetags/tz.py:do_timezone`). Printing does the same, but a datetime through `|date` is printed as a string.

`date` passes its argument to `django.utils.formats.date_format`, which looks it up as a format's name, in the active language's format modules and then the format settings, and takes an argument that names none as the format itself (`django/utils/formats.py:get_format`). For 27 September 2026, `|date:"SHORT_DATE_FORMAT"` gives `"09/27/2026"` in American English and `"27.09.2026"` in German; `|date:"Y-m-d"` is the same in both; no argument means `"DATE_FORMAT"`. `{% localize off %}` changes nothing, as `Context.use_l10n` is read only where a value is printed. `time` works alike with `"TIME_FORMAT"`. Both give `""` for `None`, `""` or a value without the parts its letters ask for; but a `datetime.date` asked for a time letter, as by `|date:"H:i"`, raises `TypeError`, which `date` does not catch, and the render fails (`django/utils/dateformat.py:Formatter.format`).

`|timesince` and `|timeuntil` put the time between the value and the argument, or now, into words (`django/utils/timesince.py:timesince`).

## Logic

`default` returns `value or arg`, replacing any false value; `default_if_none` replaces only `None` (`django/template/defaultfilters.py:default`). They part on a variable that does not resolve. With the engine's `"string_if_invalid"` empty, the default, `FilterExpression.resolve` hands the filters `""`: `|default:"unknown"` prints `"unknown"`, `|default_if_none:"unknown"` nothing. With it set, the string is returned at once and no filter runs (`django/template/base.py:FilterExpression.resolve`). An argument written in quotes arrives marked safe, so `|default:"<unknown>"` prints its angle brackets unescaped.

`pluralize` takes a plural suffix, `"s"` by default, or a singular and a plural, `"y,ies"` (`django/template/defaultfilters.py:pluralize`). A value `float` makes 1 is singular, `"1"` and `"1.0"` too; one `float` cannot take, a list, is singular at length 1. A string that is not a number, `None`, or an argument of more than two parts gives `""`.

`|yesno` maps true, false and `None` to the words of its argument, by default `"yes,no,maybe"` translated. `|divisibleby` tells whether `int` of the value divides by `int` of the argument, and a value that is not a number ends the render (`django/template/defaultfilters.py:yesno`, `django/template/defaultfilters.py:divisibleby`).
