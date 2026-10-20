---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The seven date views

Django has seven date views: six for the periods an archive shows, from everything up to the present (`ArchiveIndexView`) down to a single day, and one, `DateDetailView`, for an object found by its date. They differ in what they read from the URL and put in the context, and in a few particulars, such as `YearArchiveView`'s `make_object_list` and the clock `TodayArchiveView` reads.

How a date view reads its date, turns it into an interval and finds the periods on either side is told in [The date views: a date, an interval and its neighbours](dates.md), with a `MonthArchiveView`. Six of the seven are list views, each a base view joined to `MultipleObjectTemplateResponseMixin` with a template suffix of its own; `DateDetailView` is built from `BaseDetailView` and the detail view's response mixin (`django/views/generic/dates.py:MonthArchiveView`, `django/views/generic/dates.py:DateDetailView`).

| view | reads from the URL | `date_list` | template suffix |
|---|---|---|---|
| `ArchiveIndexView` | nothing: it has no interval | years, newest first | `"_archive"` |
| `YearArchiveView` | a year | months | `"_archive_year"` |
| `MonthArchiveView` | a year and a month | days | `"_archive_month"` |
| `WeekArchiveView` | a year and a week | `None` | `"_archive_week"` |
| `DayArchiveView` | a year, a month and a day | `None` | `"_archive_day"` |
| `TodayArchiveView` | nothing: the day is today | `None` | `"_archive_day"` |
| `DateDetailView` | a year, a month, a day, and a slug or a primary key | none: it shows one object | `"_detail"` |

*The date views, by what each reads from its URL and what it lists.*

## What each view puts in the context

Besides the list and `date_list`, the views for a year, a month, a week and a day put into the context the first day of their own period and of the neighbours they found. The index adds nothing, and `DateDetailView` has only its object.

Each line below is the context one of Django's classes makes for the Gazette's articles, with no other attributes set but those in braces: an article is named by its slug, a month is written as the default `"%b"` reads it, and the keys of the view, of pagination and under the model's name are left out. The index's list is there twice, as `object_list` and as `"latest"`.

Look for the neighbours. Under the defaults each is found by a query: 14 March's are the 3rd and the 28th, and for the week of 8 March the next week is that of the 22nd, since the week of the 15th has no article. With `allow_empty` true they are found by the calendar: 15 March, a day with no article and so, under the defaults, a 404, has the 14th and the 16th. The last two lines ask for May, whose one article is dated after the recording's clock: it is listed only by a view with `allow_future` true.

```text recording=views
The date views: what each puts in the context, for the model Article and its field published
...
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
      context(generic.MonthArchiveView, {"allow_future": True}, year=2026, month="may")  ->  date_list = [2026-05-01 00:00+00:00]; month = 2026-05-01; next_month = None; object_list = [may-day]; previous_month = 2026-04-01
      context(generic.MonthArchiveView, year=2026, month="may")  ->  raises Http404: No articles available
      ...
```

## `ArchiveIndexView` and `YearArchiveView`

`ArchiveIndexView` has no interval. Its list is everything up to the present, under the context name `"latest"`, and its `date_list` is the years, in descending order (`django/views/generic/dates.py:BaseArchiveIndexView`).

`YearArchiveView` shows no objects unless `make_object_list` is true: a year's page is a list of months. Its `get_dated_items` replaces the queryset with an empty one made by `none()`, still a queryset because the parent classes inspect it to find out about the model (`django/views/generic/dates.py:BaseYearArchiveView.get_dated_items`). In the request for 2026, the year's query runs under `get_dated_queryset`, which applies the interval to the queryset, and `get_make_object_list` answers after it:

```text recording=views
GET /archive/2026/: a YearArchiveView, which lists months and, unless told to, no articles
...
              BaseDateListView.get_dated_queryset(published__gte=2026-01-01 00:00+00:00, published__lt=2027-01-01 00:00+00:00)
                ...
                SQL SELECT "gazette_article"."id", "gazette_article"."slug", "gazette_article"."headline", "gazette_article"."published" FROM "gazette_article" WHERE ("gazette_article"."published" >= %s AND "gazette_article"."published" < %s AND "gazette_article"."published" <= %s) ORDER BY "gazette_article"."published" DESC with params ('2026-01-01 00:00:00', '2027-01-01 00:00:00', '2026-04-10 09:00:00')
                -> a QuerySet of Article, ordered by -published, already fetched
              ...
              BaseYearArchiveView.get_make_object_list  ->  False
              ...
              -> (a QuerySet of 3 datetimes, an empty QuerySet of Article: its query is marked empty, {'year': 2026-01-01, 'next_year': None, 'previous_year': None})
              ...
```

> **Trap.** By default, a `YearArchiveView` that shows no objects fetches them all the same. With `allow_empty` false, as it is in the date views unless set, and no pagination, `get_dated_queryset` finds out whether the year is empty by testing the queryset itself, which loads every row of the year into memory, and `get_dated_items` then throws them away. With pagination it asks with `exists` instead, a cheap query that its comment prefers to loading the unpaginated queryset into memory (`django/views/generic/dates.py:BaseDateListView.get_dated_queryset`).

## `WeekArchiveView` and `week_format`

`WeekArchiveView` has to know which day a week starts on, and takes it from `week_format`: `"%U"` counts weeks from Sunday, `"%W"` and `"%V"` from Monday. `"%V"` is the ISO week and is refused unless the year's format is the ISO year `"%G"`: under the default `"%Y"` the view raises `ValueError`, `"ISO week directive '%V' is incompatible with the year directive '%Y'. Use the ISO year '%G' instead."` An unknown format is a `ValueError` too. Both are mistakes in the view and not in the request, and are not turned into a 404 (`django/views/generic/dates.py:BaseWeekArchiveView.get_dated_items`).

## `DayArchiveView` and `TodayArchiveView`

`DayArchiveView` looks up four neighbours, the days and the months on either side, and with `allow_empty` false each is a query. For a field that is a plain date it filters by equality; for a `models.DateTimeField` it uses the interval from one midnight to the next (`django/views/generic/dates.py:BaseDayArchiveView._get_dated_items`, `django/views/generic/dates.py:DateMixin._make_single_date_lookup`).

`TodayArchiveView` is the day view with its date taken from the clock and not from the URL: `BaseTodayArchiveView.get_dated_items` hands today's date to `BaseDayArchiveView._get_dated_items`, and the rest is the day view's (`django/views/generic/dates.py:BaseTodayArchiveView.get_dated_items`).

> **Trap.** `TodayArchiveView`'s day is `datetime.date.today()`, the process's local date, and `DateDetailView` refuses a future date by the same clock. Everything else in the date views that asks for the present asks `timezone.now()` or `timezone_today`, and the second is the date in the current time zone when `settings.USE_TZ` is true, `datetime.date.today()` only when it is false (`django/views/generic/dates.py:BaseTodayArchiveView.get_dated_items`, `django/views/generic/dates.py:BaseDateDetailView.get_object`, `django/views/generic/dates.py:timezone_today`). Django sets the process's time zone to `settings.TIME_ZONE` as it loads the settings module, on a platform that allows it, which Windows does not (`django/conf/__init__.py:Settings.__init__`). So with `settings.USE_TZ` true the two dates can differ where a request activates a time zone of its own (`django/utils/timezone.py:activate`), and, where Django has not set the process's zone, wherever `settings.TIME_ZONE` is not that zone. On a site whose process's zone is UTC and which activates each reader's zone, a reader in Auckland, between midnight there and midnight in UTC, is shown the day before as today's archive, and `DateDetailView` refuses as in the future a URL dated that reader's today.

## `DateDetailView`

`DateDetailView` is a detail view whose queryset is narrowed to one day before the usual lookup by slug or primary key. An object that exists under another date is not found. Unless `allow_future` is true it also refuses a date in the future, by `TodayArchiveView`'s clock, with an `Http404` before it asks the database anything (`django/views/generic/dates.py:BaseDateDetailView.get_object`).
