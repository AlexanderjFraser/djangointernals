"""The habits of the section "What changed in templates", release by release: what a template
renders, or how it fails, under each release (partials loaded by name, the loop's length,
`{% querystring %}` with nothing to keep and with two mappings, two dots in a variable, in a
literal and in a tag's argument, a removed filter, a method that creates rows), what the helpers
of a custom tag do with an old call, and what `format_html` and `urlize` do. Each template is
compiled by an `Engine` of the habit's own, its options at their defaults (so a variable that
cannot be resolved renders as ''), and no TEMPLATES setting is needed. Run by
recordings/changes.py under each release; _run.py says how a habit is written.
"""
from _run import configure, habit, main, tables

configure()


def engine(**templates):
    """An engine of its own, with the templates given here as the only ones it can load."""
    from django.template import Engine

    return Engine(loaders=[("django.template.loaders.locmem.Loader", templates)])


def request_for(path):
    from django.test import RequestFactory

    return RequestFactory().get(path)


# Partials and the loop

@habit("get_template(\"entries.html#row\").render(...): one partial of a template, loaded by its name")
def partial_by_name():
    from django.template import Context

    templates = engine(**{
        "entries.html": "{% partialdef row %}<li>{{ entry }}</li>{% endpartialdef %}"
                        "<ul>{% for entry in entries %}{% partial row %}{% endfor %}</ul>",
    })
    return repr(templates.get_template("entries.html#row").render(Context({"entry": "Harbour"})))


@habit("{% for entry in entries %}{{ forloop.length }}{% endfor %}, over three entries")
def forloop_length():
    from django.template import Context

    template = engine().from_string("{% for entry in entries %}{{ forloop.length }}{% endfor %}")
    return repr(template.render(Context({"entries": ["Harbour", "Quay", "Pier"]})))


# {% querystring %}

@habit("{% querystring %}, on a request for /entries/ with no query string")
def querystring_with_nothing_to_keep():
    from django.template import RequestContext

    template = engine().from_string("<a href=\"{% querystring %}\">")
    return repr(template.render(RequestContext(request_for("/entries/"))))


@habit("{% querystring first second %}, given two mappings, {\"year\": \"2026\"} and {\"page\": \"2\"}")
def querystring_with_two_mappings():
    from django.template import RequestContext

    template = engine().from_string("<a href=\"{% querystring first second %}\">")
    context = RequestContext(request_for("/entries/"), {"first": {"year": "2026"}, "second": {"page": "2"}})
    return repr(template.render(context))


# Two dots in a row

@habit("{{ entry..title }}: two dots in a variable")
def two_dots_in_a_variable():
    from django.template import Context

    template = engine().from_string("{{ entry..title }}")
    return repr(template.render(Context({"entry": {"title": "Harbour"}})))


@habit("{{ \"a..b\" }}: two dots in a string literal")
def two_dots_in_a_literal():
    from django.template import Context

    return repr(engine().from_string("{{ \"a..b\" }}").render(Context()))


@habit("{% if entry..title %}yes{% else %}no{% endif %}: two dots in a tag's argument")
def two_dots_in_a_tag():
    from django.template import Context

    template = engine().from_string("{% if entry..title %}yes{% else %}no{% endif %}")
    return repr(template.render(Context({"entry": {"title": "Harbour"}})))


# Removed, and not called

@habit("{{ entries|length_is:3 }}, over three entries")
def length_is():
    from django.template import Context

    template = engine().from_string("{{ entries|length_is:3 }}")
    return repr(template.render(Context({"entries": ["Harbour", "Quay", "Pier"]})))


@habit("{{ entries.create }}, given Entry.objects: a method that creates a row")
def manager_create_in_a_template():
    from django.template import Context
    from journal.models import Entry

    tables()
    # Called, create() with no values would fail on the NOT NULL date and raise.
    return repr(engine().from_string("{{ entries.create }}").render(Context({"entries": Entry.objects})))


# The helpers of a custom tag

@habit("parse_bits(parser, bits, params, varargs, varkw, defaults, kwonly, kwonly_defaults, takes_context, name)")
def parse_bits_with_takes_context():
    from django.template.base import Parser
    from django.template.library import parse_bits

    args, kwargs = parse_bits(Parser([]), ["3"], ["context", "number"], None, None, None, [], None, True,
                              "page_link")
    return repr(([str(arg) for arg in args], kwargs))


@habit("@register.simple_tag(takes_context=True) on def page_link(number): the decoration")
def simple_tag_without_context():
    from django.template import Library

    register = Library()

    def page_link(number):
        return f"?page={number}"

    register.simple_tag(takes_context=True)(page_link)
    return "accepted"


# Safe HTML and links

@habit("format_html(\"<b>journal</b>\"): given nothing to format")
def format_html_without_arguments():
    from django.utils.html import format_html

    return format_html("<b>journal</b>")


@habit("urlize(\"journal.example.com\"): the scheme assumed for a bare domain")
def urlize_bare_domain():
    from django.utils.html import urlize
    return urlize("journal.example.com")


@habit("urlize(\"journal.example.com\") under the setting URLIZE_ASSUME_HTTPS = True")
def urlize_bare_domain_assuming_https():
    from django.test import override_settings
    from django.utils.html import urlize

    with override_settings(URLIZE_ASSUME_HTTPS=True):
        return urlize("journal.example.com")


main()
