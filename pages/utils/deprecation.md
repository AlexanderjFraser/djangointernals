---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Deprecation: warnings named by year, `warn_about_external_use` and `deprecate_posargs`

`django/utils/deprecation.py` holds the warning classes with which Django marks what it will remove, `RemovedInDjango2028Warning` and `RemovedInDjango2029Warning`, and the helpers that raise them: `warn_about_external_use`, which warns only when the code using a deprecated feature is outside Django, `warn_about_implementation`, which names a definition, and `deprecate_posargs`, which makes parameters keyword-only while still taking them by position for a time.

A deprecated feature has to go on working and warn the code that uses it, naming that code's line, which is seldom the line that raises the warning. Most of the module is about finding it.

## Two steps, and a class for each release

Django's deprecation policy is written in feature releases: a feature deprecated in A.x keeps working in every A.x release but raises warnings, and is removed in B.0, or in B.1 when it was deprecated in the last A.x, so that a deprecation spans at least two feature releases (`docs/internals/release-process.txt`). Following DEP 20, the releases planned as 7.0 and 7.1 are Django 2028 and 2029, and each warning class is named for the release that removes what it marks (`docs/releases/6.2.txt`). The timeline lists under 2028 what 6.0 and 6.1 deprecated, with the new shape of `django.VERSION` that 6.2 announces, and under 2029 the rest of what 6.2 deprecated (`docs/internals/deprecation.txt`).

`RemovedInDjango2028Warning` derives from `DeprecationWarning`, and `RemovedInDjango2029Warning`, the farther off, from `PendingDeprecationWarning` (`django/utils/deprecation.py:RemovedInDjango2028Warning`). `RemovedInNextVersionWarning` and `RemovedAfterNextVersionWarning` are the same two classes, named by distance rather than year; nothing in the `django` package uses them, and Django's test suite turns both into errors (`tests/runtests.py`). Code that must change when a deprecation ends but raises no warning carries a comment above it naming the class (`docs/internals/contributing/writing-code/submitting-patches.txt`).

## What Python shows

Python's default filters show a `DeprecationWarning` only when it is attributed to the module `__main__`, once for each line, and ignore every `PendingDeprecationWarning`. A filter is matched against the module the warning is attributed to, not the one that raised it, so the attribution decides both the line a warning names and whether it is seen at all:

```text
# a run of a script, with Python's default filters
django.VERSION[2], in the script                  shown: RemovedInDjango2028Warning
django.VERSION[2], in harbour/office/board.py     nothing shown
MiddlewareMixin from django.utils.deprecation    nothing shown
RemovedInDjango70Warning from the same            shown: UserWarning
```

Python's `-Wd` option shows them all, the third a `RemovedInDjango2029Warning`.

## The module's `__getattr__`

A name the module does not define is looked up in its `__getattr__` (`django/utils/deprecation.py:__getattr__`). `MiddlewareMixin`, moved to `django/middleware/__init__.py` in 6.2, is answered with a `RemovedInDjango2029Warning` naming the importing line, and imported inside the function, its comment says, so that importing the module does not need `django.middleware`'s dependencies ([Sync and async in one chain](../handlers/async.md)). The old name RemovedInDjango70Warning answers with `RemovedInDjango2028Warning` and a warning of no category, a `UserWarning`, shown anywhere. Importing RemovedInDjango71Warning fails with `ImportError`.

## `django_file_prefixes`: the first frame outside Django

Most of Django's deprecations warn whoever calls, and `django_file_prefixes` lets such a warning name the first caller outside Django. The standard library's `warnings.warn` takes skip_file_prefixes, a tuple of path prefixes: counting up the stack to the frame it names, it passes over every frame whose file begins with one of them. `django_file_prefixes` gives the `django` package's directory with a separator at the end, computed once (`django/utils/warnings.py:django_file_prefixes`). A warning raised with `skip_file_prefixes=django_file_prefixes()` names the first frame above its raiser whose file is not Django's, as `JsonResponse` does when given its deprecated safe argument (`django/http/response.py:JsonResponse.__init__`).

## `warn_about_external_use`: silent for Django's own calls

When one deprecated feature is built on another, Django's own call would warn a project about code it did not write; the docstring of `warn_about_external_use` gives avoiding that cascade as its reason. It finds the **effective caller**, the code that used the feature, and warns only if that is outside Django (`django/utils/deprecation.py:warn_about_external_use`). From its own frame it goes up:

1. It passes over two frames: its own, and its caller's.
2. Given skip_name_prefixes, it passes over frames while each one's qualified name, its module's `__name__`, a dot and the code's qualified name, begins with one of them.
3. It passes over skip_frames more.
4. The frame reached is the effective caller. If its qualified name begins with one of internal_modules and a dot, `("django",)` unless given, nothing happens; otherwise `warnings.warn` is called with the stacklevel that counts to that frame.

Inside is decided by the module's name, not its file, so a script, `__main__`, is outside.

```text figure=effective-caller
The stack when warn_about_external_use is called, top first.
skip_name_prefixes is "django.utils.version.VersionTuple"; skip_frames is 0.

patch_level() in harbour/office/board.py reads django.VERSION[2]
  django.utils.deprecation.warn_about_external_use   passed over: its own frame
  django.utils.version.VersionTuple._warn            passed over: its caller
  django.utils.version.VersionTuple.__getitem__      passed over: begins with skip_name_prefixes
  harbour.office.board.patch_level                   effective caller, outside "django.":
                                                     RemovedInDjango2028Warning, naming this line
  __main__.<module>                                  not looked at

version_line() in harbour/office/board.py calls django.get_version(), whose get_main_version
slices django.VERSION
  django.utils.deprecation.warn_about_external_use   passed over: its own frame
  django.utils.version.VersionTuple._warn            passed over: its caller
  django.utils.version.VersionTuple.__getitem__      passed over: begins with skip_name_prefixes
  django.utils.version.get_main_version              effective caller, inside "django.": no warning
  django.utils.version.get_version                   not looked at
  harbour.office.board.version_line                  not looked at
  __main__.<module>                                  not looked at
```

*`warn_about_external_use` walks up from its own frame: two frames always, then those matching skip_name_prefixes, then skip_frames more. From the example, a deprecated read of `django.VERSION` warns and names the example's line; through `get_version`, the walk stops at Django's own code and nothing is warned.*

`VersionTuple._warn` passes its class's prefix, so that the code that read the tuple is the effective caller ([Django's version: `VersionTuple` and `get_version`](version.md)). The deprecated settings pass as prefixes the settings classes and the test utilities that override settings (`django/conf/__init__.py:_show_settings_deprecation_warning`), and `get_connection`, under `deprecate_posargs`, passes `skip_frames=1`, for its wrapper (`django/core/mail/__init__.py:get_connection`).

## `warn_about_implementation`: the line of a definition

`warn_about_implementation` is for deprecations found in code a project wrote rather than in a call, such as an override with an old signature, where the line to name is its definition, which need not be on the stack. It takes a function, a class, a bound method, or a classmethod, staticmethod or property object, finds the unwrapped function's file and line with `inspect.getsourcefile` and `inspect.getsourcelines`, and calls `warnings.warn_explicit` with them (`django/utils/deprecation.py:warn_about_implementation`). `ModelAdmin` uses it for an override of `ModelAdmin.get_actions` without the action_location parameter (`django/contrib/admin/options.py:ModelAdmin._get_actions_with_action_location`; [Actions: `response_action` and `delete_selected`](../admin/actions.md)).

## `deprecate_posargs`

Making a parameter keyword-only breaks every call that passes it by position; `deprecate_posargs` lets the function be written in its final form, after a `*`, and still take the old calls for the period (`django/utils/deprecation.py:deprecate_posargs`). It is given the warning class and the names that became keyword-only, in their old order:

```python
# harbour/office/board.py
class RemovedInHarbour3Warning(DeprecationWarning):
    pass


@deprecate_posargs(RemovedInHarbour3Warning, ["berth"])
def moor(ship, *, berth="North Quay"):
    return f"{ship} moored at {berth}"
```

As it decorates, it refuses with `TypeError` a class (it goes on `__init__`), a classmethod or staticmethod object (it goes under them), a function with `*args` or no keyword-only parameter, and a listed name that is not keyword-only. A call with no more positional arguments than the function has positional parameters passes straight through. Extra ones are taken, in order, as the first of the listed names and moved into the keyword arguments, and the warning is raised with `skip_file_prefixes=django_file_prefixes()`. A coroutine function gets a coroutine wrapper, and the message for an `__init__` names its class, read from `__qualname__` because the class does not yet exist.

```text
# a run in a script, every warning recorded
moor("Beagle", berth="Pier 2")            'Beagle moored at Pier 2'
moor("Beagle", "Pier 2")                  'Beagle moored at Pier 2'   RemovedInHarbour3Warning:
    Passing positional argument(s) 'berth' to moor() is deprecated. Use keyword arguments instead.
moor("Beagle", "Pier 2", "Pier 3")
    TypeError: moor() takes at most 2 positional argument(s) (including 1 deprecated) but 3 were given.
moor("Beagle", "Pier 2", berth="Pier 3")
    TypeError: moor() got both deprecated positional and keyword argument values for 'berth'.
```

The docstring's caution follows: during the period no positional parameter may be added, since an old call's value would land in it. Django decorates the functions of `django.core.mail` and the constructors of `EmailMessage` and `EmailMultiAlternatives` ([Email messages: `EmailMessage` and `EmailMultiAlternatives`](../services/email-messages.md)).

## Renamed methods: `RenameMethodsBase`

`RenameMethodsBase` is a metaclass for renaming a method, its docstring citing ticket 15363; a subclass lists triples of old name, new name and warning class in `RenameMethodsBase.renamed_methods` (`django/utils/deprecation.py:RenameMethodsBase`). A class defining only the old name is warned as it is made and gets the new name too, and one defining only the new name gets the old; in both cases the old name becomes a `warn_about_renamed_method` wrapper that warns at each call. Nothing in Django uses either.
