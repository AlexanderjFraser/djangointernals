---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Settings for one test: `override_settings` and `TestContextDecorator`

`override_settings` changes settings for a block, a test or a test case class and puts them back, and `modify_settings` adds items to a list setting or takes them out. Both are built on `TestContextDecorator`, which makes one pair of methods serve as a context manager, a function decorator and a class decorator; so are `isolate_apps`, `override_script_prefix`, `override_system_checks` and `ignore_warnings`.

A test may change something the whole process shares, for a few lines, one test or every test of a class, and the next test must find it as it was. What `override_settings` does to the settings on entering and leaving is told in [Overriding settings](../startup/overrides.md).

## `TestContextDecorator`: one change, three scopes

A subclass implements `TestContextDecorator.enable`, which makes the change and may return a value, and `TestContextDecorator.disable`, which undoes it. As a context manager it calls the first on entering and the second on leaving, letting an exception go on. Called on a class it uses `decorate_class`, on any other callable `decorate_callable`, and refuses anything else with a `TypeError` (`django/test/utils.py:TestContextDecorator.__call__`).

`TestContextDecorator.decorate_callable` wraps the function in one that runs it inside `with self`, passing the value of `enable` under the keyword `TestContextDecorator.kwarg_name` holds, if any. A coroutine function gets a coroutine function as its wrapper, so that, in the comment's words, the `with` statement executes at the right time: a plain wrapper would leave the block on making the coroutine, before its body ran. `SimpleTestCase` runs a test method through `async_to_sync` only if it is a coroutine function, which the wrapper is ([One test, in order: `SimpleTestCase`](simple-test-case.md); `django/test/utils.py:TestContextDecorator.decorate_callable`, `django/test/testcases.py:SimpleTestCase._setup_and_call`).

`TestContextDecorator.decorate_class` takes only a subclass of `unittest.TestCase`, else `TypeError`, and replaces its `setUp` with one that calls `enable`, registers `disable` with `unittest.TestCase.addCleanup`, sets the value of `enable` as the attribute `TestContextDecorator.attr_name` names, if any, and calls the class's own `setUp`. The change holds for each test from `setUp` to its cleanups, even when the class's `setUp` raises, since `unittest` runs the cleanups of a test whose set-up failed. It does not hold in `setUpClass`, and a subclass that defines a `setUp` without calling its parent's loses it (`django/test/utils.py:TestContextDecorator.decorate_class`).

## `override_settings` on a test and on a class

On a function, `override_settings` uses the inherited `decorate_callable`. On a class, `override_settings.decorate_class` replaces no `setUp`: it takes only a subclass of `SimpleTestCase`, refusing any other with a `ValueError`, "Only subclasses of Django SimpleTestCase can be decorated with override_settings", and records the values as `SimpleTestCase._overridden_settings` (`django/test/utils.py:override_settings.decorate_class`). `SimpleTestCase.setUpClass` enters an `override_settings` of those values with `unittest.TestCase.enterClassContext`, which leaves it as a class cleanup, after `tearDownClass` (`django/test/testcases.py:SimpleTestCase.setUpClass`). The values hold for a `TestCase`'s `setUpTestData`, every test and `tearDownClass`, but not for what a class's own `setUpClass` does before calling its parent's.

A subclass inherits `_overridden_settings`. If the class has one already, `override_settings.save_options` makes a new dictionary of those values and its own, which win, the comment saying this prevents subclasses from altering their parent. Of two decorators on one class, the outer wins.

A test method's override is entered when the method is called, after `setUp`, inside the class's. Here the class mounts the site under archive/, and its tests put the project's URLconf back:

```python
# harbour/office/tests/test_overrides.py
from django.apps import apps
from django.conf import settings
from django.db import models
from django.test import SimpleTestCase, modify_settings, override_settings
from django.test.utils import isolate_apps
from django.urls import include, path, reverse

urlpatterns = [path("archive/", include("harbour.urls"))]


@override_settings(ROOT_URLCONF="harbour.office.tests.test_overrides")
class ArchiveUrlTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        print("setUpClass:", reverse("ship-detail", args=[1]))

    def setUp(self):
        print("setUp:", reverse("ship-detail", args=[1]))

    @override_settings(ROOT_URLCONF="harbour.urls")
    def test_method_override(self):
        print("test:", reverse("ship-detail", args=[1]))

    @override_settings(ROOT_URLCONF="harbour.urls")
    async def test_async(self):
        print("test:", reverse("ship-detail", args=[1]))


class MiddlewareTests(SimpleTestCase):
    @modify_settings(MIDDLEWARE={"remove": "django.middleware.csrf.CsrfViewMiddleware"})
    def test_without_csrf(self):
        print(*settings.MIDDLEWARE, sep="\n")


class BuoyTests(SimpleTestCase):
    @isolate_apps("harbour.office", kwarg_name="registry")
    def test_buoy(self, registry):
        class Buoy(models.Model):
            number = models.PositiveIntegerField()

        print([m.__name__ for m in registry.get_models()], Buoy in apps.get_models())
```

```text
$ python manage.py test harbour.office.tests.test_overrides -v 2
Found 4 test(s).
Skipping setup of unused database(s): archive, default.
System check identified no issues (0 silenced).
setUpClass: /archive/ships/1/
test_async (harbour.office.tests.test_overrides.ArchiveUrlTests.test_async) ... setUp: /archive/ships/1/
test: /ships/1/
ok
test_method_override (harbour.office.tests.test_overrides.ArchiveUrlTests.test_method_override) ... setUp: /archive/ships/1/
test: /ships/1/
ok
test_buoy (harbour.office.tests.test_overrides.BuoyTests.test_buoy) ... ['Buoy'] False
ok
test_without_csrf (harbour.office.tests.test_overrides.MiddlewareTests.test_without_csrf) ... django.contrib.sessions.middleware.SessionMiddleware
django.middleware.common.CommonMiddleware
django.contrib.auth.middleware.AuthenticationMiddleware
django.contrib.messages.middleware.MessageMiddleware
ok

----------------------------------------------------------------------
Ran 4 tests in 0.005s

OK
```

`setUpClass` and each `setUp` saw the class's URLconf, and each method its own, the async one too.

If a receiver raises while an override is entered, `override_settings.enable` keeps the exception as `override_settings.enable_exception` and calls `disable`, which restores the settings, sends the signal for leaving, and raises it (`django/test/utils.py:override_settings.enable`, `django/test/utils.py:override_settings.disable`). `COMPLEX_OVERRIDE_SETTINGS`, the settings that may not work well with `override_settings` (ticket #19031), holds `"DATABASES"` alone, and for it a receiver warns on entering "Overriding setting DATABASES can lead to unexpected behavior." (`django/test/signals.py:complex_setting_changed`). `SimpleTestCase.settings` and `SimpleTestCase.modify_settings` return a new decorator of each kind, for a `with` block (`django/test/testcases.py:SimpleTestCase.settings`, `django/test/testcases.py:SimpleTestCase.modify_settings`).

## `modify_settings`: items of a list

`modify_settings` takes, for each setting, a dictionary of actions, `"append"`, `"prepend"` and `"remove"`, each with a list of items or a string, which counts as one item. `modify_settings.enable` works out each new list for `override_settings.enable`, from a copy of the setting's value (an empty list if it is not defined), applying the actions in the dictionary's order, adding only items not already there and removing every item named. Any other action, `"insert"` say, raises `ValueError` ("Unsupported action: insert") before the settings are touched (`django/test/utils.py:modify_settings.enable`).

On a class it uses `override_settings.decorate_class`, with its refusal and message. `modify_settings.save_options` keeps a list of pairs, a setting and its actions, as `SimpleTestCase._modified_settings`, a subclass's added to a copy of its parent's, and `SimpleTestCase.setUpClass` enters it after the class's `override_settings`, whichever decorator is written first. Where the list names a setting twice, from a parent and a subclass, `enable` cumulates, in its comment's word: the later entry starts from the list the earlier made.

## The other changes

`isolate_apps` gives a test its own app registry: `isolate_apps.enable` keeps `Options.default_apps`, puts in its place a new `Apps` populated with the applications it is given, and returns it (`django/test/utils.py:isolate_apps.enable`). A new model's options take that registry as their `apps` unless its `Meta` gives one, and `ModelBase.__new__` registers a model that is not abstract there, not in the project's registry (`django/db/models/options.py:Options.__init__`, `django/db/models/options.py:Options.contribute_to_class`, `django/db/models/base.py:ModelBase.__new__`). The run's Buoy was in the new registry alone. On a class it is entered in `setUp`, so a model in the class's body is not isolated.

> **Trap.** The documentation calls the arguments app labels, but `Apps` takes them as entries of `INSTALLED_APPS`: `isolate_apps("office")` raises `ModuleNotFoundError`, "No module named 'office'" (`docs/topics/testing/tools.txt`; `django/apps/registry.py:Apps.populate`).

`override_script_prefix` sets a script prefix and puts the old one back ([The script prefix, the current URLconf and the caches](../urls/state.md); `django/test/utils.py:override_script_prefix`). `override_system_checks` leaves the check registry only the checks it is given, and the deployment checks too when its second argument is not `None` ([The system checks](../commands/checks.md); `django/test/utils.py:override_system_checks.enable`). `ignore_warnings` adds an `"ignore"` filter inside `warnings.catch_warnings`, which leaving restores (`django/test/utils.py:ignore_warnings.enable`).
