---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Lazy values: `lazy`, `Promise` and `keep_lazy`

`lazy` turns a function into one that returns a **lazy value**: an instance of a class derived from `Promise` that keeps the arguments and calls the function again each time it is used. `keep_lazy` makes a function return a lazy value when one of its arguments is one; `format_lazy` and `lazystr` are built on `lazy`.

Code that runs at import, such as a class body or a module's constant, often needs a value that can only be computed later: a message in the language of a request that has not arrived, a URL from a URLconf not yet loaded. A lazy value stands in for the call. `django.utils.translation.gettext_lazy` is `lazy(gettext, str)` ([Lazy translations](../i18n/lazy.md)), and `reverse_lazy` is `lazy(reverse, str)` ([Reversing a name](../urls/reversing.md)). The example's FLEET is `lazy(fleet_size, str)()` ([The utility layer](../utils.md)).

## The proxy class

`lazy(func, *resultclasses)` defines a class in its own body, `__proxy__`, a subclass of `Promise`, and returns a function, wrapped with `functools.wraps` to look like func, that makes an instance of it holding the arguments it was given (`django/utils/functional.py:lazy`). So the class is built once for each call of `lazy`: every value one lazy function returns shares it, and a second `lazy(fleet_size, str)` builds another. Each method that needs the value calls func with the kept arguments, and nothing is stored: the docstring says results are not memoized, and FLEET counts the ships at each use.

The proxy gets its methods in two ways. The class body writes some out: `__repr__`, `__str__`, the comparisons, `__hash__` and `__format__`, which the comment above them says are defined on `object` and so would not be overloaded by the loop that follows; and `__add__`, `__radd__`, `__mod__` and `__mul__`, which a second comment says certain operations on `int` and `str` need (`django/utils/functional.py:lazy.__proxy__`). `str` itself has no `__radd__`; the proxy's is what makes `"Valletta: " + FLEET` work. A comparison evaluates a `Promise` on its other side too, and `__hash__` is the result's hash, so a lazy value finds a dictionary's entry under its string.

Then a loop runs over each result class, each class in its MRO, and each name in that class's `__dict__` that the proxy class does not already have, and sets on the proxy class a wrapper that calls func and then the method of that name on the result. The name is bound as a keyword argument's default, against late binding, as the comment says; and since the wrapper finds the method on whatever func returned, one wrapper serves every result class. This is how a lazy value has wrappers of `str.upper`, `str.__len__` and `str.__getitem__` (`django/utils/functional.py:lazy`).

What each of these methods returns is the result's own answer, a plain value and not a lazy one: `FLEET + ", Valletta"` written at import is fixed then.

```text
# a run of the example: FLEET from harbour/office/board.py
isinstance(FLEET, str)                      False                            0 queries
FLEET == "2 ships in harbour"               True                             1 query
{"2 ships in harbour": "posted"}[FLEET]     'posted'                         2 queries
"Valletta: " + FLEET                        'Valletta: 2 ships in harbour'   1 query
FLEET.upper()                               '2 SHIPS IN HARBOUR'             1 query
", ".join([FLEET, "Valletta"])              raises TypeError                 0 queries
```

The lookup in the dictionary called the function twice, once for the hash and once for the comparison that follows a matching hash.

## `Promise`: the mark Django tests for

A result class gives the proxy methods, never a base: a lazy value is not a `str`, and code that tests for one passes it by or refuses it, as `str.join` did above (`"sequence item 0: expected str instance, __proxy__ found"`). `Promise` is empty; its docstring says it is there to recognize promises in code (`django/utils/functional.py:Promise`). Where a lazy value may arrive, Django tests for `Promise` and does one of four things:

- keeps it: `smart_str` and `smart_bytes` return it as it is ([Text and bytes: `django/utils/encoding.py`](encoding.md)) (`django/utils/encoding.py:smart_str`), and `normalize_choices` returns it as given ([Choices: `normalize_choices` and the choice iterators](choices.md)) (`django/utils/choices.py:normalize_choices`);
- evaluates it: `iri_to_uri` (`django/utils/encoding.py:iri_to_uri`), `conditional_escape` ([Autoescaping and safe strings](../templates/autoescape.md)), `resolve_url`, whose comment says a lazy value can cause issues in functions such as `urllib.parse.urlparse` (`django/shortcuts.py:resolve_url`), and `Field.get_prep_value`, which calls the proxy's private method by its mangled name (`django/db/models/fields/__init__.py:Field.get_prep_value`);
- writes its string: `DjangoJSONEncoder` (`django/core/serializers/json.py:DjangoJSONEncoder.default`), and `serializer_factory` for a migration file ([Serializing values: `serializer_factory` and `deconstruct`](../makemigrations/serializer.md));
- counts it as text, testing it beside `str`: a member's label in `ChoicesType.__new__` (`django/db/models/enums.py:ChoicesType.__new__`), a choice's value or label in the check of a field's choices (`django/db/models/fields/__init__.py:Field._choices_is_value`), and an address in the `ADMINS` or `MANAGERS` setting (`django/core/mail/__init__.py:_send_server_message`).

## Copying and pickling

A proxy is its own deep copy: `__deepcopy__` puts it in the memo and returns it, and the comment's reason is that an instance is effectively immutable, only a collection of functions (`django/utils/functional.py:lazy.__proxy__.__deepcopy__`). There is no `__copy__`, so `copy.copy` goes through `__reduce__` and makes a new proxy.

`__reduce__` gives pickle `_lazy_proxy_unpickle` with the function, its arguments and the result classes, so a lazy value is pickled as the call it stands for, never as a result (`django/utils/functional.py:lazy.__proxy__.__reduce__`). Unpickling calls `lazy` again, which builds a new class, and the value it returns calls the function at each use like any other (`django/utils/functional.py:_lazy_proxy_unpickle`). The function must be one pickle can find by its name: a lazy value of a lambda cannot be pickled.

```text
# a run of the example: FLEET from harbour/office/board.py
copy.deepcopy(FLEET) is FLEET               True                             0 queries
copy.copy(FLEET) is FLEET                   False                            0 queries
back = pickle.loads(pickle.dumps(FLEET))    a lazy value                     0 queries
type(back) is type(FLEET)                   False                            0 queries
(a third ship is saved)
str(back)                                   '3 ships in harbour'             1 query
```

## `keep_lazy` and `keep_lazy_text`

Given a lazy translation, a function that works on text should not make it a string at once: outside a view, the documentation says, the active language may not be the right one (`docs/ref/utils.txt`). `keep_lazy(*resultclasses)` decorates such a function: it makes `lazy(func, *resultclasses)` once, when it decorates, and the wrapper returns a lazy value of the call if any argument, positional or keyword, is a `Promise`, and otherwise calls the function at once (`django/utils/functional.py:keep_lazy`). With no result classes it raises `TypeError` before it decorates anything. `keep_lazy_text` is `keep_lazy(str)`.

In `django/utils/text.py`, `capfirst`, `wrap`, `get_text_list`, `slugify` and others are under `keep_lazy_text` ([Text helpers: `Truncator` and `django/utils/text.py`](text.md)) (`django/utils/text.py:slugify`), and `mark_safe` and `escape` are under `keep_lazy(SafeString)` ([Autoescaping and safe strings](../templates/autoescape.md)). The test looks at the arguments themselves and not inside them: a list that holds a lazy value is an ordinary argument.

```text
# a run of the example: FLEET from harbour/office/board.py
slug = slugify(FLEET)                       a lazy value                     0 queries
slugify("Grand Harbour")                    'grand-harbour'                  0 queries
listed = get_text_list([FLEET, "Valletta"]) '2 ships in harbour or Valletta' 1 query
(a third ship is saved)
str(slug)                                   '3-ships-in-harbour'             1 query
listed                                      '2 ships in harbour or Valletta' 0 queries
```

## `format_lazy` and `lazystr`

`format_lazy` is `lazy(_format_lazy, str)`, a call of `str.format` made at each use (`django/utils/text.py:format_lazy`). Unlike a function under `keep_lazy`, it returns a lazy value whatever its arguments, and its format string may itself be lazy, since `str.format` is among the methods the loop wraps; [Lazy translations](../i18n/lazy.md) tells its use. `lazystr(text)` is `lazy(str, str)(text)`, a value made a string at each use (`django/utils/functional.py:lazystr`); nothing under `django/` calls it.

```runtime-names
__proxy__    django/utils/functional.py:lazy    # the class lazy defines in its body at each call, a subclass of Promise
```
