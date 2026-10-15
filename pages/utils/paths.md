---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Paths and archives: `safe_join`, `safe_makedirs` and `extract`

`django/utils/_os.py` holds Django's helpers for paths on disk: `safe_join`, which joins a name to a directory and refuses a result outside it, and `makedirs` and `safe_makedirs`, which give a mode to every directory they make. `django/utils/archive.py` unpacks a tar or zip file with `extract`, and refuses a member that would land outside its target.

Much of what Django reads or writes on disk is named from outside: a URL's path, an uploaded file's name, a template's name, the members of an archive. Joined to a directory by `os.path.join`, such a name can climb out with `..`, or replace the directory by being absolute. `safe_join` and `extract` answer alike: they work out the final path and check that it still lies under the directory.

## `safe_join`

`safe_join` joins its arguments and makes the result absolute and normal with `os.path.abspath`, which resolves `..` in the text, and does the same to the base. The result is accepted when it begins with the base followed by a separator, when it is the base itself, or when the base is a root, "/" or a drive's. Each comparison is made after `os.path.normcase`, which lowers the case on Windows, whose filesystems ignore it. Anything else raises `SuspiciousFileOperation`, whose message names both paths (`django/utils/_os.py:safe_join`).

Only the final path is judged, so a name that climbs out and back in is accepted. The separator refuses a sibling whose name begins with the base's, "media-old" beside "media". And the test is of text alone: no symbolic link is followed, so a link inside the base that points out of it passes.

```text
# a run: safe_join(MEDIA_ROOT, name), on Windows, separators shown as "/"
'ships/endeavour.jpg'             MEDIA_ROOT/ships/endeavour.jpg
'ships/../../media/beagle.jpg'    MEDIA_ROOT/beagle.jpg
''                                MEDIA_ROOT
'../settings.py'                  SuspiciousFileOperation
'../media-old/endeavour.jpg'      SuspiciousFileOperation
'/etc/passwd'                     SuspiciousFileOperation
```

Its main callers differ in what they do with a refusal:

- `FileSystemStorage.path`, through which the other methods find a file, lets it reach the caller (`django/core/files/storage/filesystem.py:FileSystemStorage.path`, [File storage: `Storage`, `FileSystemStorage` and `storages`](../services/storage.md)).
- The filesystem template loader, and the application directories loader that inherits from it, pass over a directory the name escapes, since the name may lie inside another (`django/template/loaders/filesystem.py:Loader.get_template_sources`, [Finding a template: `Engine` and the loaders](../templates/loaders.md)).
- The static file view lets it go, and the handler answers with a 400 (`django/views/static.py:serve`, [The static file view](../views/static-files.md)).
- `TemplateCommand.download` uses it to give a downloaded template a better name, which may come from the server's Content-Disposition header, and lets a refusal end the command (`django/core/management/templates.py:TemplateCommand.download`).

## `makedirs` and `safe_makedirs`

`os.makedirs` gives its mode only to the last directory it makes; the parents get the default, less the process's umask. A storage with `FILE_UPLOAD_DIRECTORY_PERMISSIONS`, or a file cache whose directories are its owner's alone, needs the mode at every level. Django's `makedirs` is a copy, its comment says, of a CPython pull request (23901) that adds `parent_mode=None`, the mode for each parent it makes; `safe_makedirs` passes one mode as both (`django/utils/_os.py:safe_makedirs`).

Django added one call to the copy: after each `os.mkdir` it sets the mode again with `os.chmod`, since, the comment says, the kernel masks `os.mkdir`'s mode with the umask, and this gives the exact mode without changing the umask, which is global state (`django/utils/_os.py:makedirs`). A directory that exists keeps its own mode. A parent that another thread makes meanwhile is passed over; when the last directory cannot be made, `exist_ok=True` is content if one is there, whatever the error's code, which may be EACCES or EROFS. The `os.chmod` reaches the parents too, so a call without a parent mode would set them to the default, 0o777, whatever the umask, though the docstring says they respect it; but Django calls `makedirs` only through `safe_makedirs`, which always passes one.

`FileSystemStorage._save` calls `safe_makedirs` with the storage's directory mode when one is set, and `os.makedirs` when not (`django/core/files/storage/filesystem.py:FileSystemStorage._save`); `FileBasedCache._createdir` makes the cache's directory with 0o700 ([The cache backends](../services/cache-backends.md)) (`django/core/cache/backends/filebased.py:FileBasedCache._createdir`).

`to_path` returns a `pathlib.Path` as it is, makes a string one, and raises `TypeError` for anything else; the template autoreloader and `GeoIP2` call it (`django/utils/_os.py:to_path`). Only Django's tests ask `symlinks_supported` whether a symbolic link can be made (`django/utils/_os.py:symlinks_supported`).

## Unpacking an archive: `extract`

`extract` opens the file as an `Archive` and unpacks it into a directory (`django/utils/archive.py:extract`). `Archive` chooses its class by the file's name in lower case: the last extension, or if that names nothing the one before, so "x.tar.gz" is found by its ".tar". A tar extension (".tar", ".tgz", ".txz" and others) gives `TarArchive`, which leaves the compression to `tarfile.open`; ".zip" gives `ZipArchive`; anything else raises `UnrecognizedArchiveFormat` (`django/utils/archive.py:Archive._archive_cls`).

`TarArchive.extract` and `ZipArchive.extract` take the members in order and do the same with each:

1. **The leading directory is dropped.** When every member's path begins with the same first part, as in an archive of one directory, that part is cut from each name, so the directory's contents land in the target itself (`django/utils/archive.py:BaseArchive.has_leading_dir`).
2. **The destination is checked.** `BaseArchive.target_filename` joins the name to the absolute target and raises `SuspiciousOperation` unless `os.path.commonpath` of the two is the target; a path on another drive of Windows is refused too (`django/utils/archive.py:BaseArchive.target_filename`).
3. **The member is written**, and a file is given the member's permission bits if they let others read it (`django/utils/archive.py:BaseArchive._copy_permissions`).

> **Why.** The check compares whole parts of the path, so a member that lands beside the target in a directory whose name begins with the target's is refused. The release notes of CVE-2025-59682 say that `extract` allowed a partial directory traversal through an archive whose paths shared a prefix with the target directory (`docs/releases/5.2.7.txt`).

A refusal ends the loop, and what was written stays. A link in a tar to a file in it is written as an ordinary file holding that file's content; one that names nothing in the archive is reported on standard output and skipped, or, when no file has come before it, reported and then the loop fails with `UnboundLocalError` (`django/utils/archive.py:TarArchive.extract`).

```text
# a run: archive.extract("harbour_template.tar.gz", "out"), members in order
#   harbour_template/manage.py-tpl
#   harbour_template/../escape.txt
#   harbour_template/project_name/settings.py-tpl
raised SuspiciousOperation: Archive contains invalid path: '../escape.txt'
on disk: out/manage.py-tpl
```

The one caller is `TemplateCommand.extract`, which startproject and startapp reach when `--template` names an archive, or a URL that downloads one ([The commands Django ships](../commands/builtin.md)). It unpacks into a new temporary directory and turns `ArchiveException` and `OSError` into a `CommandError` (`django/core/management/templates.py:TemplateCommand.extract`). `SuspiciousOperation` is neither: given the archive above, startproject raised it as it was, and left the temporary directory, holding manage.py-tpl, behind, since the removal is at the end of `TemplateCommand.handle`.
