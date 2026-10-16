---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The test environment: `setup_test_environment`

`setup_test_environment` prepares the process for a test run: it adds `"testserver"` to `ALLOWED_HOSTS`, sets `settings.DEBUG`, points every mailer at the local-memory email backend, and makes every render of a Django template send `template_rendered`. `teardown_test_environment` puts back what it saved.

A project's settings are written for a server: its hosts, perhaps debugging, a mail server. A test must not send mail, must not be refused for the host the test client invents, and must be able to ask which templates a view rendered. A function in `django/test/utils.py` makes these changes once for a run, and again in each worker that --parallel starts by spawn or forkserver (`django/test/runner.py:_init_worker`). `DiscoverRunner.setup_test_environment` calls it with the runner's debug mode, then `unittest.installHandler`, which `DiscoverRunner.teardown_test_environment` undoes with `unittest.removeHandler` (`django/test/runner.py:DiscoverRunner.setup_test_environment`). With that handler, a first Ctrl-C lets the running test finish, then stops the run, which reports its results and destroys the test databases (`docs/topics/testing/overview.txt`).

## The host and debugging

The test client builds a request whose `"SERVER_NAME"` is `"testserver"`, with no `"Host"` header unless the test gives one, so `HttpRequest.get_host` takes `"testserver"` as the host and checks it against `ALLOWED_HOSTS` ([Headers, host and scheme](../http/headers.md); `django/test/client.py:RequestFactory._base_environ`). `setup_test_environment` sets the setting to a new list, the project's hosts and `"testserver"` (`django/test/utils.py:setup_test_environment`). Django's documentation says hosts are checked in tests so the test client can tell the project's URLs from external ones (`docs/topics/testing/advanced.txt`).

`settings.DEBUG` is set to the argument, or left alone when that is `None`, the default. The runner passes its debug mode, false unless --debug-mode is given, so its tests run with debugging off whatever the settings say; the documentation's reason is that what a test observes should be what production shows (`docs/topics/testing/overview.txt`).

## Mail kept in memory

Where the project defines `MAILERS`, `setup_test_environment` replaces the setting with one with the same aliases, each given only `"django.core.mail.backends.locmem.EmailBackend"` and no `"OPTIONS"`. Without `MAILERS`, `EMAIL_BACKEND` is set to that backend, a branch marked for removal with `RemovedInDjango2028Warning`. `mailers` reads the settings each time it makes a backend (`django/core/mail/handler.py:MailersHandler.create_connection`), so each backend it makes from then on is that one, which appends a copy of each message to `outbox` on `django.core.mail` ([Sending email: `mailers` and the email backends](../services/mailers.md)). `setup_test_environment` sets that list empty, and `SimpleTestCase._pre_setup` empties it again before each test ([One test, in order: `SimpleTestCase`](simple-test-case.md)).

> **Trap.** The settings are changed by plain assignment, which sends no `setting_changed`, so nothing built from an old value is rebuilt. A Django template engine whose `"OPTIONS"` give no `"debug"` takes it from `settings.DEBUG` as it is built (`django/template/backends/django.py:DjangoTemplates.__init__`): with the harbour's settings, one built before `setup_test_environment(debug=False)` kept it on. The runner calls it before loading a test or running a check.

The receivers of `setting_changed` in `django/test/signals.py` are connected not by `setup_test_environment` but when anything first imports from `django.test` ([Overriding settings](../startup/overrides.md)).

## Templates that report their renders

`Template._render` and `PartialTemplate._render` walk a template's nodes once the context is bound. `setup_test_environment` replaces both, on the classes, with `instrumented_test_render`, which sends `template_rendered` with the template and the context and then renders the nodes (`django/test/utils.py:instrumented_test_render`). A parent named by `{% extends %}` and an included template are rendered through `_render` too, so each is reported ([Rendering: nodes and the render context](../templates/rendering.md)). A Jinja2 template sends nothing (`django/template/backends/jinja2.py:Template.render`).

Only `instrumented_test_render` sends `template_rendered`, and Django's listeners are temporary: `Client.request` and `AsyncClient.request` for each request, to give the response `HttpResponseBase.templates` and the contexts ([The test client: `Client` and `ClientHandler`](client.md)), and `SimpleTestCase.assertTemplateUsed` and `SimpleTestCase.assertTemplateNotUsed` as context managers, for their block ([Assertions on a response: `assertContains`, `assertRedirects` and `assertTemplateUsed`](response-assertions.md)).

## The harbour's environment

```python
# harbour/office/tests/test_environment.py
from django.conf import settings
from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase
from django.test.signals import template_rendered

from harbour.fleet.models import Port


def report(sender, template, context, **kwargs):
    print("rendered", template.name)


class EnvironmentTests(TestCase):
    def test_settings(self):
        print(settings.DEBUG, settings.ALLOWED_HOSTS, settings.MAILERS)

    def test_mail(self):
        port = Port.objects.create(name="Valletta", country="Malta")
        self.client.force_login(User.objects.create(username="nora"))
        self.client.post("/ships/new/", {"name": "Beagle", "tonnage": 235, "home": port.pk})
        print(mail.outbox[0].subject, mail.outbox[0].to)

    def test_renders(self):
        template_rendered.connect(report)
        self.client.get("/ships/")
        template_rendered.disconnect(report)
```

```text
$ python manage.py test harbour.office.tests.test_environment -v 0
System check identified no issues (0 silenced).
New ship: Beagle ['master@harbour.example']
rendered office/ship_list.html
rendered office/base.html
False ['harbour.example', 'testserver'] {'default': {'BACKEND': 'django.core.mail.backends.locmem.EmailBackend'}}
----------------------------------------------------------------------
Ran 3 tests in 0.025s

OK
```

The settings say `DEBUG = True` and give the mailer a host; with --debug-mode the same run printed True. The list page reported its template, then its base.

## Translation and teardown

Last, `setup_test_environment` calls `deactivate`, which drops the thread's active translation, so the run begins in `LANGUAGE_CODE`; teardown does not undo it (`django/utils/translation/trans_real.py:deactivate`).

The old values are kept on `_TestState`, an empty class. A second call while they are there would overwrite them, a comment says, and raises `RuntimeError` instead. `teardown_test_environment` restores `ALLOWED_HOSTS`, `settings.DEBUG`, whichever mail setting was replaced, and the two `_render` methods, then deletes the saved values and `outbox` (`django/test/utils.py:teardown_test_environment`).
