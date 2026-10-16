---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Comparing HTML, XML and JSON: `assertHTMLEqual` and `parse_html`

`SimpleTestCase.assertHTMLEqual` and `SimpleTestCase.assertInHTML` compare markup by its structure, not its characters: `parse_html` turns each string into a tree of `Element` objects, normalised as it is built, and the assertions compare or count the trees. `compare_xml` does the like for `SimpleTestCase.assertXMLEqual`, and `SimpleTestCase.assertJSONEqual` compares what `json.loads` makes of its first argument with its second, parsed too if a string.

One piece of markup has many spellings: attributes in any order and either quote, `"<br>"` or `"<br/>"`, `"&#39;"` or `"&#x27;"`, lines broken between tags, attributes or words. A page compared character by character fails on edits no reader sees. The docstring of `parse_html` gives the aim, a structure "that can be easily compared against other HTML on semantic equivalence" (`django/test/html.py:parse_html`). In places the normalisation forgives more than a browser would. Every assertion here passes:

```python
# harbour/office/tests/test_markup.py
from django.test import SimpleTestCase, TestCase

from harbour.fleet.models import Port, Ship


class MarkupRuleTests(SimpleTestCase):
    def test_equal_writings(self):
        self.assertHTMLEqual('<li class="ship moored">Endeavour</li>', "<li class='moored ship'>\n  Endeavour\n</li>")
        self.assertHTMLEqual("<input checked>", '<input checked="checked">')
        self.assertHTMLEqual("<p><b>366</b> tons</p>", "<p><b>366</b>tons</p>")
        self.assertHTMLEqual("<ul><li>Endeavour</ul>", "<ul><li>Endeavour</li></ul>")


class ShipMarkupTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        valletta = Port.objects.create(name="Valletta", country="Malta")
        cls.endeavour = Ship.objects.create(name="Endeavour", tonnage=366, home=valletta)

    def test_list_items(self):
        page = self.client.get("/ships/").content.decode()
        url = f"/ships/{self.endeavour.pk}/"
        self.assertInHTML(f'<li><a href="{url}">Endeavour</a>, 366 tons, of Valletta</li>', page, count=1)
        self.assertInHTML("Endeavour", page)
        self.assertNotInHTML("366 tons", page)

    def test_json(self):
        response = self.client.get(f"/ships/{self.endeavour.pk}.json")
        self.assertJSONEqual(response.content, {"home": "Valletta", "name": "Endeavour", "tonnage": 366})
```

## Parsing: `parse_html`

`parse_html` feeds the string to a `Parser`, a subclass of `html.parser.HTMLParser` that keeps a root and a stack of the elements still open (`django/test/html.py:Parser`). A start tag makes an `Element`, appends it to the innermost open element, or the root, and pushes it on the stack unless its name is in `VOID_ELEMENTS`, the elements without content (`django/utils/html.py:VOID_ELEMENTS`). A self-closing tag is a start tag and, unless the element is void, its end tag, so `"<p/>"` is `"<p></p>"`. Text goes to the innermost open element. Comments, the doctype and processing instructions go to the standard parser's methods, which do nothing; character references arrive as characters, except in raw text such as a script's.

An end tag pops the stack until it has popped an element of its own name, closing whatever it passes (`django/test/html.py:Parser.handle_endtag`). So a missing end tag is forgiven, `"<ul><li>Endeavour</ul>"` parsing as though `"</li>"` were there, and an element still open at the end of the string is closed by it. An end tag that matches nothing open raises `HTMLParseError` with the tag and the parser's position, its column counted from zero.

`parse_html` then finalises the tree and returns the root's only child where the root holds one element and no text; otherwise the `RootElement`, a nameless element that prints as its children (`django/test/html.py:RootElement`).

## What the tree keeps: `Element`

An `Element` is a name, a sorted list of attributes, and a list of children, each an element or a string; two are equal when their names, attributes and children, in order, are (`django/test/html.py:Element.__eq__`).

**Attributes** pass through `normalize_attributes` and are sorted, so their order does not count (`django/test/html.py:Element.__init__`, `django/test/html.py:normalize_attributes`). The value of `"class"` is split, sorted and joined again, so that, its comment says, the order of the classes does not matter. An attribute in `BOOLEAN_ATTRIBUTES`, a set of boolean attributes its comment takes from the HTML standard, loses its value when that is empty or its own name: `"<input checked>"` equals `'<input checked="checked">'` but not `'<input checked="yes">'`. Any other attribute without a value is given `""`.

> **Trap.** The set spells one entry `"defer "`, with a space, so `"defer"` is not boolean: `"<script defer>"` equals `'<script defer="">'` but not `'<script defer="defer">'`.

**Text** is normalised as it is appended (`django/test/html.py:Element.append`): each run of ASCII white space becomes one space, and neighbouring text is joined. Text of white space alone is dropped when an element follows it, and `Element.finalize` strips every piece of text at both ends. So white space inside a run of text counts as one space, and at a run's edge not at all, even beside an inline element, where a browser shows it: `"<p><b>366</b> tons</p>"` equals `"<p><b>366</b>tons</p>"`. Of dropping white space between elements, the comment in `Element.append` concedes that it can misrepresent the document, white space between inline tags being significant.

## The assertions

`assertHTMLEqual` parses each side through `assert_and_parse_html`, which turns a parse error into a failure naming the argument, and fails when the trees differ, showing both, each cut past 80 characters, and a `difflib.ndiff` of their lines unless it is longer than `unittest.TestCase.maxDiff` (`django/test/testcases.py:SimpleTestCase.assertHTMLEqual`). The lines are those of `Element.__str__`, which breaks the line after the start tag and before the end tag of an element with children, and writes one without as its start tag alone, so the diff is of the normalised trees. `SimpleTestCase.assertHTMLNotEqual` is the converse. Two failures:

```python
# harbour/office/tests/test_markup_fail.py
from django.test import SimpleTestCase


class MarkupFailureTests(SimpleTestCase):
    def test_mismatch(self):
        self.assertHTMLEqual('<p class="tonnage">366 tons</p>', '<p class="tonnage">\n  368 tons\n</p>')

    def test_stray_end_tag(self):
        self.assertHTMLEqual("<p>Endeavour</li>", "<p>Endeavour</p>")
```

The run, cut to the two messages:

```text
$ python manage.py test harbour.office.tests.test_markup_fail
...
AssertionError: <p class="tonnage">
366 tons
</p> != <p class="tonnage">
368 tons
</p>
  <p class="tonnage">
- 366 tons
?   ^

+ 368 tons
?   ^

  </p>
...
AssertionError: First argument is not valid HTML:
('Unexpected end tag `li` (Line 1, Column 12)', (1, 12))
```

`assertInHTML` parses both and counts the needle in the haystack with `Element.count` (`django/test/html.py:Element._count`). An element equal to the needle counts once and is not searched further; any other is searched child by child, and a needle of several elements, a `RootElement`, also matches a run of consecutive children, though after a partial match the scan does not retry the child that broke it: `"<li>A</li><li>B</li>"` is not found in `"<li>A</li><li>A</li><li>B</li>"`. A needle of text alone matches only an element whose whole content is that text: in the example `"Endeavour"`, the whole text of its link, is found, and `"366 tons"`, part of ", 366 tons, of Valletta", is not. With `count=None` one match is enough, and otherwise the number must be exact; `SimpleTestCase.assertNotInHTML` (5.1) asks for none (`django/test/testcases.py:SimpleTestCase.assertInHTML`). `SimpleTestCase.assertContains` with `html=True` parses and counts the same way ([Assertions on a response: `assertContains`, `assertRedirects` and `assertTemplateUsed`](response-assertions.md)).

## XML: `compare_xml`

`assertXMLEqual` and `SimpleTestCase.assertXMLNotEqual` hand both strings to `compare_xml` (`django/test/utils.py:compare_xml`). Each string is stripped, and a backslash followed by an n becomes a line break. Unless the first begins with an XML declaration, both are wrapped in a root element, so that a fragment of sibling elements parses. Both are parsed by `xml.dom.minidom.parseString`, and from the first node that is not a comment, a document type or a processing instruction, elements are compared by tag name, text, attributes as a dictionary, and child elements in order; comments inside are not read.

The text is held more strictly than in HTML: an element's text is its own text nodes joined, and only runs of two or more spaces, tabs or line feeds become one space. A single line break stays, and white space at either end counts, so `"<ship>\n  <name>Endeavour</name>\n</ship>"` does not equal the same document on one line.

## JSON: `assertJSONEqual`

`assertJSONEqual` parses its first argument with `json.loads`, which takes bytes as well as a string, and its second only if it is a string, so the example can pass a dictionary (`django/test/testcases.py:SimpleTestCase.assertJSONEqual`). Then `unittest.TestCase.assertEqual` compares them. `SimpleTestCase.assertJSONNotEqual` is its converse.
