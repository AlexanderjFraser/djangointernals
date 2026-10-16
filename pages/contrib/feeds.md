---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Feeds: `django.contrib.syndication` and the feed generator

How a feed, a subclass of `django.contrib.syndication.views.Feed`, answers a request with an RSS or Atom document: the object it is about, the attributes that may each be a value or a method, and the feed generator of `django/utils/feedgenerator.py`, a `SyndicationFeed` such as `Rss201rev2Feed` or `Atom1Feed`, which writes the XML.

A feed is made in two layers. The view knows the request: it finds the object, takes the current site's domain for links, renders templates and makes dates aware (`django/contrib/syndication/views.py:Feed`). The **feed generator** knows nothing of requests or models: it keeps what it is handed in dictionaries and writes one dialect of XML (`django/utils/feedgenerator.py:SyndicationFeed`).

## A feed is a view

The URLconf holds one instance of a `Feed` subclass (`django/contrib/syndication/views.py:Feed`), and every request to its pattern calls that one object ([What the handler asks of a view](../views/callable.md)). `Feed.__call__` does four things (`django/contrib/syndication/views.py:Feed.__call__`):

1. It passes the request and the captured arguments to `Feed.get_object`, which by default returns `None`. An `ObjectDoesNotExist` from it, such as a `Model.DoesNotExist` or a `FeedDoesNotExist`, becomes `Http404("Feed object does not exist.")`.
2. It calls `Feed.get_feed` for a filled feed generator.
3. It makes an `HttpResponse` with the generator's `content_type`, and, if the feed has an attribute `"item_pubdate"` or `"item_updateddate"`, a Last-Modified header from `SyndicationFeed.latest_post_date`, the newest date of any item or else the present, so that, says the comment, `ConditionalGetMiddleware` can answer 304 ([Cache headers and conditional requests: `django/utils/cache.py`](../services/http-caching.md#conditionalgetmiddleware)).
4. It has the generator write itself into the response, in UTF-8.

> **Trap.** Only `get_object` is inside the `try`. The docstring of `get_feed` says to raise `FeedDoesNotExist` for invalid parameters, but one raised in `"items"` escaped the view, and the handler made it a 500, not a 404.

The office's second feed is of one port's bulletins, in Atom, a chart attached to one; port 9, which does not exist, gave a 404:

```python
# notes/feeds.py, in part
from django.utils.feedgenerator import Atom1Feed


class PortBulletins(Feed):
    feed_type = Atom1Feed
    link = "/bulletins/"

    def get_object(self, request, pk):
        return Port.objects.get(pk=pk)

    def title(self, obj):
        return f"Bulletins for {obj.name}"

    def items(self, obj):
        return obj.bulletins.order_by("-published")

    def item_pubdate(self, item):
        return item.published

    def item_enclosure_url(self, item):
        if item.title == "Breakwater closed":
            return "/media/charts/north-breakwater.pdf"

    item_enclosure_length = 48213
    item_enclosure_mime_type = "application/pdf"

# in the URLconf
path("ports/<int:pk>/bulletins.atom", PortBulletins()),
```

## A value or a method: `_get_dynamic_attr`

Every part of a feed but four plain attributes, `Feed.feed_type`, `Feed.language`, `Feed.title_template` and `Feed.description_template`, and two methods always called, `Feed.feed_extra_kwargs` and `Feed.item_extra_kwargs`, is read through `Feed._get_dynamic_attr`, with one argument: the object from `Feed.get_object` for a part of the feed, the item for a part of an item (`django/contrib/syndication/views.py:Feed._get_dynamic_attr`). A missing name gives a default, `None` unless the caller passes one; a value that is not callable is the answer. A callable is called with the argument if its code has two positional parameters, `self` and one more, and otherwise without. The code is reached through `inspect.unwrap`, which follows the `__wrapped__` that `functools.wraps` leaves on a decorator's function, or, for an object with no `__code__`, through its `__call__`. The comment prefers this to catching a `TypeError` from the call, since one might come from inside the function.

Code with no positional parameter, a wrapper of `*args`, is taken for a decorator made without `functools.wraps` and refused instead, unless the feed holds a `staticmethod` under the function's own name. An `"item_title"` decorated so raised `ImproperlyConfigured`: "Feed method 'item_title' decorated by 'wrapper' needs to use @functools.wraps."

## Filling the generator: `get_feed`

`Feed.get_feed` works in this order (`django/contrib/syndication/views.py:Feed.get_feed`):

1. It asks `get_current_site` for the current site, a `Site`, or a `RequestSite` when the sites application is not installed ([Sites: `Site`, `get_current_site` and the `shortcut` view](sites.md)).
2. It makes the generator, an instance of `Feed.feed_type`, by default `Rss201rev2Feed`, from `"title"`, `"link"`, `"description"` and the rest, with the request's path if there is no `"feed_url"`, `django.utils.translation.get_language` if there is no `Feed.language`, and `Feed.feed_extra_kwargs`.
3. It loads `Feed.title_template` and `Feed.description_template`; a missing one is passed over silently.
4. For each of `"items"`, it renders those templates with the context of `Feed.get_context_data`, the item as `"obj"` and the site as `"site"`, or else asks `"item_title"` and `"item_description"`, by default the item's `str` (for the title, escaped). The link is `"item_link"`, by default the item's `get_absolute_url`. A naive `"item_pubdate"` or `"item_updateddate"` is made aware in the default time zone, whatever `USE_TZ` says ([Time zones](../i18n/time-zones.md)); `"item_guid"` defaults to the link. `SyndicationFeed.add_item` takes these and `Feed.item_extra_kwargs`.

The feed's link, its `"feed_url"` and each item's link go through `add_domain`: a path gets the scheme, `"https"` when `HttpRequest.is_secure` says so, and the domain; a URL beginning `"http://"`, `"https://"` or `"mailto:"` is left alone, and one beginning `"//"` gets the scheme, which RSS requires, says the comment, citing ticket 16753 (`django/contrib/syndication/views.py:add_domain`). Domain and path are joined as they are: `"bulletins/"` became `"http://harbour.examplebulletins/"`. An enclosure's URL is no link: `Feed.item_enclosures` makes at most one `Enclosure`, from `"item_enclosure_url"`, `"item_enclosure_length"` and `"item_enclosure_mime_type"`, each through `str`, so a missing length is written `"None"` (`django/contrib/syndication/views.py:Feed.item_enclosures`).

Valletta's feed, one element to a line, its first entry left out:

```text
200 application/atom+xml; charset=utf-8
Last-Modified: Tue, 13 Oct 2026 07:30:00 GMT
<?xml version="1.0" encoding="utf-8"?>
<feed xml:lang="en-us" xmlns="http://www.w3.org/2005/Atom">
  <title>Bulletins for Valletta</title>
  <link href="http://harbour.example/bulletins/" rel="alternate"/>
  <link href="http://harbour.example/ports/1/bulletins.atom" rel="self"/>
  <id>http://harbour.example/bulletins/</id>
  <updated>2026-10-13T07:30:00+00:00</updated>
  ...
  <entry>
    <title>Breakwater closed</title>
    <link href="http://harbour.example/bulletins/1/" rel="alternate"/>
    <published>2026-10-12T06:00:00+00:00</published>
    <id>http://harbour.example/bulletins/1/</id>
    <summary type="html">Breakwater closed</summary>
    <link href="/media/charts/north-breakwater.pdf" length="48213" rel="enclosure" type="application/pdf"/>
  </entry>
</feed>
```

The ids are the links. The times are in UTC, as the database returned them; the feed's updated is the newest.

`Feed.item_title` escapes the item's `str` as HTML, and its comment says titles should be double escaped by default, citing ticket 6533 (`django/contrib/syndication/views.py:Feed.item_title`); the generator escapes again, as XML. A bulletin "Tugs & pilots" became `<title>Tugs &amp;amp; pilots</title>` in this feed, and `<title>Tugs &amp; pilots</title>` in the bulletins' feed, whose `"item_title"` returns the title unescaped.

## The feed generator: `SyndicationFeed`

`SyndicationFeed.__init__` keeps the feed's values in a dictionary, text made strings and URLs escaped, the id `"feed_guid"` or else the link, and any keyword it does not know (`django/utils/feedgenerator.py:SyndicationFeed.__init__`); `SyndicationFeed.add_item` appends one for each item. `SyndicationFeed.write` raises `NotImplementedError`: writing is a dialect's.

`RssFeed.write` makes a `SimplerXMLGenerator` over the file ([Text helpers: `Truncator` and `django/utils/text.py`](../utils/text.md#the-xml-writer)) and writes the declaration, any stylesheets, an rss element and a channel, the feed's elements and the items (`django/utils/feedgenerator.py:RssFeed.write`); `Atom1Feed.write`, a feed element and entries. Both call four hooks, empty on `SyndicationFeed`: `SyndicationFeed.root_attributes`, `SyndicationFeed.add_root_elements`, `SyndicationFeed.item_attributes` and `SyndicationFeed.add_item_elements`. A format built on RSS or Atom subclasses `Rss201rev2Feed` or `Atom1Feed` and extends them, calling the superclass's, says the documentation (`docs/ref/contrib/syndication.txt`). GeoDjango's `Feed` uses one, `GeoRSSFeed`, handing it geometries through its own `feed_extra_kwargs` and `item_extra_kwargs` (`django/contrib/gis/feeds.py:Feed`) ([GeoDjango's forms, admin, feeds and data tools](gis-extras.md)).

| generator | `content_type` | root | an item's elements | enclosures |
|---|---|---|---|---|
| `RssUserland091Feed` | `"application/rss+xml; charset=utf-8"` | rss 0.91 | title, link, description | none |
| `Rss201rev2Feed`, `DefaultFeed` | `"application/rss+xml; charset=utf-8"` | rss 2.0 | those, author or dc:creator, pubDate, comments, guid, ttl, category | one; a second raises `ValueError` |
| `Atom1Feed` | `"application/atom+xml; charset=utf-8"` | feed | title, link, published, updated, author, id, summary, category, rights | each, as a link |

*The generators of `django/utils/feedgenerator.py`. `DefaultFeed` is `Rss201rev2Feed`.*

RSS writes dates with `rfc2822_date` and Atom with `rfc3339_date`; the channel's lastBuildDate and the feed's updated are `SyndicationFeed.latest_post_date`. An Atom entry with no unique id gets one from `get_tag_uri`; from a feed view, only when `"item_guid"` returns `None`, as in `"tag:harbour.example,2026-10-13:/bulletins/2//"` (`django/utils/feedgenerator.py:get_tag_uri`).

### Stylesheets

> **Changed in 5.2.** The feed generators take stylesheets (`docs/releases/5.2.txt`).

Each is a URL, made a `Stylesheet`, or a `Stylesheet`, whose type is guessed from the extension unless given, whose media is `"screen"` unless given, and whose URL is read only when written, so a lazy one from `reverse_lazy` works (`django/utils/feedgenerator.py:Stylesheet`). A string alone raised `TypeError`: "stylesheets should be a list, not <class 'str'>". `RssFeed.add_stylesheets` writes them before the first tag. `Atom1Feed.write` never calls the hook, empty on `SyndicationFeed`, so the port's feed, given the list, wrote none. The bulletins' RSS feed given `["/static/notes/feed.xsl"]` began:

```text
<?xml version="1.0" encoding="utf-8"?>
<?xml-stylesheet href="/static/notes/feed.xsl" media="screen" type="text/xsl"?><rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom"><channel>
```
