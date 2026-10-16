---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Sitemaps: `Sitemap` and the sitemap views

`django.contrib.sitemaps` writes sitemap XML from Python: a subclass of `Sitemap` says which items it lists and what is known of each, and the views `index` and `sitemap` turn a dictionary of sitemaps into an index and the files it lists, with absolute URLs on the current site and, if asked, one for each language.

A sitemap tells a crawler a site's URLs and, optionally, when each page last changed, how often it changes and its priority, in files of at most 50,000 URLs that an index lists. The views are given a dictionary whose keys are the **sections** and whose values are sitemaps, classes or instances; `sitemap` renders one section, or all of them in one file, and `index` lists a URL for each page of each section.

## What a sitemap says of each item

`Sitemap.items` returns the objects to list, a list or a queryset, by default none. `Sitemap.location`, `lastmod`, `changefreq` and `priority` each say one thing of an item, as a value for all or a method that takes the item. `Sitemap._get` gives `None` for one the sitemap lacks, calls a callable with the item, and otherwise returns the value (`django/contrib/sitemaps/__init__.py:Sitemap._get`). Of the four, the base class defines only `location`, the item's `get_absolute_url`, a path; the template writes the other three only where the item has a value for them.

`Sitemap._urls` makes a dictionary for each item of the page asked for, with the keys `"item"`, `"location"`, `"lastmod"`, `"changefreq"`, `"priority"` and `"alternates"`; the location joins the protocol, the domain and the path, and the priority is a string, empty for none (`django/contrib/sitemaps/__init__.py:Sitemap._urls`). The list is the template's `"urlset"`; a project's template finds each object at `"item"`, paired with a language code where each language is listed. `_urls` also stores the page's latest lastmod on the sitemap, where the `sitemap` view reads it as `"latest_lastmod"`, but only if every item of the page had one.

## Pages and the domain

`Sitemap.limit` is 50,000, a limit its comment calls Google's, citing sitemaps.org. `Sitemap.paginator` makes a new `Paginator` of the items, `limit` to a page, each time it is read, calling `items` again (`django/contrib/sitemaps/__init__.py:Sitemap.paginator`). The paginator warns of a queryset with no ordering: a `GenericSitemap` of every lighthouse raised `UnorderedObjectListWarning` ([Pagination: `Paginator` and `Page`](../services/pagination.md)).

`Sitemap.get_urls` takes a page, a site and a protocol. The protocol is `Sitemap.get_protocol`'s: the sitemap's own `Sitemap.protocol`, else the one passed, else `"https"`. The domain is `Sitemap.get_domain`'s: the site passed, else the current site by `SITE_ID`; without the sites application or that row, `ImproperlyConfigured`, "To use sitemaps, either enable the sites framework or pass a Site/RequestSite object in your view." (`django/contrib/sitemaps/__init__.py:Sitemap.get_domain`). The `sitemap` view always passes the request's site and scheme, so the `"https"` and the lookup serve code that builds a sitemap outside a request.

## A URL for each language

With `Sitemap.i18n` true, each item is listed once for each of its languages, which are `Sitemap.get_languages_for_item`'s, by default `Sitemap.languages` or the codes of `LANGUAGES`. `Sitemap._items` makes the pairs of item and code before pagination, so that, its comment says, pages are cut with every language counted: `limit` counts URLs, not objects (`django/contrib/sitemaps/__init__.py:Sitemap._items`). `_get` hands a method the object alone, and `Sitemap._location` calls `location` inside `django.utils.translation.override` of the pair's language, so under `i18n_patterns` `reverse` writes that language's prefix (`django/contrib/sitemaps/__init__.py:Sitemap._location`) ([The active language](../i18n/active-language.md), [Language prefixes and translated routes](../urls/i18n.md)).

With `Sitemap.alternates` also true, each URL links to the item in each of its languages, and with `Sitemap.x_default` once more, as `"x-default"`, when `LANGUAGE_CODE` is among them: the URL in that language with the first path segment that is its code cut out (`django/contrib/sitemaps/__init__.py:Sitemap._urls`). With the lighthouses' URL pattern moved under `i18n_patterns`, `LANGUAGES` English and Maltese and `LANGUAGE_CODE` `"en"`, the office lists them with:

```python
# notes/sitemaps.py
from django.contrib.sitemaps import Sitemap

from notes.models import Lighthouse


class LighthouseSitemap(Sitemap):
    i18n = True
    alternates = True
    x_default = True

    def items(self):
        return Lighthouse.objects.order_by("name")
```

St Elmo's two URLs, at /en/ and /mt/, carry the same three links; the first, one element to a line:

```text
<url>
<loc>http://harbour.example/en/lighthouses/1/</loc>
<xhtml:link rel="alternate" hreflang="en" href="http://harbour.example/en/lighthouses/1/"/>
<xhtml:link rel="alternate" hreflang="mt" href="http://harbour.example/mt/lighthouses/1/"/>
<xhtml:link rel="alternate" hreflang="x-default" href="http://harbour.example/lighthouses/1/"/>
</url>
```

## `GenericSitemap`

`GenericSitemap` is a sitemap made from a dictionary: `"queryset"` gives the items and an optional `"date_field"` names the field read as an item's lastmod. `priority`, `changefreq` and `protocol` may be passed as arguments, and count only where the class's own value is false, such as `None` (`django/contrib/sitemaps/__init__.py:GenericSitemap.__init__`). It goes into the dictionary as an instance, which lives as long as the URLconf. `GenericSitemap.items` returns a clone of the queryset, by `QuerySet.filter` with no arguments, against premature evaluation, its comment says: the queryset the instance keeps is never evaluated and holds no rows between requests.

The index asks each sitemap for `Sitemap.get_latest_lastmod`, which returns a `lastmod` that is a value, and calls one that is a method on every item and takes the greatest; `None` if it has none or some item's is `None` (`django/contrib/sitemaps/__init__.py:Sitemap.get_latest_lastmod`). `GenericSitemap.get_latest_lastmod`, given a `"date_field"`, asks the database for one value, and otherwise returns `None` (`django/contrib/sitemaps/__init__.py:GenericSitemap.get_latest_lastmod`). For the bulletins, the first selected every column of every bulletin; a `GenericSitemap` with `"date_field"` `"published"` sent `SELECT "notes_bulletin"."published" AS "published" FROM "notes_bulletin" ORDER BY 1 DESC LIMIT 1`.

## The views: `index` and `sitemap`

Both views call a value of the dictionary that is callable, a class, to make a sitemap for the request, and use an instance as it is. Both take the domain from `get_current_site` and the protocol from the request's scheme unless a sitemap sets its own ([Sites: `Site`, `get_current_site` and the `shortcut` view](sites.md)), return a `TemplateResponse` of `"sitemap_index.xml"` or `"sitemap.xml"` by default, as `"application/xml"` ([`SimpleTemplateResponse` and `TemplateResponse`](../templates/responses.md)), and are wrapped by `x_robots_tag`, which sets X-Robots-Tag to `"noindex, noodp, noarchive"` (`django/contrib/sitemaps/views.py:x_robots_tag`).

`index` reverses the URL its sitemap_url_name argument names, by default `"django.contrib.sitemaps.views.sitemap"`, with the section as `"section"`, and makes a `SitemapIndexItem` of the absolute URL and the sitemap's `get_latest_lastmod`; each page after the first adds the URL with `"?p="` and the page's number, and the same date (`django/contrib/sitemaps/views.py:index`). `sitemap` renders the section named, raising `Http404` for a key the dictionary lacks, or, given none, every sitemap in one file. The page is the query string's `"p"`, 1 by default, asked of every sitemap rendered; the paginator's `EmptyPage` and `PageNotAnInteger` become `Http404` (`django/contrib/sitemaps/views.py:sitemap`).

Each view sends Last-Modified only when every sitemap it covers gives a date: `index` from each `get_latest_lastmod`, `sitemap` from the `"latest_lastmod"` that `_urls` left on the sitemap; an instance in the dictionary keeps it between requests, so a later page with an undated item carried an earlier page's date. `_get_latest_lastmod` keeps the greatest, a date taken as midnight and a naive datetime as UTC (`django/contrib/sitemaps/views.py:_get_latest_lastmod`).

> **Why.** So that `ConditionalGetMiddleware` can answer 304 Not Modified, the comment at each header says ([Cache headers and conditional requests: `django/utils/cache.py`](../services/http-caching.md)).

With the bulletins' sitemap given a `limit` of 2, the views gave these; the last three called the view directly:

```text
/sitemap.xml 200
    <loc>http://harbour.example/sitemap-bulletins.xml</loc>
    <lastmod>2026-10-14T07:15:00+02:00</lastmod>
    <loc>http://harbour.example/sitemap-bulletins.xml?p=2</loc>
    <lastmod>2026-10-14T07:15:00+02:00</lastmod>
    <loc>http://harbour.example/sitemap-lighthouses.xml</loc>
    Last-Modified: None
/sitemap-bulletins.xml 200
    <loc>http://harbour.example/bulletins/3/</loc>
    <loc>http://harbour.example/bulletins/2/</loc>
    Last-Modified: Wed, 14 Oct 2026 05:15:00 GMT
/sitemap-bulletins.xml?p=2 200
    <loc>http://harbour.example/bulletins/1/</loc>
    Last-Modified: Mon, 12 Oct 2026 06:00:00 GMT
/sitemap-bulletins.xml?p=3     Http404: Page 3 empty
/sitemap-bulletins.xml?p=two   Http404: No page 'two'
/sitemap-ships.xml             Http404: No sitemap available for section: 'ships'
```

The lighthouses give no dates, so the index has no Last-Modified; in it both pages of the bulletins carry the sitemap's latest date, while each file's header carries its own page's.

## Flat pages and geometries

`FlatPageSitemap` lists the current site's flat pages that require no login. It asks for the current site without the request, so needs `SITE_ID` even where the views find the site by host, and raises `ImproperlyConfigured` without the sites application (`django/contrib/flatpages/sitemaps.py:FlatPageSitemap.items`) ([Flat pages and redirects: the fallback middleware](flatpages-and-redirects.md)). GeoDjango's `KMLSitemap` and `KMZSitemap` list geometry fields, at views that write KML ([GeoDjango's forms, admin, feeds and data tools](gis-extras.md)).
