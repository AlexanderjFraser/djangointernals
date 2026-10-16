---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Assertions on a response: `assertContains`, `assertRedirects` and `assertTemplateUsed`

`SimpleTestCase` gives every Django test case assertions about what a view answered: `assertContains` and `assertNotContains` look for text in a response's body, `assertRedirects` checks a redirect and the page it leads to, `assertTemplateUsed` and `assertTemplateNotUsed` check which templates were rendered, and `assertFormError` and `assertFormSetError` check a form's errors.

The assertions differ in what they read. A status and a body are on every response, so `assertContains` works on any, the test client's or not. Which templates rendered and where redirects led are on a response only if the test client put them there: it sets them as `HttpResponseBase.templates` and, after `follow=True`, `HttpResponseBase.redirect_chain`, beside itself as `HttpResponseBase.client` and the request's arguments as `HttpResponseBase.request` ([The test client: `Client` and `ClientHandler`](client.md)). Each takes `msg_prefix="…"`, put before its own message with `": "` after it; a parse failure under `html=True` leaves it out.

The harbour office's tests of its responses:

```python
# harbour/office/tests/test_responses.py
from django.contrib.auth.models import User
from django.template.loader import render_to_string
from django.test import TestCase

from harbour.fleet.models import Port, Ship


class ShipResponseTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.valletta = Port.objects.create(name="Valletta", country="Malta")
        cls.endeavour = Ship.objects.create(name="Endeavour", tonnage=366, home=cls.valletta)
        cls.beagle = Ship.objects.create(name="Beagle", tonnage=235, home=cls.valletta)

    def test_list(self):
        response = self.client.get("/ships/")
        self.assertContains(response, "tons", count=2)
        self.assertContains(response, "<h1>Ships</h1>", html=True)
        self.assertTemplateUsed(response, "office/base.html", count=1)

    def test_detail_tonnage(self):
        response = self.client.get(f"/ships/{self.endeavour.pk}/")
        self.assertContains(response, "368 tons")

    def test_new_ship_needs_login(self):
        response = self.client.get("/ships/new/")
        self.assertRedirects(response, "/accounts/login/?next=/ships/new/")

    def test_detail_extends_base(self):
        with self.assertTemplateUsed("office/base.html"):
            render_to_string("office/ship_detail.html", {"ship": self.endeavour})

    def test_tonnage_of_zero(self):
        self.client.force_login(User.objects.create_user("nora"))
        response = self.client.post(
            "/ships/new/", {"name": "Bounty", "tonnage": 0, "home": self.valletta.pk}
        )
        self.assertFormError(
            response.context["form"], None, "Constraint “ship_has_tonnage” is violated."
        )
```

## `assertContains` and `assertNotContains`

`SimpleTestCase.assertContains` and `SimpleTestCase.assertNotContains` both call `SimpleTestCase._assert_contains`, which gets the body and counts the text in it (`django/test/testcases.py:SimpleTestCase._assert_contains`):

1. A response with a render method that has not yet rendered is rendered first. A `TemplateResponse` that came through the test client was rendered by the handler; one from a view called directly was not ([`SimpleTemplateResponse` and `TemplateResponse`](../templates/responses.md)).
2. The status is compared with `status_code=200`, or the one given, before any text is looked for: "Couldn't retrieve content: Response code was 200 (expected 404)".
3. A streaming response is read to its end, and `StreamingHttpResponse.streaming_content` is set again from a list holding the joined bytes, so a next assertion finds it again ([Streaming and file responses](../http/streaming.md)).
4. Text that is not bytes, or any text with `html=True`, is made a string and the body decoded in `HttpResponseBase.charset`; bytes are looked for in the raw body.
5. With `html=True`, both sides are parsed by `parse_html` through `assert_and_parse_html`, a parse error failing with the side that was not valid HTML, and the parsed text is counted in the parsed body ([Comparing HTML, XML and JSON: `assertHTMLEqual` and `parse_html`](html-assertions.md)).

`assertContains` passes on one occurrence or more, or with `count=2` on exactly two; `assertNotContains` on none. Their messages take the form of `unittest`'s own, "2 != 3 : …" or "False is not true : …", and end with the body as bytes. The module's run, lines left out:

```text
$ python manage.py test harbour.office.tests.test_responses
...
.F...
======================================================================
FAIL: test_detail_tonnage (harbour.office.tests.test_responses.ShipResponseTests.test_detail_tonnage)
----------------------------------------------------------------------
...
AssertionError: False is not true : Couldn't find '368 tons' in the following response
b'<!doctype html>\n<html lang="en">\n<head><title>Endeavour</title></head>\n<body>\n<main>\n<h1>Endeavour</h1>\n<p class="tonnage">366 tons</p>\n<p class="home">Home port: Valletta</p>\n</main>\n</body>\n</html>\n'
...
```

> **Changed in 6.1.** Either can be called twice on one streaming response; before, the first call used the content up (`docs/releases/6.1.txt`). The body has been in their messages since 5.1.

## `assertRedirects`

`SimpleTestCase.assertRedirects` checks that the response redirected with `status_code=302` or another given, that it led to the expected URL, and that the page there, where it is fetched or was followed, answers `target_status_code=200` (`django/test/testcases.py:SimpleTestCase.assertRedirects`).

A followed response ends the chain, and the `HttpResponseBase.redirect_chain` the test client gave it lists each redirect's URL and status. The chain must not be empty; its first status and its last URL are the ones compared, and the response's own status must be the target's. Nothing is fetched, and a request redirected twice is checked against where it ended.

A response not followed is the redirect itself: its status is compared, and its URL is `HttpResponseRedirectBase.url`, the Location header, a path not starting with `"/"` joined to the request's path. Unless `fetch_redirect_response=False`, the target is then fetched. A host in the URL must be one `validate_host` accepts from `ALLOWED_HOSTS`, such as `"testserver"`, which the test environment adds; another is a `ValueError`, not a failure, suggesting the host be added or not fetched (`django/http/request.py:validate_host`). The client that made the response then gets the path without its host, the query as a `QueryDict`, `secure=True` for https, and the `Client.extra` and `Client.headers` stored by the latest call of its methods named for HTTP methods (`django/test/client.py:Client.get`); that page must answer with the target status, as new_ship's login page did.

Both ways end in `SimpleTestCase.assertURLEqual`, which sorts the pairs of each URL's query string, parsed by `urllib.parse.parse_qsl`, and compares the rest as written: a run found new_ship's relative Location unequal to the same URL with "http://testserver" before it (`django/test/testcases.py:SimpleTestCase.assertURLEqual`).

> **Trap.** The docstring says "/path/?a=1&a=2" does not equal "/path/?a=2&a=1", but the pairs are sorted by name and value, and a run finds them equal. A parameter with an empty value is dropped: "/ships/?a=" equals "/ships/".

## `assertTemplateUsed` and `assertTemplateNotUsed`

`SimpleTestCase.assertTemplateUsed` and `SimpleTestCase.assertTemplateNotUsed` learn what rendered from `template_rendered`, which the test environment's render method sends before rendering each template of Django's own language ([The test environment: `setup_test_environment`](environment.md)). While a request runs, the test client keeps each template the signal reports, and the list becomes the response's `HttpResponseBase.templates` (`django/test/client.py:store_rendered_templates`). `assertTemplateUsed` reads their names, leaving out a template with none, as one compiled from a string. The list holds every template the request rendered, in the order each began: "office/ship_list.html", then the "office/base.html" it extends, and, on a page with a form, those of its fields and widgets. `count=1` is how many times the name is in it. An empty list fails as "No templates used to render the response", a missing name with the templates used listed (`django/test/testcases.py:SimpleTestCase._assert_template_used`). A response without `templates`, given with a name, is a `ValueError`: the method "is only usable on responses fetched using the Django test Client" (`django/test/testcases.py:SimpleTestCase._check_test_client_response`).

Given only a template name, the method returns a context manager, which checks nothing outside a `with`: `SimpleTestCase._get_template_used` takes a first argument without `templates` for the name, and no argument at all is a `TypeError` (`django/test/testcases.py:SimpleTestCase._get_template_used`). The context manager, `_AssertTemplateUsedContext`, connects its own receiver to `template_rendered` on entering, disconnects it on leaving, and checks what it heard only if the block raised nothing (`django/test/testcases.py:_AssertTemplateUsedContext`). It hears any render in the block, as the `render_to_string` of test_detail_extends_base.

> **Trap.** The context manager names a `PartialTemplate` by its template's name, `"#"` and its own; on a response, `SimpleTestCase._get_template_used` takes the partial's own name alone: for a partial row of "office/ship_rows.html", a run found "row" on the response and refused "office/ship_rows.html#row" (`django/test/testcases.py:_AssertTemplateUsedContext.rendered_template_names`, `django/test/testcases.py:SimpleTestCase._get_template_used`; [Template partials: `{% partialdef %}` and `{% partial %}`](../templates/partials.md)).

`assertTemplateNotUsed` works both ways, fails if the name is listed, and takes no count.

## `assertFormError` and `assertFormSetError`

`SimpleTestCase.assertFormError` takes a form, a field's name and the errors expected, one message or a list (`to_list`). It fails for an unbound form, which "will never have any errors", and for a field the form lacks. With `None` for the field it compares `BaseForm.non_field_errors`, otherwise the field's entry in `BaseForm.errors` or an empty list, so `errors=[]` asserts a field is clean; reading the errors validates a bound form not yet validated ([Validation: `full_clean`, `cleaned_data` and the errors](../forms/validation.md)). A difference fails through `unittest.TestCase.assertEqual`, which shows both lists (`django/test/testcases.py:SimpleTestCase._assert_form_error`). In test_tonnage_of_zero the check constraint's message is an error of the whole form.

`SimpleTestCase.assertFormSetError` also takes a form's index: `form_index=None` with a field is a `ValueError`, and an unbound formset or an index past the last form fails. An index checks that form as above; `None` checks `BaseFormSet.non_form_errors` (`django/test/testcases.py:SimpleTestCase.assertFormSetError`; [Formsets: `BaseFormSet` and the management form](../forms/formsets.md)).
