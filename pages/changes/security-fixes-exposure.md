---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Security fixes: disclosure, spoofing and privilege

The security fixes from Django 5.0 to this commit that keep a response from the wrong reader, a header or a name from passing for another, and a user within their permissions: what `UpdateCacheMiddleware` will store, the headers `ASGIRequest` drops, the timing of authentication, file names and modes, the admin's formsets, signed cookies, SMTP's STARTTLS and GeoDjango's rasters.

Each CVE is followed by the patch releases of 5.0 and later that carried its fix; the code at this commit has every fix.

## What the page cache stores

A page cache keeps a response under a key made from the URL and the request headers its `"Vary"` names, and gives it back, headers and all, to every later request with that key ([The page cache: `UpdateCacheMiddleware`, `FetchFromCacheMiddleware` and `cache_page`](../services/page-cache.md)). A response that depends on who asked must name that in `"Vary"`, giving each asker a key of their own, or not be stored. `UpdateCacheMiddleware.process_response`, which `cache_page` runs too, returns a response unstored at the first of its checks that holds, among them checks on the flag `FetchFromCacheMiddleware` leaves, streaming, a status other than 200 or 304 and a `"max-age"` of 0, and stores a 200 that passes them all unless its timeout is 0; the fixes of 2026 changed what it refuses and adds to `"Vary"` (`django/middleware/cache.py:UpdateCacheMiddleware.process_response`).

A response that sets a cookie while varying on `"Cookie"` is refused whatever cookies the request carried; the refusal used to need a request with no cookies, so a request with a language or a theme cookie could have a response setting a session cookie stored (CVE-2026-48588; 5.2.16, 6.0.7). With `SESSION_SAVE_EVERY_REQUEST` true, the session cookie was set on a response that did not vary on cookies when the session was not modified (CVE-2026-35192; 5.2.14, 6.0.5). `SessionMiddleware.process_response` now adds `"Cookie"` to `"Vary"` whenever it sets or deletes the cookie; standing inside `UpdateCacheMiddleware`, it hands on a response that sets a cookie and varies on `"Cookie"`, which is refused (`django/contrib/sessions/middleware.py:SessionMiddleware.process_response`; [`SessionMiddleware`: the cookie and the save](../auth/session-middleware.md)).

The directives `"private"`, `"no-cache"` and `"no-store"` are found in any case: a response marked Private was stored (CVE-2026-8404; 5.2.15, 6.0.6). `split_directive_names` lowers each name and drops its value, so `private="Set-Cookie"` counts as `"private"` (`django/utils/http.py:split_directive_names`). A `"Vary"` holding `"*"` was stored (CVE-2026-6907; 5.2.14, 6.0.5), and a `"*"` with white space around it was not recognised, `has_vary_header` not stripping it (CVE-2026-48587; 5.2.15, 6.0.6). `split_header_value` now strips every part it yields, and `has_vary_header` the name it is asked about (`django/utils/http.py:split_header_value`, `django/utils/cache.py:has_vary_header`).

A response to a request with an `"Authorization"` header was stored under a key that ignored the credential (CVE-2026-35193; 5.2.15, 6.0.6). It now varies on Authorization unless its Cache-Control has `"public"`, as RFC 9111's section 3.5 allows, the comment says (`django/middleware/cache.py:UpdateCacheMiddleware.process_response`).

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
     in any case                                         CVE-2026-8404
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

`ASGIRequest` drops every header with an underscore in its name (CVE-2026-3902; 5.2.13, 6.0.4). Written into `HttpRequest.META` as WSGI writes them, hyphens as underscores, such a name could stand for one that a proxy had stripped by its hyphenated name. Under WSGI that is the server's affair; Daphne, the release notes say, ignores them too (`django/core/handlers/asgi.py:ASGIRequest.__init__`; [Making the request: `WSGIRequest` and `ASGIRequest`](../http/request.md)).

`DomainNameValidator` refuses a value with a newline in it (CVE-2026-53878; 5.2.16, 6.0.7): its pattern ends at `"\Z"`, the string's end (`django/core/validators.py:DomainNameValidator.__init__`; [Validators: `django/core/validators.py`](../forms/validators.md)).

`log_message` writes every string it formats into the message through Python's `"unicode_escape"` codec, so a newline or other control character in a request's path reaches a log escaped (CVE-2025-48432; 5.1.10, 5.2.2, completed in 5.1.11 and 5.2.3). The notes put the escaping in `log_response`, which calls it, as does the development server (`django/utils/log.py:log_message`; [Logging](../startup/logging.md)).

## What timing and outcomes tell

A login that answers sooner for some names tells which accounts exist. `ModelBackend.authenticate` hashes the password for nothing when no user has the name, through `check_password_with_timing_attack_mitigation` ([Authenticating: `authenticate` and the backends](../auth/authenticating.md)). A user with an unusable password could still be told apart by timing (CVE-2024-39329; 5.0.7): `verify_password` now runs the default hasher once on random characters when the stored password is unusable, its hasher unknown or the password given `None` (`django/contrib/auth/hashers.py:verify_password`; [Password hashing: `make_password` and the hashers](../auth/hashers.md)). The mod_wsgi handler's `check_password` let names be told apart by timing too (CVE-2025-13473; 5.2.11, 6.0.2), and now calls the same mitigation (`django/contrib/auth/handlers/modwsgi.py:check_password`).

A password reset whose mail failed to send went unhandled, and the outcome showed whether the address had an account (CVE-2024-45231; 5.0.9, 5.1.1). `PasswordResetForm.send_mail` catches any exception from the send and logs it to `"django.contrib.auth"` (`django/contrib/auth/forms.py:PasswordResetForm.send_mail`; [Password reset: `PasswordResetTokenGenerator` and the reset views](../auth/password-reset.md)).

## File names, archives and modes

`Storage.save` checks a name with `validate_file_name` on arrival, after `Storage.get_available_name` and after `_save`: a subclass that overrode `Storage.generate_filename` without its checks could save outside its directory, though Django's own could not (CVE-2024-39330; 5.0.7) (`django/core/files/storage/base.py:Storage.save`; [File storage: `Storage`, `FileSystemStorage` and `storages`](../services/storage.md)).

`extract`, which startproject and startapp use for a template given as an archive, refuses a member unless `os.path.commonpath` of its path and the target is the target: a path into a sibling directory whose name began with the target's passed before (CVE-2025-59682; 5.1.13, 5.2.7) (`django/utils/archive.py:BaseArchive.target_filename`; [Paths and archives: `safe_join`, `safe_makedirs` and `extract`](../utils/paths.md)).

`FileSystemStorage`, when it has a mode for directories, and `FileBasedCache` make them through `safe_makedirs`, which sets the mode with `os.chmod` after each `os.mkdir`. They used to change the process's umask for a moment, which in a threaded server could reach another thread's files and directories (CVE-2026-25674; 5.2.12, 6.0.3) (`django/utils/_os.py:makedirs`, `django/core/cache/backends/filebased.py:FileBasedCache._createdir`).

## The admin's formsets and links

A formset saves every form that has changed, so forged `"POST"` data can carry rows never offered. `GenericInlineModelAdmin.get_formset` gives its forms a `BaseForm.has_changed` that answers false for an existing row the user may not change and, since this fix, for a new row they may not add, as `InlineModelAdmin.get_formset` does, so the formset never saves it (CVE-2026-4277; 5.2.13, 6.0.4) (`django/contrib/contenttypes/admin.py:GenericInlineModelAdmin.get_formset`; [Inlines: `InlineModelAdmin` and its formsets](../admin/inlines.md)). The change list's formset for `ModelAdmin.list_editable` could create rows; `ModelAdmin._save_formset` raises `BadRequest` for a changed form whose object is new (CVE-2026-4292; 5.2.13, 6.0.4) (`django/contrib/admin/options.py:ModelAdmin._save_formset`; [The change list's columns: `list_display` and `list_editable`](../admin/list-display.md)).

`display_for_field` draws a value of a `django.db.models.URLField` as a link only if `URLValidator` accepts it, and as text otherwise; a stored value with a dangerous scheme was a link in the change list and read-only fields (CVE-2026-15920; 5.2.17, 6.0.8). The field's own validators, the comment says, may allow such schemes (`django/contrib/admin/utils.py:display_for_field`).

## The salt of signed cookies

`HttpRequest.get_signed_cookie` made the salt of a cookie's signature by joining the cookie's name and the salt it was given, so two pairs could give one string, and a cookie signed for one be accepted for the other (CVE-2026-6873; 5.2.15, 6.0.6). The salt now carries a prefix and the given salt's length (`django/core/signing.py:_cookie_signer_salt`); [What changed in security: Content Security Policy and signing](security.md) tells it, with `SIGNED_COOKIE_LEGACY_SALT_FALLBACK`, which when true reads cookies signed the old way.

## STARTTLS in the SMTP backend

With `EMAIL_USE_TLS`, a STARTTLS handshake that failed could leave a half-made connection later used to send mail unencrypted, when the backend was failing silently (CVE-2026-7666; 5.2.15, 6.0.6). `EmailBackend.open` now holds a new connection aside until STARTTLS and the login have succeeded, makes it the backend's connection only then, and closes what a failed attempt left at its next call or in `EmailBackend.close` (`django/core/mail/backends/smtp.py:EmailBackend.open`; [Sending email: `mailers` and the email backends](../services/mailers.md)).

## GeoDjango's rasters

Spatial lookups took a dictionary or a string as a raster, and `GDALRaster`, depending on the driver, could then write a file or make a network request as the server's process (CVE-2026-15307; 5.2.17, 6.0.8). `GDALRaster.check_raster_lookup_value` raises `DisallowedRasterLookup`, a `SuspiciousOperation`, for a dictionary, a string or a path, and `BaseSpatialField.get_prep_value` tries a string only as a geometry, refusing it when `GEOSGeometry` cannot read it; a value wrapped in a `GDALRaster` passes, and assigning to a field is unchanged (`django/contrib/gis/gdal/raster/source.py:GDALRaster.check_raster_lookup_value`, `django/contrib/gis/db/models/fields.py:BaseSpatialField.get_prep_value`; [Spatial fields: the geometry fields and `RasterField`](../contrib/spatial-fields.md)).

A `GDALRaster` made from bytes now gives its in-memory file the bytes' length, so `GDALRaster.vsi_buffer` reads back exactly them; it could read some 32 bytes past the buffer (CVE-2026-53877; 5.2.16, 6.0.7) (`django/contrib/gis/gdal/raster/source.py:GDALRaster.__init__`, `tests/gis_tests/gdal_tests/test_raster.py:GDALRasterTests.test_vsi_buffer_length`).
