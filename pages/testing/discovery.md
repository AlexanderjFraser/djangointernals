---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Finding and ordering the tests: `DiscoverRunner.build_suite`

`DiscoverRunner.build_suite` turns the labels typed after `test` into the suite the runner runs: each label loaded by name or discovered by `unittest`'s loader, the tests narrowed by `-k` and by tags, sorted into bins by test case class, reversed or shuffled on request, and counted.

The runner calls it after setting up the test environment; what it returns decides what runs and which test databases are made ([The runner: the test command and `DiscoverRunner`](runner.md), [Which databases a test uses: `databases`](test-databases.md)).

## The steps

In order (`django/test/runner.py:DiscoverRunner.build_suite`):

1. With no labels, the one label `"."`, the current directory.
2. The pattern (`--pattern`, `"test*.py"` by default) and the top-level directory (`-t`) gathered for discovery.
3. With `--shuffle`, the shuffler made and its seed logged, before anything loads.
4. Each label loaded by `DiscoverRunner.load_tests_for_label`, and flattened into one list of tests by `iter_test_cases`, which refuses a string with a `TypeError`, a comment says to prevent an unfriendly `RecursionError` (`django/test/utils.py:iter_test_cases`).
5. With `--tag` or `--exclude-tag`, the list filtered.
6. The list reordered by `reorder_tests`, which drops duplicates.
7. "Found N test(s)." logged, and the list made into a suite by `DiscoverRunner.test_suite` (`unittest.TestSuite` by default); with `--parallel` above 1 and more than one class, cut by class for the workers ([Running in parallel: `ParallelTestSuite`](parallel.md)).

## A label, by name or by path

`load_tests_for_label` first asks whether the label exists on disk. If not, it is a dotted name, and `unittest.TestLoader.loadTestsFromName` loads it as a module, a class or one method; if that holds a test, it is the answer. A name whose import raises `ImportError`, or that names something missing, holds one too: an instance of `unittest.loader._FailedTest`, which raises the error when it runs. Any other error in the import, a `SyntaxError` among them, ends the run (`django/test/runner.py:DiscoverRunner.load_tests_for_label`).

For a label on disk, or one that loaded nothing, `try_importing` imports it. A module that is not a package ends there, with whatever the loader found. A label that does not import, is not a directory and exists is a file, and is refused. A package or a directory is searched by `unittest.TestLoader.discover` for modules that match the pattern; so is `"."`, whose `TypeError` from `importlib.import_module` counts as not importable (`django/test/runner.py:try_importing`).

| label | example | what is run |
|---|---|---|
| a module, a class or a method | harbour.office.tests.test_ships.ShipPageTests | what is loaded by the name |
| a package | harbour.office | the modules discovered, if its own module holds no test |
| a directory | harbour/office/tests | the modules discovered |
| a file | harbour/office/tests/test_ships.py | nothing: refused |

```text
$ python manage.py test harbour/office/tests/test_ships.py
...
RuntimeError: One of the test labels is a path to a file: 'harbour/office/tests/test_ships.py', which is not supported. Use a dotted module name or path to a directory instead.
```

For a directory, unless `-t` was given, `find_top_level` climbs from the label's directory while each holds an `"__init__.py"`, and discovery imports from the first that does not. Its comment gives the reason: `unittest` would take the start directory itself as the top level, and break its modules' relative imports (`django/test/runner.py:find_top_level`). After each discovery the runner sets the top level kept on its loader, `DiscoverRunner.test_loader` (`unittest.defaultTestLoader` by default), to `None`, which the comment says supports running tests from two top levels; on Python 3.14, `unittest.TestLoader.discover` already restores, on returning, the value it began with (`django/test/runner.py:DiscoverRunner.load_tests_for_label`).

## Choosing by name: `-k`

`DiscoverRunner.__init__` wraps a `-k` pattern without `"*"` in a `"*"` at each end, as `unittest`'s own `-k` does; a comment notes that `unittest` does not export the function. `DiscoverRunner.load_with_patterns` sets the patterns as the loader's `unittest.TestLoader.testNamePatterns` while a label loads, and puts the old value back in a `finally`. The loader matches them with `fnmatch.fnmatchcase` against a test method's full name, module, class and method dotted together, so a pattern with a star must match the whole name: `-k "test_*url"` found no test, `-k "*test_*url"` found test_detail_url. The patterns filter what the loader collects from a class; a method named outright by a label is loaded whatever `-k` says.

## Tags

The decorator `tag` keeps a set of names on the class or the method as its tags attribute; where there are tags already, inherited ones too, it assigns the union, a new set, so a tagged subclass leaves its parent's alone (`django/test/utils.py:tag`).

`test_match_tags` takes a test's tags to be its class's and its method's together. With `--tag`, a test must have one of the names; with `--exclude-tag`, none of them, so exclusion wins. A test that failed to load always matches: the comment's reason is to keep a syntax error, for instance, from letting tests falsely pass (`django/test/runner.py:test_match_tags`). `filter_tests_by_tags` applies it to the whole list, and the names are logged at the debug level, which is printed from verbosity 2.

A second module beside test_ships.py has a tagged test:

```python
# harbour/office/tests/test_registry.py
import unittest

from django.test import TransactionTestCase, tag

from harbour.fleet.models import Port, Ship


class RegistryTests(TransactionTestCase):
    @tag("slow")
    def test_register(self):
        home = Port.objects.create(name="Valletta", country="Malta")
        Ship.objects.create(name="Beagle", tonnage=235, home=home)
        self.assertEqual(Ship.objects.count(), 1)

    def test_starts_empty(self):
        self.assertFalse(Ship.objects.exists())


class TonnageTests(unittest.TestCase):
    def test_tons_to_tonnes(self):
        self.assertEqual(round(366 * 1.016), 372)
```

With a misspelt label typed last, the failed import passes the tag filter and runs first:

```text
$ python manage.py test harbour.office harbour.office.tests.test_shps --tag slow -v 2
Including test tag(s): slow.
Found 2 test(s).
...
test_shps (unittest.loader._FailedTest.test_shps) ... ERROR
test_register (harbour.office.tests.test_registry.RegistryTests.test_register) ... ok
...
```

## The order: `reorder_tests`

Django's documentation gives the reason for the order: to guarantee that every `TestCase` starts with a clean database (`docs/topics/testing/overview.txt`). `reorder_tests` is given `unittest.loader._FailedTest`, then the classes of `DiscoverRunner.reorder_by`, `TestCase` and `SimpleTestCase`; it keeps a bin for each and one for the rest, and puts each test in the bin of the first class it is an instance of. The failures of loading come first, a comment says for quicker feedback. A `TransactionTestCase`, being no `TestCase`, lands in the bin of `SimpleTestCase` (`django/test/runner.py:reorder_tests`).

Inside a bin each class's tests are kept in an `OrderedSet`: a class's tests come together even when loaded apart, the classes in the order first met, and a test loaded twice is kept once, two tests of one class and method being equal. The labels harbour.office and harbour.office.tests.test_ships found seven tests, not eleven. Both modules, database lines left out:

```text
$ python manage.py test harbour.office -v 2
Found 7 test(s).
...
test_list_shows_ships (harbour.office.tests.test_ships.ShipPageTests.test_list_shows_ships) ... ok
test_missing_ship_is_404 (harbour.office.tests.test_ships.ShipPageTests.test_missing_ship_is_404) ... ok
test_rename (harbour.office.tests.test_ships.ShipPageTests.test_rename) ... ok
test_register (harbour.office.tests.test_registry.RegistryTests.test_register) ... ok
test_starts_empty (harbour.office.tests.test_registry.RegistryTests.test_starts_empty) ... ok
test_detail_url (harbour.office.tests.test_ships.ShipUrlTests.test_detail_url) ... ok
test_tons_to_tonnes (harbour.office.tests.test_registry.TonnageTests.test_tons_to_tonnes) ... ok
...
```

RegistryTests precedes ShipUrlTests because discovery met test_registry.py first: `unittest` sorts the paths it imports, and a class's method names.

## Reversing and shuffling

Each bin passes through `reorder_test_bin`, so neither option moves a test out of its bin. `--reverse` reverses the bin's list, which stays grouped by class: the run above, reversed, began with test_rename and ended its second bin with test_register (`django/test/runner.py:reorder_test_bin`).

`--shuffle` takes an optional seed. Its default, `False`, is what `DiscoverRunner.setup_shuffler` reads as no shuffling; given bare it is `None`, and `Shuffler` draws a seed of at most ten digits. `Shuffler.shuffle` sorts the items by the MD5 of the seed followed by each item's key, so the order of two items depends only on the seed and their keys. That is the docstring's consistency property: for one seed and key function, two sets shuffled agree in order on the items they share (`django/test/runner.py:Shuffler`). `shuffle_tests` shuffles each class's tests by their ids, then the classes by module and qualified name, so a class's tests stay together (`django/test/runner.py:shuffle_tests`).

The seed is logged before the tests load and again after the suite, by `DiscoverRunner.run_suite`:

```text
$ python manage.py test harbour.office --shuffle 42 -v 2
Using shuffle seed: 42 (given)
...
test_missing_ship_is_404 (harbour.office.tests.test_ships.ShipPageTests.test_missing_ship_is_404) ... ok
test_rename (harbour.office.tests.test_ships.ShipPageTests.test_rename) ... ok
test_list_shows_ships (harbour.office.tests.test_ships.ShipPageTests.test_list_shows_ships) ... ok
...
Used shuffle seed: 42 (given)
...
```

A second run with seed 42 printed the same order, and with `-k Ship` added these three still ran in this order. With both options the tests are shuffled, then reversed, which the docstring of `reorder_tests` says allows reversing the same random order.
