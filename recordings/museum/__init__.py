"""The project the recording of chapter 6 resolves and reverses against: a museum's URLs.

`urls.py` is the root URLconf. It includes `gallery/urls.py` twice, once for each wing of the
building, includes a list of patterns for the shop, and has one route written as a regular
expression. `converters.py` has a converter of the project's own, `views.py` the views.

Five more URLconfs each serve a particular part of the recording: `urls_languages.py` puts
some routes under a language prefix and translates one of them, `urls_members.py` is what a
middleware gives the requests of one host, `urls_mistakes.py` holds one of each mistake the
system checks look for, `urls_early.py` reverses a name while it is being imported, and
`urls_broken.py` cannot be imported at all.
"""
