---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Where Django came from, and who makes it

Django began in 2003 at World Online, the web department of the Lawrence Journal-World newspaper in Lawrence, Kansas. A team of volunteers runs it under a steering council, with the Django Software Foundation beside them, and its larger changes go through Django Enhancement Proposals, which since 2018 have also reshaped how the project is governed. The project makes promises to those who build on it, about security and about stability.

## A framework drawn from a newsroom

World Online, a newspaper's web operation, built web applications on journalism's deadlines, often with only hours to take a complicated one from concept to launch. In the autumn of 2003 its developers, Adrian Holovaty and Simon Willison, moved from PHP to Python, and as they built sites such as Lawrence.com they drew a general framework out of them, which they kept improving for two years. In the summer of 2005 World Online decided to release it as open source, as Django (`docs/faq/general.txt`).

The name is that of Django Reinhardt, a jazz manouche guitarist of the 1930s to the early 1950s, and it is said JANG-oh, the D silent (`docs/faq/general.txt`).

Django is distributed under the three-clause BSD licence, which grants broad permission to modify and redistribute it (`docs/faq/general.txt`); its file LICENSE names the Django Software Foundation and the individual contributors as the holders of the copyright (`django:LICENSE`). Python's licence stands beside it, because Django includes code from Python's standard library (`django:LICENSE.python`).

## The foundation and the project

The [Django Software Foundation](https://www.djangoproject.com/foundation/) is a non-profit organization that handles the financial and legal matters of the Django project. The project itself is not a legal entity, and beyond money and law the foundation leaves it to run the framework's development, its ecosystem and its community. The foundation appears in the project's workings at fixed points; among them, it can fund the posts of the Django Fellows, and its board runs the elections of the steering council and ratifies their results (`docs/internals/organization.txt`).

## Django Enhancement Proposals

A **Django Enhancement Proposal**, a DEP, is a design document that informs the community or describes a new feature or a process for Django, with a concise specification and the reasons for it. It is meant to be the project's main means of proposing a major feature and of recording a design decision. DEP 1, which set up the process in 2014, was written by Adrian Holovaty and Jacob Kaplan-Moss and is, by its own account, a near-copy of Python's PEP process (`deps:final/0001-dep-process.rst`). A DEP is submitted as a pull request to a separate repository, [django/deps](https://github.com/django/deps), and the steering council has the final word on it. The repository files each proposal under its state: draft, accepted, final once its implementation is in Django, withdrawn, rejected or superseded.

None of the documents that set the project's rules says exactly which changes need a DEP. The governance defines a **major change** as one large enough to need a DEP, and a **minor change** as one that is not; DEP 1 adds that small enhancements and patches usually need none; and DEP 19 says that a proposer of a major change "may be asked" to write one (`deps:accepted/0019-technical-governance-6x.rst`). A new feature is first proposed among the project's new-feature ideas on GitHub, which the steering council reviews (`docs/internals/contributing/bugs-and-features.txt`).

## Who decides

Anyone may open a ticket, triage one, write a fix or review a pull request; merging, releasing and deciding belong to roles, whose present holders the project's [teams page](https://www.djangoproject.com/foundation/teams/) lists (`docs/internals/contributing/triaging-tickets.txt`, `docs/internals/organization.txt`):

- **The mergers** are the few people who merge pull requests into Django's repository. A merger may merge a minor change; one the merger mainly wrote needs the approval of another merger, or of a member of the triage and review team or of the security team, and the documentation accepts a member of the steering council too.
- **The releasers** build Django's releases and upload them to the Python Package Index and to djangoproject.com.
- **The steering council**, five members, oversees development and the release process, selects the mergers and the releasers, may make a binding decision on any question of a technical change to Django, and accepts or rejects the proposals for major changes (`deps:final/0001-dep-process.rst`).
- **The security team** receives the reports of vulnerabilities (`docs/internals/security.txt`), and may ask for a security release at a time of its choosing (`deps:final/0010-new-governance.rst`, `deps:accepted/0019-technical-governance-6x.rst`).
- **The triage and review team** are regular contributors with extra permissions on GitHub for processing pull requests (`deps:final/0010-new-governance.rst`).
- **The Django Fellows** are paid by the foundation for work that includes triaging issues, reviewing and merging pull requests and managing releases (`deps:final/0010-new-governance.rst`); a merger or a releaser need not be a Fellow (`docs/internals/organization.txt`).

Two accounts of these rules stand at this commit. Django's documentation describes the organization as DEP 10 set it up and DEP 12 amended it, and those two DEPs, each of which now calls itself a historical document, send their reader to it for how the council works (`docs/internals/organization.txt`, `deps:final/0010-new-governance.rst`, `deps:final/0012-steering-council.rst`). DEP 19, accepted by the steering council, restates the governance in one document, declares that it supersedes both, and differs from the documentation on how the council is chosen, what it may do and how it decides (`deps:accepted/0019-technical-governance-6x.rst`).

The documentation and the DEPs at this commit settle that a change to the governance is adopted only once the foundation's board votes for it (`deps:final/0010-new-governance.rst`). They leave open whether DEP 19 has been adopted, and so which of the two accounts governs: none of them records the board's vote, the documentation still describes the older rules, and DEP 19's state cannot tell, since an adopted DEP stays accepted until its implementation is complete (`deps:final/0001-dep-process.rst`).

> **History.** DEP 10 recalls that Django's two co-BDFLs, its benevolent dictators for life, "Adrian and Jacob", could once speak for the project, and that since they stepped back no one person can. By 2018 governance was, in its words, "ad-hoc on the public mailing list, with a nebulous and often-inactive 'core' and a purely reactive technical board". DEP 10, written that year by James Bennett, dissolved the team of committers: push access was left to the mergers, the first of them the Fellows of the day, and uploads to the releasers; "Django Core Developer" became an honorary title; and the technical board was given the powers to decide, to veto, and to choose the mergers and the releasers (`deps:final/0010-new-governance.rst`).
>
> DEP 12, written in 2022 by Andrew Godwin, renamed the board the steering council, widened who could stand for it, and added a way to force a new election when the council neglects its duties, because the boards had acted mostly as a last hurdle for proposals and appointments and the latest election had found five candidates for five seats (`deps:final/0012-steering-council.rst`).

## What is stable, and what is internal

Django's stability promise is that code written against one release keeps working with later ones, apart from minor changes their release notes list as backwards incompatible (`docs/misc/api-stability.txt`). A stable API is not moved or renamed without a backwards-compatible alias, gains features without changing the meaning of what is there, and when it has to go is first deprecated: it stays, warning when it is used, for at least two feature releases. It is broken without that only where a bug or a security hole leaves no other way.

What is stable is, in general, what the documentation covers, apart from its internals area. Two marks put a name outside the promise: the documentation's calling it internal, which reserves Django's right to change it, and an underscore at its start, Python's way of marking a name private. Such a name, `BaseHandler._get_response` or `QuerySet._fetch_all`, says how the code works at one commit; it is not an interface, and code that calls or overrides it may find it changed or gone in a later release, with no alias and no warning. The security policy draws the same line from the other side: a vulnerability that depends on calling Django's private, undocumented functions in an unsafe way is not a valid report (`docs/internals/security.txt`).

> **Trap.** The underscore and the documentation do not always agree. `Model._meta`, the `Options` each model class carries, begins with an underscore and is documented all the same, as the Model `_meta` API (`django/db/models/options.py:Options`, `docs/ref/models/meta.txt`). The other way round, `QuerySet.query` has no underscore and the documentation calls it an opaque object outside the public API (`docs/ref/models/querysets.txt`); and of the app registry's methods only those the documentation lists are public, which leaves out `Apps.populate`, the method `django.setup` calls (`docs/ref/applications.txt`).

## Releases and security fixes

Django has made a feature release about every eight months, every third one a **long-term support release** that receives security and data-loss fixes for three years, with patch releases between (`docs/internals/release-process.txt`, `deps:final/0004-release-schedule.rst`). DEP 20, accepted, makes the release after 6.2 Django 2028, the first of one feature release a year, each supported for three years (`deps:accepted/0020-annual-release-cycle.rst`); the releases and their dates are in [What changed](../changes.md#the-releases).

A security issue is reported by email to security@djangoproject.com, which reaches the security team, and not in the public ticket tracker. The team acknowledges a report within three working days and aims to resolve each within ninety days. A confirmed issue is disclosed on a day set in advance: usually about a week before it, the django-announce mailing list is told the date and the severity, and a private list, mostly of operating-system vendors and other distributors of Django, is sent the full description and the patches. On the day, the patches are applied to main, to the two newest release series and to the long-term support releases still supported, new releases are uploaded, and a post on the project's blog describes the issue; an issue that affects only main is fixed in public (`docs/internals/security.txt`).

How the code came to be what it is at this commit is told in [The first decade: from a newsroom to 1.8](../changes/first-decade.md) and [The second decade: from 1.9 to 5.0](../changes/second-decade.md).
