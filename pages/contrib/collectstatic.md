---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Collecting static files: the collectstatic command

The collectstatic command of `django.contrib.staticfiles` copies or links every file the finders list into the `"staticfiles"` storage, keeping the first file it finds for each path and passing over a file whose copy is up to date; then it gives everything it found to the storage's `post_process`, if the storage has one, and prints one line that counts what it did.

A project runs collectstatic at each deployment, over the last deployment's files. The command is made to be run again: it compares each file with its copy and copies only what has changed, and `--clear` is how it starts without the old files. It copies through a storage, which need not be on the server's disk; `--link` makes its links on the disk itself.

That storage is `staticfiles_storage`, which the command takes when it is made: a `ConfiguredStorage`, a `LazyObject` that stands for the storage `storages` makes for the alias `"staticfiles"` (`django/contrib/staticfiles/storage.py:ConfiguredStorage`) ([Lazy objects: `LazyObject` and `SimpleLazyObject`](../utils/lazy-objects.md)).

## Before collecting: checks, ignore patterns and the prompt

The collectstatic command sets `BaseCommand.requires_system_checks` to one tag, `Tags.staticfiles`, so `BaseCommand.execute` runs before it only the checks of that tag, in Django `check_finders` and `check_storages`, and no model check can stop it ([Running a command: `BaseCommand`](../commands/running.md), [Finding static files: the finders](static-finders.md)) (`django/contrib/staticfiles/management/commands/collectstatic.py:Command`).

`Command.set_options` takes the patterns of `--ignore` and, unless `--no-default-ignore` is given, adds the `ignore_patterns` of the staticfiles application's config, `StaticFilesConfig` or a project's subclass of it (`django/contrib/staticfiles/management/commands/collectstatic.py:Command.set_options`). The finders apply them as they list, to a file's name and to its path inside the directory it is listed from (`django/contrib/staticfiles/utils.py:get_files`). A prefix is not part of that path: the harbour office's legend.css, in a directory of `STATICFILES_DIRS` under the prefix charts, was kept out by `--ignore legend.css` and collected in spite of `--ignore charts/legend.css`.

`Command.handle` asks before it collects, unless `--noinput` is given, whenever the destination may hold files. When `Command.is_local_storage` finds a `FileSystemStorage` with a location, the prompt names the directory and is shown only if the directory exists and has something in it; otherwise the command does not look and, its comment says, plays safe and asks. The warning is "This will DELETE ALL FILES in this location!" with `--clear` and "This will overwrite existing files!" without; any answer but "yes" raises `CommandError`, "Collecting static files cancelled." (`django/contrib/staticfiles/management/commands/collectstatic.py:Command.handle`). The harbour office's first run, into an empty directory, asked nothing; a run into the full directory asked.

## The collection, in order

`Command.collect` does the work and returns five lists, from which `handle` makes the summary (`django/contrib/staticfiles/management/commands/collectstatic.py:Command.collect`).

1. **A link needs a local storage.** With `--link`, a storage that is not local is refused: "Can't symlink to a remote destination." `Command.local` is false when the storage's `path` raises `NotImplementedError`, as `Storage.path` does (`django/core/files/storage/base.py:Storage.path`).
2. **`--clear` empties the storage.** `Command.clear_dir` walks the storage from its root and deletes each file through it, counting each as deleted; a broken symbolic link it unlinks itself. Directories are left in place, empty.
3. **Every finder lists.** For each finder of `get_finders`, in the order of `STATICFILES_FINDERS`, `BaseFinder.list` yields each file's path with the storage it came from. When that storage's attribute `"prefix"` is not empty (`FileSystemFinder` sets it on each directory's storage), the destination path is the prefix joined to the path. The first file for a destination path goes into a dictionary, from the destination path to its source storage and path, and is copied or linked at once; a later one is counted as skipped. So the order of the finders, and of each finder's directories, decides which file is collected.
4. **The storage post-processes**, if it has a `post_process` method and `--no-post-process` was not given.

## Copied, linked or left alone

`Command.copy_file` and `Command.link_file` each begin by asking `Command.delete_file` whether a file already at the destination may stay (`django/contrib/staticfiles/management/commands/collectstatic.py:Command.delete_file`). It stays when its modified time is no earlier than the source's, both cut to the whole second (the comment cites tickets 14665 and 19540). If either storage cannot give a time, raising `NotImplementedError` or `OSError`, the file is replaced. In a local storage it is replaced, whatever its time, when it is a link and this run copies, or a copy and this run links; in another storage, which the comment calls remote, links are not relevant and only the times count. A file that stays is counted unmodified; one that goes is deleted through the storage, uncounted.

Copying opens the source through its own storage and gives it to the destination storage's `Storage.save` under the destination path ([File storage: `Storage`, `FileSystemStorage` and `storages`](../services/storage.md)). Linking makes the directories and puts at the destination a link, made by `os.symlink`, to the source's absolute path (`django/contrib/staticfiles/management/commands/collectstatic.py:Command.copy_file`, `django/contrib/staticfiles/management/commands/collectstatic.py:Command.link_file`). The harbour office's second run, after the copy of harbour.css had been dated a day back:

```text
# collectstatic --noinput --verbosity 2, on Windows: separators shown as "/",
# STATIC_ROOT and NOTES standing for the collected directory and the notes application's
Skipping 'notes/base.css' (not modified)
Skipping 'legend.css' (not modified)
...
Skipping 'img/anchor.png' (not modified)
Found another file with the destination path 'notes/base.css'. It will be ignored since only the first encountered file is collected. If this is not what you want, make sure every static file has a unique path.
Deleting 'notes/harbour.css'
Copying 'NOTES/static/notes/harbour.css'
Skipped post-processing 'gis/img/draw_line_off.svg'
...
Skipped post-processing 'img/anchor.png'
Post-processed 'gis/css/ol3.css' as 'gis/css/ol3.90ae889d12fb.css'
Post-processed 'gis/js/OLMapWidget.js' as 'gis/js/OLMapWidget.a266a5a10a4e.js'
Post-processed 'notes/base.css' as 'notes/base.932853cb9945.css'
Post-processed 'charts/legend.css' as 'charts/legend.54538fc9da40.css'
Post-processed 'notes/harbour.css' as 'notes/harbour.f60ecf1ef40a.css'

1 static file copied to 'STATIC_ROOT', 11 unmodified, 5 post-processed, 1 skipped due to conflict.
```

The finders listed the office's own notes/base.css first, so the notes application's was the conflict. A "Skipping" line names a file by its path in its source: legend.css, without its prefix.

## Post-processing

`collect` gives `post_process` the dictionary of every file found in the run, unmodified ones included, and it yields, for each file, the original path, the processed path, and whether it processed the file; the command counts the processed. `ManifestStaticFilesStorage` reads each original through its source storage, not the copy, and processes a file whose hashed copy is missing and, every time, each CSS or JavaScript file, whose references it rewrites: twelve on the first run, five on the second (`django/contrib/staticfiles/storage.py:HashedFilesMixin._post_process`) ([Static file storages: `ManifestStaticFilesStorage` and hashed names](static-storage.md)). With `--no-post-process` the storage is not asked: the files keep their names and no manifest is written.

An exception comes back in the third place. The command writes "Post-processing '…' failed!" and a blank line to standard error, and raises a `CommandError` from it whose message is the exception's, with its notes below. With `--clear --ignore notes/base.css`, which kept out both files of that path, harbour.css's `@import "base.css"` named a file not collected: the message was the `ValueError` "The file 'notes/base.css' could not be found with" the storage, and its note named harbour.css, the reference and its line. The manifest is saved only when the storage's generator runs to its end, which the raise prevented, and `--clear` had deleted the old one: the run left no staticfiles.json (`django/contrib/staticfiles/storage.py:ManifestFilesMixin.post_process`).

## The summary line and `--dry-run`

At verbosity 1 or more, `handle` returns one line, which `execute` writes: the files deleted, if `--clear` deleted any; the files copied, or "symlinked" with `--link`; "to" the directory, when the prompt could name one; and, each only when not zero, the counts unmodified, post-processed and "skipped due to conflict" (`django/contrib/staticfiles/management/commands/collectstatic.py:Command.handle`).

> **Changed in 6.0.** At verbosity 1, files skipped for a conflict and files deleted by `--clear` appear only as counts in the summary; verbosity 2 names each (`docs/releases/6.0.txt`).

`--dry-run` writes nothing. `clear_dir` and `delete_file` only say what they would delete; a copy or a link is announced at verbosity 1 as pretended; and `post_process` is called with `dry_run=True`, on which `HashedFilesMixin.post_process` does nothing and no manifest is saved (`django/contrib/staticfiles/storage.py:HashedFilesMixin.post_process`). With `--clear` the counts are not the real run's: nothing was deleted, so each copy still up to date is counted unmodified. One directory, holding the twelve files, their hashed copies and the manifest, gave:

```text
# collectstatic --noinput --clear --dry-run, then collectstatic --noinput --clear
25 static files deleted, 0 static files copied to 'STATIC_ROOT', 12 unmodified, 1 skipped due to conflict.
25 static files deleted, 12 static files copied to 'STATIC_ROOT', 12 post-processed, 1 skipped due to conflict.
```
