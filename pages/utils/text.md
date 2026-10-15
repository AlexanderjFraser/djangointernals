---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Text helpers: `Truncator` and `django/utils/text.py`

`django/utils/text.py` holds the text helpers that Django's filters, models, forms, storage and middleware share: `Truncator`, which cuts text to a number of characters or words, plain or as HTML; `slugify` (`django/utils/text.py:slugify`), `get_valid_filename`, `capfirst` and `get_text_list`; the splitting of a template tag's arguments; and the gzip compression of `GZipMiddleware`. Beside it, `django/utils/xmlutils.py` has `SimplerXMLGenerator`, the serializer's and the feeds' XML writer.

`capfirst`, `wrap`, `get_valid_filename`, `get_text_list`, `normalize_newlines`, `phone2numeric`, `unescape_string_literal` and `slugify` are decorated with `keep_lazy_text`: with plain arguments the function runs at once; given a `Promise` among them, it returns a lazy value that runs the function each time it is used (`django/utils/functional.py:keep_lazy`). So a form field's label, made by `capfirst` from a model field's lazily translated verbose name, is translated when shown (`django/db/models/fields/__init__.py:Field.formfield`). The module also defines `format_lazy`, a lazy `str.format`; both are told in [Lazy values: `lazy`, `Promise` and `keep_lazy`](lazy.md).

## `Truncator`

`Truncator` is a `SimpleLazyObject` whose function makes the text a string: making one does nothing with the text (`django/utils/text.py:Truncator`). `Truncator.chars` and `Truncator.words` each begin by calling `SimpleLazyObject._setup` themselves, so the string is made again at every call. The four truncating filters make one for each value ([The built-in filters](../templates/filters.md)) (`django/template/defaultfilters.py:truncatechars`), as do the admin's raw-id widget and `migrate --plan` (`django/core/management/commands/migrate.py:Command.describe_operation`).

### Characters, words and the truncation text

What marks a cut is the **truncation text**. By default it is the format "%(truncated_text)s…", translated with `pgettext` under the context "String to return when truncating text", so a translation decides where the mark goes. One given that holds "%(truncated_text)s" is used as a format in the same way; any other is appended to the cut text, unless that text already ends with it (`django/utils/text.py:add_truncation_text`).

`chars` first normalizes the text to NFC, so that a letter and its accent become one character where Unicode has one; the plain count skips a combining character left over. `calculate_truncate_chars_length` subtracts the truncation text's own characters from the length asked for, so a cut result, mark included, is that long unless the mark alone is longer (`django/utils/text.py:Truncator._text_chars`). `words` splits at white space and joins the words it keeps with single spaces, so it loses the text's line breaks even when nothing is cut (`django/utils/text.py:Truncator._text_words`).

```python
# harbour/office/board.py
DESCRIPTION = (
    "Endeavour, a bark of 366 tons out of Valletta, carries cargo "
    "and passengers between the islands."
)
DESCRIPTION_HTML = (
    "<p>Endeavour, a <b>bark</b> of 366 tons out of Valletta, carries "
    "<i>cargo &amp; passengers</i> between the islands.</p>"
)
```

```text
# a run of the example: a ship's description, cut
Truncator(DESCRIPTION).chars(30)                        'Endeavour, a bark of 366 tons…'
Truncator(DESCRIPTION).chars(30, truncate=" [more]")    'Endeavour, a bark of 36 [more]'
Truncator("Endeavour\n  of   Valletta").words(9)        'Endeavour of Valletta'
```

### As HTML

With `html=True` the text is fed to an `html.parser.HTMLParser`, a `TruncateCharsHTMLParser` or a `TruncateWordsHTMLParser`, and only the text between tags is counted (`django/utils/text.py:TruncateHTMLParser`). A start tag is copied as written and, unless it is a void element such as `"br"` (`django/utils/html.py:VOID_ELEMENTS`), pushed on a stack of open tags. An end tag other than a void element's is written out, and pops the stack only when it closes the tag opened last. When the count runs out inside a run of text, the parser writes the part that fits and the truncation text, stops, and closes every tag still open, the latest first (`django/utils/text.py:TruncateHTMLParser.feed`).

The parser decodes the text and writes it through `html.escape`, so even a fragment shorter than the length comes out escaped afresh: an apostrophe comes back as a character reference. And the words' parser counts the pieces of each run of text, so white space standing alone between two tags is a word (`django/utils/text.py:TruncateWordsHTMLParser.process`):

```text
# a run of the example: the description as HTML
Truncator(DESCRIPTION_HTML).chars(60, html=True)
    '<p>Endeavour, a <b>bark</b> of 366 tons out of Valletta, carries <i>carg…</i></p>'
Truncator(DESCRIPTION_HTML).words(5, html=True)
    '<p>Endeavour, a <b>bark</b> of 366…</p>'
Truncator("<p>Endeavour's crew</p>").chars(100, html=True)
    '<p>Endeavour&#x27;s crew</p>'
Truncator("<ul>\n<li>Endeavour</li>\n<li>Beagle</li>\n</ul>").words(2, html=True)
    '<ul>\n<li>Endeavour</li>…</ul>'
```

The line break after the list's opening tag was the first word.

## Slugs

`slugify` makes a slug, lower-case words joined by hyphens for a URL (`django/utils/text.py:slugify`). Unless `allow_unicode=True` is given, it decomposes the text by NFKD and drops every character outside ASCII, so an accent falls off its letter and a letter of another script disappears; with it, the text is composed by NFKC and keeps its letters. It then lowers the case, removes everything but letters, digits, underscores, white space and hyphens, turns each run of white space and hyphens into one hyphen, and strips hyphens and underscores from the ends. Within Django only the template filter of the same name calls it (`django/template/defaultfilters.py:slugify`).

```text
# a run of the example: a voyage's title, TITLE = "Valletta to Πειραιάς, via Mílos"
slugify(TITLE)                        'valletta-to-via-milos'
slugify(TITLE, allow_unicode=True)    'valletta-to-πειραιάς-via-mílos'
slugify("Πειραιάς")                   ''
```

## File names, lists and capitals

`get_valid_filename` makes a name fit to be a file's: it strips the ends, turns spaces into underscores and removes every character but letters, digits, `"-"`, `"_"` and `"."`, so unlike `slugify` it keeps the case and the dots, and every script, which `slugify` keeps only with `allow_unicode=True`. A result that is empty, `"."` or `".."` raises `SuspiciousFileOperation` (`django/utils/text.py:get_valid_filename`). It is what `Storage.get_valid_name` does unless a storage overrides it ([File storage: `Storage`, `FileSystemStorage` and `storages`](../services/storage.md)).

`capfirst` returns a false value as it is, makes anything else a string, and upper-cases its first character (`django/utils/text.py:capfirst`). Django calls it mostly on verbose names: `Field.formfield` makes a form field's label with it, `Model.unique_error_message` and `Model.date_error_message` the names in their messages (`django/db/models/fields/__init__.py:Field.formfield`, `django/db/models/base.py:Model.unique_error_message`), and the admin and the authentication app their labels, titles and prompts. The template filter `capfirst` is a function of its own (`django/template/defaultfilters.py:capfirst`).

`get_text_list` joins items into a phrase, "a, b or c". The separator is translated with `gettext` and the last word defaults to a lazy translation of "or", so both are in the language active when the function runs (`django/utils/text.py:get_text_list`). `Model.unique_error_message` names the fields of a unique set with it, and the template parser the end tags it expected (`django/template/base.py:Parser.invalid_block_tag`).

```text
# a run of the example
get_valid_filename("Endeavour's log, 1768.pdf")     'Endeavours_log_1768.pdf'
get_valid_filename("..")                            SuspiciousFileOperation: Could not derive file name from '..'
get_text_list(["Piraeus", "Valletta", "Mílos"])     'Piraeus, Valletta or Mílos'
  the same, with "zh-hans" active                   'Piraeus，Valletta 或 Mílos'
```

## Splitting, wrapping and the smaller helpers

`smart_split` splits text at white space but keeps a quoted phrase whole, quotes and escapes included, and `unescape_string_literal` takes the quotes off such a phrase, raising `ValueError` for text that is not one (`django/utils/text.py:smart_split`). `Token.split_contents` splits a template tag's contents with the first, and a template variable that is a quoted literal is read with the second (`django/template/base.py:Token.split_contents`; [From text to nodes: the lexer and the parser](../templates/compiling.md)); the admin splits a search term with both, keeping a quoted phrase one term (`django/contrib/admin/options.py:ModelAdmin.get_search_results`).

`wrap` wraps text to a width with `textwrap.TextWrapper`, keeping the line breaks already there and never breaking a long word, so a line can be longer than the width; it is the `wordwrap` filter's (`django/utils/text.py:wrap`). `normalize_newlines` turns "\r\n" and "\r" into "\n" for `linebreaks` and the `linebreaksbr` filter. `phone2numeric` turns letters into keypad digits for its filter. `camel_case_to_spaces` turns a class's name into lower-case words, a model's default verbose name ([The options: what a model keeps as `_meta`](../models/options.md)). And `django/utils/lorem_ipsum.py` makes the placeholder Latin of `{% lorem %}` ([The built-in tags](../templates/tags.md)).

## Compressing a response

`compress_string` compresses bytes with gzip, and `compress_sequence` and `acompress_sequence` an iterator and an asynchronous iterator, yielding the header first and then what each item adds (`django/utils/text.py:compress_sequence`). Given `max_random_bytes`, they write a file name in the header, a run of the byte "a" of a random length below that number, so the compressed length varies; without it, the same bytes, or the same items, always compress to the same output, since all three write 0 as the header's time (`django/utils/text.py:compress_string`). `GZipMiddleware` passes its `GZipMiddleware.max_random_bytes`, 100 (`django/middleware/gzip.py:GZipMiddleware.process_response`). The documentation's reason: compression may expose a site to attacks such as BREACH, and adding a random number of bytes to each response, a technique called Heal The Breach, makes them less effective (`docs/ref/middleware.txt`, `docs/releases/4.2.txt`).

## The XML writer

`SimplerXMLGenerator` is the standard library's `xml.sax.saxutils.XMLGenerator` with a shortcut, `SimplerXMLGenerator.addQuickElement`, for an element with text and no children (`django/utils/xmlutils.py:SimplerXMLGenerator`). Text or an attribute's value holding a control character XML 1.0 does not allow, any below 0x20 but tab, line feed and carriage return, raises `UnserializableContentError`, a `ValueError`. And the attributes are written sorted by name, for a deterministic output. Its users are the XML serializer, which raises a `ValueError` naming the object in its place ([Serialization: `serialize`, `deserialize` and `DeserializedObject`](../services/serializers.md)), and the RSS and Atom feeds ([Content types, static files and the other contrib apps](../contrib.md)).
