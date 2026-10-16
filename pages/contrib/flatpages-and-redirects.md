---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Flat pages and redirects: the fallback middleware

How `FlatpageFallbackMiddleware` and `RedirectFallbackMiddleware` turn a 404 on its way out into a page or a redirect read from rows of `FlatPage` and `Redirect`; the views `flatpage` and `render_flatpage`, the URL pattern that serves flat pages without the middleware, `FlatpageForm`, and the tag `get_flatpages`.

A site has pages not worth an application of their own, an "About" or a privacy notice, and paths that have moved. The flat pages application keeps the first in the database, one-off pages a project would not write an application for, in its documentation's words (`docs/ref/contrib/flatpages.txt`); the redirects application keeps the second. Their middleware are, in the same documentation's words, a last resort: a path the project answers costs them no query, and a path it does not know is theirs only once the project has given up on it. So both act on the way out, and only on a 404. The harbour office's requests are on the opening page ([Content types, static files and the other contrib apps](../contrib.md#pages-from-the-database-flat-pages-and-redirects)).

## The rows: `FlatPage` and `Redirect`

A flat page has a `url`, the path it answers, indexed but not unique; a `title`, and a `content` of raw HTML that may be blank; a `template_name`, blank for the default; `registration_required`; and `sites`, a many-to-many to `Site`. One more field, `enable_comments`, is read by nothing in Django and shown by no fieldset of the admin; the documentation leaves it to a project (`django/contrib/flatpages/models.py:FlatPage`).

A redirect belongs to one `site`, a foreign key, and has an `old_path`, indexed, and a `new_path`: an absolute path, a full URL, or empty. Site and old path are unique together (`django/contrib/redirects/models.py:Redirect`).

## The two middleware on the way out

`FlatpageFallbackMiddleware` and `RedirectFallbackMiddleware` are both built on `MiddlewareMixin` and have no hook but `process_response`, which returns at once any response whose status is not 404. Acting on the way out, the one listed later in `MIDDLEWARE` acts first ([Handlers and middleware](../handlers.md)). The harbour office lists the redirect middleware last, so a redirect is looked for first, and its 301 is no longer a 404 when it reaches the flat-page middleware: with a redirect from /pilots/ to /pilotage/ beside a flat page at /pilots/, the run answered 301 to /pilotage/. A miss costs queries: once the current site was cached, a 404 for /nowhere sent four, for a redirect at /nowhere and at /nowhere/, then for a flat page at the same two paths. Both set `async_capable = False`, so under ASGI the chain runs them synchronously ([Sync and async in one chain](../handlers/async.md)).

### `RedirectFallbackMiddleware`

`RedirectFallbackMiddleware.__init__` raises `ImproperlyConfigured` when the sites application is not installed, so the chain cannot be built without it. `RedirectFallbackMiddleware.process_response` looks among the current site's redirects and compares `old_path` with the request's full path, `HttpRequest.get_full_path`, query string included, and exactly. Failing that, when `settings.APPEND_SLASH` is true and the path does not end in a slash, it tries once more with a slash put before the query string. A match with an empty `new_path` is answered with an instance of `RedirectFallbackMiddleware.response_gone_class`, `HttpResponseGone`; any other with `RedirectFallbackMiddleware.response_redirect_class`, `HttpResponsePermanentRedirect`, given the new path. Both are class attributes, for a subclass to change, a comment says (`django/contrib/redirects/middleware.py:RedirectFallbackMiddleware`). With a redirect from /notices.php?id=7 to /bulletins/1/ added, the test client got:

```text
GET /timetable              301  Location: /sailings/
GET /timetable/?day=sat     404
GET /notices.php?id=7       301  Location: /bulletins/1/
GET /notices.php?id=8       404
```

### `FlatpageFallbackMiddleware`

`FlatpageFallbackMiddleware.process_response` calls the view `flatpage` with the request and `HttpRequest.path_info`, the path without the script prefix or the query string, and returns what the view returns. If the view raises `Http404`, the original 404 goes back. If it raises anything else, so does the 404, unless `settings.DEBUG` is true, when the exception goes on; the comment's reason is that a middleware cannot assume the error will be caught elsewhere (`django/contrib/flatpages/middleware.py:FlatpageFallbackMiddleware.process_response`). With no template "flatpages/default.html" anywhere, /about/ was a plain 404 with `settings.DEBUG` off; with it on, `TemplateDoesNotExist` came out of the middleware.

`BaseHandler._get_response` calls the `process_view` hooks only after the URL resolves, so none has run for a path that resolves nowhere (`django/core/handlers/base.py:BaseHandler._get_response`) ([The centre of the chain](../handlers/view.md)).

## The views `flatpage` and `render_flatpage`

`flatpage` is the public view, and finds the page. It puts a slash in front of a URL that lacks one, such as a path a URL pattern captured, and asks `get_object_or_404` for the `FlatPage` with that URL on the current site ([Sites: `Site`, `get_current_site` and the `shortcut` view](sites.md)). When there is none, `settings.APPEND_SLASH` is true and the URL does not end in a slash, it asks again with one, and if that page exists answers `HttpResponsePermanentRedirect` to the request's path with a slash, the query string dropped. `CommonMiddleware` would not: it adds a slash only when the path with one resolves in the URLconf, and the path of a flat page the middleware serves resolves nowhere ([Resolving a path](../urls/resolving.md#the-resolvers-other-callers)) (`django/contrib/flatpages/views.py:flatpage`).

Only `render_flatpage`, the inner function, is decorated with `csrf_protect`, and the comment above the views says why. The view is called from the middleware's `process_response` after a 404, which often means `CsrfViewMiddleware.process_view` has not run even where that middleware is installed, so the view needs the decorator in case its template uses `{% csrf_token %}`. But when no page matches, or a redirect is needed for authentication, the 404 must go back without any CSRF check; so only the inner function is protected. With the checks enforced, anonymous POSTs to /nowhere/ and /about got their 404 and their 301 unchecked, and one to /about/ got 403. The check for a login, though, is inside `render_flatpage`, after the decorator's: a POST to /members/ got 403 too, not the redirect to the login ([The CSRF check: `CsrfViewMiddleware.process_view`](../security/csrf-check.md)).

For a page with `registration_required` and a user who is not authenticated, `render_flatpage` returns `redirect_to_login` of the request's path, without its query string ([Requiring a login: `login_required`, `permission_required` and `LoginRequiredMiddleware`](../auth/requiring-login.md)). Otherwise a page with a `template_name` is rendered with `select_template` of that name and "flatpages/default.html", a name found nowhere falling back to the default; a page without one, with the default. The title and the content are marked safe, because, a comment says, they are raw HTML in the first place, and a template should not need the `|safe` filter for them. The view gives the template one variable, "flatpage", and the request, so the context processors add theirs (`django/contrib/flatpages/views.py:render_flatpage`).

The run added a page /pilots/, titled "Pilots & tugs", with the content `"<p>Pilots board at the <em>breakwater</em>.</p>"` and a template of its own:

```text
# templates/flatpages/notice.html
<article class="notice"><h1>{{ flatpage.title }}</h1>{{ flatpage.content }}</article>

GET /pilots/                200
<article class="notice"><h1>Pilots & tugs</h1><p>Pilots board at the <em>breakwater</em>.</p></article>
GET /about                  301  Location: /about/
GET /about?print=1          301  Location: /about/
GET /about/?print=1         200
GET /members/?page=2        302  Location: /accounts/login/?next=/members/
GET /members/, as nora      200
```

> **Trap.** The documentation warns that Django does not sanitize a flat page's HTML, that a malicious page can lead to permission escalation, and that only trusted users should add or edit pages (`docs/ref/contrib/flatpages.txt`).

## Serving flat pages from a URL pattern

The flat pages application's URLconf is one pattern, `"<path:url>"` to `flatpage`, for a project to include under a prefix (`django/contrib/flatpages/urls.py`). The view is then reached by resolving, so the `process_view` hooks run for it, `CsrfViewMiddleware`'s check among them, and a page's URL is the path after the prefix. Included under pages/, it served the page /about/ at /pages/about/, and the view redirected /pages/about to /pages/about/.

`FlatPage.get_absolute_url` reverses the view with the page's URL, without its leading slash and then with it; when neither reverses, it returns the URL after the script prefix, added by hand, a comment says, because it bypasses `reverse` (`django/contrib/flatpages/models.py:FlatPage.get_absolute_url`). The page /about/ gave /about/ with the middleware alone, and /pages/about/ with the URLconf under pages/.

Included at the root after every other pattern, the same URLconf matches every path the others did not, the root aside, and leaves `CommonMiddleware` no unresolved path to add a slash to: /bulletins/1 came back 404 from the flat-page view, where without it the answer is a redirect to /bulletins/1/. The documentation's catch-all is a regular expression that matches only a path ending in a slash (`docs/ref/contrib/flatpages.txt`); with it, /bulletins/1 was redirected again.

## `FlatpageForm` and the admin

The database does not stop two pages from having one URL on one site; `FlatpageForm`, the admin's form for flat pages, does. Its `url` field is a `RegexField` of letters, digits, dots, underscores, hyphens, slashes and tildes; `FlatpageForm.clean_url` requires a leading slash, and a trailing one when `settings.APPEND_SLASH` is true and `MIDDLEWARE` holds "django.middleware.common.CommonMiddleware"; `FlatpageForm.clean` refuses a URL another page has on any of the chosen sites (`django/contrib/flatpages/forms.py:FlatpageForm`). Bound in the run:

```text
"/about/"            site 1   Flatpage with url /about/ already exists for site harbour.example
"/about/"            site 2   valid
"about/"             site 1   URL is missing a leading slash.
"/contact"           site 1   URL is missing a trailing slash.
"/harbour master/"   site 1   This value must contain only letters, numbers, dots, underscores, dashes, slashes or tildes.
```

`FlatPageAdmin` uses the form, and puts `registration_required` and `template_name` in a collapsed fieldset of advanced options (`django/contrib/flatpages/admin.py:FlatPageAdmin`).

## The tag `get_flatpages`

The application's template library has one tag, `get_flatpages`, which puts a queryset of flat pages into the context under the name after "as" ([Libraries: `Library`, custom tags and `{% load %}`](../templates/libraries.md)). `FlatpageNode.render` takes the site from the request in the context, through `get_current_site`, or else from `SITE_ID`; keeps the pages whose URL starts with the prefix, if a string or a variable gives one; and keeps only those without `registration_required` unless the tag names, after "for", a user who is authenticated. It never looks at the request's user (`django/contrib/flatpages/templatetags/flatpages.py:FlatpageNode.render`):

```text
{% get_flatpages as pages %}             anonymous: /about/ /pilots/
                                         nora:      /about/ /pilots/
{% get_flatpages for user as pages %}    anonymous: /about/ /pilots/
                                         nora:      /about/ /members/ /pilots/
```

`FlatPageSitemap` lists for a sitemap the pages without `registration_required` of the site `SITE_ID` names, asking `SiteManager.get_current` without a request (`django/contrib/flatpages/sitemaps.py:FlatPageSitemap.items`) ([Sitemaps: `Sitemap` and the sitemap views](sitemaps.md)).
