---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
contents: overview, startup, commands, handlers, http, urls, views, models, querysets, sql, backends, migrations, templates, forms, security, i18n, services, utils, auth, admin, contrib, testing, changes
---

# Django Internals

How Django works, read from its source: what each part owns, when it runs, and why it is built the way it is.

Django's documentation says how to use Django, and says it well. This book is about the other thing: how the framework itself works. It follows a request from the server's call to the response, a model from its class statement to the SQL it produces, a template from text to output, and at each step it says which object is responsible, when that object runs, and what it hands to the next.

It is written for people who need a working model of the system, whether to debug it, to extend it, or to direct an agent that is doing either, and for the agents themselves. Every class, function and setting named here exists in Django's source at the commit the book describes, and every passage names the code it is about, so a reader can go and look.
