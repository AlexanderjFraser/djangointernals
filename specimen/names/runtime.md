---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
status: verified
owns: "`ModelBase.add_to_class`, `Model._meta`, `Model.objects`"
---

# Names made as the code runs

Where in the source is `Model._meta` attached to a model class, and where does a `Manager` become `Model.objects`?

`Options.contribute_to_class` assigns the `Options` object to the class as `Model._meta` (`django/db/models/options.py:Options.contribute_to_class`). `BaseManager.contribute_to_class` sets an attribute of the name it is given on the class it is given, with `setattr`: a `ManagerDescriptor` made from the manager (`django/db/models/manager.py:BaseManager.contribute_to_class`).

```runtime-names
Model._meta    django/db/models/options.py:Options.contribute_to_class      # assigned there, on the class it is handed; Model itself has none
Model.objects  django/db/models/manager.py:BaseManager.contribute_to_class  # set there, under the name it is given; Model itself has none
ROOT_URLCONF   django/conf/__init__.py:Settings.__init__                    # the defaults do not define it; one of the places a setting is set
```

## Where does `Model._meta` come from?

`ModelBase.__new__` returns the new class at once when none of the class's bases is an instance of `ModelBase`, which is the case for `Model` itself. Further down, where nothing before it has raised, it calls `ModelBase.add_to_class` with the name `"_meta"` and a new `Options`. So `Model._meta` is in no model's class body, and `Model` itself has no such attribute (`django/db/models/base.py:ModelBase.__new__`).

`ModelBase.add_to_class` calls the value's method named `"contribute_to_class"`, passing the class and the name, when `_has_contribute_to_class` accepts the value, and otherwise sets the attribute with `setattr` (`django/db/models/base.py:ModelBase.add_to_class`). `Options.contribute_to_class` assigns the `Options` object to the class as `Model._meta` (`django/db/models/options.py:Options.contribute_to_class`).

## Where does `Model.objects` come from?

`ModelBase.__new__` returns an abstract class before it reaches its call to `ModelBase._prepare` (`django/db/models/base.py:ModelBase.__new__`). When the class's `Options.managers` is empty, `ModelBase._prepare` raises `ValueError` if one of its `Options.fields` is named `"objects"`, and otherwise makes a `Manager` and passes it to `ModelBase.add_to_class` under the name `"objects"` (`django/db/models/base.py:ModelBase._prepare`).

`BaseManager.contribute_to_class` sets an attribute of the name it is given on the class it is given, with `setattr`: a `ManagerDescriptor` made from the manager (`django/db/models/manager.py:BaseManager.contribute_to_class`). Read on a class, that attribute goes through `ManagerDescriptor.__get__`, which raises `AttributeError` when it is read from an instance, on an abstract class or on a swapped one, and otherwise returns the entry of the class's `Options.managers_map` under the manager's name. That entry is what the name `Model.objects` stands for (`django/db/models/manager.py:ManagerDescriptor.__get__`).

> A name made as the code runs is written on the class a reader knows it by: `Model._meta`, though `Model` itself has none. Nothing can be checked after such a name, so a member reached through it is written on its own class: `Options.get_field`.

## Which setting has no default?

`ROOT_URLCONF` is not assigned in `django/conf/global_settings.py`. One of the places a setting gets a value is `Settings.__init__`: it imports the settings module it is given and, in a loop over that module's upper-case names, sets each on itself with `setattr` (`django/conf/__init__.py:Settings.__init__`). `get_resolver` reads `settings.ROOT_URLCONF` when its argument is `None` (`django/urls/resolvers.py:get_resolver`).
