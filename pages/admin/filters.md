---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Filters and search: `list_filter`, `search_fields` and `date_hierarchy`

A change list is narrowed three ways, each set by an option of the model admin and carried in the query string: the filters of `ModelAdmin.list_filter`, each a `ListFilter` made for the request; the search of `ModelAdmin.search_fields`, which `ModelAdmin.get_search_results` turns into one `Q` for each term; and the drill-down through dates of `ModelAdmin.date_hierarchy`. Preserved filters carry the narrowing to the change form and back.

The change list keeps nothing between requests: a filter clicked or a year chosen is a parameter of its URL. `ChangeList.get_filters` first puts every parameter to `BaseModelAdmin.lookup_allowed`, which admits a lookup reaching into a related model only when a filter or the date hierarchy names it (or a raw-id popup needs it); then it lets each filter take its own parameters, and hands back the rest to be applied as plain lookups ([The change list: `changelist_view` and `ChangeList`](change-list.md)) (`django/contrib/admin/views/main.py:ChangeList.get_filters`). The search's parameter, `"q"`, is set aside before that: the user gives only a term, and the lookups it becomes are the model admin's own.

## The three forms of `list_filter`

`ModelAdmin.list_filter`, as `ModelAdmin.get_list_filter` returns it for the request, holds items of three kinds, and `get_filters` makes an object of each, in order:

- a field's name, or a path across relations (`"home__country"`), for which `FieldListFilter.create` chooses a class;
- a pair of a field's name and a subclass of `FieldListFilter`, used as it is: the way to ask for `RelatedOnlyFieldListFilter` (only related rows in use) or `EmptyFieldListFilter`, which no test chooses;
- a subclass of `ListFilter`, in practice of `SimpleListFilter`, made with the request, the parameters, the model and the model admin.

## What a filter is: `ListFilter`

A **filter** answers the change list in four methods. `ListFilter.expected_parameters` names the keys it understands; `ListFilter.__init__` starts `ListFilter.used_parameters` empty, and the constructors of `SimpleListFilter` and `FieldListFilter` pop those keys from the request's parameters into it. `ListFilter.queryset` narrows the queryset, or returns `None` to leave it. `ListFilter.has_output` says whether there is anything to show, and `ListFilter.choices` yields the links, which the `admin_list_filter` tag renders with `ListFilter.template`, `"admin/filter.html"`, under `ListFilter.title`. A filter without a title is refused with `ImproperlyConfigured` (`django/contrib/admin/filters.py:ListFilter`, `django/contrib/admin/templatetags/admin_list.py:admin_list_filter`).

A choice's link comes from `ChangeList.get_query_string`, which copies the current parameters, drops the keys that begin with the prefixes it is given, and adds the new ones (`django/contrib/admin/views/main.py:ChangeList.get_query_string`). So one filter's links keep the other filters and the search: with the tonnage filter below set to large, the home filter offered ?home__id__exact=1&size=large for Valletta.

> **Trap.** A filter whose `has_output` is false is left out with its `queryset`, but has taken its parameters: with Piraeus deleted, the home filter had one choice and no output, and ?home__id__exact=2 listed both ships.

## `SimpleListFilter`

`SimpleListFilter` is the filter a project writes when the narrowing is not a lookup on one field. It takes one parameter, `SimpleListFilter.parameter_name`, and is refused with `ImproperlyConfigured` without one. Its choices are the pairs of value and label that `SimpleListFilter.lookups` returns; with none, it has no output. `SimpleListFilter.value` is the parameter's last value, a string, or `None` (`django/contrib/admin/filters.py:SimpleListFilter`). The office adds one by tonnage:

```python
# harbour/fleet/admin.py
class TonnageFilter(admin.SimpleListFilter):
    title = "tonnage"
    parameter_name = "size"

    def lookups(self, request, model_admin):
        return [("small", "Under 300 tons"), ("large", "300 tons and over")]

    def queryset(self, request, queryset):
        if self.value() == "small":
            return queryset.filter(tonnage__lt=300)
        if self.value() == "large":
            return queryset.filter(tonnage__gte=300)

# and in ShipAdmin: list_filter = ["home", TonnageFilter]
```

For nora, ?size=large listed Endeavour alone, its count and its page each sent with `WHERE "fleet_ship"."tonnage" >= 300`.

## `FieldListFilter` and the choice of class

A filter named by a field is a `FieldListFilter`. It pops its parameters through `prepare_lookup_value`, which splits an `"__in"` value at `FieldListFilter.list_separator` and makes an `"__isnull"` one a boolean. Its `queryset` joins the parameters with AND, and each one's values with OR, into a `Q`; a `ValueError` or `ValidationError` from a value becomes `IncorrectLookupParameters`, which the change list answers with a redirect to its bare path with "e=1" (`django/contrib/admin/filters.py:FieldListFilter`).

The class comes from a registry, `FieldListFilter._field_list_filters`, of pairs of a test and a class. `FieldListFilter.register` appends a pair, or with priority puts it ahead of those registered without; `FieldListFilter.create` makes the first class whose test the field passes (`django/contrib/admin/filters.py:FieldListFilter.create`). The module registers `RelatedFieldListFilter` for a relation, `BooleanFieldListFilter`, `ChoicesFieldListFilter` for a field with choices, `DateFieldListFilter` for a date (Any date, Today, Past 7 days, This month, This year, as `"__gte"` and `"__lt"`), and last `AllValuesFieldListFilter`, offering each distinct value. That one accepts every field, as the last resort its comment calls it, so a pair registered after it without priority is never chosen.

The office's `"home"` makes a `RelatedFieldListFilter`. It reads its choices when it is made, in the ordering of the related model's model admin, or of the related model when that sets none: the query for the ports that every load of the ships' list sends. It adds an empty choice for a nullable or many-to-many field, and has output only with more than one choice (`django/contrib/admin/filters.py:RelatedFieldListFilter`). For nora it offered All, selected, then Piraeus (?home__id__exact=2) and Valletta (?home__id__exact=1).

## Facets

`ModelAdmin.show_facets` decides whether each choice shows the count of rows it would leave: `ShowFacets.ALLOW`, the default, when the query string has `"_facets"`; `ShowFacets.ALWAYS`; or `ShowFacets.NEVER` (`django/contrib/admin/views/main.py:ChangeList.__init__`). For each filter, `FacetsMixin.get_facet_queryset` builds the change list's queryset again with every filter but this one, the search included, and aggregates over it a count for each choice, restricted by that choice's lookup; a `SimpleListFilter` runs its own `queryset` with each value in turn (`django/contrib/admin/filters.py:FacetsMixin.get_facet_queryset`, `django/contrib/admin/filters.py:SimpleListFilter.get_facet_counts`). So a count is what choosing it would show. Building the queryset again makes every filter again: "_facets" added four queries to nora's list, the ports and the aggregate for each filter, a cost the documentation warns of (`docs/ref/contrib/admin/index.txt`). The choices read Piraeus (0), Valletta (2), Under 300 tons (1) and 300 tons and over (1).

## The search: `ModelAdmin.get_search_results`

The `search_form` tag draws the search box when the model admin has `search_fields`, with `ModelAdmin.search_help_text` under it. The change list calls `get_search_results` with the request, the queryset as the filters and the ordering have left it, and the term, and gets back the queryset narrowed and whether a row may now appear twice (`django/contrib/admin/options.py:ModelAdmin.get_search_results`).

The method makes each name of `ModelAdmin.get_search_fields` a lookup: after `"^"`, `"istartswith"`; after `"="`, `"iexact"`; after `"@"`, `"search"`; a path ending in a lookup its last field has, such as `"tonnage__exact"`, as written; anything else, `"icontains"`. It splits the term with `smart_split`, which keeps a quoted phrase whole, and unquotes a phrase with `unescape_string_literal`. Each piece becomes the OR of the lookups, and the pieces are joined with AND: every piece must match some field. "valletta" found both ships by their home's name, and "end valletta" Endeavour, two such ORs joined by AND.

```text
# nora's searches; search_fields = ["name", "home__name"]
q=end
    WHERE ("fleet_ship"."name" LIKE '%end%' ESCAPE '\' OR "fleet_port"."name" LIKE '%end%' ESCAPE '\')
    Endeavour
q="end valletta"
    WHERE ("fleet_ship"."name" LIKE '%end valletta%' ESCAPE '\' OR "fleet_port"."name" LIKE '%end valletta%' ESCAPE '\')
    no ships
```

An `"exact"` lookup on a field that is not text is treated apart: each piece is first converted by the field's form field (booleans more strictly, by `django/contrib/admin/formfields.py`), and where it does not convert the lookup is left out of that piece's OR; a piece no lookup can take matches nothing. With `search_fields = ["name", "tonnage__exact"]`, "beagle 235" compared beagle with the name alone, and 235 with the name or, as a number, the tonnage.

> **Changed in 6.1.** A term that a field's type cannot take is skipped for that field (`docs/ref/contrib/admin/index.txt`).

Last, `lookup_spawns_duplicates` asks of each searched path whether it crosses a relation that can repeat a row, a many-to-many or a foreign key followed backwards; if one does, the change list makes its queryset distinct (`django/contrib/admin/utils.py:lookup_spawns_duplicates`).

## `date_hierarchy`

`ModelAdmin.date_hierarchy` names a date or date-time field, the model's or across a relation, and puts above the list links that narrow by year, then month, then day. Its parameters are the path with "__year", "__month" and "__day", but given a year `get_filters` pops them and puts a range in their place, from the first instant of the year, month or day (`"__gte"`) to the first of the next (`"__lt"`), made aware when `USE_TZ` is true; its comment gives the reason, a more efficient query. A value that makes no date raises `IncorrectLookupParameters` (`django/contrib/admin/views/main.py:ChangeList.get_filters`).

The `date_hierarchy` tag draws the links. With no parameter it asks for the earliest and latest dates listed, and starts at the months of one year, or the days of one month, when every row falls in it; `QuerySet.dates`, or `QuerySet.datetimes`, at that level give the links (`django/contrib/admin/templatetags/admin_list.py:date_hierarchy`). With Voyage's model admin given `date_hierarchy = "sailed"`:

```text
# piet's change list of voyages; date_hierarchy = "sailed"
/admin/fleet/voyage/
    links  1768 (?sailed__year=1768), 1771 (?sailed__year=1771)
/admin/fleet/voyage/?sailed__year=1768
    WHERE ("fleet_voyage"."sailed" >= '1768-01-01' AND "fleet_voyage"."sailed" < '1769-01-01')
    links  August 1768 (?sailed__month=8&sailed__year=1768)
```

## Preserved filters

A user who filters the list, opens a ship and saves it should come back to the same list. `ModelAdmin.get_preserved_filters` gives, on the change list, its query string encoded as one parameter, `"_changelist_filters"`, and on the model admin's other pages the one they were given; with `ModelAdmin.preserve_filters` false, nothing (`django/contrib/admin/options.py:ModelAdmin.get_preserved_filters`). `add_preserved_filters`, a template tag the views also call, adds it to a URL, unpacked when the URL is the change list's (`django/contrib/admin/templatetags/admin_urls.py:add_preserved_filters`). The rows' links carry it, the change form keeps it, and the redirects back to the change list after a save or a delete give it back (`django/contrib/admin/options.py:ModelAdmin._response_post_save`, `django/contrib/admin/options.py:ModelAdmin.response_delete`). On ?home__id__exact=1, nora's link to Endeavour ended in ?_changelist_filters=home__id__exact%3D1, and "Save" on its change form answered 302 to /admin/fleet/ship/?home__id__exact=1.
