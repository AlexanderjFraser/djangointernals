---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
part: The other contrib apps
contents: content-types, making-content-types, generic-foreign-key, generic-relation, sites, static-finders, collectstatic, static-storage, serving-static, flatpages-and-redirects, sitemaps, feeds, humanize, postgres, postgres-fields, postgres-search, postgres-indexes, geometries, spatial-fields, spatial-backends, spatial-queries, gis-extras
---

# Content types, static files and the other contrib apps

The applications of `django.contrib` that are not authentication, sessions, messages or the admin: content types, which give the models rows of their own so that a row can point at any model; sites, which keep a row for each domain a project serves; static files, which find, collect, name and serve a project's CSS, JavaScript and images; flat pages, redirects, sitemaps, feeds and humanize, small applications, most of them built on those; and the PostgreSQL and GIS extensions to the ORM.

`django.contrib` is where Django keeps the applications it ships beside the framework. None of them is the framework: each is an ordinary application that a project lists in `INSTALLED_APPS` or leaves out, and each plugs into Django through the means a project's own applications have, but for the GIS application, whose config adds its `"geojson"` format to Django's own table of serializers (`django/contrib/gis/apps.py:GISConfig.ready`), and the static files application, whose finders and storage Django's default settings name (`django/conf/global_settings.py`). Such an application may have models and migrations, an application config whose `ready` connects receivers of Django's signals or registers system checks, and middleware, views, template libraries and management commands. Where Django's core needs to know whether one of them is there, it asks: the `{% static %}` tag, for one, asks the app registry whether the static files application is installed before deciding how to write a URL (`django/templatetags/static.py:StaticNode.handle_simple`). Authentication, sessions and messages have a chapter of their own ([Authentication, sessions and messages](auth.md)), and so has the admin ([The admin](admin.md)). This chapter is the rest.

Two of the rest are services that other applications build on. The content types application ordinarily gives each installed model a row in a table, so that anything that has to name a model in the database, a permission, a line of the admin's log or a note attached to any row, can hold a key to that row. The sites application keeps a row for each domain the project serves, of which it makes only the first, so that content can belong to a site and a page can be asked which site it is on. Static files are a third service, of another kind: they do not live in the database at all, and the application's work is to find them, put them in one place and give each a name that changes when its content does. Most of the rest are small applications, several of which ask for the current site, and two large ones extend the ORM to PostgreSQL's types and to geometry.

| application | what it adds | how it plugs in |
|---|---|---|
| `django.contrib.contenttypes` | `ContentType`, a row for each model; generic foreign keys and generic relations | a receiver of `post_migrate` that makes the rows, one of `pre_migrate` that follows a renamed model, two model checks |
| `django.contrib.sites` | `Site`, a row for each site; the current site | a receiver of `post_migrate` that makes the first site; a check of `SITE_ID` |
| `django.contrib.staticfiles` | the finders, collectstatic and findstatic, storages that put a hash in a file's name, serving in development | management commands, a runserver of its own, the `"staticfiles"` storage, checks |
| `django.contrib.flatpages` | pages whose HTML is kept in the database | a middleware that answers a 404 with a page, or a URL pattern; a template library |
| `django.contrib.redirects` | redirects kept in the database | a middleware that answers a 404 with a redirect |
| `django.contrib.sitemaps` | sitemap XML made from lists of items, usually querysets | two views and their templates |
| `django.contrib.syndication` | RSS and Atom feeds | a view class, over `django.utils.feedgenerator` |
| `django.contrib.humanize` | filters that write numbers and dates for people | a template library |
| `django.contrib.postgres` | PostgreSQL's array, hstore and range fields, full-text search, indexes, exclusion constraints, migration operations | a receiver of `connection_created`; lookups registered on the model fields `django.db.models.CharField` and `django.db.models.TextField`, and, once the range fields are imported, `"contained_by"` on five of the number and date fields; `OpClass` made a wrapper of index expressions |
| `django.contrib.gis` | geometry and raster fields, spatial lookups and functions, Python geometries over GEOS and GDAL | database backends of its own, wrappers of two libraries, a serializer format its config adds, the commands ogrinspect and inspectdb |

*The applications of this chapter. Each is a package under `django/contrib/`; the feed generator is `django/utils/feedgenerator.py`.*

## The harbour office's public site

The harbour office publishes notices to mariners and a few pages about itself at harbour.example. Its settings install the applications of this chapter beside harbour's own and two of the office's, notes and charts:

```python
# harbour/settings.py
INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.sites",
    "django.contrib.flatpages",
    "django.contrib.redirects",
    "django.contrib.sitemaps",
    "django.contrib.syndication",
    "django.contrib.humanize",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "django.contrib.gis",
    "harbour.fleet",
    "harbour.crew",
    "harbour.office",
    "notes",
    "charts",
]
MIDDLEWARE = [
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.flatpages.middleware.FlatpageFallbackMiddleware",
    "django.contrib.redirects.middleware.RedirectFallbackMiddleware",
]
SITE_ID = 1
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "collected"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.ManifestStaticFilesStorage"},
}
```

The notes application attaches a line of text to any row, a ship, a port or a lighthouse, and keeps the office's bulletins:

```python
# notes/models.py
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.db import models


class Note(models.Model):
    text = models.CharField(max_length=200)
    added = models.DateTimeField()
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveBigIntegerField()
    content_object = GenericForeignKey("content_type", "object_id")


class Lighthouse(models.Model):
    name = models.CharField(max_length=60)
    port = models.ForeignKey("fleet.Port", on_delete=models.CASCADE)
    notes = GenericRelation(Note, related_query_name="lighthouse")


class Bulletin(models.Model):
    title = models.CharField(max_length=100)
    body = models.TextField()
    published = models.DateTimeField()
    port = models.ForeignKey("fleet.Port", on_delete=models.CASCADE)
    sites = models.ManyToManyField("sites.Site")
```

Its URLconf serves each bulletin and lighthouse at a page of its own, a feed of the bulletins at bulletins/feed/, a sitemap index at sitemap.xml with a sitemap of the bulletins and one of the flat pages, and the content types' `shortcut` view at r/. The database has the site harbour.example as site 1, two flat pages, /about/ and /members/, the second only for users who have logged in, and two redirects, from /timetable/ to /sailings/ and from /old-notices/ to nothing. Django's test client, sending `"Host"` harbour.example, made these requests:

| request | response | what answered |
|---|---|---|
| `"GET"` /r/21/1/ | 302 to http://harbour.example/lighthouses/1/ | `shortcut`: content type 21 is the lighthouse model, which has no site of its own, so the domain is the current site's |
| `"GET"` /about/ | 200, the flat page "About the harbour office" | no URL pattern matched; `FlatpageFallbackMiddleware` found the page |
| `"GET"` /members/ | 302 to /accounts/login/?next=/members/ | the same middleware; the page requires a login |
| `"GET"` /timetable/ | 301 to /sailings/ | `RedirectFallbackMiddleware` |
| `"GET"` /old-notices/ | 410 | the same middleware: a redirect to nothing means the page is gone |
| `"GET"` /nowhere/ | 404 | neither middleware had anything for the path |
| `"GET"` /sitemap.xml | 200, a sitemap index of two sitemaps | `django.contrib.sitemaps.views.index` |
| `"GET"` /bulletins/feed/ | 200, an RSS 2.0 document of three items | the bulletins' feed, an instance of a subclass of `Feed` (`django/contrib/syndication/views.py:Feed`) |

*Requests to the harbour office's public site. The flat-page and redirect answers came out of middleware on the way out of a 404.*

## Content types: a row for every model

A foreign key names its target in the schema: a ship's home is a port, and the column holds a port's key. Some relations cannot be written so. A permission belongs to a model, any model. A line of the admin's log is about an object of any model. A note of the harbour office is attached to a ship in one row and to a port in the next. Each needs to name a model in a column, and a model is not a row of anything, unless something makes it one.

`ContentType` is that row. Besides its key, it has two fields, `app_label` and `model`, the model's name in lower case, unique together, in the table `"django_content_type"`. Its manager, `ContentTypeManager`, finds the row for a model class with `get_for_model`, which answers for a proxy model with its concrete model's row unless told otherwise, and makes the row on the spot if there is none; and it keeps every row found or made so in a cache held on the manager, by database and both by the pair and by the row's key, so that a later lookup of the same content type does not ask the database again until `clear_cache` empties the cache (`django/contrib/contenttypes/models.py:ContentTypeManager.get_for_model`). The other way, `ContentType.model_class` asks the app registry for the model the row names, and answers `None` for a row whose model has gone (`django/contrib/contenttypes/models.py:ContentType.model_class`) ([Content types: `ContentType` and its cache](contrib/content-types.md)).

The rows are made after each migrate. `ContentTypesConfig.ready` connects `create_contenttypes` to `post_migrate`, which Django sends for every installed application with a models module once migrate has run, and `create_contenttypes` inserts, in one `bulk_create`, a row for each of the application's models in the state the migrations leave that has none; the auth application's receiver calls it too, before its own work (`django/contrib/contenttypes/apps.py:ContentTypesConfig.ready`, `django/contrib/contenttypes/management/__init__.py:create_contenttypes`). It deletes nothing: the row of a model that was deleted stays until the command remove_stale_contenttypes removes it. A model renamed by a migration ordinarily keeps its row, because a receiver of `pre_migrate` puts a `RenameContentType` operation into the plan after each `RenameModel`; where a row of the new name exists already, the rename is skipped with a `RuntimeWarning` ([Making content types: `create_contenttypes` and `RenameContentType`](contrib/making-content-types.md)). A content type's key is whatever its database gave it: in the run behind this page the ship model's was 12 and the lighthouse's 21.

### A generic foreign key

A note of the harbour office points at its object with two ordinary columns, a foreign key to `ContentType` and a number, and a `GenericForeignKey` that reads them as one relation. The `GenericForeignKey` has no column of its own: it is put among the model's private fields, beside the concrete ones, and names the two fields it reads (`django/contrib/contenttypes/fields.py:GenericForeignKey.contribute_to_class`):

```text figure=the-generic-key
notes_note                                                 django_content_type
 id  text                  content_type_id  object_id      id  app_label  model
 1   Hull recaulked        12               1          ->  12  fleet      ship        - ->  fleet_ship        id 1, name Endeavour
 2   Pilot boards at the   11               1          ->  11  fleet      port        - ->  fleet_port        id 1, name Valletta
     breakwater
 3   Lamp changed          21               1          ->  21  notes      lighthouse  - ->  notes_lighthouse  id 1, name St Elmo

->    content_type_id is a foreign key, with a constraint, to django_content_type.
- ->  object_id is a plain number: no constraint ties it to any table.
```

*Three notes in one table, each attached to a row of another model. The content type says which table; the object id says which row of it; only Django puts the two together.*

Reading a note's content_object, in the default fetch mode, takes the content type's key from the row without loading the content type, gets the content type by that key through the manager's cache, and asks the model it names, through the model's base manager, for the row with the object's key; the object is then cached on the note, and a second read sends nothing while the note's two fields are unchanged (`django/contrib/contenttypes/fields.py:GenericForeignKeyDescriptor.__get__`, `django/contrib/contenttypes/fields.py:GenericForeignKeyDescriptor.fetch_one`). Reading the three notes and their objects sent four queries: the notes, then a ship, a port and a lighthouse, one at a time; `prefetch_related("content_object")` groups the notes by content type and sends one query for each type instead ([Generic foreign keys: `GenericForeignKey`](contrib/generic-foreign-key.md)).

Because nothing in the database ties the object id to a table, nothing in the database keeps it right. When the run deleted the ship Endeavour, its note stayed, with its content type and object id unchanged, and its content_object was `None`.

### A generic relation

The other end is declared on the model pointed at, if anywhere. A `GenericRelation` on the lighthouse model gives each lighthouse a manager of its notes, lets a query cross from lighthouses to notes and, with its `related_query_name`, from notes to lighthouses, and makes deleting a lighthouse delete its notes, which the run confirmed. It is a `ForeignObject` that joins the lighthouse's key to the note's object id, with one more condition, on the content type (`django/contrib/contenttypes/fields.py:GenericRelation.get_extra_restriction`). A query for the lighthouses with a note that begins "Lamp" compiled, for SQLite, to:

```text
Lighthouse.objects.filter(notes__text__startswith="Lamp")

SELECT "notes_lighthouse"."id", "notes_lighthouse"."name", "notes_lighthouse"."port_id"
FROM "notes_lighthouse"
INNER JOIN "notes_note" ON ("notes_lighthouse"."id" = "notes_note"."object_id"
                            AND ("notes_note"."content_type_id" = %s))
WHERE "notes_note"."text" LIKE %s ESCAPE '\'
params: (21, 'Lamp%')
```

The ship and port models have no such field, so a query cannot cross from them to their notes, and their deletes leave their notes behind. Forms and the admin edit the notes attached to any object, a port's as well as a lighthouse's, with formsets built on the note's two fields, which need no `GenericRelation` ([Generic relations: `GenericRelation` and generic inlines](contrib/generic-relation.md)).

## Sites: the current site

A project can serve several domains from one database, and some content belongs to some of them: a bulletin of the harbour office appears on harbour.example, and one about Piraeus on piraeus.harbour.example as well. `Site` is a row for each domain, a domain and a display name in the table `"django_site"`, and the question flat pages, redirects, sitemaps, feeds and the content types' `shortcut` view ask of it is which site the current request is on (`django/contrib/sites/models.py:Site`).

`SiteManager.get_current` answers it. With `SITE_ID` set to anything true, the current site is the row with that key, whatever the request; otherwise it is the row whose domain matches the request's host, ignoring case, with its port and, failing that, without. Either way the row found is kept in a dictionary of the module, under the key, the host or the host's domain it was found by, and a receiver of `pre_save` and `pre_delete` removes from it the entries under a site's key and its stored domain when the site is saved or deleted (`django/contrib/sites/models.py:SiteManager.get_current`, `django/contrib/sites/models.py:clear_site_cache`). The function the other applications call with a request is `get_current_site`, which asks the manager when the sites application is installed and otherwise makes a `RequestSite`, an object with a domain and a name that are both the request's host and that cannot be saved (`django/contrib/sites/shortcuts.py:get_current_site`). The flat-page view and the redirect middleware look up their rows by it; sitemaps write their absolute URLs with its domain, and feeds the feed's link and each item's; the content types' `shortcut` view, which the admin's "View on site" link goes through unless a model admin gives a URL of its own, uses it to decide which domain to send a browser to; and so does the auth application's password reset, unless given a domain, for the link it mails ([Sites: `Site`, `get_current_site` and the `shortcut` view](contrib/sites.md)).

The first row is made by a receiver of `post_migrate`, which inserts example.com, keyed by `SITE_ID` (1 without the setting), when the table is empty and the router allows it (`django/contrib/sites/management.py:create_default_site`). The harbour office changed its domain to harbour.example.

## Static files: found, collected, named

A project's CSS, JavaScript and images are scattered: each application keeps its own in a directory called static, and the project keeps more in directories of its own. In production a web server should serve them, from one directory, and a browser should be able to cache each for as long as it likes, which it can only do if a file's URL changes when its content does. The static files application does three things to get there: it finds a file by its path among all those directories, it collects every file into one storage, by default the directory `STATIC_ROOT`, and that storage can name each collected file after a hash of its content and keep a record of the names, which the `{% static %}` tag reads to write a URL while `settings.DEBUG` is off.

```text figure=a-static-file
notes/static/notes/harbour.css             a file in the notes application's static directory
    |
    |  python manage.py collectstatic
    |    each finder of STATICFILES_FINDERS lists its files;
    |    AppDirectoriesFinder lists "notes/harbour.css"
    v
STATIC_ROOT/notes/harbour.css              copied by the "staticfiles" storage
    |
    |  ManifestFilesMixin.post_process
    |    reads the original, notes/static/notes/harbour.css, not this copy;
    |    rewrites its references to base.css and anchor.png to their hashed names,
    |    then hashes the content: md5, the first 12 hex digits
    v
STATIC_ROOT/notes/harbour.f60ecf1ef40a.css
STATIC_ROOT/staticfiles.json               the manifest
    "notes/harbour.css": "notes/harbour.f60ecf1ef40a.css"
    |
    |  {% static "notes/harbour.css" %} in a template
    |    staticfiles_storage.url, which looks the name up in the manifest
    v
/static/notes/harbour.f60ecf1ef40a.css
```

*One file of the notes application, from where it is kept to the URL a page links it by.*

A **finder** finds a file by its relative path and lists the files it has. `STATICFILES_FINDERS` names two by default: `FileSystemFinder`, which looks in the directories of `STATICFILES_DIRS`, each optionally under a prefix, and `AppDirectoriesFinder`, which looks in the static directory of each installed application, in the order of `INSTALLED_APPS`. `find` asks them in that order for a relative path and, unless given `find_all=True`, takes the first match, which is how the harbour office's own notes/base.css, in a directory of `STATICFILES_DIRS`, shadows the notes application's file of the same name (`django/contrib/staticfiles/finders.py:find`) ([Finding static files: the finders](contrib/static-finders.md)). Collectstatic asks every finder to list its files, less those its ignore patterns match, keeps the first file it meets for each path and skips the rest, and copies or links each into the storage the `STORAGES` setting names `"staticfiles"`, ordinarily passing over one whose copy there is as new as its source (`django/contrib/staticfiles/management/commands/collectstatic.py:Command.collect`). For the harbour office it copied twelve files, the GIS application's map widget among them, and skipped one, the notes application's base.css ([Collecting static files: the collectstatic command](contrib/collectstatic.md)).

Then, if the storage has a `post_process` method and `--no-post-process` was not given, collectstatic calls it with the first file the finders found for each path, copied in this run or not. `ManifestStaticFilesStorage` uses it to give each file a name with a hash of its content, and to rewrite the references inside CSS files (`url()`, `@import`, a source map's comment) and JavaScript files (a source map's comment) that lead to static files, by a relative path or one under `STATIC_URL`, to their hashed names. A reference changes the content, and the content gives the hash, so after a first pass over every file the CSS and JavaScript files are processed again, pass after pass, until no name changes, for at most five more passes. The names go into a manifest, staticfiles.json, in the same storage unless another is given (`django/contrib/staticfiles/storage.py:HashedFilesMixin.post_process`, `django/contrib/staticfiles/storage.py:ManifestFilesMixin.save_manifest`). The harbour office's harbour.css came out of it as:

```css
@import url("base.932853cb9945.css");

body {
    background: url("../img/anchor.b357a19c8762.png") no-repeat;
}

/* The old banner was url("old-banner.png"), retired in 2025. */
```

The reference inside the comment was left alone: a match that begins strictly inside a comment or a quoted string is not rewritten ([Static file storages: `ManifestStaticFilesStorage` and hashed names](contrib/static-storage.md)).

`{% static "notes/harbour.css" %}` then gave /static/notes/harbour.f60ecf1ef40a.css, the name read from the manifest. With `settings.DEBUG` on the same tag gave /static/notes/harbour.css, because the storage's `url` hashes nothing while `settings.DEBUG` is true; with it off, a name the manifest lacks raised `ValueError`: "Missing staticfiles manifest entry for 'notes/missing.css'" (`django/contrib/staticfiles/storage.py:ManifestFilesMixin.stored_name`).

Nothing has to be collected during development. The static files application's runserver, which ordinarily replaces Django's own, wraps the project's handler in a `StaticFilesHandler` while `settings.DEBUG` is on or `--insecure` is given, unless `--nostatic` is, and that handler answers every request whose path is under a `STATIC_URL` that names no host by finding the file with the finders and serving it, without the project's middleware (`django/contrib/staticfiles/management/commands/runserver.py:Command.get_handler`, `django/contrib/staticfiles/handlers.py:StaticFilesHandler`) ([Serving static files: `StaticFilesHandler` and the development server](contrib/serving-static.md)).

## Pages from the database: flat pages and redirects

Flat pages and redirects keep in the database what would otherwise be a URL pattern: a page of HTML at a path, or a path that now leads somewhere else. Their middleware look for them only when the response is a 404; a flat page can also be served by a URL pattern of its own. `FlatpageFallbackMiddleware` and `RedirectFallbackMiddleware` do nothing on the way in; on the way out, each looks at the response, passes on anything that is not a 404, and for a 404 looks for the request's path on the current site: the flat-page middleware by the path without the script prefix or the query string, the redirect middleware by the full path, query string included, exactly (`django/contrib/flatpages/middleware.py:FlatpageFallbackMiddleware.process_response`, `django/contrib/redirects/middleware.py:RedirectFallbackMiddleware.process_response`).

The harbour office lists the redirect middleware last, so its `process_response` runs first on the way out. For /timetable/ it found a redirect and answered 301, which the flat-page middleware passed on; for /old-notices/, a redirect with an empty target, it answered 410 Gone. For /about/ it found nothing, and the flat-page middleware, given the 404, called the flat-page view, which found the page for the path and the site and rendered it with its template, "flatpages/default.html" unless the page names another that exists; for /members/ the page requires a login, and the view sent the anonymous client to `LOGIN_URL`. The flat-page middleware hands back the original 404 when the view raises `Http404`, and also when it raises anything else, unless `settings.DEBUG` is on ([Flat pages and redirects: the fallback middleware](contrib/flatpages-and-redirects.md)).

## Sitemaps and feeds

A sitemap and a feed are both lists of a site's pages for a program to read, written as XML from a list of items, usually a queryset, and both views ask the current site for the domain their absolute URLs need. A `Sitemap` subclass says which items it lists and, for each, its location, by default its `get_absolute_url`, and optionally when it last changed, how often it changes and its priority; it is cut by a `Paginator` into pages of `Sitemap.limit` URLs, 50,000 unless a subclass sets another. The `index` view lists one URL for each sitemap and page, the `sitemap` view renders the URLs of one **section**, a key of the dictionary of sitemaps the views are given, or of all when none is named, and both send an X-Robots-Tag header and, ordinarily when every sitemap involved can say when it last changed, a Last-Modified header (`django/contrib/sitemaps/views.py:index`, `django/contrib/sitemaps/views.py:sitemap`). The harbour office's index had no Last-Modified header, because its sitemap of flat pages gives no dates ([Sitemaps: `Sitemap` and the sitemap views](contrib/sitemaps.md)).

A feed is a class too, and an instance of it is the view. Its `__call__` asks `get_object` for the object the feed is about, if any, and builds a feed generator, by default an RSS 2.0 one, from attributes of the class, most of which may be a value, a method that takes the object (for a part of an item, the item), or a method that takes nothing; it adds an item for each of `items`, and writes the XML into the response (`django/contrib/syndication/views.py:Feed.__call__`, `django/contrib/syndication/views.py:Feed.get_feed`). The generator, in `django/utils/feedgenerator.py`, knows RSS and Atom and nothing of Django's models ([Feeds: `django.contrib.syndication` and the feed generator](contrib/feeds.md)).

`django.contrib.humanize` is a template library and the catalogues that translate it: filters such as `intcomma`, `naturalday` and `naturaltime` that write a number or a date as a person would, in the active language ([Humanize: `naturaltime`, `intcomma` and the other filters](contrib/humanize.md)).

## PostgreSQL

`django.contrib.postgres` adds to the ORM what PostgreSQL has and the other databases Django supports do not share: fields for arrays, key-value pairs and ranges, full-text search, kinds of index with PostgreSQL's storage parameters, an exclusion constraint, aggregates such as `ArrayAgg`, and migration operations that install extensions. Among what it does at start-up, `PostgresConfig.ready` connects a receiver to `connection_created` that registers hstore, and citext's array type, with the driver for each new PostgreSQL connection, by type numbers it asks each database alias for and keeps until `CreateExtension` clears them; and it registers the transform `"unaccent"`, and `"search"` and three trigram lookups, on `CharField` and `TextField`, for every database (`django/contrib/postgres/apps.py:PostgresConfig.ready`) ([The PostgreSQL application: `PostgresConfig`, operations and aggregates](contrib/postgres.md)).

The rest is written with the ORM's own means: a field is a `django.db.models.Field` whose `db_type` names a PostgreSQL type, a lookup a `Lookup` that writes an operator or a `Transform` that writes a function, an index an `Index` with a method. The charts application's sailings have a range of times, an array of names and an hstore of cargo, a GIN index and a constraint that no two sailings of one vessel overlap; a schema editor for PostgreSQL, made with no server behind it, wrote:

```text
CREATE TABLE "charts_sailing" ("id" bigint NOT NULL PRIMARY KEY GENERATED BY DEFAULT AS IDENTITY, "vessel" varchar(60) NOT NULL, "window" tstzrange NOT NULL, "crew" varchar(60)[] NOT NULL, "cargo" hstore NOT NULL, CONSTRAINT "one_sailing_at_a_time" EXCLUDE USING GIST ("window" WITH &&, "vessel" WITH =));
CREATE INDEX "sailing_cargo_gin" ON "charts_sailing" USING gin ("cargo");
```

The fields have a section, [PostgreSQL fields: `ArrayField`, the range fields and hstore](contrib/postgres-fields.md); so has search, [Full-text search: `SearchVector`, `SearchQuery` and `SearchRank`](contrib/postgres-search.md), and the indexes and constraint, [PostgreSQL indexes and `ExclusionConstraint`](contrib/postgres-indexes.md).

## GeoDjango

`django.contrib.gis` is the largest application of `django.contrib`, and the one that reaches furthest into Django. It adds fields that hold geometries and rasters, lookups and functions that compare and measure them, and a spatial database backend for each database it supports: PostGIS for PostgreSQL, SpatiaLite for SQLite, MySQL and Oracle. A project names one of them as a database's `"ENGINE"`, `"django.contrib.gis.db.backends.postgis"` in place of `"django.db.backends.postgresql"`; each is a subclass of the plain backend whose operations know the spatial types and functions, whose schema editor ordinarily gives a geometry field a spatial index, and whose adapter turns a geometry into a parameter. A geometry field asks the connection's operations for its column's type, so it can only be created on such a backend (`django/contrib/gis/db/models/fields.py:BaseSpatialField.db_type`) ([Spatial fields: the geometry fields and `RasterField`](contrib/spatial-fields.md), [Spatial backends: PostGIS, SpatiaLite, MySQL and Oracle](contrib/spatial-backends.md)). The charts application's moorings have a point; PostGIS's schema editor, with no server behind it, wrote:

```text
CREATE TABLE "charts_mooring" ("id" bigint NOT NULL PRIMARY KEY GENERATED BY DEFAULT AS IDENTITY, "name" varchar(60) NOT NULL, "position" geometry(POINT,4326) NOT NULL, "depth" numeric(5, 1) NOT NULL);
CREATE INDEX "charts_mooring_position_91c43e7d_id" ON "charts_mooring" USING GIST ("position");
```

In Python a geometry is a `GEOSGeometry`, an object over GEOS, a library of geometry whose C interface is reached through `ctypes`; coordinate systems, transformations, rasters and files of vector data go through GDAL, another library, the same way. GeoDjango loads GDAL as soon as `django.contrib.gis.gdal` is imported, and GEOS as soon as `django.contrib.gis.geos` is, which the geometry fields' module does; each is found by a path in the settings or by the names the library is known by on the platform (`django/contrib/gis/gdal/libgdal.py`, `django/contrib/gis/geos/libgeos.py:load_geos`) ([Geometries in Python: GEOS and GDAL](contrib/geometries.md)). A lookup such as `"distance_lte"` or a function such as `django.contrib.gis.db.models.functions.Distance` turns into the backend's own SQL function or operator, with the geometry passed through the adapter ([Spatial lookups, functions and distances](contrib/spatial-queries.md)), and the application has form fields and map widgets, a `ModelAdmin` subclass, feeds, KML sitemaps, a serializer and tools for loading data of its own ([GeoDjango's forms, admin, feeds and data tools](contrib/gis-extras.md)).

## Where it meets the rest of Django

Every application of this chapter is put in place by the app registry, and some by an application config's `ready` as well ([Settings, apps and startup](startup.md)), and the receivers of `post_migrate` that make content types and the first site run after migrate ([Migrations](migrations.md)); the permissions of the auth application and the admin's log name their models by content type ([Authentication, sessions and messages](auth.md), [The admin](admin.md)). The fallback middleware are middleware like any other ([Handlers and middleware](handlers.md)). Static files are served in development by the development server's handler, a `WSGIHandler`, or by the finders' view in a URL pattern, both through `django.views.static.serve` ([The static file view](views/static-files.md)), and in production by whatever serves `STATIC_ROOT`; the storages that hold them are file storages ([File storage: `Storage`, `FileSystemStorage` and `storages`](services/storage.md)). The PostgreSQL and GIS applications extend the ORM through its fields, lookups, expressions, indexes and constraints ([Models and fields](models.md), [From QuerySet to SQL](sql.md)), and GIS through its backends too ([Database backends](backends.md)). The sitemap views and feeds are views that build XML ([Views](views.md)), humanize a template library ([Templates](templates.md)).
