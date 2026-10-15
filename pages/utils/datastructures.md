---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Data structures: `MultiValueDict` and its neighbours

`django/utils/datastructures.py` holds the containers that the request, the ORM and the template engine share: `MultiValueDict`, the dictionary of lists under a request's query, form data and files; `CaseInsensitiveMapping`, under its headers; `ImmutableList`, `OrderedSet`, `DictWrapper` and `DeferredSubDict`. Beside them, `make_hashable` in `django/utils/hashable.py` makes a value built of lists and dictionaries fit to be hashed.

## `MultiValueDict`

A `MultiValueDict` is a `dict` whose stored values are lists, one to a key, with the methods that read and write a single value changed to hide the list (`django/utils/datastructures.py:MultiValueDict`). Its docstring says why: the cgi module's parse_qs returned a list for every key, though most web forms submit one value under each name. The storage shows through `dict()`, which gives the lists.

### Reading one value or all

`MultiValueDict.__getitem__` returns the last item of the key's list, so a name sent twice gives its later value. A missing key raises `MultiValueDictKeyError`, a subclass of `KeyError`, which a dictionary's caller still catches; an empty list gives `[]`. `MultiValueDict.get` returns its default for a missing key and for an empty list. `MultiValueDict.items`, `MultiValueDict.values` and `MultiValueDict.dict` give last values too, the first two as generators, not views; `MultiValueDict.lists` gives each key with its stored list.

`MultiValueDict.getlist` returns a copy of a key's list; a missing key gives `[]` or the default passed. `MultiValueDict._getlist` makes that copy when asked to, and otherwise returns the stored list itself (`django/utils/datastructures.py:MultiValueDict._getlist`).

### Writing

Assigning by subscript replaces the key's list with a list of the one value; `MultiValueDict.setlist` stores the list it is given; `MultiValueDict.appendlist` appends to the list that `MultiValueDict.setlistdefault` returns, making the key if it is missing. `setlistdefault` and `MultiValueDict.setdefault` set a key only when it is missing, and then look it up again rather than return what they were given. Their comments say why: a subclass's `setlist` or `__setitem__` may store another value, and `QueryDict`'s do: they decode bytes, and its `setlist` stores a new list (`django/utils/datastructures.py:MultiValueDict.setlistdefault`, `django/http/request.py:QueryDict.setlist`). On a mutable `QueryDict` the list `setlistdefault` returns is not the one it was given.

`MultiValueDict.update` extends and never replaces. Another `MultiValueDict` has its lists added to the ends of this one's; from a mapping, pairs or keyword arguments each value is appended to its key, so a plain dictionary whose value is a list appends the list as one value (`django/utils/datastructures.py:MultiValueDict.update`).

### Copying and pickling

`MultiValueDict.copy` and `copy.copy` make a new dictionary with each list copied, their values shared; `copy.deepcopy` copies keys and lists deeply (`django/utils/datastructures.py:MultiValueDict.__copy__`, `django/utils/datastructures.py:MultiValueDict.__deepcopy__`). At protocols 2 to 5, the default among them, pickle writes a subclass of `dict` with the pairs its `items` yields, here the last values only, so `MultiValueDict.__getstate__` adds the whole lists to the state under `"_data"`, and `MultiValueDict.__setstate__` stores them again with `setlist` before restoring the rest of the instance's `__dict__` (`django/utils/datastructures.py:MultiValueDict.__setstate__`).

```text
# a run of the example: a posted berth form's fields, as a MultiValueDict
post = MultiValueDict({"berth": ["3"], "ship": ["Endeavour", "Beagle"]})
post["ship"]                           'Beagle'
post.getlist("ship")                   ['Endeavour', 'Beagle']
post.setlist("crew", [])
post["crew"]                           []
post.get("crew")                       None
post.dict()                            {'berth': '3', 'ship': 'Beagle', 'crew': []}
dict(post)                             {'berth': ['3'], 'ship': ['Endeavour', 'Beagle'], 'crew': []}
post.update({"ship": "Resolution"})    getlist("ship"): ['Endeavour', 'Beagle', 'Resolution']
post.update({"berth": ["5", "6"]})     getlist("berth"): ['3', ['5', '6']]
post.setdefault("pilot", "Cook")       'Cook'
post.setdefault("pilot", "Banks")      'Cook'
```

`QueryDict`, for a request's query and form data, is a `MultiValueDict` that parses, decodes and, unless made mutable, refuses changes ([`QueryDict`](../http/querydict.md)). Uploaded files are kept in a plain one (`django/http/multipartparser.py:MultiPartParser._parse`), and the URL resolver files its candidates for reversing in one ([Reversing a name](../urls/reversing.md)) (`django/urls/resolvers.py:URLResolver._populate`).

## `ImmutableList`

`ImmutableList` is a tuple that answers an attempt to change it as a list with `AttributeError` and the message its maker passes to `ImmutableList.__new__` as the warning argument, or a default one. `ImmutableList.complain`, which raises it, is bound to the name of every method by which a list changes, those behind item assignment, deletion, `+=` and `*=` included, except `list.clear`, which fails with Python's own message (`django/utils/datastructures.py:ImmutableList`). A plain tuple refuses most of these with Python's errors, and lets `+=` and `*=` bind the name to a new tuple, where an `ImmutableList` raises.

`HttpRequest.parse_file_upload` turns the request's upload handlers into one as parsing begins ([Multipart parsing and upload handlers](../http/uploads.md)). A model's options hand out the lists of fields they cache as one, with a message that names the list and says to make a copy first ([The options: what a model keeps as `_meta`](../models/options.md)) (`django/db/models/options.py:make_immutable_fields_list`).

## `CaseInsensitiveMapping`

`CaseInsensitiveMapping` is a read-only `collections.abc.Mapping` whose keys are found whatever their case. It keeps a dictionary from each key in lower case to the key as written and its value; a lookup lowers the key it is given, and iteration and `repr` give the keys as written (`django/utils/datastructures.py:CaseInsensitiveMapping`). Keys differing only in case are one key; the later wins, with its spelling. The mapping equals any mapping with the same items once the keys are lowered, and `CaseInsensitiveMapping.copy` returns the mapping itself. Given pairs, `CaseInsensitiveMapping._unpack_items` refuses with `ValueError` one that is not two items or whose key is not a string.

```text
# a run of the example: a mapping of headers
h = CaseInsensitiveMapping([("Content-Type", "text/html"), ("X-Berth", "3"), ("x-berth", "4")])
h                                      {'Content-Type': 'text/html', 'x-berth': '4'}
h["CONTENT-TYPE"]                      'text/html'
```

A request's `HttpHeaders` and a response's `ResponseHeaders` are built on it ([Headers, host and scheme](../http/headers.md), [The response object](../http/response.md)).

## `OrderedSet`, `DictWrapper` and `DeferredSubDict`

`OrderedSet` keeps its items as the keys of a dictionary made with `dict.fromkeys`, so membership is a dictionary lookup, and iteration, reversed or not, follows the order of insertion, which adding an item again does not change (`django/utils/datastructures.py:OrderedSet`). It can add, remove and discard an item, and has no set operators. Among the places Django uses it to drop duplicates and keep the order are the values on the right of an `In` lookup (`django/db/models/lookups.py:In.process_rhs`) and a model's ancestors (`django/db/models/options.py:Options.all_parents`).

`DictWrapper` is a dictionary that, for a key beginning with a given prefix, takes the prefix off and passes the value through a given function (`django/utils/datastructures.py:DictWrapper`). The parameters of a model field's column type are one, over the field's `__dict__`, so that `"qn_column"` gives the column's name quoted ([Column types: from a field to a column](../backends/column-types.md)) (`django/db/models/fields/__init__.py:Field.db_type_parameters`). `DeferredSubDict` looks a key up in a dictionary inside another only when indexed; its one user is the `{% partial %}` tag, whose partial may be defined below it ([Template partials: `{% partialdef %}` and `{% partial %}`](../templates/partials.md)) (`django/utils/datastructures.py:DeferredSubDict`, `django/template/defaulttags.py:partial_func`).

## `make_hashable`

`make_hashable` turns a value into one that can be hashed. A dictionary becomes a tuple of its pairs sorted by key, each value made hashable in turn; a value that hashes is returned as it is, so a string or a frozenset is not taken apart; one that does not hash but can be iterated becomes a tuple of its items, each made hashable; anything else raises the `TypeError` of `hash` (`django/utils/hashable.py:make_hashable`). The docstring says equal values should give the same hash, and the sorting keeps that for dictionaries built in different orders. The cost: a dictionary's keys must be mutually comparable, and a list and a tuple of the same items come out alike.

```text
# a run of the example: the ports each ship calls at
calls = {"Endeavour": ["Valletta", "Piraeus"], "Beagle": ["Valletta"]}
make_hashable(calls)                   (('Beagle', ('Valletta',)), ('Endeavour', ('Valletta', 'Piraeus')))
make_hashable({1: "Valletta", "two": "Piraeus"})   raises TypeError: '<' not supported between instances of 'str' and 'int'
```

Its users compare by value: `ValidationError.__hash__` ([Django's exceptions: `django.core.exceptions`](exceptions.md)); `Node.__hash__` (`django/utils/tree.py:Node.__hash__`); the identity of a `Q` object, a lookup and an expression ([Expressions: `resolve_expression` and `as_sql`](../sql/expressions.md)); the compiler, dropping a repeated ordering (`django/db/models/sql/compiler.py:SQLCompiler.get_order_by`); `Model._get_FIELD_display`, for a choice whose value is a list. `Node` is the tree a `Q` and a where clause are built from ([`filter`, `exclude` and `Q` objects](../querysets/filters.md), [The where clause: `build_filter`, `add_q` and `WhereNode`](../sql/where.md)).
