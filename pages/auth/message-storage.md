---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Message storage: `CookieStorage`, `SessionStorage` and `FallbackStorage`

`CookieStorage`, `SessionStorage` and `FallbackStorage` keep the messages no page has shown until a later request: the first in the signed cookie `"messages"`, the second in the session, and the third, which `MESSAGE_STORAGE` names by default, in the cookie and, for what the cookie cannot hold, the session.

A storage class owes `BaseStorage` two methods. `BaseStorage._get` returns the messages an earlier response stored, with a flag saying whether they are all there; `BaseStorage._store` stores a list of messages on a response and returns those it could not store. The rest is `BaseStorage`'s ([Messages: `add_message`, `Message` and `MessageMiddleware`](messages.md)) (`django/contrib/messages/storage/base.py:BaseStorage`).

## The cookie's contents

`MessageEncoder` turns each `Message` into a JSON list: the marker `"__json_message"`, 1 if the text is safe HTML (a `SafeData`) and 0 if not, the level, the text, and the extra tags unless they are `None` (`django/contrib/messages/storage/cookie.py:MessageEncoder.default`). `MessageDecoder` walks the decoded JSON through lists and dictionaries and turns each list that begins with the marker back into a `Message`, passing the text through `mark_safe` when the flag is 1 (`django/contrib/messages/storage/cookie.py:MessageDecoder.process_messages`). So a message made with `format_html` keeps its HTML through the cookie, and the next page does not escape it.

The JSON is signed by the signer `get_cookie_signer` makes, with the salt `CookieStorage.key_salt`, `"django.contrib.messages"`: an instance of the class `SIGNING_BACKEND` names, `TimestampSigner` by default ([Signing: `Signer`, `TimestampSigner`, `dumps` and `loads`](../security/signing.md)) (`django/core/signing.py:get_cookie_signer`). `CookieStorage._encode_parts` calls `Signer.sign_object` with compression, which compresses only when that saves space and marks compressed data with a leading `"."` (`django/contrib/messages/storage/cookie.py:CookieStorage._encode_parts`). After nora's berth request the cookie held one message, not compressed:

```text
W1siX19qc29uX21lc3NhZ2UiLDAsMjUsIkJlcnRoIHJlcXVlc3RlZCBmb3IgRW5kZWF2b3VyLiIsIiJdXQ:1xHgAI:07BN-yT9oFcs-ywq0rP6qPGbVItD7m-doJ6W6SMPQKg
```

At the colons it is the JSON in URL-safe base64, the time of signing in base 62, and the signature, which makes a change detectable but hides nothing. `CookieStorage._decode` checks it with `Signer.unsign_object` and no maximum age, so the time is never compared and a message cookie does not expire by its signature (`django/contrib/messages/storage/cookie.py:CookieStorage._decode`).

`CookieStorage._update_cookie` borrows the session cookie's `SESSION_COOKIE_DOMAIN`, `SESSION_COOKIE_SECURE`, `SESSION_COOKIE_HTTPONLY` and `SESSION_COOKIE_SAMESITE`, but not its path or age: the path is `"/"`, the default of `HttpResponseBase.set_cookie`, and with no max-age the cookie lasts the browser's session. With nothing to store it deletes the cookie ([Cookies](../http/cookies.md)) (`django/contrib/messages/storage/cookie.py:CookieStorage._update_cookie`).

`CookieStorage._get` reads the cookie and decodes it. No cookie gives `None` in place of a list, which tells a caller the storage was not used. When the last item is `CookieStorage.not_finished`, the string `"__messagesnotfinished__"` (the **not-finished marker**), it removes it and answers that not every message was retrieved (`django/contrib/messages/storage/cookie.py:CookieStorage._get`).

## When the messages do not fit the cookie

`CookieStorage.max_cookie_size` is 2,048. The comment beside it gives the reason: uwsgi's default configuration allows 4 KB for all the HTTP headers, and half is kept for the other cookies and headers (ticket 18781). What is measured is the signed, compressed value, so text that repeats goes far: three hundred messages "Berth requested for ship 1." to "ship 300." made a cookie of 1,154 characters.

`CookieStorage._store` encodes the whole list and stores it if it fits. When it does not, it looks by bisection for the longest run of messages that fits with the not-finished marker after it (`django/contrib/messages/storage/cookie.py:CookieStorage._store`). `MessagePartSerializer` has turned each message into JSON once, and for each trial `MessagePartGatherSerializer` joins a slice's strings into a JSON list, so a trial encodes no message again: it repeats the join, the compression, the base64 and the signature.

With `remove_oldest=True`, the default, `bisect_keep_right` keeps the newest messages that fit and the oldest are returned; with `remove_oldest=False`, `bisect_keep_left` keeps the oldest and the newest are returned. Either way the cookie ends with the marker (`django/contrib/messages/storage/cookie.py:bisect_keep_right`, `django/contrib/messages/storage/cookie.py:bisect_keep_left`). Of eight messages from a view of the office's, each carrying a pass of 300 random characters, a `CookieStorage` made by hand kept the third to the eighth; told to keep the oldest, it kept the first six. A `CookieStorage` that is the request's storage hands its leftovers to `MessageMiddleware`, which drops them, or raises `ValueError` under `settings.DEBUG` ([Messages: `add_message`, `Message` and `MessageMiddleware`](messages.md)).

## `SessionStorage`

`SessionStorage` keeps the messages in the session under `SessionStorage.session_key`, `"_messages"`, and refuses to be made for a request without a session ([Authentication, sessions and messages](../auth.md)) (`django/contrib/messages/storage/session.py:SessionStorage.__init__`). It stores the list as a string: `SessionStorage.serialize_messages` encodes it with `MessageEncoder`, the same lists as in the cookie, and `SessionStorage.deserialize_messages` decodes a non-empty string with `MessageDecoder` and returns anything else as it found it, `None` included (`django/contrib/messages/storage/session.py:SessionStorage.deserialize_messages`).

`SessionStorage._get` always answers that every message was retrieved, since, as its docstring says, it stores everything it is given. `SessionStorage._store` sets the entry when it has messages, removes it when it has none, and returns an empty list (`django/contrib/messages/storage/session.py:SessionStorage._store`). Setting the entry, or removing one that was there, modifies the session, and `SessionMiddleware` saves it on the way out ([`SessionMiddleware`: the cookie and the save](session-middleware.md)). A visitor with no session gets one: in a run, an anonymous request whose messages overflowed the cookie inserted a session row and set `"sessionid"`.

## `FallbackStorage`

`FallbackStorage.storage_classes` is `CookieStorage` and then `SessionStorage`, and a `FallbackStorage` makes one of each for its request (`django/contrib/messages/storage/fallback.py:FallbackStorage`).

`FallbackStorage._get` asks each storage in order and gathers their messages into one list. It stops at a storage that returns `None`, as one that was not used does, and after one that has retrieved everything; it notes which storages held messages (`django/contrib/messages/storage/fallback.py:FallbackStorage._get`). A cookie without the not-finished marker ends the read, and the session is not asked.

`FallbackStorage._store` gives the messages to each storage in turn with `remove_oldest=False` and passes on what each returns: the cookie keeps the oldest that fit, the session the rest, and the order survives the split. A storage given nothing that held messages when they were read is emptied, so the cookie is deleted and the session's entry removed (`django/contrib/messages/storage/fallback.py:FallbackStorage._store`).

> **Why.** Django's documentation gives the reason for trying the cookie first: it avoids writing to the session whenever possible, and should perform best in the general case (`docs/ref/contrib/messages.txt`).

Nora posted the eight long messages in one request and then loaded the berths page, whose loop showed all eight in order:

```text figure=the-fallback
first request: POST, eight messages added; no cookie, so no earlier ones
  on the way out: FallbackStorage._store(eight)
    CookieStorage._store(eight, remove_oldest=False)
      the eight: more than 2,048 characters
      bisect_keep_left: the first six and the marker fit
      cookie "messages" set to them
      returns the seventh and eighth
    SessionStorage._store(the seventh and eighth)
      session "_messages": the two, as a JSON string
  SessionMiddleware: the session modified, saved

next request: GET /berths/, the page loops over the messages
  FallbackStorage._get
    CookieStorage._get: six; the marker removed: not all retrieved
    SessionStorage._get: two: all retrieved
  the page shows the eight, first to last
  on the way out: FallbackStorage._store(an empty list)
    CookieStorage held messages: the cookie deleted
    SessionStorage held messages: "_messages" removed
  SessionMiddleware: the session modified, saved
```

*Eight messages too many for the cookie, over two requests. The cookie keeps the first six and the marker, the session the other two; the next page reads the cookie, finds the marker, reads the session, and then empties both.*

## A cookie the client changed

When something reads the storage, `CookieStorage._decode` returns `None` for a value whose signature does not match, or that is not base64 or JSON, and marks the storage used so that, as its comment says, the bad data is removed. When `CookieStorage` is the request's storage, `BaseStorage.update` then stores its queue, and with no new messages the response deletes the cookie. Under `FallbackStorage` the mark falls on the storage inside, which nothing asks (`django/contrib/messages/storage/cookie.py:CookieStorage._decode`, `django/contrib/messages/storage/base.py:BaseStorage.update`). Runs with one character of the cookie changed showed both; under `FallbackStorage` the page showed no message, the response left the cookie alone, and the next request sent it again. It stays until a response stores messages over it.
