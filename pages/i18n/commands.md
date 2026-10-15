---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Making catalogues: makemessages and compilemessages

makemessages collects the messages that a project's Python files, templates and JavaScript mark for translation into a `.po` file for each locale, and compilemessages compiles each `.po` file into the `.mo` catalogue Django reads. Both drive the GNU gettext programs; Django adds the choice of files and of where their messages go, and `django.utils.translation.templatize`, which rewrites a template as something xgettext can read.

A catalogue passes through three files. xgettext reads source files and writes a template of their messages, a `.pot` file, with every translation empty; msgmerge merges the template into a locale's `.po` file, keeping what translators wrote there; msgfmt compiles the `.po` file into the `.mo` file. Each runs as a child process through `popen_wrapper` (`django/core/management/utils.py:popen_wrapper`). A command first looks for each on PATH with `find_command`, and stops with a `CommandError` asking for GNU gettext 0.19 or newer when one is missing; the version is not checked (`django/core/management/commands/makemessages.py:check_programs`).

## makemessages, in order

The command's `Command.handle` works in this order (`django/core/management/commands/makemessages.py:Command.handle`):

1. It checks the options. The domain, `--domain`, is `"django"`, the default, or `"djangojs"`; the extensions are those of `--extension`, else `"html"`, `"txt"` and `"py"`, or `"js"` for `"djangojs"`. One of `--locale`, `--exclude` and `--all` is required.
2. It settles the **locale directories**, where the `.po` files go, and the default among them.
3. It settles the locales: with `--all`, each directory under the default locale directory whose name begins with two lower-case letters, `--exclude` ignored; otherwise those of `--locale`, or that list when only `--exclude` is given, less those of `--exclude`.
4. It looks for msguniq, msgmerge and msgattrib, if there are locales, and xgettext.
5. `Command.build_potfiles` writes a `.pot` file into each locale directory that receives messages.
6. For each locale, it checks the name and writes a `.po` file under each `.pot` file's directory.
7. It deletes the `.pot` files, after an error too, unless `--keep-pot` is given.

In the `"django"` domain a file not ending `.py`, a `.js` file added with `--extension` too, is read as a template (`django/core/management/commands/makemessages.py:BuildFile.is_templatized`).

## Where the messages go

A locale directory holds a directory for each locale, as `"locale/nl/LC_MESSAGES/"`. Run in a directory that has `"conf/locale"`, as Django's own package does, makemessages starts with that one candidate; otherwise with the directories of `LOCALE_PATHS`, then a `locale` directory where it runs. The first is the default, made if missing (`django/core/management/commands/makemessages.py:Command.handle`). makemessages sets `BaseCommand.requires_settings` false; run without settings, it has no `LOCALE_PATHS` and skips neither `MEDIA_ROOT` nor `STATIC_ROOT`.

`Command.find_files` walks the tree from where the command runs, passing over what matches an ignore pattern (those of `--ignore`, and `"CVS"`, `".*"`, `"*~"` and `"*.pyc"` unless `--no-default-ignore` is given) and the directories `MEDIA_ROOT` and `STATIC_ROOT` name. Each `locale` directory it meets goes to the front of the candidates and is not descended into. A file goes to the first candidate whose parent directory's path begins its own directory's path: as the walk goes downwards, the nearest `locale` directory above it, though a file in an `"office2/"` would go to `"office/locale/"` too. So the office's files go to `"office/locale/"`. A file with none above it goes to the default; with no default, a message in it stops the command with a `CommandError` (`django/core/management/commands/makemessages.py:Command.find_files`).

> **Trap.** `--all` reads its locales from the default locale directory, before the walk. Run at the harbour project's root, with no `LOCALE_PATHS` and no `locale` directory there, it finds none and updates no `.po` file, though `"office/locale/nl/"` exists; run inside `"office/"`, it finds `"nl"`.

## From files to a template of messages

`Command.process_locale_dir` handles one locale directory's files together, making a `BuildFile` for each (`django/core/management/commands/makemessages.py:Command.process_locale_dir`). A file of the `"django"` domain that is not Python is templatized: `BuildFile.preprocess` rewrites it with `django.utils.translation.templatize` and writes the result beside it, its name with `.py` added, `"arrivals.html.py"` (`django/core/management/commands/makemessages.py:BuildFile.preprocess`). One xgettext then reads the group's files, copies for templates, from a list in a temporary file. It is told the language, Python or JavaScript, and names of Django's functions, some with the place of their arguments: `"--keyword=pgettext:1c,2"` makes the first a context and the second the message. `Command.xgettext_options` adds `"--add-comments=Translators"`: as the documentation says, a comment beginning "Translators" on the line before a message appears with it in the `.po` file (`docs/topics/i18n/translation.txt`).

`BuildFile.postprocess_messages` puts each template's path back where the `#:` lines name its copy, `write_pot_file` writes the `.pot` file, the copies are deleted, and msguniq is run over each `.pot` file (`django/core/management/commands/makemessages.py:Command.build_potfiles`).

## A template rewritten as Python

`django.utils.translation.templatize` turns a Django template into text in which xgettext, reading Python, finds the template's messages (`django/utils/translation/template.py:templatize`). It cuts the template into tokens with the template engine's `Lexer` ([From text to nodes: the lexer and the parser](../templates/compiling.md)) and writes each anew. On the example's template, `"office/arrivals.html"`, it gives:

```text
BBBB BBBBXXXXXXXXX
XXX ngettext(u'One ship expected.', u'%(counter)s ships expected.', count) SSS SSSS SSSSSSSSSPPPPPPPPPPP PPPPP PPPPPPPPPXXXX
XXXX
BBB BBBB BB BBBBB  XXXXX X  XXXXXX
BBBBBBXXXXX
```

A translation tag becomes the call xgettext knows: `{% translate %}` a call of gettext, or of pgettext with a context; `{% blocktranslate %}` the same, or with `{% plural %}` a call of ngettext (npgettext with a context), written at the end tag, with its variables as `%(counter)s` and a `%` in its text doubled. The rest, but comments, goes through `blankout`, which turns each character that is not whitespace into a letter: B for a tag, X for text, F for a filter, S and P for a block's singular and plural (`django/utils/translation/template.py:blankout`). A variable outside a block leaves only its filters; a `_("…")`, in a tag, a variable or a filter's argument, is copied as it stands. The whitespace stays, so the line numbers xgettext writes are the template's, except below a `{% comment %}` with no line for translators that ends mid-line, which adds a line. `{{ title }}` left nothing: "Arrivals" is found in `"office/views.py"`, where it is marked.

A comment for translators becomes a Python comment: of a `{% comment %}` block, the lines from the last that begins "Translators"; a `{# … #}` comment beginning "Translators", unless a tag or a variable follows it on its line, when it is dropped with a `TranslatorCommentWarning`. In these lines of the harbour's berths, the first comment is kept and the second dropped, with a warning that it "wasn't the last item on the line":

```text
{# Translators: a berth with no ship in it #}
<td>{% translate "Free" context "berth" %}</td>
<td>{# Translators: a service with no charge #}{% translate "Free" context "price" %}</td>
```

## From a template of messages to each `.po` file

`Command.write_po_file` writes `<locale directory>/<locale>/LC_MESSAGES/<domain>.po` (`django/core/management/commands/makemessages.py:Command.write_po_file`). An existing file msgmerge updates in place, keeping its translations; the documentation notes that an entry may come out fuzzy, its translation inferred from strings translated before (`docs/topics/i18n/translation.txt`). A new file is the `.pot` file copied, and `Command.copy_plural_forms` puts into its header the Plural-Forms line of Django's own catalogue for the locale, where Django has one, so that it starts with its language's plural formula. With `--no-obsolete`, msgattrib then removes the obsolete messages (`docs/ref/django-admin.txt`).

makemessages takes a locale name, `"nl_BE"`, not a language code: a name it refuses, `"nl-be"` or `"NL"`, is skipped, with a line proposing the name it guesses, `"nl_BE"` or `"nl"`.

## compilemessages

compilemessages looks for msgfmt, then gathers locale directories: `"conf/locale"` and `locale` where it runs, those of `LOCALE_PATHS` when the environment names a settings module, and each `locale` directory found by walking the tree, less those `--ignore` matches; with none, it stops with a `CommandError`. It compiles the `.po` files of the locales of `--locale`, else of every one found, less those of `--exclude`; where that leaves none, of every locale, the excluded too (`django/core/management/commands/compilemessages.py:Command.handle`).

`Command.compile_messages` passes over a `.po` file whose `.mo` file is at least as new, refuses one that begins with a byte order mark, and gives up a locale directory when the first file, if it is to be compiled, is in a directory that cannot be written. Each remaining file goes to a thread pool that runs msgfmt with `"--check-format"`: the documentation shows compilemessages failing where a translation's format specifications differ from its message's (`docs/topics/i18n/translation.txt`). `--use-fuzzy` adds `"-f"`, which compiles fuzzy entries too. A failure does not stop the others; the command ends with one `CommandError` (`django/core/management/commands/compilemessages.py:Command.compile_messages`).

> **Trap.** compilemessages leaves `BaseCommand.requires_settings` true: run by django-admin with no settings module, it stops with the settings' error before its code runs ([Finding the command](../commands/finding.md)).

The `.mo` files are read when a language's translations are made ([Message catalogues: `DjangoTranslation`](catalogues.md)).
