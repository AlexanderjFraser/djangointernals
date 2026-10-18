---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Security fixes: disclosure, spoofing and privilege

Fixes from 5.0 on that keep a response from the wrong reader, a header or log line from passing for another, and a user within their permissions: the page cache, `ASGIRequest`, login timing, file names, the admin, signed cookies, STARTTLS and rasters.

5.2.17, 6.0.8 and 6.1.1 carry each fix here. 6.1 came out on 5 August 2026, the day after 5.2.17 and 6.0.8 (`docs/releases/6.1.txt`), with a patch of its own for each fix of that day (`docs/releases/security.txt`). 6.1.1 lists no security fix. The fixes up to 5.2.13 and 6.0.4 also went to 4.2; no later one did.

## What the page cache stores

The fixes of 2026 fell most on the page cache, which keeps a response under a key made from its URL and the request headers its `"Vary"` names. They narrowed what it stores, and widened the key ([The page cache: `UpdateCacheMiddleware`, `FetchFromCacheMiddleware` and `cache_page`](../services/page-cache.md)).

With `SESSION_SAVE_EVERY_REQUEST` true, `SessionMiddleware` set the session cookie even when nothing in it changed. It then varied on `"Cookie"` only if the session was read, so a page that never read it could be stored with one visitor's cookie and served to the next (CVE-2026-35192; 5.2.14, 6.0.5). `SessionMiddleware.process_response` now adds `"Cookie"` to `"Vary"` whenever it sets or deletes the cookie, and when the session was read (`django/contrib/sessions/middleware.py:SessionMiddleware.process_response`; [`SessionMiddleware`: the cookie and the save](../auth/session-middleware.md)).

The rest are `UpdateCacheMiddleware`'s. A response that sets a cookie while varying on `"Cookie"` is refused whatever the request carried, where an unrelated cookie in the request used to let one be stored (CVE-2026-48588; 5.2.16, 6.0.7). Cache-Control's `"private"`, `"no-cache"` and `"no-store"` are found whatever their case, where `"Private"` was not (CVE-2026-8404; 5.2.15, 6.0.6). A `"Vary"` of `"*"` used to be stored (CVE-2026-6907; 5.2.14, 6.0.5), as did a star with white space around it (CVE-2026-48587; 5.2.15, 6.0.6); `has_vary_header` now compares stripped names (`django/utils/cache.py:has_vary_header`). A response to a request bearing `"Authorization"` was stored under a key that ignored the credential (CVE-2026-35193; 5.2.15, 6.0.6). It now varies on Authorization unless its Cache-Control has `"public"`.

`UpdateCacheMiddleware.process_response`, which `cache_page` runs too, returns a response unstored at the first check that holds (`django/middleware/cache.py:UpdateCacheMiddleware.process_response`). Three checks no fix changed: a request `FetchFromCacheMiddleware` did not flag on the way in, as it flags a `"GET"` or `"HEAD"` it could not answer from the cache; a response that streams, or whose status is neither 200 nor 304; and, with no page timeout, a max-age of 0. What passes is stored if its status is 200 and its timeout not 0. The figure gives the checks in order.

```text figure=what-is-stored
With SessionMiddleware inside UpdateCacheMiddleware, on the way out:
  SessionMiddleware.process_response sets or deletes the session cookie
    -> "Cookie" added to Vary                  CVE-2026-35192

UpdateCacheMiddleware.process_response: the first that holds returns it unstored
  1  the flag FetchFromCacheMiddleware set on the request is missing or false
  2  the response is streaming, or its status is neither 200 nor 304
  3  it sets a cookie and its Vary names Cookie,
     whatever cookies the request had          CVE-2026-48588
  4  its Cache-Control has private, no-cache or no-store,
     whatever their case                       CVE-2026-8404
  5  its Vary holds *                          CVE-2026-6907
     each name stripped of white space first   CVE-2026-48587
  6  no page timeout is set, and its max-age is 0

Then, for a response that passed:
  the request has Authorization and Cache-Control lacks public
    -> "Authorization" added to Vary           CVE-2026-35193
  a status of 200 and a timeout other than 0: the response is stored;
    otherwise it is returned unstored
```

*The page cache's checks at this commit, and what is added to `"Vary"`; a step a fix of 2026 made or changed carries its CVE.*

## Header names, domain names and log lines

`ASGIRequest` drops every header with an underscore in its name (CVE-2026-3902; 5.2.13, 6.0.4). Since it writes a header into `HttpRequest.META` as WSGI does, its hyphens as underscores, a header named x_forwarded_for landed on X-Forwarded-For's key, past a proxy that strips X-Forwarded-For (`django/core/handlers/asgi.py:ASGIRequest.__init__`; [Making the request: `WSGIRequest` and `ASGIRequest`](../http/request.md#from-an-asgi-scope)).

`DomainNameValidator` refuses a value with a newline in it (CVE-2026-53878; 5.2.16, 6.0.7). Its pattern ends at `"\Z"`, where `"$"` would match before a final newline (`django/core/validators.py:DomainNameValidator.__init__`; [Validators: `django/core/validators.py`](../forms/validators.md)). A newline let through could inject a header into a response, though `HttpResponse` refuses one in a header (`django/http/response.py:ResponseHeaders._convert_to_charset`).

A control character logged raw can forge a line or drive a terminal. Since 5.2.2 and 5.1.10 `log_response` escapes every string argument with the `"unicode_escape"` codec (CVE-2025-48432). At this commit `log_response` leaves the escaping to `log_message` (`django/utils/log.py:log_message`; [Logging](../startup/logging.md)).

The development server's own line went unescaped until 6.0. Since then `WSGIRequestHandler.log_message` hands its arguments to `log_message`, and no 6.0 note says so (`django/core/servers/basehttp.py:WSGIRequestHandler.log_message`; [The development server](../commands/runserver.md)). For a request line holding the escape character, 5.2.17's `"\x1b"` is the character itself, which a terminal obeys, and the later releases' `"\\x1b"` four characters:

```text recording=changes
runserver's log of the request line "GET /entries/\x1b[2J HTTP/1.1", answered 404
    5.2.17       '"GET /entries/\x1b[2J HTTP/1.1" 404 179'
    6.0.8        '"GET /entries/\\x1b[2J HTTP/1.1" 404 179'
    6.1.1        '"GET /entries/\\x1b[2J HTTP/1.1" 404 179'
    this commit  '"GET /entries/\\x1b[2J HTTP/1.1" 404 179'
```

## What timing and outcomes tell

A login answered sooner for some names tells which accounts exist. An unusable password ran no hasher, and so told its user apart (CVE-2024-39329; 5.0.7). `verify_password` now hashes random characters when the stored password is unusable or its hasher unknown, or the password given is `None` (`django/contrib/auth/hashers.py:verify_password`; [Authenticating: `authenticate` and the backends](../auth/authenticating.md)). The mod_wsgi handler hashed nothing for a name with no account (CVE-2025-13473; 5.2.11, 6.0.2). At this commit it calls `check_password_with_timing_attack_mitigation`, which hashes for nothing when there is no user (`django/contrib/auth/handlers/modwsgi.py:check_password`).

A password reset whose mail failed raised, and so showed whether an address had an account (CVE-2024-45231; 5.0.9, 5.1.1). `PasswordResetForm.send_mail` now logs the failure to `"django.contrib.auth"` (`django/contrib/auth/forms.py:PasswordResetForm.send_mail`; [Password reset: `PasswordResetTokenGenerator` and the reset views](../auth/password-reset.md)).

## File names, archives and modes

`Storage.save` checks a name with `validate_file_name` as it arrives, after `Storage.get_available_name`, and after `_save`. It refuses an absolute name or one with `".."` among its parts (`django/core/files/storage/base.py:Storage.save`; [File storage: `Storage`, `FileSystemStorage` and `storages`](../services/storage.md)). Before 5.0.7 it checked only after `_save` had written, so a storage of a project's own could write an absolute name and then refuse it (CVE-2024-39330); Django's own were not open.

`extract`, which startproject and startapp use for a template archive, refuses a member unless `os.path.commonpath` of its path and the target is the target (`django/utils/archive.py:BaseArchive.target_filename`; [Paths and archives: `safe_join`, `safe_makedirs` and `extract`](../utils/paths.md)). A member bound for a sibling whose name begins with the target's used to pass (CVE-2025-59682; 5.1.13, 5.2.7).

`FileSystemStorage`, given a mode for directories, and `FileBasedCache` make their directories through `safe_makedirs` and so `makedirs`, which sets each mode with `os.chmod` after `os.mkdir` (`django/utils/_os.py:makedirs`). Both used to change the process's umask for a moment, and every thread shares it (CVE-2026-25674; 5.2.12, 6.0.3).

## The admin's formsets and links

A formset saves every changed form, so forged `"POST"` data can carry rows never offered. `GenericInlineModelAdmin.get_formset` gives its forms a `BaseForm.has_changed` that answers false for a new row the user may not add, or an existing one they may not change, as `InlineModelAdmin.get_formset` does (CVE-2026-4277; 5.2.13, 6.0.4; `django/contrib/contenttypes/admin.py:GenericInlineModelAdmin.get_formset`; [Inlines: `InlineModelAdmin` and its formsets](../admin/inlines.md)). `ModelAdmin.list_editable`'s formset could create rows (CVE-2026-4292; 5.2.13, 6.0.4). `ModelAdmin._save_formset` raises `BadRequest` for a changed form whose object is new (`django/contrib/admin/options.py:ModelAdmin._save_formset`; [The change list's columns: `list_display` and `list_editable`](../admin/list-display.md)).

`display_for_field` makes a model's URL field a link only if `URLValidator` accepts the value, whatever the field's own validators allow (`django/contrib/admin/utils.py:display_for_field`). A value with a dangerous scheme used to be a link (CVE-2026-15920; 5.2.17, 6.0.8).

## The salt of signed cookies

A signed cookie's salt was its name joined to the caller's salt, so two pairs of name and salt could make one string, and a cookie signed for one passed for the other (CVE-2026-6873; 5.2.15, 6.0.6). The salt now carries a prefix and the given salt's length (`django/core/signing.py:_cookie_signer_salt`). The old salt is still read while the setting `SIGNED_COOKIE_LEGACY_SALT_FALLBACK` is true, its default before 6.1 (`django/core/signing.py:_unsign_cookie`; [What changed in security: Content Security Policy and signing](security.md)).

## STARTTLS in the SMTP backend

With `EMAIL_USE_TLS` and `fail_silently=True`, a failed STARTTLS handshake left a half-made connection that the next send used, unencrypted (CVE-2026-7666; 5.2.15, 6.0.6). `EmailBackend.open` now makes a new connection the backend's only once STARTTLS and the login have succeeded (`django/core/mail/backends/smtp.py:EmailBackend.open`; [Sending email: `mailers` and the email backends](../services/mailers.md)).

## GeoDjango's rasters

Spatial lookups took a dictionary or a string as a raster (CVE-2026-15307; 5.2.17, 6.0.8). GDAL could then, by its driver, write to disk or fetch over the network. `GDALRaster.check_raster_lookup_value` refuses a dictionary, a string or a path with `DisallowedRasterLookup`, a `SuspiciousOperation` (`django/contrib/gis/gdal/raster/source.py:GDALRaster.check_raster_lookup_value`). `BaseSpatialField.get_prep_value` raises it for a dictionary at once, for a string only if it fails as a `GEOSGeometry` and begins "/vsi" or looks like JSON, and never for a `GDALRaster` (`django/contrib/gis/db/models/fields.py:BaseSpatialField.get_prep_value`; [Spatial fields: the geometry fields and `RasterField`](../contrib/spatial-fields.md)).

A `GDALRaster` made from bytes gives its in-memory file exactly their length (`django/contrib/gis/gdal/raster/source.py:GDALRaster.__init__`). `GDALRaster.vsi_buffer`, which reads the file back, used to read some 32 bytes past the buffer (CVE-2026-53877; 5.2.16, 6.0.7).
