---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The date views

The seven views of `django/views/generic/dates.py`, from `ArchiveIndexView` to `DateDetailView`: how those that take a date from the URL turn its parts into an interval on a model's date field, what `allow_future` and `allow_empty` change, and how `_get_next_prev` finds the periods on either side.

A site that publishes things by date wants an archive: a page for a year that lists its months, a page for a month that lists what appeared in it, a page for a day, and on each a link to the period before and the period after. The pages differ in the size of the period. Each has to do the same things. It reads a date out of the URL. It turns the date into an interval with a beginning and an end. It asks the database for the objects whose date falls inside. And it works out what else the page needs: the smaller periods within this one that have anything in them, and the neighbours worth linking to.

Six of the seven views are built on the same mixins as [the list view](generic.md#listview-many-objects-and-pages-of-them), `MultipleObjectMixin` and `MultipleObjectTemplateResponseMixin`, with those steps added. The seventh shows one object and is built on the detail view's.

## The parts

A mixin for each unit knows how to read that unit from a request and how to step from one period to the next. `YearMixin`, `MonthMixin`, `DayMixin` and `WeekMixin` have the same attributes and methods under their own unit's name, and `WeekMixin` one more, `_get_weekday`. These are the month's (`django/views/generic/dates.py:MonthMixin`):

- `month_format`, a `strptime` directive that says how the month is written in the URL, and `get_month_format`, which returns it. It is `"%b"` unless changed, the month's abbreviated name; the year's is `"%Y"`, the day's `"%d"` and the week's `"%U"`.
- `get_month`, which finds the value: the view's `month` attribute if it has one, then the keyword argument of that name from the path, then the query string. Finding none is an `Http404`.
- `_get_current_month`, which takes a date and returns the first day of the month it is in.
- `_get_next_month`, which returns the first day of the month after.
- `get_next_month` and `get_previous_month`, for the links, which hand the question to `_get_next_prev`.

`DateMixin` knows about the model's field. `date_field` names it, and must be set. `allow_future` says whether objects dated after the present moment are shown, and is false unless set. And `DateMixin.uses_datetime_field` reports whether the field is a `models.DateTimeField`, which decides how the lookups on the field are written (`django/views/generic/dates.py:DateMixin`).

`BaseDateListView` joins `DateMixin` to `MultipleObjectMixin` and supplies the one handler method all six list-shaped date views share. Its `get` calls `get_dated_items`, which each view declares for itself and which returns three things: a list of dates, the objects, and a dictionary of extra context. The three go into `get_context_data` and the page is rendered (`django/views/generic/dates.py:BaseDateListView`).

The defaults are not an ordinary `ListView`'s. `allow_empty` is false, so a period with nothing in it is a 404. And the list is ordered by the date field, newest first, unless the view sets an `ordering`.

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

The figure is the whole of what a request for March comes to, and the recordings after it take the steps one at a time.

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

**A date.** `BaseMonthArchiveView.get_dated_items` asks the mixins for the year and the month and for the format of each, and gives all four to `_date_from_string`. That function builds one string from the values and another from the formats, joined by a delimiter, and has `strptime` parse the first by the second (`django/views/generic/dates.py:_date_from_string`).

```text recording=views
YearMixin.get_year  ->  2026
MonthMixin.get_month  ->  3
DateMixin.get_date_field  ->  'published'
YearMixin.get_year_format  ->  '%Y'
MonthMixin.get_month_format  ->  '%m'
_date_from_string(2026, '%Y', 3, '%m')  ->  2026-03-01
```

A value that does not parse is an `Http404`, so a month numbered thirteen is a page not found and not a server error:

```text recording=views
          _date_from_string(2026, '%Y', 13, '%m')  raises Http404
response_for_exception(request, Http404)  ->  an HttpResponseNotFound, status 404
log, WARNING to django.request: Not Found: /archive/2026/13/
start_response("404 Not Found", headers)
```

**An interval.** The month runs from its first day to the first day of the next month, which `_get_next_month` supplies. The end is excluded: the lookups are a greater-than-or-equal on the start and a strict less-than on the end. The docstrings of the stepping methods define every period so, as start date <= item date < next start date.

```text recording=views
DateMixin._make_date_lookup_arg(2026-03-01)
  DateMixin.uses_datetime_field
    DateMixin.get_date_field  ->  'published'
    -> True
  -> 2026-03-01 00:00+00:00
MonthMixin._get_next_month(2026-03-01)  ->  2026-04-01
DateMixin._make_date_lookup_arg(2026-04-01)  ->  2026-04-01 00:00+00:00
```

The field here is a `models.DateTimeField`, so `DateMixin._make_date_lookup_arg` turns each boundary from a date into a datetime at midnight, and, with time zone support on, into midnight in the current time zone. Its docstring gives the reason: so that the items shown are consistent with the URL. An article published late on the last evening of March, by the site's clock, belongs to March whatever its timestamp is in UTC ([Internationalization and time zones](../i18n.md)).

**A query.** `BaseDateListView.get_dated_queryset` applies the interval to the view's queryset, and then two more conditions that are not in the URL (`django/views/generic/dates.py:BaseDateListView.get_dated_queryset`).

```text recording=views
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
```

Unless `allow_future` is true, it filters out everything dated after now. The third parameter of the query is that moment: the recording's clock stands at 10 April 2026. For a datetime field the comparison is with `timezone.now()`, and for a date field with `timezone_today`: the date in the current time zone when `settings.USE_TZ` is true.

Unless `allow_empty` is true, it finds out whether the result is empty, and raises `Http404` if it is. A view that paginates asks with `exists`. One that does not, like this one, tests the queryset itself, and that fetches every row: the articles of the month are loaded here, by the view, where a plain `ListView` leaves the query for the template to run.

```text recording=views
          BaseDateListView.get_dated_queryset(published__gte=2025-12-01 00:00+00:00, published__lt=2026-01-01 00:00+00:00)
            MultipleObjectMixin.get_queryset
              BaseDateListView.get_ordering
                DateMixin.get_date_field  ->  'published'
                -> '-published'
              -> a QuerySet of Article, ordered by -published, not yet fetched
            DateMixin.get_date_field  ->  'published'
            DateMixin.get_allow_future  ->  False
            MultipleObjectMixin.get_allow_empty  ->  False
            MultipleObjectMixin.get_paginate_by(queryset)  ->  None
            SQL SELECT "gazette_article"."id", "gazette_article"."slug", "gazette_article"."headline", "gazette_article"."published" FROM "gazette_article" WHERE ("gazette_article"."published" >= %s AND "gazette_article"."published" < %s AND "gazette_article"."published" <= %s) ORDER BY "gazette_article"."published" DESC with params ('2025-12-01 00:00:00', '2026-01-01 00:00:00', '2026-04-10 09:00:00')
            raises Http404
response_for_exception(request, Http404)  ->  an HttpResponseNotFound, status 404
log, WARNING to django.request: Not Found: /archive/2025/12/
start_response("404 Not Found", headers)
```

**The dates inside.** `BaseDateListView.get_date_list` makes the list of smaller periods that have something in them: here, the days of the month on which an article appeared. It calls the queryset's `datetimes` or `dates` with a unit from `date_list_period`, which is `"year"` in `BaseDateListView`, `"month"` in the year's view and `"day"` in the month's. It is a second query, a `SELECT DISTINCT` over the same interval. The views for a week, a day and today make no such list.

```text recording=views
BaseDateListView.get_date_list(queryset)
  DateMixin.get_date_field  ->  'published'
  MultipleObjectMixin.get_allow_empty  ->  False
  BaseDateListView.get_date_list_period  ->  'day'
  SQL SELECT DISTINCT django_datetime_trunc(%s, "gazette_article"."published", %s, %s) AS "datetimefield" FROM "gazette_article" WHERE ("gazette_article"."published" >= %s AND "gazette_article"."published" < %s AND "gazette_article"."published" <= %s AND "gazette_article"."published" IS NOT NULL) ORDER BY 1 ASC with params ('day', 'UTC', 'UTC', '2026-03-01 00:00:00', '2026-04-01 00:00:00', '2026-04-10 09:00:00')
  -> a QuerySet of datetimes, already fetched: 2026-03-03 00:00+00:00, 2026-03-14 00:00+00:00, 2026-03-28 00:00+00:00
```

## The periods on either side

A page for March wants links to February and April. The obvious answer, the months before and after, can lead to a page that is a 404, since an empty month is one by default. `_get_next_prev` is written to avoid offering such a link, and its docstring sets out the cases (`django/views/generic/dates.py:_get_next_prev`).

When `allow_empty` is true, every period has a page, and the neighbour is found by arithmetic: the next period's first day, or the first day of the period before this one. It is still withheld if it lies after today and `allow_future` is false.

When `allow_empty` is false, as it is unless set, the neighbour has to be a period with something in it, and only the database knows. For the next period the function looks for the earliest object dated at or after this period's end. For the previous one, the latest object dated before its start. Either search stops at the present moment unless `allow_future` is true. It takes that one object's date and returns the first day of the period the date is in, or `None` if there was no object.

```text recording=views
MonthMixin.get_next_month(2026-03-01)
  _get_next_prev(view, 2026-03-01, is_previous=False, period='month')
    DateMixin.get_date_field  ->  'published'
    MultipleObjectMixin.get_allow_empty  ->  False
    DateMixin.get_allow_future  ->  False
    MonthMixin._get_current_month(2026-03-01)  ->  2026-03-01
    MonthMixin._get_next_month(2026-03-01)  ->  2026-04-01
    DateMixin._make_date_lookup_arg(2026-04-01)  ->  2026-04-01 00:00+00:00
    MultipleObjectMixin.get_queryset
      BaseDateListView.get_ordering
        DateMixin.get_date_field  ->  'published'
        -> '-published'
      -> a QuerySet of Article, ordered by -published, not yet fetched
    SQL SELECT "gazette_article"."id", "gazette_article"."slug", "gazette_article"."headline", "gazette_article"."published" FROM "gazette_article" WHERE ("gazette_article"."published" >= %s AND "gazette_article"."published" <= %s) ORDER BY "gazette_article"."published" ASC LIMIT 1 with params ('2026-04-01 00:00:00', '2026-04-10 09:00:00')
    MonthMixin._get_current_month(2026-04-02)  ->  2026-04-01
    -> 2026-04-01
  -> 2026-04-01
MonthMixin.get_previous_month(2026-03-01)
  _get_next_prev(view, 2026-03-01, is_previous=True, period='month')
    DateMixin.get_date_field  ->  'published'
    MultipleObjectMixin.get_allow_empty  ->  False
    DateMixin.get_allow_future  ->  False
    MonthMixin._get_current_month(2026-03-01)  ->  2026-03-01
    MonthMixin._get_next_month(2026-03-01)  ->  2026-04-01
    DateMixin._make_date_lookup_arg(2026-03-01)  ->  2026-03-01 00:00+00:00
    MultipleObjectMixin.get_queryset
      BaseDateListView.get_ordering
        DateMixin.get_date_field  ->  'published'
        -> '-published'
      -> a QuerySet of Article, ordered by -published, not yet fetched
    SQL SELECT "gazette_article"."id", "gazette_article"."slug", "gazette_article"."headline", "gazette_article"."published" FROM "gazette_article" WHERE ("gazette_article"."published" < %s AND "gazette_article"."published" <= %s) ORDER BY "gazette_article"."published" DESC LIMIT 1 with params ('2026-03-01 00:00:00', '2026-04-10 09:00:00')
    MonthMixin._get_current_month(2026-02-27)  ->  2026-02-01
    -> 2026-02-01
  -> 2026-02-01
-> (a QuerySet of 3 datetimes, a QuerySet of Article, ordered by -published, already fetched, {'month': 2026-03-01, 'next_month': 2026-04-01, 'previous_month': 2026-02-01})
```

Each neighbour cost a query with a limit of one. The month's page ran four queries before any template was rendered: the articles, the days, the next month and the previous one.

April is the month the recording's clock is in, and the Gazette's only later article is dated 1 May. April's page offers no next month:

```text recording=views
MonthMixin.get_next_month(2026-04-01)
  _get_next_prev(view, 2026-04-01, is_previous=False, period='month')
    DateMixin.get_date_field  ->  'published'
    MultipleObjectMixin.get_allow_empty  ->  False
    DateMixin.get_allow_future  ->  False
    MonthMixin._get_current_month(2026-04-01)  ->  2026-04-01
    MonthMixin._get_next_month(2026-04-01)  ->  2026-05-01
    DateMixin._make_date_lookup_arg(2026-05-01)  ->  2026-05-01 00:00+00:00
    MultipleObjectMixin.get_queryset
      BaseDateListView.get_ordering
        DateMixin.get_date_field  ->  'published'
        -> '-published'
      -> a QuerySet of Article, ordered by -published, not yet fetched
    SQL SELECT "gazette_article"."id", "gazette_article"."slug", "gazette_article"."headline", "gazette_article"."published" FROM "gazette_article" WHERE ("gazette_article"."published" >= %s AND "gazette_article"."published" <= %s) ORDER BY "gazette_article"."published" ASC LIMIT 1 with params ('2026-05-01 00:00:00', '2026-04-10 09:00:00')
    -> None
  -> None
MonthMixin.get_previous_month(2026-04-01)
...
-> (a QuerySet of 2 datetimes, a QuerySet of Article, ordered by -published, already fetched, {'month': 2026-04-01, 'next_month': None, 'previous_month': 2026-03-01})
```

## The seven views

Each of the six list-shaped views is a base view that declares `get_dated_items`, joined to `MultipleObjectTemplateResponseMixin` with a template suffix. `DateDetailView` is built from `BaseDetailView` and the detail view's response mixin.

| view | reads from the URL | `date_list` | template suffix |
|---|---|---|---|
| `ArchiveIndexView` | nothing: it lists everything | years, newest first | `"_archive"` |
| `YearArchiveView` | a year | months | `"_archive_year"` |
| `MonthArchiveView` | a year and a month | days | `"_archive_month"` |
| `WeekArchiveView` | a year and a week | `None` | `"_archive_week"` |
| `DayArchiveView` | a year, a month and a day | `None` | `"_archive_day"` |
| `TodayArchiveView` | nothing: the day is today | `None` | `"_archive_day"` |
| `DateDetailView` | a year, a month, a day, and a slug or a primary key | none: it shows one object | `"_detail"` |

*The date views, by what each reads from its URL and what it lists. The interval is the period the URL names.*

Besides the list and `date_list`, the views for a year, a month, a week and a day put into the context the first day of their own period and of the neighbours they found. The index adds nothing, and `DateDetailView` has only its object.

The recording below asks each view but the one for today what it puts in the context for the Gazette's articles. Each line makes the view from Django's own class, for the Gazette's model and date field, with the attributes written in braces and no others, calls it with the arguments that follow, and lists the context, an article by its slug. Six keys are left out, which the recording names: the view, the three of pagination, and the two under the model's name. These are the classes' own defaults, so a month is written as `"%b"` wants it.

```text recording=views
context(generic.ArchiveIndexView)  ->  date_list = [2026-01-01 00:00+00:00]; latest = [regatta, spring-fair, council-budget, lighthouse-open-day, ferry-timetable, harbour-wall]; object_list = [regatta, spring-fair, council-budget, lighthouse-open-day, ferry-timetable, harbour-wall]
context(generic.YearArchiveView, year=2026)  ->  date_list = [2026-02-01 00:00+00:00, 2026-03-01 00:00+00:00, 2026-04-01 00:00+00:00]; next_year = None; object_list = []; previous_year = None; year = 2026-01-01
context(generic.YearArchiveView, {"make_object_list": True}, year=2026)  ->  date_list = [2026-02-01 00:00+00:00, 2026-03-01 00:00+00:00, 2026-04-01 00:00+00:00]; next_year = None; object_list = [regatta, spring-fair, council-budget, lighthouse-open-day, ferry-timetable, harbour-wall]; previous_year = None; year = 2026-01-01
context(generic.MonthArchiveView, year=2026, month="mar")  ->  date_list = [2026-03-03 00:00+00:00, 2026-03-14 00:00+00:00, 2026-03-28 00:00+00:00]; month = 2026-03-01; next_month = 2026-04-01; object_list = [council-budget, lighthouse-open-day, ferry-timetable]; previous_month = 2026-02-01
context(generic.WeekArchiveView, year=2026, week=10)  ->  date_list = None; next_week = 2026-03-22; object_list = [lighthouse-open-day]; previous_week = 2026-03-01; week = 2026-03-08
context(generic.DayArchiveView, year=2026, month="mar", day=14)  ->  date_list = None; day = 2026-03-14; next_day = 2026-03-28; next_month = 2026-04-01; object_list = [lighthouse-open-day]; previous_day = 2026-03-03; previous_month = 2026-02-01
context(generic.DayArchiveView, year=2026, month="mar", day=15)  ->  raises Http404: No articles available
context(generic.DayArchiveView, {"allow_empty": True}, year=2026, month="mar", day=15)  ->  date_list = None; day = 2026-03-15; next_day = 2026-03-16; next_month = 2026-04-01; object_list = []; previous_day = 2026-03-14; previous_month = 2026-02-01
context(generic.DateDetailView, year=2026, month="mar", day=14, slug="lighthouse-open-day")  ->  object = lighthouse-open-day
context(generic.DateDetailView, year=2026, month="mar", day=15, slug="lighthouse-open-day")  ->  raises Http404: No article found matching the query
```

The two lines for 15 March, a day with no article, are the two settings of `allow_empty` side by side. With the default the day is a 404, raised by `get_dated_queryset` before any neighbour is looked for. With `allow_empty` true it has a page, and its neighbours are the days on either side by the calendar, where the line for the 14th, under the defaults, has the 3rd and the 28th, each found by a query.

`ArchiveIndexView` has no interval. Its list is everything up to the present, under the context name `"latest"`, and its `date_list` is the years, in descending order (`django/views/generic/dates.py:BaseArchiveIndexView`).

`YearArchiveView` shows no objects unless `make_object_list` is true: a year's page is a list of months. But with `allow_empty` false and no pagination, as here, the objects are fetched all the same. `get_dated_queryset` loads the year's rows to find out whether there are any, and `get_dated_items` then replaces the queryset with an empty one made by `none()`. A comment explains why it is still a queryset: the parent classes inspect it to find out about the model (`django/views/generic/dates.py:BaseYearArchiveView.get_dated_items`).

```text recording=views
BaseDateListView.get_dated_queryset(published__gte=2026-01-01 00:00+00:00, published__lt=2027-01-01 00:00+00:00)
  MultipleObjectMixin.get_queryset
    BaseDateListView.get_ordering
      DateMixin.get_date_field  ->  'published'
      -> '-published'
    -> a QuerySet of Article, ordered by -published, not yet fetched
  DateMixin.get_date_field  ->  'published'
  DateMixin.get_allow_future  ->  False
  MultipleObjectMixin.get_allow_empty  ->  False
  MultipleObjectMixin.get_paginate_by(queryset)  ->  None
  SQL SELECT "gazette_article"."id", "gazette_article"."slug", "gazette_article"."headline", "gazette_article"."published" FROM "gazette_article" WHERE ("gazette_article"."published" >= %s AND "gazette_article"."published" < %s AND "gazette_article"."published" <= %s) ORDER BY "gazette_article"."published" DESC with params ('2026-01-01 00:00:00', '2027-01-01 00:00:00', '2026-04-10 09:00:00')
  -> a QuerySet of Article, ordered by -published, already fetched
BaseDateListView.get_date_list(queryset)
  DateMixin.get_date_field  ->  'published'
  MultipleObjectMixin.get_allow_empty  ->  False
  BaseDateListView.get_date_list_period  ->  'month'
  SQL SELECT DISTINCT django_datetime_trunc(%s, "gazette_article"."published", %s, %s) AS "datetimefield" FROM "gazette_article" WHERE ("gazette_article"."published" >= %s AND "gazette_article"."published" < %s AND "gazette_article"."published" <= %s AND "gazette_article"."published" IS NOT NULL) ORDER BY 1 ASC with params ('month', 'UTC', 'UTC', '2026-01-01 00:00:00', '2027-01-01 00:00:00', '2026-04-10 09:00:00')
  -> a QuerySet of datetimes, already fetched: 2026-02-01 00:00+00:00, 2026-03-01 00:00+00:00, 2026-04-01 00:00+00:00
BaseYearArchiveView.get_make_object_list  ->  False
...
-> (a QuerySet of 3 datetimes, an empty QuerySet of Article: its query is marked empty, {'year': 2026-01-01, 'next_year': None, 'previous_year': None})
```

`WeekArchiveView` has to know which day a week starts on, and takes it from `week_format`: `"%U"` counts weeks from Sunday, `"%W"` and `"%V"` from Monday. `"%V"` is the ISO week and is refused, with a `ValueError`, unless the year's format is the ISO year `"%G"`. An unknown format is a `ValueError` too. Both are mistakes in the view and not in the request, and are not turned into a 404 (`django/views/generic/dates.py:BaseWeekArchiveView.get_dated_items`).

```text recording=views
context(generic.WeekArchiveView, {"week_format": "%V"}, year=2026, week=10)  ->  raises ValueError: ISO week directive '%V' is incompatible with the year directive '%Y'. Use the ISO year '%G' instead.
```

`DayArchiveView` looks up four neighbours, the days and the months on either side, and with `allow_empty` false each is a query. For a field that is a plain date it filters by equality; for a `models.DateTimeField` it uses the interval from one midnight to the next (`django/views/generic/dates.py:BaseDayArchiveView._get_dated_items`, `django/views/generic/dates.py:DateMixin._make_single_date_lookup`).

`TodayArchiveView` is the day view with the date supplied by `datetime.date.today()`, the process's local date. The filter against the future compares with `timezone.now()` when the field is a `models.DateTimeField` and with `timezone_today` when it is a plain date. The search for neighbours does the same when `allow_empty` is false, and compares with `timezone_today` whatever the field when it is true. `timezone_today` returns the date in the current time zone when `settings.USE_TZ` is true, and `datetime.date.today()` when it is not (`django/views/generic/dates.py:BaseTodayArchiveView.get_dated_items`, `django/views/generic/dates.py:timezone_today`).

`DateDetailView` is a detail view, built on `BaseDetailView` as `DetailView` is, whose queryset is narrowed to one day before the usual lookup by slug or primary key. An object that exists under another date is not found. Unless `allow_future` is true it also refuses, with an `Http404`, a date later than `datetime.date.today()`, before it asks the database anything (`django/views/generic/dates.py:BaseDateDetailView.get_object`).

A view that does allow the future shows what the others leave out. The Gazette's article of 1 May is after the recording's clock, and May's page exists only for such a view:

```text recording=views
context(generic.MonthArchiveView, {"allow_future": True}, year=2026, month="may")  ->  date_list = [2026-05-01 00:00+00:00]; month = 2026-05-01; next_month = None; object_list = [may-day]; previous_month = 2026-04-01
context(generic.MonthArchiveView, year=2026, month="may")  ->  raises Http404: No articles available
```
