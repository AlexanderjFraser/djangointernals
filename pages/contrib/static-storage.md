---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Static file storages: `ManifestStaticFilesStorage` and hashed names

The storages of `django.contrib.staticfiles`: `StaticFilesStorage`, which keeps the collected files at `STATIC_ROOT`; `HashedFilesMixin`, whose `post_process` names each file after a hash of its content and rewrites the references between files, in passes; and `ManifestFilesMixin`, which records the names in a manifest, staticfiles.json, and looks them up there. `ManifestStaticFilesStorage` is the three together, with nothing of its own.

A browser may keep a static file as long as it likes only if its URL changes with its content. So the name comes from the content, known once the file is collected; a stylesheet must name an image by its new name, which changes the stylesheet's content and so its name; and a template must get the name without hashing. `post_process`, called by collectstatic after collecting, does the first two ([Collecting static files: the collectstatic command](collectstatic.md)); the manifest does the third, since hashing at run time could, the documentation says, burden the site (`docs/ref/contrib/staticfiles.txt`).

## `StaticFilesStorage`

`StaticFilesStorage` is a `FileSystemStorage` whose location and base URL default to `STATIC_ROOT` and `STATIC_URL` ([File storage: `Storage`, `FileSystemStorage` and `storages`](../services/storage.md)). Its `__init__` calls `check_settings`, which raises `ImproperlyConfigured` for an empty base URL, media settings equal to the static ones, and, while `settings.DEBUG` is on, a `MEDIA_URL` inside `STATIC_URL` (`django/contrib/staticfiles/storage.py:StaticFilesStorage`, `django/contrib/staticfiles/utils.py:check_settings`). Without `STATIC_ROOT` a `StaticFilesStorage` is still made: since `FileSystemStorage` would fall back to `MEDIA_ROOT`, it puts the empty location back, writes URLs, and raises `ImproperlyConfigured` in `StaticFilesStorage.path` for whatever needs a file, making a `ManifestStaticFilesStorage` among them, since that reads its manifest (`django/contrib/staticfiles/storage.py:StaticFilesStorage.path`, `django/contrib/staticfiles/storage.py:ManifestFilesMixin.read_manifest`).

## Hashed names

`HashedFilesMixin.file_hash` gives the first 12 hex digits of the MD5 of the content (`django/contrib/staticfiles/storage.py:HashedFilesMixin.file_hash`). `HashedFilesMixin.hashed_name` puts the hash before the extension and keeps the name's query string and fragment. Given no content, it opens the file of that name in the storage itself, and raises `ValueError` when there is none (`django/contrib/staticfiles/storage.py:HashedFilesMixin.hashed_name`).

## The patterns and the ignored blocks

`HashedFilesMixin.patterns` pairs a glob of file names with the expressions that find references: for `"*.css"`, url(…), `@import "…"` and a source map's comment; for `"*.js"`, a source map's comment. Each is given a template that writes the reference back in one form, so `@import "base.css";` became `@import url("base.932853cb9945.css");` in harbour.css, and the expression of the blocks to ignore: comments, escape sequences and quoted strings, and in JavaScript line comments and template literals too. Setting `HashedFilesMixin.support_js_module_import_aggregation` adds expressions for JavaScript modules' imports and `export … from` (`django/contrib/staticfiles/storage.py:HashedFilesMixin.__init__`).

`HashedFilesMixin.get_ignored_blocks` finds those blocks in a file, and a match that begins strictly inside one is left alone; one that begins where a block begins is rewritten, as a source map's comment, itself a comment, needs (`django/contrib/staticfiles/storage.py:HashedFilesMixin.is_in_ignored_block`).

## Rewriting a reference: `url_converter`

`HashedFilesMixin.url_converter` makes the function each substitution calls with a match (`django/contrib/staticfiles/storage.py:HashedFilesMixin.url_converter`). It leaves the match alone when it begins in an ignored block; when the URL begins with a scheme in lower case, data: or https:, or with //; when it is an absolute path outside `STATIC_URL`; and when it has no path, as a bare fragment. Otherwise it finds the file meant: under `STATIC_URL`, by the rest of the path; a relative URL from the directory of the file being rewritten, so ../img/anchor.png in notes/harbour.css means img/anchor.png. `HashedFilesMixin._url`, with `force=True` so that `settings.DEBUG` makes no difference, gives its URL through `HashedFilesMixin._stored_name`: the name recorded so far in this collection, or else the hash of the file as it stands in the storage. Only the last segment is replaced, so a relative reference stays relative.

For a file that does not exist, the `ValueError` gets a note naming the file being rewritten, the text matched and its line. Handed a file notes/notice.css whose third line refers to ../img/buoy.png, which nothing provides, `HashedFilesMixin.post_process` yielded:

```text
# post_process's ValueError for notes/notice.css, with its note
The file 'img/buoy.png' could not be found with <django.contrib.staticfiles.storage.ManifestStaticFilesStorage object at 0x00000229BE83FED0>.
'notes/notice.css' contains this reference 'url("../img/buoy.png")' on line 
3:     background: url("../img/buoy.png");
```

## `post_process` and its passes

`HashedFilesMixin.post_process` is given every collected path with the storage and path a finder found it at, and does nothing on a dry run (`django/contrib/staticfiles/storage.py:HashedFilesMixin.post_process`). A file that matches a glob of the patterns is **adjustable**. A pass is a call of `HashedFilesMixin._post_process`, which takes the files deepest directory first and opens each where the finder found it, not the copy, which, a comment says, might be far away, on S3 for instance (`django/contrib/staticfiles/storage.py:HashedFilesMixin._post_process`). A file starts from the name recorded for it so far or, the first time, the name hashed from its original content. One that is not adjustable is saved under that name unless the name exists. An adjustable file is read as UTF-8, rewritten, and saved under a name hashed from the rewritten content; if `HashedFilesMixin.keep_intermediate_files` is true, also under the name it started from, an **intermediate file**.

The first pass goes over every file. Passes over the adjustable files follow, each rewriting the originals with the names recorded so far, until one changes no name, at most `HashedFilesMixin.max_post_process_passes`, 5. A reference to a stylesheet not yet processed gets the hash of its unprocessed copy, so a file can need another pass once the files it refers to have changed; files that refer to each other, the documentation adds, never converge. Names still changing after the last pass are yielded with a `RuntimeError`, "Max post-process passes exceeded."; errors in decoding and rewriting a file are yielded too, not raised, and collectstatic stops at the first. Files that are not adjustable are yielded during the first pass, the others at the end with their final names.

In the run, the first pass saved base.css, which refers to nothing, as notes/base.932853cb9945.css and anchor.png as img/anchor.b357a19c8762.png; harbour.css, whose original content hashes to a10e57d9c6ea, was rewritten to refer to them and saved as notes/harbour.f60ecf1ef40a.css. The second pass got the same content for both stylesheets, so the same names, and was the last.

```text figure=the-passes
HashedFilesMixin.post_process over harbour.css and the two files it refers to (the others left out)

first pass: every collected file, deepest directory first
  notes/base.css     nothing to rewrite: saved as notes/base.932853cb9945.css
  img/anchor.png     not adjustable: saved as img/anchor.b357a19c8762.png, and yielded
  notes/harbour.css  the original content hashes to a10e57d9c6ea
                     url("../img/anchor.png")  ->  url("../img/anchor.b357a19c8762.png")
                     @import "base.css"  ->  @import url("base.932853cb9945.css")
                     the rewritten content: saved as notes/harbour.f60ecf1ef40a.css

second pass: the adjustable files, rewritten again from their originals
  notes/base.css     the same content: saved as notes/base.932853cb9945.css, unchanged
  notes/harbour.css  the same content: saved as notes/harbour.f60ecf1ef40a.css, unchanged
  no name changed: no more passes; base.css and harbour.css yielded with their final names

ManifestFilesMixin.save_manifest writes the names to STATIC_ROOT/staticfiles.json
```

*The passes over harbour.css and the two files it refers to, in one run of collectstatic: the first over every file, the second over the stylesheets, which changed no name, and then the manifest.*

## A file's URL: `stored_name`

`HashedFilesMixin.url` answers through `HashedFilesMixin._url`, which hashes nothing while `settings.DEBUG` is true unless given `force=True`, and otherwise asks the storage's `stored_name` (`django/contrib/staticfiles/storage.py:HashedFilesMixin._url`).

`HashedFilesMixin.stored_name`, without a manifest, looks in the names this storage has recorded, by `HashedFilesMixin.post_process` or an earlier lookup, and otherwise works the name out from the files: it hashes the file, then the file of the hashed name, until a file's name is its own hash. The intermediate files make that chain: after collecting with a storage of `HashedFilesMixin` over `StaticFilesStorage`, a fresh one went from notes/harbour.css to the intermediate notes/harbour.a10e57d9c6ea.css, holding the rewritten content, then to notes/harbour.f60ecf1ef40a.css, which hashes to itself (`django/contrib/staticfiles/storage.py:HashedFilesMixin.stored_name`).

## The manifest: `ManifestFilesMixin`

`ManifestFilesMixin` keeps the names in a file instead, and sets `keep_intermediate_files` to false. Its `ManifestFilesMixin.manifest_name` is `"staticfiles.json"`, kept in the storage itself unless `manifest_storage=` names another. `__init__` reads it with `ManifestFilesMixin.load_manifest`: the `"paths"` and `"hash"` of a manifest of version `"1.0"` or `"1.1"`, nothing without a file, `ValueError` for anything else (`django/contrib/staticfiles/storage.py:ManifestFilesMixin.load_manifest`). It is read once, when the storage is made, and `storages` makes one storage for an alias in a process (`django/core/files/storage/handler.py:StorageHandler.__getitem__`): a server process that made its storage before collectstatic ran keeps the names it read.

`ManifestFilesMixin.post_process` empties the names, runs the passes, and, unless on a dry run, calls `ManifestFilesMixin.save_manifest`, which sorts the pairs, hashes their JSON with `HashedFilesMixin.file_hash` for the manifest's own hash, and replaces the file (`django/contrib/staticfiles/storage.py:ManifestFilesMixin.save_manifest`):

```text
# STATIC_ROOT/staticfiles.json, one line; the GIS and charts files' entries left out
{"paths": {..., "img/anchor.png": "img/anchor.b357a19c8762.png", "notes/base.css": "notes/base.932853cb9945.css", "notes/harbour.css": "notes/harbour.f60ecf1ef40a.css"}, "version": "1.1", "hash": "11564bbb3aff"}
```

> **Changed in 6.0.** The manifest's paths are written sorted, to make manifests reproducible, the release notes say.

`ManifestFilesMixin.stored_name` looks the name, without its query string and fragment, up in the manifest's names. A missing name raises `ValueError`, "Missing staticfiles manifest entry for …", while `ManifestFilesMixin.manifest_strict` is true, as by default; when it is false, the name is hashed from the file in the storage (`django/contrib/staticfiles/storage.py:ManifestFilesMixin.stored_name`). The `{% static %}` tag asks the `"staticfiles"` storage for a URL when the static files application is installed ([The libraries to load: static, i18n, l10n, tz and cache](../templates/loadable-libraries.md)).

> **Trap.** The documentation says that with `manifest_strict` false "nonexistent paths will remain unchanged" (`docs/ref/contrib/staticfiles.txt`); the code hashes whatever file has the name. In the run, such a storage gave notes/late.css, put in `STATIC_ROOT` after collecting, the URL /static/notes/late.292af459cbe0.css, of no file, and raised `ValueError` for notes/missing.css.
