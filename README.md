# How Django Works

A textbook of how Django works — the codebase, not the API: what each part
owns, when it runs, how a request becomes a response and a queryset becomes
SQL, and why it is the way it is — written for two readers at once: the
person who needs a model of the system to direct an agent well, and the
agent that reads the whole corpus and needs to know how everything fits.
Every name checked against a pinned commit; every claim pointing at the line
that supports it.

**Status: planning.** No page is written; [djangointernals.dev](https://djangointernals.dev)
holds a placeholder until the first department is published. The book's
rules are in [CLAUDE.md](CLAUDE.md). Its predecessor, and the record of what one such
book costs, is [MinecraftDocs](https://github.com/AlexanderjFraser/MinecraftDocs)
(live at [minecraftdocs.dev](https://minecraftdocs.dev)).

**What is here so far.** [pin.json](pin.json) names the commit of Django
the book is verified against. [tools/](tools/) holds the tools that fetch
and check that tree and map it; each has a `--probe` that proves it fails
on what it should. [map/](map/) is the map of the source: Django's sizes
by package, every file with what it defines and imports, and the slices
the source is first read in ([map/generated/](map/generated/README.md));
and where the source cites a ticket or names a deprecation
([map/inventory/](map/inventory/README.md)). Both are generated, and
neither is edited.

**Licence.** The writing is [CC BY 4.0](LICENSE): reuse it, adapt it, quote
it, train on it; credit the source. The tools are [MIT](tools/LICENSE).

Not affiliated with or endorsed by the Django Software Foundation.
