---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The change list: `changelist_view` and `ChangeList`

`ModelAdmin.changelist_view` serves a model's list page, and `ChangeList` turns the query string into its queryset: the filters, the lookups left over, the joins, the ordering, the search, the count and the page. `BaseModelAdmin.lookup_allowed` decides which lookups a query string may make.

Whatever a user does to the list, filtering, sorting, searching or paging, is written in its query string, which is also the user's to write: the change list takes the keys it knows as instructions and every other key as a lookup on the model, and refuses a lookup that reaches too far. A `ChangeList` is made for each request and does all of this in its `__init__`, so the view receives it built and counted (`django/contrib/admin/views/main.py:ChangeList.__init__`).

## `changelist_view` in its order

The view asks `BaseModelAdmin.has_view_or_change_permission`, and raises `PermissionDenied` without it. `ModelAdmin.get_changelist_instance` reads the hooks (`ModelAdmin.get_list_display` and the others), puts `"action_checkbox"` in front of the columns when the user has an action for the change list, and makes the class `ModelAdmin.get_changelist` returns (`django/contrib/admin/options.py:ModelAdmin.get_changelist_instance`).

A query string the change list cannot use raises `IncorrectLookupParameters`, and the view redirects to its own path with `"?e=1"`, every other parameter dropped. If the error comes again with `"e"` present, the view renders `"admin/invalid_setup.html"`, "Database error": bad parameters with the flag already set mean, the comment reasons, that the database is at fault. `DisallowedModelAdminLookup` and `DisallowedModelAdminToField` are not caught: they are `SuspiciousOperation`s, which the handler answers with 400 ([How an exception becomes a response](../handlers/exceptions.md)) (`django/contrib/admin/options.py:ModelAdmin.changelist_view`).

A `"POST"` with an action goes to `ModelAdmin.response_action` with the queryset `ChangeList.get_queryset` builds again, the filtered list, of which the action gets the selected rows ([Actions: `response_action` and `delete_selected`](actions.md)). A `"POST"` with `"_save"` saves the rows of `ModelAdmin.list_editable`; otherwise, for a user who may change, the view builds that formset for the page ([The change list's columns: `list_display` and `list_editable`](list-display.md)). Then come the action form, the media and the context, with the preserved filters, the query string each link to a change form carries so that a save can return to the same list ([Filters and search: `list_filter`, `search_fields` and `date_hierarchy`](filters.md)). The note "0 of 2 selected" on nora's list counts the page's rows with `len`, which is the query that fetches them. The template is `ModelAdmin.change_list_template`, or the model's, the application's or `"admin/change_list.html"`, the first found ([The admin's templates and media](templates.md)).

## Reading the query string: `ChangeList.__init__`

| key | name | what it holds |
|---|---|---|
| `"q"` | `SEARCH_VAR` | the search term, read by `ChangeListSearchForm` |
| `"o"` | `ORDER_VAR` | the ordering, as indexes of columns |
| `"p"` | `PAGE_VAR` | the page number, 1 if it is not a number |
| `"all"` | `ALL_VAR` | every row, if no more than `ModelAdmin.list_max_show_all` |
| `"e"` | `ERROR_FLAG` | set by the redirect after an error |

`IGNORED_PARAMS` lists the keys that are not lookups: `"all"`, `"o"`, `"q"`, and the admin's `"_facets"`, `"_popup"`, `"_source_model"` and `"_to_field"`; `"p"` and `"e"` are deleted from the parameters outright. Every other key is a lookup (`django/contrib/admin/views/main.py:ChangeList.get_filters_params`). Errors of the search form become messages and do not stop the page: `"?q=%00"` showed "Null characters are not allowed." above an unsearched list.

`"_to_field"` is how a related-object popup names the field its relation points at, the primary key or another ([The admin's widgets: related objects, raw ids and autocomplete](widgets.md)). `BaseModelAdmin.to_field_allowed` admits the primary key, which a comment says the change page's URL shows already, a field that the table of one of the model's own many-to-many fields points at, and one that a relation from a registered model or an inline's model points at; it refuses the rest. `"?_to_field=tonnage"` was answered 400 (`django/contrib/admin/options.py:BaseModelAdmin.to_field_allowed`).

`ChangeList.root_queryset` is the model admin's `BaseModelAdmin.get_queryset`: the default manager, ordered by `BaseModelAdmin.get_ordering` ([Registering models: `AdminSite.register` and `ModelAdmin`](registration.md)). The title follows the permission: "Select ship to change" for nora, "Select port to view" on the ports.

## Which lookups are allowed: `lookup_allowed`

`ChangeList.get_filters` puts each lookup and each of its values to `BaseModelAdmin.lookup_allowed` before it makes a filter, and raises `DisallowedModelAdminLookup` at the first refusal. The documentation gives the reason: the lookups can be written by the user, and "they must be sanitized to prevent unauthorized data exposure" (`docs/ref/contrib/admin/index.txt`). A filter tests a value whether or not the page shows it, and a lookup across relations can test any model they reach.

The method walks the lookup's parts and keeps those that go somewhere new: the first field, and each field reached across a relation, except the related model's primary key, a link to a parent model and, where the related model's key is automatic, the field the foreign key was told to point at. A lookup with no more than one such part, a local field or a foreign key's value, is allowed, as is one that names no field and fails later. A longer one is allowed only where its path is `ModelAdmin.date_hierarchy` or is named by `get_list_filter`: as a field path, as the field of a pair, or as a `SimpleListFilter.parameter_name`. First of all it admits the lookups, value and all, by which a foreign key to the model limits its choices, which raw-id popups send (`django/contrib/admin/options.py:BaseModelAdmin.lookup_allowed`).

As nora, `"?tonnage__gt=300"` listed Endeavour, and `"?home__id__exact=1"` passed, the port's id being what home's key holds. `"?home__country=Malta"` was answered 400, logged as "Filtering by home__country not allowed", and so was `"?home__name=Valletta"`, though home__name is a search field: a search goes through `ModelAdmin.get_search_results`, not `lookup_allowed`.

## Building the queryset: `ChangeList.get_queryset`

`ChangeList.get_queryset` builds the queryset in a fixed order (`django/contrib/admin/views/main.py:ChangeList.get_queryset`). For a request that filters, searches and sorts:

```text figure=the-query
GET /admin/fleet/ship/?home__id__exact=1&q=end&o=2, as nora

ChangeList.__init__
  root_queryset      ShipAdmin.get_queryset: Ship's default manager
  get_queryset
    get_filters      lookup_allowed("home__id__exact", "1")  ->  True
                     home's RelatedFieldListFilter takes home__id__exact
                     and reads the ports for its choices: SELECT ... FROM "fleet_port"
    the filter       WHERE "fleet_ship"."home_id" = 1
    the leftovers    none
    apply_select_related  home is a column: INNER JOIN "fleet_port"
    get_ordering     o=2, index 2 of action_checkbox, name, tonnage, home, is_large:
                     tonnage, then "-pk", tonnage not being total
    get_search_results  "end" in the name, OR in home's name
    distinct         no: no path that repeats a row
  get_results
    the count, filtered and searched: SELECT COUNT(*) ...  ->  1
    the full count, of root_queryset: SELECT COUNT(*) FROM "fleet_ship"  ->  2
    one page: the result list is the whole queryset, not fetched

changelist_view
  "0 of 1 selected", the len of the result list:
    SELECT ... ORDER BY tonnage ASC, id DESC  ->  Endeavour
```

*One request to ShipAdmin's change list, with the SQL each step sent or added. The page reads "1 result (2 total)".*

`get_filters` makes a filter of each item of `ModelAdmin.list_filter`, and each filter takes the keys it expects out of the parameters, so what is left is lookups no filter claimed; the date hierarchy's year, with any month and day, becomes a bounded range. The leftovers go through `prepare_lookup_value`, which splits an `"__in"` value at its commas and makes an `"__isnull"` value a boolean (`django/contrib/admin/views/main.py:ChangeList.get_filters`).

`get_queryset` applies each filter's `ListFilter.queryset`, then the leftovers as one `Q` made by `build_q_object_from_lookup_parameters`, the values of one key joined by OR and the keys by AND: `"?name=Beagle&name=Endeavour"` listed both ships. Any exception there but `SuspiciousOperation` and `ImproperlyConfigured` becomes `IncorrectLookupParameters`, since, the comment says, there is no other way to validate the lookups; `"?tonnage=abc"` was redirected to `"?e=1"`.

`ChangeList.apply_select_related` runs unless the queryset has a `QuerySet.select_related` already. With `ModelAdmin.list_select_related` false, the default, it joins each column of `ModelAdmin.list_display` that is a foreign key or one-to-one field written by its name: ShipAdmin's list joins the port, and a column home_id would join nothing. A list or tuple joins what it names (`django/contrib/admin/views/main.py:ChangeList.apply_select_related`, `django/contrib/admin/views/main.py:ChangeList.get_select_related_fields`).

> **Changed in 6.1.** A false `list_select_related` used to join every non-null foreign key when `list_display` named one, and now joins only those it names (`docs/releases/6.1.txt`, `docs/ref/contrib/admin/index.txt`). `True` is deprecated: `ModelAdmin.__init_subclass__` warns with `RemovedInDjango2028Warning` as a class that sets it is defined, and `get_changelist_instance` when the hook returns it though the attribute is not `True`.

`ChangeList.get_ordering` starts from `BaseModelAdmin.get_ordering`, or the model's ordering. An `"o"` replaces it: indexes joined by dots, each with `"-"` for descending, into the columns as the change list holds them, `"action_checkbox"` first. So `"o=2"` is tonnage for nora, and would be home for a user with no action. `ChangeList.get_ordering_field` turns a column into a field, a method by its `"admin_order_field"`: `"?o=-4"`, the Large column, sorted by descending tonnage. A column with none, or an index past the end, is skipped: `"?o=9"` left only `"-pk"`. The queryset's own ordering is added, and `"-pk"` last unless `QuerySet.totally_ordered` finds the ordering total, so that, as the docstring says, the order is deterministic ([Annotations, ordering and the other methods that change the query](../querysets/methods.md)) (`django/contrib/admin/views/main.py:ChangeList.get_ordering`).

The search follows, from `get_search_results`, which says whether it may repeat rows. `QuerySet.distinct` is added when it may, or a field's filter or a leftover may: `lookup_spawns_duplicates` follows a path and answers yes where it crosses a many-to-many or a reverse foreign key. home__name does not; a search of ports by their ships' names would (`django/contrib/admin/utils.py:lookup_spawns_duplicates`).

## Counting and the page: `ChangeList.get_results`

`ChangeList.get_results` asks `ModelAdmin.get_paginator` for a paginator with `ModelAdmin.list_per_page`, 100 by default, and counts with it. Unless `BaseModelAdmin.show_full_result_count` is false it counts `root_queryset` too, for the total beside a filtered count, a query the documentation warns is costly on a large table (`docs/ref/contrib/admin/index.txt`). A list that fits one page, or one asked for with `"all"` and no longer than `list_max_show_all`, 200 by default, is the whole queryset; any other is `Paginator.page` of the page number, and an `InvalidPage` becomes `IncorrectLookupParameters` ([Pagination: `Paginator` and `Page`](../services/pagination.md)) (`django/contrib/admin/views/main.py:ChangeList.get_results`).

So `"?p=9"` on the two ships showed both: they fit one page, and the number was never used. With `list_per_page = 1` in a subclass of ShipAdmin, `"?p=9"` was redirected to `"?e=1"`, and `"?p=9&e=1"` was the "Database error" page.
