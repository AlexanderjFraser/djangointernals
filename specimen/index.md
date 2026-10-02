---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
status: verified
contents: handler, names
---

# A specimen of the book

What does a page of *How Django Works* look like at each of its three statuses, and what does the site say about it?

This is not the book. It is a handful of pages that put the book's page spec through the site that bakes it: a page at each status, a table, a figure with its source, a name that Django makes only as it runs, a pointer into a library. The book's own pages will stand where these do.

## What does each status publish?

A page's status is one of three words in its head, and the site decides from that word alone what a reader is given.

| status | what exists | what the site publishes |
|---|---|---|
| *outline* | the head, and the sections as questions | an entry in the contents: the title, the lede, the status. No page |
| *verified* | the page, written from claims that were each checked against the source | the page |
| *read* | the page, read together with the pages around it and revised after a reader's read | the page |

No page says of itself how far it has come. The line under a page's title is written by the site from the status, so it cannot stay behind when the status moves.

## What is real here, and what is for show?

What these pages say about Django is real. Every name in a code span exists in the pinned source, every pointer resolves there, and each claim was checked against the source at the commit named at the head of its page.

The statuses are for show. A status here says how the site renders that status: no page of the specimen was read by a student, whatever its head says.

## Where is the rule these pages follow?

The page spec is `SPEC.md`, at the root of [the repository](https://github.com/AlexanderjFraser/djangointernals). It says what a page's head holds, what a section is, how a claim carries its pointer and how a figure is written. The site refuses to bake a page that breaks the part of it a program can check.
