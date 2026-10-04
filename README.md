# Django Internals

A textbook of how Django works: the codebase, not the API. What each part
owns, when it runs, how a request becomes a response and a queryset becomes
SQL, and why it is built the way it is. Read it at
[djangointernals.dev](https://djangointernals.dev).

It is written for people who need a working model of the framework and for
the agents they direct. Every class, function and setting it names exists
in Django's source at the commit in [pin.json](pin.json), and every passage
points at the code it is about; the tools in [tools/](tools/) check both.

## What is here

- [pages/](pages/): the book, as markdown. Each page is also served as it
  is, at its address with `.md` after it.
- [SPEC.md](SPEC.md): what a page is.
- [recordings/](recordings/): scripts that run Django and write down what
  happens, and their output. The chapters' flows are taken from these.
- [map/](map/): Django's source by chapter, with sizes and reading orders.
- [tools/](tools/): the gates that check every name and pointer in the
  book against the pinned source, and every link in the built site.
- [djangointernals/](djangointernals/) and [manage.py](manage.py): the
  site, a Django project that bakes the book to static files.

## Building it

```
python -m venv .venv                        Python 3.12 or later
pip install -r requirements.txt
python tools/pin.py fetch                   fetches Django at the pinned commit into reference/
pip install -e reference/django
python manage.py bake                       checks every page and writes the site to dist/
python manage.py preview                    serves it at http://127.0.0.1:8000/
```

## Corrections

If something in the book is wrong,
[open an issue](https://github.com/AlexanderjFraser/djangointernals/issues)
with the page and the line of Django's source that shows it.

## Licence

The writing is [CC BY 4.0](LICENSE): reuse it, adapt it, quote it, train on
it; credit the source. The tools are [MIT](tools/LICENSE).

Not affiliated with or endorsed by the Django Software Foundation.
