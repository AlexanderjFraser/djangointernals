---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Email messages: `EmailMessage` and `EmailMultiAlternatives`

`EmailMessage` holds the parts of one email, its subject, body, sender, recipients, attachments and extra headers, and `EmailMessage.message` builds from them a message of the standard library's `email` package. `EmailMultiAlternatives` adds other versions of the body, such as HTML beside the plain text.

An `EmailMessage` is a container of plain Python values. Writing a message out, encoding its body, checking its headers, nesting its parts, is the work of the standard library's modern email API: an `email.message.EmailMessage` and its **policy**, the object from `email.policy` that sets the rules for building and writing it. `EmailMessage.message` builds one afresh at each call, and each of Django's email backends but the dummy one calls it as it sends, the SMTP backend with `email.policy.SMTP` for the line endings SMTP requires.

## Making a message

`EmailMessage.__init__` takes the subject, the body, the sender and the To list by position or by name, and the rest by name only (`django/core/mail/message.py:EmailMessage.__init__`). Each of to, cc, bcc and reply_to is copied into a new list, and a non-empty string given for one is refused with a `TypeError`. The sender is from_email or, when that is empty, `DEFAULT_FROM_EMAIL` as it stands at that moment. The headers are kept as `EmailMessage.extra_headers`, and each attachment given is passed to `EmailMessage.attach`. No header is parsed and nothing is encoded until `message` is called.

> **Deprecated.** Passing any argument after the first four by position warns with `RemovedInDjango2028Warning` (6.0; `django/utils/deprecation.py:deprecate_posargs`). A backend given as `connection=`, and the `EmailMessage.connection` property, are deprecated in 6.1 in favour of an alias of `MAILERS` (`docs/releases/6.1.txt`). They warn only when the caller is outside Django, so `EmailMultiAlternatives`, which passes the connection on to `EmailMessage.__init__`, gives no warning (`django/utils/deprecation.py:warn_about_external_use`).

## Building the message: `EmailMessage.message`

`EmailMessage.message` makes an empty `email.message.EmailMessage` under the policy it is given, `email.policy.default` unless the caller names another, and fills it in a fixed order (`django/core/mail/message.py:EmailMessage.message`):

1. **The body.** `EmailMessage._add_bodies` sets it with `email.message.EmailMessage.set_content`, as text of the subtype `EmailMessage.content_subtype` (`"plain"` unless changed), in the charset `EmailMessage.encoding` names or else `DEFAULT_CHARSET`. A message with attachments and an empty body gets no text part.
2. **The attachments**, if any. `EmailMessage._add_attachments` makes the message multipart/mixed with `email.message.MIMEPart.make_mixed`, the body becoming its first part, and adds each attachment after it.
3. **The addressing headers.** Subject, then From: the extra header "From" if there is one, else the sender. To, Cc and Reply-To each come from an extra header of that name if there is one, else from the list, joined by commas, and are left out when the list is empty (`EmailMessage._set_list_header_if_not_empty`).
4. **Date and Message-ID**, each unless the extra headers name it, whatever the case of the name. The date is now, in UTC or, when `EMAIL_USE_LOCALTIME` is true, in the current time zone. The identifier comes from `email.utils.make_msgid` with the domain `DNS_NAME`, a `CachedDnsName`, which asks `socket.getfqdn` for the machine's name when first needed and keeps it, as the lookup can take seconds and slow the server's restart, its comment says (`django/core/mail/utils.py:CachedDnsName`).
5. **The other extra headers.** One named Bcc is refused with a `ValueError`; blind copies are given with the bcc argument.
6. **Non-ASCII domains.** Unless the policy allows UTF-8 in headers, as neither `email.policy.default` nor `email.policy.SMTP` does, a domain outside ASCII in an address header is rewritten in its IDNA form; the comment cites CPython issue 83938, in which the email package would write it as an RFC 2047 encoded word (`django/core/mail/message.py:EmailMessage._idna_encode_address_header_domains`).

The checking is the policy's. A header is parsed as it is set, and a value that a carriage return, a line feed or another line boundary splits into more than one line raises `ValueError`, on which Django's protection against header injection relies, its documentation says (`docs/topics/email.txt`). A single break at the very end of a value splits nothing, and is encoded into the header. A subject with a newline inside it makes an `EmailMessage` without complaint and fails when the message is built, which the local-memory backend does at the send for that alone (`django/core/mail/backends/locmem.py:EmailBackend.send_messages`).

> **Trap.** The extra headers that replace From, To, Cc and Reply-To are looked up by exactly those spellings, and the loop over the others skips those names in any case: given as `"from"` or `"to"`, a header is written nowhere.

The example's notice to the harbour master, with a blind copy to the records:

```python
# notices/messages.py
from django.core.mail import EmailMessage, EmailMultiAlternatives


def sailing_notice(voyage):
    return EmailMessage(
        subject=f"{voyage.ship} sailed on {voyage.sailed:%d %B %Y}",
        body=f"Voyage {voyage.pk}: the {voyage.ship} has sailed.",
        to=["master@harbour.example"],
        bcc=["records@harbour.example"],
    )
```

For Endeavour's voyage, the text of what `message()` built, without its Date and Message-ID lines:

```text
Content-Type: text/plain; charset="utf-8"
Content-Transfer-Encoding: 7bit
MIME-Version: 1.0
Subject: Endeavour sailed on 12 October 2026
From: office@harbour.example
To: master@harbour.example

Voyage 1: the Endeavour has sailed.
```

> **Changed in 6.0.** `EmailMessage.message` returns an `email.message.EmailMessage` of the modern API (`docs/releases/6.0.txt`). Deprecated with the change, to go in Django 2028: the legacy classes it built, `SafeMIMEText` and `SafeMIMEMultipart`; the helpers `forbid_multi_line_headers` and `sanitize_address`; attachments of the legacy `email.mime.base.MIMEBase`; and `BadHeaderError`, now `ValueError` itself so that code catching it catches what the modern API raises, its comment says (`django/core/mail/message.py:BadHeaderError`).

## Recipients, Bcc and sending

`EmailMessage.recipients` returns the To, Cc and Bcc lists joined, empty entries left out (`django/core/mail/message.py:EmailMessage.recipients`). It is the list a backend sends to, and the only place the Bcc list goes: `message` writes no Bcc header, so for the example's sailing notice it returned both addresses while the text names one. The SMTP backend gives the server `recipients` as the envelope's recipients and `EmailMessage.from_email` as its sender, whatever the headers say (`django/core/mail/backends/smtp.py:EmailBackend._send`).

`EmailMessage.send` returns what the backend's `send_messages` returns, the number sent (`django/core/mail/message.py:EmailMessage.send`). With no recipients it returns 0 before any backend is made, sparing the network connection, its comment says. Otherwise the backend is `mailers[using]` when `using=` names an alias; else the connection the message holds; else what the deprecated `django.core.mail.get_connection` returns, which, where `MAILERS` is defined, is a new instance of the default mailer, and otherwise the backend `EMAIL_BACKEND` names. `using=` with a connection or with the deprecated `fail_silently=True` is a `TypeError`. The rest of the send is in [Sending email: `mailers` and the email backends](mailers.md).

## Attachments: `attach` and `attach_file`

`EmailMessage.attach` takes an attachment in one of two forms, besides the deprecated `email.mime.base.MIMEBase` (`django/core/mail/message.py:EmailMessage.attach`). An `email.message.MIMEPart`, built with whatever headers the caller needs, is kept as it is. Otherwise it takes a filename, a content, which is required, and a type, which when not given is guessed from the filename by `mimetypes.guess_type`, and failing that is `DEFAULT_ATTACHMENT_MIME_TYPE`, `"application/octet-stream"`. Content of a text type given as bytes is decoded as UTF-8; if that fails, the bytes are kept and the type becomes `"application/octet-stream"`. The attachment is kept as an `EmailAttachment`, a named tuple of the three. `EmailMessage.attach_file` reads a file's bytes and attaches them under the file's name.

When the message is built, `EmailMessage._add_attachment` adds each tuple by its main type: text as a string in the message's charset; a message type such as message/rfc822 as a message object, a Django `EmailMessage` being built by its own `message` under the same policy; any other as bytes. It decodes text again, its comment says, for attachments put into `EmailMessage.attachments` without `attach` (`django/core/mail/message.py:EmailMessage._add_attachment`).

## Alternatives: `EmailMultiAlternatives`

`EmailMultiAlternatives` is an `EmailMessage` with a list of other versions of its body, `EmailMultiAlternatives.alternatives`, each an `EmailAlternative` of a content and a type, added with `EmailMultiAlternatives.attach_alternative` or given to the constructor (`django/core/mail/message.py:EmailMultiAlternatives.attach_alternative`). `send_mail`, `mail_admins` and `mail_managers` build their messages with it, and attach as an alternative the HTML they are given (`django/core/mail/__init__.py:send_mail`, `django/core/mail/__init__.py:_send_server_message`).

When the message is built, only the body is added differently (`django/core/mail/message.py:EmailMultiAlternatives._add_bodies`). The plain body is set as before, unless it is empty and there are alternatives. If there are, `email.message.MIMEPart.make_alternative` then makes the message multipart/alternative, the plain body its first part, and each alternative follows. Alternatives are added before attachments, so on a message with both, the mixed part wraps the alternative one. The notice again, with an HTML version and the ports of call attached:

```python
# notices/messages.py, continued
def sailing_notice_html(voyage):
    notice = EmailMultiAlternatives(
        subject=f"{voyage.ship} sailed on {voyage.sailed:%d %B %Y}",
        body=f"Voyage {voyage.pk}: the {voyage.ship} has sailed.",
        to=["master@harbour.example"],
    )
    notice.attach_alternative(f"<p>The <b>{voyage.ship}</b> has sailed.</p>", "text/html")
    notice.attach("calls.txt", "\n".join(port.name for port in voyage.calls.all()).encode())
    return notice
```

The parts it built for Endeavour's voyage, as a tree; the bytes of calls.txt were decoded, and its type guessed from the name:

```text
multipart/mixed
  multipart/alternative
    text/plain
    text/html
  text/plain  attachment, calls.txt
```

`EmailMultiAlternatives.body_contains` is true when a text is in the plain body and in every alternative of a text type, which its documentation says can be useful in tests (`django/core/mail/message.py:EmailMultiAlternatives.body_contains`, `docs/topics/email.txt`).
