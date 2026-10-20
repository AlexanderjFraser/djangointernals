---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Pagination: `Paginator` and `Page`

How `Paginator` cuts a list or a queryset into numbered pages: the count, orphans, the check of a page number, the slice and the `Page`; and its asynchronous twins, `AsyncPaginator` and `AsyncPage`.

A paginator is given a whole list and a page size, and must find any page's objects without loading the list. A count and a slice suffice, and on a queryset each is one query: a count, and a SELECT with a LIMIT and, past the first page, an OFFSET. What the two paginators share is in `BasePaginator` (`django/core/paginator.py:BasePaginator`). `ListView` makes one when it is given a page size ([`DetailView` and `ListView`](../views/display.md#listview-many-objects-and-pages-of-them)).

## Making a paginator

`BasePaginator.__init__` keeps the list; the page size and the number of **orphans**, objects that may join the last page rather than make one of their own, both through `int`; whether the first page may be empty, `allow_empty_first_page=True` by default; and `BasePaginator.default_error_messages` with any given in `error_messages=` merged over them by key (`django/core/paginator.py:BasePaginator.__init__`).

> **Deprecated.** Orphans not fewer than the page size: `__init__` warns, `RemovedInDjango2028Warning`, whoever the caller, and is to raise `ValueError` in Django 2028 (`docs/releases/6.0.txt`).

On a queryset each page is its own query. Where the list's `ordered`, which a queryset has and a list lacks, is false, `BasePaginator._check_object_list_is_ordered` warns with `UnorderedObjectListWarning` that pagination "may yield inconsistent results" (`django/core/paginator.py:BasePaginator._check_object_list_is_ordered`). The test is of `QuerySet.ordered`, not `QuerySet.totally_ordered`, so an ordering by a column whose values repeat passes it ([Annotations, ordering and the other methods that change the query](../querysets/methods.md#ordered-and-totally_ordered)).

## Counting and the number of pages

`Paginator.count` calls the list's `count` where it is callable, not built in, and takes no argument, as `QuerySet.count` does, and otherwise takes `len` (`django/core/paginator.py:Paginator.count`). The built-in test turns away a list's own `count`, which `method_has_no_args`, not seeing a built-in as a method, would accept.

`count` and `Paginator.num_pages` are cached properties. `num_pages` is 0 for an empty list with `allow_empty_first_page=False`, and otherwise the count less the orphans, at least 1, divided by the page size and rounded up: an empty list has one empty page, and orphans add no page (`django/core/paginator.py:Paginator.num_pages`). `Paginator.page_range` runs from 1 to the number of pages; iterating a paginator yields its pages.

## A page by its number: `page` and `get_page`

`Paginator.page` checks the number and slices one page size from (number − 1) × page size; where the slice's end plus the orphans reaches the count, the slice runs to the end, and the orphans join the last page (`django/core/paginator.py:Paginator.page`). `BasePaginator._get_page`, a hook for a subclass that wants another class, wraps the slice in a `Page` (`django/core/paginator.py:BasePaginator._get_page`). Slicing a queryset not yet fetched only sets limits on a copy's query ([Evaluation and the result cache](../querysets/evaluation.md#an-index-and-a-slice)), so the rows wait until the page is read.

`Paginator.validate_number` hands the number and the number of pages to `BasePaginator._validate_number`, which returns the number through `int`, or raises a subclass of `InvalidPage` with one of the paginator's error messages, the defaults marked for translation (`django/core/paginator.py:BasePaginator._validate_number`):

| the number | raises | key of the message |
|---|---|---|
| a float with a fraction, or what `int` refuses (`1.5`, `"2.0"`, `None`) | `PageNotAnInteger`: That page number is not an integer | `"invalid_page"` |
| less than 1 | `EmptyPage`: That page number is less than 1 | `"min_page"` |
| above the number of pages | `EmptyPage`: That page contains no results | `"no_results"` |

`Paginator.get_page` takes a number as a request gave it: `PageNotAnInteger` becomes the first page, `EmptyPage` the last (`django/core/paginator.py:Paginator.get_page`). With `allow_empty_first_page=False` and nothing to page it still raises `EmptyPage`: there is no page 1, and the last page is then page 0.

Ten berths at Valletta, numbered 1 to 10, four to a page, then with two orphans, with the SQL each line sent:

```text
berths = Berth.objects.order_by("number")
paginator = Paginator(berths, 4)
paginator.num_pages  ->  3
  SELECT COUNT(*) AS "__count" FROM "office_berth"
page = paginator.page(2)  ->  <Page 2 of 3>   (0 queries)
[berth.number for berth in page]  ->  [5, 6, 7, 8]
  SELECT "office_berth"."port_id", "office_berth"."number", "office_berth"."metres" FROM "office_berth" ORDER BY "office_berth"."number" ASC LIMIT 4 OFFSET 4
page[0]  ->  <Berth: Berth object ((1, 5))>   (0 queries)
paginator.page(4)  ->  raises EmptyPage: That page contains no results
paginator.get_page(4)  ->  <Page 3 of 3>
paginator.get_page("four")  ->  <Page 1 of 3>

paginator = Paginator(berths, 4, orphans=2)
paginator.num_pages  ->  2
  SELECT COUNT(*) AS "__count" FROM "office_berth"
page = paginator.page(2)  ->  <Page 2 of 2>
[berth.number for berth in page]  ->  [5, 6, 7, 8, 9, 10]
  SELECT "office_berth"."port_id", "office_berth"."number", "office_berth"."metres" FROM "office_berth" ORDER BY "office_berth"."number" ASC LIMIT 6 OFFSET 4
page.start_index(), page.end_index()  ->  (5, 10)
```

## `Page`

`Page` is a `collections.abc.Sequence`, which builds iteration, `in` and `reversed` on its `__len__` and `__getitem__` (`django/core/paginator.py:Page`). The first time `Page.__getitem__` is used it turns the page's objects into a list, so that, its comment says, a queryset is not a query for each index. Iteration goes through it, so the rows are fetched once; the run's `page[0]` sent nothing.

`Page.has_next` compares the number with the paginator's `num_pages`; `Page.next_page_number` and `Page.previous_page_number` go through `validate_number`, so past either end they raise `EmptyPage`. `Page.start_index` and `Page.end_index` count from 1 across the list: the start is 0 for an empty list, and the last page ends at the count, orphans included (`django/core/paginator.py:Page.start_index`, `django/core/paginator.py:Page.end_index`).

## The elided page range

`Paginator.get_elided_page_range` gives the numbers for a long row of links, with `BasePaginator.ELLIPSIS`, a translatable `"…"`, for what it leaves out. It keeps `on_ends=2` pages at each end and `on_each_side=3` around the current one, gives every page when there are no more than twice their sum, and never elides a single page (`django/core/paginator.py:BasePaginator._get_elided_page_range`).

> **Trap.** `get_elided_page_range` is a generator function: a number it refuses raises when the result is first iterated, not when it is called.

## `AsyncPaginator` and `AsyncPage`

> **Changed in 6.0.** `AsyncPaginator` and `AsyncPage` are new (`docs/releases/6.0.txt`).

`AsyncPaginator` takes the same arguments and has an asynchronous twin of each method, named with an a in front (`AsyncPaginator.apage`), and `acount`, `anum_pages` and `apage_range` for the properties. `AsyncPaginator.acount` awaits the list's `acount` where it is a coroutine function with no argument, as `QuerySet.acount` is, and otherwise takes `len` (`django/core/paginator.py:AsyncPaginator.acount`).

`AsyncPage` is not a sequence. Its `__len__`, `__getitem__` and `__reversed__` are synchronous and fetch nothing: while its objects are not a list they raise `TypeError`, until `AsyncPage.aget_object_list` makes them one, by `async for` where the list allows it and otherwise by `list` under `sync_to_async` (`django/core/paginator.py:AsyncPage.aget_object_list`). An `async for` over the page needs no such step.

```text
page = await AsyncPaginator(berths, 4).apage(3)  ->  <Async Page 3>
len(page)  ->  raises TypeError: AsyncPage.aget_object_list() must be awaited before calling len().
```
