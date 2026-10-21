---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The date views: a date, an interval and its neighbours

The date views `YearArchiveView`, `MonthArchiveView`, `WeekArchiveView` and `DayArchiveView` read a date from the URL, turn it into an interval on the model's date field, ask the database for what falls inside it, and find the periods on either side. A `MonthArchiveView` does it all in its `get_dated_items`, taking the field's name from `date_field` and leaving out what is dated after the present unless `allow_future` is set.

A site that publishes things by date wants an archive: a page for a year that lists its months, a page for a month that lists what appeared in it, a page for a day, and on each a link to the period before and the period after. The pages differ in the size of the period. Each has to do the same things. It reads a date out of the URL. It turns the date into an interval with a beginning and an end. It asks the database for the objects whose date falls inside. And it works out what else the page needs: the smaller periods within a year or a month that have anything in them, and the neighbours worth linking to.

Of the seven date views ([The seven date views](date-views.md)), six are built on the same mixins as the list view, `MultipleObjectMixin` and `MultipleObjectTemplateResponseMixin` ([`DetailView` and `ListView`](display.md#listview-many-objects-and-pages-of-them)). The seventh shows one object and is built on the detail view's.

## The unit mixins and `DateMixin`: reading a date from the URL

A mixin for each unit, `YearMixin`, `MonthMixin`, `WeekMixin` and `DayMixin`, knows how to read that unit from a request and how to step from one period to the next, in attributes and methods named for its unit. Each has a format, the `strptime` directive the unit is written in, and a method that finds the value: in an attribute of the view, then among the path's keyword arguments, then in the query string, with an `Http404` if it finds none. Two more give, for a date, the first day of its period and of the next (`django/views/generic/dates.py:MonthMixin`).

`DateMixin` knows about the model's field. `date_field` names it, and must be set. `allow_future` says whether a list includes objects dated after the present moment, and is false unless set. And `DateMixin.uses_datetime_field` reports whether the field is a `models.DateTimeField`, which decides how the lookups on the field are written (`django/views/generic/dates.py:DateMixin`).

`BaseDateListView` joins `DateMixin` to `MultipleObjectMixin` and supplies the one handler method all six list-shaped date views share. Its `get` calls `get_dated_items`, which each view declares for itself and which returns three things: a list of dates or `None`, the objects, and a dictionary of extra context. The three go into `get_context_data`, and the context into `render_to_response` (`django/views/generic/dates.py:BaseDateListView`).

The defaults are not an ordinary `ListView`'s. `allow_empty` is false, so a period with nothing in it is a 404. And the list is ordered by the date field, newest first, unless the view sets an `ordering` (`django/views/generic/dates.py:BaseDateListView.get_ordering`).

## From a URL to an interval

The Gazette's archive for a month is a `MonthArchiveView` with a model, a date field, and a month written as a number.

```python
# gazette/views.py
class ArticleMonth(MonthArchiveView):
    model = Article
    date_field = "published"
    month_format = "%m"

# gazette/urls.py
path("archive/<int:year>/<int:month>/", views.ArticleMonth.as_view(), name="month"),
```

By the time the archive is asked for, the Gazette has seven articles, the last of them dated after the recording's clock, which stands at 10 April 2026:

```text recording=views
The Gazette's articles by now: one was added and changed, and two were deleted
    2026-02-27 09:00 UTC  harbour-wall: Harbour wall to be rebuilt
    2026-03-03 08:00 UTC  ferry-timetable: New ferry timetable
    2026-03-14 10:00 UTC  lighthouse-open-day: Lighthouse open day
    2026-03-28 18:00 UTC  council-budget: Council passes budget
    2026-04-02 12:00 UTC  spring-fair: Spring fair dates set
    2026-04-05 17:00 UTC  regatta: Regatta results, corrected
    2026-05-01 07:00 UTC  may-day: May Day programme
```

A request for March comes to three conditions on the one date field, two from the URL and the third from the clock, and its neighbours are the months of the nearest articles on either side:

```text figure=the-interval
The request is for /archive/2026/3/, and the clock stands at 10 April 2026, 09:00.

           1 March                               1 April        now: 10 April
  ............|.....................................|...............|...............
   27 Feb     |  3 March    14 March    28 March    |  2 and 5 April  |   1 May
   an article |  the three articles of the month    |  two articles   |   an article, dated after now

the month's objects:     published >= 1 March  and  published < 1 April  and  published <= now
previous_month:          the latest article with  published < 1 March  and  published <= now   ->  27 Feb   ->  1 February
next_month:              the earliest article with  published >= 1 April  and  published <= now   ->  2 April  ->  1 April

For /archive/2026/4/ the same search for a next month finds nothing: the only later article is dated after now.
```

*A month as an interval, and the two searches for its neighbours. The interval includes its start and excludes its end, the first instant of the next month; with `allow_future` false, a third condition cuts everything off at the present moment. With `allow_empty` false, the neighbours are found from the nearest article on each side, not by counting months.*

**A date.** `BaseMonthArchiveView.get_dated_items` asks the mixins for the year and the month and for the format of each, and gives all four to `_date_from_string`. That function builds one string from the values and another from the formats, joined by a delimiter, and has `strptime` parse the first by the second (`django/views/generic/dates.py:_date_from_string`). For March, `MonthMixin.get_month` finds the number 3 in the path, and `MonthMixin.get_month_format` gives the Gazette's `"%m"` in place of the default, `"%b"`, the month's abbreviated name. The date the four make is the first of the month:

```text recording=views
GET /archive/2026/3/: a MonthArchiveView
...
          BaseDateListView.get(request, year=2026, month=3)
            BaseMonthArchiveView.get_dated_items
              YearMixin.get_year  ->  2026
              MonthMixin.get_month  ->  3
              DateMixin.get_date_field  ->  'published'
              YearMixin.get_year_format  ->  '%Y'
              MonthMixin.get_month_format  ->  '%m'
              _date_from_string(2026, '%Y', 3, '%m')  ->  2026-03-01
              ...
```

A value that does not parse is an `Http404`, so a month numbered thirteen is a page not found and not a server error:

```text recording=views
GET /archive/2026/13/: a month that is not one
...
              _date_from_string(2026, '%Y', 13, '%m')  raises Http404
    response_for_exception(request, Http404)  ->  an HttpResponseNotFound, status 404
    ...
```

**An interval.** The month runs from its first day to the first day of the next month, which `_get_next_month` supplies. The end is excluded: the lookups are a greater-than-or-equal on the start and a strict less-than on the end. Every period of the date views is defined so, as start date <= item date < next start date (`django/views/generic/dates.py:BaseMonthArchiveView.get_dated_items`, `django/views/generic/dates.py:MonthMixin._get_next_month`).

The field here is a `models.DateTimeField`, so `DateMixin._make_date_lookup_arg` turns each boundary from a date into a datetime at midnight, and, with time zone support on, into midnight in the current time zone. `DateMixin.uses_datetime_field` is worked out at the first boundary and kept for the rest of the request (`django/views/generic/dates.py:DateMixin.uses_datetime_field`), and each boundary comes back as midnight with its offset:

```text recording=views
...
DateMixin._make_date_lookup_arg(2026-03-01)
  DateMixin.uses_datetime_field
    DateMixin.get_date_field  ->  'published'
    -> True
  -> 2026-03-01 00:00+00:00
MonthMixin._get_next_month(2026-03-01)  ->  2026-04-01
DateMixin._make_date_lookup_arg(2026-04-01)  ->  2026-04-01 00:00+00:00
...
```

> **Why.** The boundaries are midnight in the current time zone so that what a page lists agrees with the period its URL names: an article published late on 31 March in the current time zone belongs to March whatever its timestamp is in UTC ([Time zones](../i18n/time-zones.md)) (`django/views/generic/dates.py:DateMixin._make_date_lookup_arg`).

**A query.** `BaseDateListView.get_dated_queryset` applies the interval to the view's queryset and, with the defaults, adds one condition the URL does not give, an upper bound at the present moment, and then tests whether anything is left (`django/views/generic/dates.py:BaseDateListView.get_dated_queryset`). The queryset it starts from is already ordered newest first, by `BaseDateListView.get_ordering`, and `get_paginate_by` is asked only to choose how the result will be tested. The query has three parameters, the month's two boundaries and the present moment, 10 April 2026 at 09:00 by the recording's clock:

```text recording=views
...
BaseDateListView.get_dated_queryset(published__gte=2026-03-01 00:00+00:00, published__lt=2026-04-01 00:00+00:00)
  MultipleObjectMixin.get_queryset
    BaseDateListView.get_ordering
      DateMixin.get_date_field  ->  'published'
      -> '-published'
    -> a QuerySet of Article, ordered by -published, not yet fetched
  DateMixin.get_date_field  ->  'published'
  DateMixin.get_allow_future  ->  False
  MultipleObjectMixin.get_allow_empty  ->  False
  MultipleObjectMixin.get_paginate_by(queryset)  ->  None
  SQL SELECT "gazette_article"."id", "gazette_article"."slug", "gazette_article"."headline", "gazette_article"."published" FROM "gazette_article" WHERE ("gazette_article"."published" >= %s AND "gazette_article"."published" < %s AND "gazette_article"."published" <= %s) ORDER BY "gazette_article"."published" DESC with params ('2026-03-01 00:00:00', '2026-04-01 00:00:00', '2026-04-10 09:00:00')
  -> a QuerySet of Article, ordered by -published, already fetched
  ...
```

Unless `allow_future` is true, `get_dated_queryset` filters out everything dated after now: for a datetime field the comparison is with `timezone.now()`, and for a date field with `timezone_today`, the date in the current time zone when `settings.USE_TZ` is true.

Unless `allow_empty` is true, it finds out whether the result is empty, and raises `Http404` if it is. A view that paginates asks with `exists`. One that does not, like this one, tests the queryset itself, and that fetches every row: the articles of the month are loaded here, by the view, where a plain `ListView` leaves the query for the template to run. The year's archive, a page of months, loads the year's articles too ([The seven date views](date-views.md#archiveindexview-and-yeararchiveview)).

December 2025 has no articles. Its query comes back empty, `get_dated_queryset` raises, and the request ends in a 404 before the list of days or either neighbour is looked for:

```text recording=views
GET /archive/2025/12/: a month with no articles
...
                SQL SELECT "gazette_article"."id", "gazette_article"."slug", "gazette_article"."headline", "gazette_article"."published" FROM "gazette_article" WHERE ("gazette_article"."published" >= %s AND "gazette_article"."published" < %s AND "gazette_article"."published" <= %s) ORDER BY "gazette_article"."published" DESC with params ('2025-12-01 00:00:00', '2026-01-01 00:00:00', '2026-04-10 09:00:00')
                raises Http404
    response_for_exception(request, Http404)  ->  an HttpResponseNotFound, status 404
    ...
```

**The dates inside.** `BaseDateListView.get_date_list` makes the list of smaller periods that have something in them: here, the days of the month on which an article appeared. It calls the queryset's `datetimes` or `dates` with a unit from `date_list_period`, which is `"year"` in `BaseDateListView`, `"month"` in the year's view and `"day"` in the month's. The views for a week, a day and today make no such list. The list is a second query, a `SELECT DISTINCT` over the same interval, with each date cut to its day (`django/views/generic/dates.py:BaseDateListView.get_date_list`):

```text recording=views
...
BaseDateListView.get_date_list(queryset)
  DateMixin.get_date_field  ->  'published'
  MultipleObjectMixin.get_allow_empty  ->  False
  BaseDateListView.get_date_list_period  ->  'day'
  SQL SELECT DISTINCT django_datetime_trunc(%s, "gazette_article"."published", %s, %s) AS "datetimefield" FROM "gazette_article" WHERE ("gazette_article"."published" >= %s AND "gazette_article"."published" < %s AND "gazette_article"."published" <= %s AND "gazette_article"."published" IS NOT NULL) ORDER BY 1 ASC with params ('day', 'UTC', 'UTC', '2026-03-01 00:00:00', '2026-04-01 00:00:00', '2026-04-10 09:00:00')
  -> a QuerySet of datetimes, already fetched: 2026-03-03 00:00+00:00, 2026-03-14 00:00+00:00, 2026-03-28 00:00+00:00
  ...
```

## The periods on either side

A page for March wants links to February and April. The obvious answer, the months before and after, can lead to a page that is a 404, since an empty month is one by default. `MonthMixin.get_next_month` and `get_previous_month` hand the question to `_get_next_prev`, which is written never to offer such a link (`django/views/generic/dates.py:_get_next_prev`).

When `allow_empty` is true, every period has a page, and the neighbour is found by arithmetic: the next period's first day, or the first day of the period before this one. It is still withheld if it lies after today and `allow_future` is false.

When `allow_empty` is false, as it is unless set, the neighbour has to be a period with something in it, and only the database knows. For the next period the function looks for the earliest object dated at or after this period's end. For the previous one, the latest object dated before its start. Either search stops at the present moment unless `allow_future` is true. It takes that one object's date and returns the first day of the period the date is in, or `None` if there was no object.

Look for March's two searches: each sets out from a boundary of the month, sends one query with a limit of one, ascending for the next month and descending for the previous, and cuts the date of the article it finds to the first of its month:

```text recording=views
GET /archive/2026/3/: a MonthArchiveView
...
              MonthMixin.get_next_month(2026-03-01)
                _get_next_prev(view, 2026-03-01, is_previous=False, period='month')
                  DateMixin.get_date_field  ->  'published'
                  MultipleObjectMixin.get_allow_empty  ->  False
                  DateMixin.get_allow_future  ->  False
                  MonthMixin._get_current_month(2026-03-01)  ->  2026-03-01
                  MonthMixin._get_next_month(2026-03-01)  ->  2026-04-01
                  ...
                  SQL SELECT "gazette_article"."id", "gazette_article"."slug", "gazette_article"."headline", "gazette_article"."published" FROM "gazette_article" WHERE ("gazette_article"."published" >= %s AND "gazette_article"."published" <= %s) ORDER BY "gazette_article"."published" ASC LIMIT 1 with params ('2026-04-01 00:00:00', '2026-04-10 09:00:00')
                  MonthMixin._get_current_month(2026-04-02)  ->  2026-04-01
                  ...
              MonthMixin.get_previous_month(2026-03-01)
                _get_next_prev(view, 2026-03-01, is_previous=True, period='month')
                  ...
                  SQL SELECT "gazette_article"."id", "gazette_article"."slug", "gazette_article"."headline", "gazette_article"."published" FROM "gazette_article" WHERE ("gazette_article"."published" < %s AND "gazette_article"."published" <= %s) ORDER BY "gazette_article"."published" DESC LIMIT 1 with params ('2026-03-01 00:00:00', '2026-04-10 09:00:00')
                  MonthMixin._get_current_month(2026-02-27)  ->  2026-02-01
                  ...
```

The month's page ran four queries before any template was rendered: the articles, the days, the next month and the previous one.

For April, the month the clock is in, the search for a next month asks for an article dated at or after 1 May and at or before the present moment, which none can be: `_get_next_prev` returns `None`, and April's page offers no next month, though the Gazette has an article in May (`django/views/generic/dates.py:_get_next_prev`).
