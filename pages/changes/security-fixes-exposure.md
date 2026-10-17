---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Security fixes: disclosure, spoofing and privilege

The security fixes from Django 5.0 to this commit that keep a response from the wrong reader, a header or a log line from passing for another, and a user within their permissions: what `UpdateCacheMiddleware` stores, `ASGIRequest`'s headers, log lines, timing, file names, the admin's formsets, signed cookies, STARTTLS and GeoDjango's rasters.

Security fixes go to every supported release ([What changed](../changes.md#the-releases)); 5.2.17, 6.0.8 and 6.1.1 carry each fix here. 6.1 came out on 5 August 2026, the day after 5.2.17 and 6.0.8 (`docs/releases/6.1.txt`), with a patch for each fix of that day, the security archive says (`docs/releases/security.txt`), and 6.1.1 lists no security fix. The fixes up to 5.2.13 and 6.0.4 also went to 4.2; no later one did. The fixes of 2026 fell most on the page cache, which hands a response stored for one visitor, cookies and all, to the next whose request has the same key: they narrowed what it stores, and widened the key. Not every change of the kind came in a patch release: the development server escapes its own log line only since 6.0.

## What the page cache stores

The page cache keeps a response under a key made from its URL and the request headers its `"Vary"` names ([The page cache: `UpdateCacheMiddleware`, `FetchFromCacheMiddleware` and `cache_page`](../services/page-cache.md)); a response that depends on who asked must name that there, or not be stored. `UpdateCacheMiddleware.process_response`, which `cache_page` runs too, returns a response unstored at the first check that holds (`django/middleware/cache.py:UpdateCacheMiddleware.process_response`).

With `SESSION_SAVE_EVERY_REQUEST` true, `SessionMiddleware` set the session cookie even when nothing in it changed, without varying on `"Cookie"` unless the session was read, so a page that never read it could be stored with one visitor's cookie and served to the next (CVE-2026-35192; 5.2.14, 6.0.5). `SessionMiddleware.process_response` now adds `"Cookie"` to `"Vary"` whenever it sets or deletes the cookie, and when the session was read (`django/contrib/sessions/middleware.py:SessionMiddleware.process_response`; [`SessionMiddleware`: the cookie and the save](../auth/session-middleware.md)). Under 5.2.13 the next visitor, without a session, got the cache's copy and the first one's cookie; since 5.2.14 the view answers. Since 5.2.16 and 6.0.7 that first response is not stored at all: it sets a cookie while varying on Cookie (CVE-2026-48588).

The rest are `UpdateCacheMiddleware`'s. A response that sets a cookie while varying on `"Cookie"` is refused whatever the request carried; the refusal used to need a request with no cookies, so an unrelated cookie let one be stored (CVE-2026-48588; 5.2.16, 6.0.7). Cache-Control's `"private"`, `"no-cache"` and `"no-store"` are found whatever their case, where only a lower-case private used to be (CVE-2026-8404; 5.2.15, 6.0.6), and with a value, as `private="Set-Cookie"` (`django/utils/http.py:split_directive_names`). A `"Vary"` of `"*"` used to be stored (CVE-2026-6907; 5.2.14, 6.0.5), as did a star with white space around it (CVE-2026-48587; 5.2.15, 6.0.6); `has_vary_header` now compares stripped names (`django/utils/cache.py:has_vary_header`). A response to a request bearing `"Authorization"` was stored under a key that ignored the credential (CVE-2026-35193; 5.2.15, 6.0.6); it now varies on Authorization unless its Cache-Control has `"public"`.

The figure gives the checks in order.

```text figure=what-is-stored
With SessionMiddleware inside UpdateCacheMiddleware, on the way out:
  SessionMiddleware.process_response sets or deletes the session cookie
    -> "Cookie" added to Vary                            CVE-2026-35192

UpdateCacheMiddleware.process_response: the first that holds returns it unstored
  1  the flag FetchFromCacheMiddleware set on the request is missing or false
  2  the response is streaming, or its status is neither 200 nor 304
  3  it sets a cookie and its Vary names Cookie,
     whatever cookies the request had                    CVE-2026-48588
  4  its Cache-Control has private, no-cache or no-store,
     whatever their case                                 CVE-2026-8404
  5  its Vary holds *                                    CVE-2026-6907
     each name stripped of white space first             CVE-2026-48587
  6  no page timeout is set, and its max-age is 0

Then, for a response that passed:
  the request has Authorization and Cache-Control lacks public
    -> "Authorization" added to Vary                     CVE-2026-35193
  a timeout other than 0 and a status of 200:
    learn_cache_key stores the names in Vary, and the response is stored;
    otherwise it is returned unstored
```

*What the page cache at this commit checks before it stores a response, in the order of the code, and what is added to the response's `"Vary"` on the way; a step a fix of 2026 made or changed carries its CVE.*

## Header names, domain names and log lines

`ASGIRequest` drops every header with an underscore in its name (CVE-2026-3902; 5.2.13, 6.0.4). It writes a header into `HttpRequest.META` as WSGI does, its hyphens as underscores, so a header sent as x_forwarded_for, which a proxy stripping X-Forwarded-For let through, landed on X-Forwarded-For's key (`django/core/handlers/asgi.py:ASGIRequest.__init__`; [Making the request: `WSGIRequest` and `ASGIRequest`](../http/request.md#from-an-asgi-scope)).

`DomainNameValidator` refuses a value with a newline in it (CVE-2026-53878; 5.2.16, 6.0.7): its pattern ends at `"\Z"`, where `"$"` would match before a final newline (`django/core/validators.py:DomainNameValidator.__init__`; [Validators: `django/core/validators.py`](../forms/validators.md)). A newline let through could inject a header into a response, though `HttpResponse` refuses one in a header (`django/http/response.py:ResponseHeaders._convert_to_charset`).

A control character in a path, logged raw, can forge a line or drive a terminal. Since 5.2.2 and 5.1.10 `log_response` escapes every string argument with the `"unicode_escape"` codec, and 5.2.3 and 5.1.11 moved more response logging to it (CVE-2025-48432). At this commit `log_message` does it for `log_response` (`django/utils/log.py:log_message`; [Logging](../startup/logging.md)). The development server's own line was not: here runserver serves a request line holding the escape character, and in the repr `"\x1b"` is that character, which a terminal obeys, and `"\\x1b"` the four written for it:

```text recording=changes
runserver's log of the request line "GET /entries/\x1b[2J HTTP/1.1", answered 404
    5.2.17       '"GET /entries/\x1b[2J HTTP/1.1" 404 179'
    6.0.8        '"GET /entries/\\x1b[2J HTTP/1.1" 404 179'
    6.1.1        '"GET /entries/\\x1b[2J HTTP/1.1" 404 179'
    this commit  '"GET /entries/\\x1b[2J HTTP/1.1" 404 179'
```

Since 6.0 `WSGIRequestHandler.log_message` hands its arguments to `log_message` (`django/core/servers/basehttp.py:WSGIRequestHandler.log_message`; [The development server](../commands/runserver.md)); no 6.0 note lists the change.

## What timing and outcomes tell

A login answered sooner for some names tells which accounts exist. `ModelBackend.authenticate` hands the user, or `None`, to `check_password_with_timing_attack_mitigation`, which hashes for nothing when there is none (`django/contrib/auth/__init__.py:check_password_with_timing_attack_mitigation`; [Authenticating: `authenticate` and the backends](../auth/authenticating.md)). An unusable password ran no hasher, and so told its user apart (CVE-2024-39329; 5.0.7); `verify_password` now hashes random characters when the stored password is unusable or its hasher unknown, or the password given is `None` (`django/contrib/auth/hashers.py:verify_password`). The mod_wsgi handler hashed nothing for a name with no account (CVE-2025-13473; 5.2.11, 6.0.2), and at this commit calls the same function (`django/contrib/auth/handlers/modwsgi.py:check_password`).

A password reset whose mail failed raised, and so showed whether an address had an account (CVE-2024-45231; 5.0.9, 5.1.1); `PasswordResetForm.send_mail` now logs the failure to `"django.contrib.auth"` (`django/contrib/auth/forms.py:PasswordResetForm.send_mail`; [Password reset: `PasswordResetTokenGenerator` and the reset views](../auth/password-reset.md)).

## File names, archives and modes

`Storage.save` checks a name with `validate_file_name` as it arrives, after `Storage.get_available_name` and after `_save`, refusing an absolute name or one with `".."` among its parts (`django/core/files/storage/base.py:Storage.save`; [File storage: `Storage`, `FileSystemStorage` and `storages`](../services/storage.md)). Before 5.0.7 it checked only after `_save` had written, so a storage of a project's own could write an absolute name and then refuse it (CVE-2024-39330); Django's own were not open.

`extract`, which startproject and startapp use for a template archive, refuses a member unless `os.path.commonpath` of its path and the target is the target (`django/utils/archive.py:BaseArchive.target_filename`; [Paths and archives: `safe_join`, `safe_makedirs` and `extract`](../utils/paths.md)); a member bound for a sibling whose name begins with the target's used to pass (CVE-2025-59682; 5.1.13, 5.2.7).

`FileSystemStorage`, given a mode for directories, and `FileBasedCache` make them through `safe_makedirs` and so `makedirs`, which sets each mode with `os.chmod` after `os.mkdir` (`django/utils/_os.py:makedirs`). They used to change the process's umask for a moment, which every thread shares (CVE-2026-25674; 5.2.12, 6.0.3).

## The admin's formsets and links

A formset saves every changed form, so forged `"POST"` data can carry rows never offered. `GenericInlineModelAdmin.get_formset` gives its forms a `BaseForm.has_changed` that answers false for a new row the user may not add and for an existing one they may not change, as `InlineModelAdmin.get_formset` does (CVE-2026-4277; 5.2.13, 6.0.4) (`django/contrib/contenttypes/admin.py:GenericInlineModelAdmin.get_formset`; [Inlines: `InlineModelAdmin` and its formsets](../admin/inlines.md)). `ModelAdmin.list_editable`'s formset could create rows; `ModelAdmin._save_formset` raises `BadRequest` for a changed form whose object is new (CVE-2026-4292; 5.2.13, 6.0.4) (`django/contrib/admin/options.py:ModelAdmin._save_formset`; [The change list's columns: `list_display` and `list_editable`](../admin/list-display.md)).

`display_for_field` makes a model's URL field a link only if `URLValidator` accepts the value, whatever the field's own validators allow (`django/contrib/admin/utils.py:display_for_field`); a value with a dangerous scheme was a link (CVE-2026-15920; 5.2.17, 6.0.8).

## The salt of signed cookies

A signed cookie's salt was its name joined to the caller's salt, so two pairs could make one string, and a cookie signed for one pass for the other (CVE-2026-6873; 5.2.15, 6.0.6). The salt now carries a prefix and the given salt's length (`django/core/signing.py:_cookie_signer_salt`). A cookie signed with the old salt is still read while the setting `SIGNED_COOKIE_LEGACY_SALT_FALLBACK` is true, its default until 6.1 (`django/core/signing.py:_unsign_cookie`; [What changed in security: Content Security Policy and signing](security.md)).

## STARTTLS in the SMTP backend

With `EMAIL_USE_TLS`, a failed STARTTLS handshake in a backend failing silently left a half-made connection, which the next send used, unencrypted (CVE-2026-7666; 5.2.15, 6.0.6). `EmailBackend.open` now makes a new connection the backend's only once STARTTLS and the login have succeeded (`django/core/mail/backends/smtp.py:EmailBackend.open`; [Sending email: `mailers` and the email backends](../services/mailers.md)).

## GeoDjango's rasters

Spatial lookups took a dictionary or a string as a raster, which GDAL, by its driver, could write to disk or fetch over the network as the server's process (CVE-2026-15307; 5.2.17, 6.0.8). `GDALRaster.check_raster_lookup_value` refuses a dictionary, a string or a path with `DisallowedRasterLookup`, a `SuspiciousOperation` (`django/contrib/gis/gdal/raster/source.py:GDALRaster.check_raster_lookup_value`). `BaseSpatialField.get_prep_value` raises it for a dictionary at once, and tries a string as a `GEOSGeometry` first; if that fails, it raises `DisallowedRasterLookup` for one that begins "/vsi" or looks like JSON, and `ValueError` for any other. A `GDALRaster` passes (`django/contrib/gis/db/models/fields.py:BaseSpatialField.get_prep_value`; [Spatial fields: the geometry fields and `RasterField`](../contrib/spatial-fields.md)). The notes call it backward incompatible, and say assignments to a field are unaffected.

A `GDALRaster` made from bytes gives its in-memory file exactly their length, which `GDALRaster.vsi_buffer` reads back; it read some 32 bytes past the buffer (CVE-2026-53877; 5.2.16, 6.0.7) (`django/contrib/gis/gdal/raster/source.py:GDALRaster.__init__`).
