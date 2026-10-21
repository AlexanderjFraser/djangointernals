---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Validators: `django/core/validators.py`

A **validator** is a callable that is given one value and raises `ValidationError` when the value will not do. `django/core/validators.py` holds the general ones: `RegexValidator` and the validators of domain names, URLs and email addresses, `BaseValidator` and the limits built on it, `DecimalValidator`, `FileExtensionValidator`, and ready-made ones such as `validate_email`.

A validator is given the value and nothing else, so a function of one argument serves as well as a class, and one validator serves form and model fields alike.

Each validator here raises with a code, which names the rule broken (`"min_value"`), and parameters, which fill the message's placeholders (`django/core/validators.py:BaseValidator.__call__`). The message is filled only when it is read (`django/core/exceptions.py:ValidationError.__iter__`), so a field's own message for the code, put in the validator's place, can use the same parameters. The berth form's tonnage, given one:

```python
# harbour/fleet/forms.py
tonnage = forms.IntegerField(
    min_value=1,
    error_messages={"min_value": "%(value)s tons is below the limit of %(limit_value)s."},
)
```

```python
>>> form = BerthForm({"ship": "heron", "tonnage": "0", "arrives": "2026-10-20"})
>>> form.errors.as_data()
{'tonnage': [ValidationError(['0 tons is below the limit of 1.'])]}
```

A validator is ordinarily made once, with its module, field class or field, and called many times (`validate_image_file_extension` makes a new one at each call): a form's copy of its fields copies each list of validators but not the validators (`django/forms/fields.py:Field.__deepcopy__`). It holds what it was made with, and nothing between calls.

## Where validators are called

A form field's `Field.run_validators` ([A form field: the base class](fields.md)) and a model field's ([Validating an instance](../instance/validation.md)) work alike: they skip an empty value, call every validator of the field, gather all their errors into one `ValidationError`, and put the field's own message in place of a validator's where the field has one for its code (`django/forms/fields.py:Field.run_validators`, `django/db/models/fields/__init__.py:Field.run_validators`).

An empty value is one of the field's `empty_values`, which both base classes copy from `EMPTY_VALUES`: `None`, `""` and an empty list, tuple or dictionary (`django/core/validators.py:EMPTY_VALUES`). Whether a field may be empty is its own question; no validator is asked it.

## A validator in a migration

Every validator class of the module is decorated with `deconstructible`, whose `deconstruct` returns the arguments an instance was made with, so that a migration can write a model field's validator as a call that makes it again ([Serializing values: `serializer_factory` and `deconstruct`](../makemigrations/serializer.md)) (`django/utils/deconstruct.py:deconstructible`).

> **Trap.** Each class has an `__eq__`, which compares only what the class defining it knows: `RegexValidator.__eq__` not a `URLValidator`'s schemes, `BaseValidator.__eq__` not a `StepValueValidator`'s offset, so two with different schemes are equal, as are two given different offsets (`django/core/validators.py:RegexValidator.__eq__`, `django/core/validators.py:BaseValidator.__eq__`). A migration still tells them apart, by their arguments (`django/db/migrations/autodetector.py:MigrationAutodetector.deep_deconstruct`).

## `RegexValidator`

`RegexValidator` is the base of the pattern validators. Its class attributes `RegexValidator.regex`, `RegexValidator.message`, `RegexValidator.code`, `RegexValidator.inverse_match` and `RegexValidator.flags` are defaults that its arguments replace, so a subclass can be written by setting attributes alone, as the auth app's username validators are (`django/contrib/auth/validators.py:ASCIIUsernameValidator`). The pattern is wrapped by `_lazy_re_compile` in a `SimpleLazyObject`, and compiled when it is first used (`django/core/validators.py:RegexValidator.__init__`, `django/utils/regex_helper.py:_lazy_re_compile`).

A call looks for the pattern anywhere in `str(value)`, by `re.Pattern.search`, and the value is invalid when it is not found or, with `inverse_match`, when it is. A pattern that must match the whole value anchors itself, as each `RegexValidator` the module makes does with `"^"` and `"\Z"` (`django/core/validators.py:RegexValidator.__call__`).

## Domain names, URLs and email addresses

`DomainNameValidator`, `URLValidator` and `EmailValidator` share one description of a host name, kept on `DomainNameValidator`: labels of 1 to 63 characters that neither begin nor end with a hyphen, then a top-level domain of letters or a punycode label, `"xn--"` and the rest (`django/core/validators.py:DomainNameValidator`). A letter may be any character from U+00A1 to U+FFFF, so bücher.example passes as it is written, and is not converted to punycode.

`DomainNameValidator` joins the parts when it is made, ASCII-only ones with `accept_idna=False`, which also refuses a value that is not ASCII. It refuses a value that is not a string or is over 255 characters long, and wants a top-level domain, so `"localhost"` fails (`django/core/validators.py:DomainNameValidator.__init__`, `django/core/validators.py:DomainNameValidator.__call__`).

`URLValidator` refuses, in order and each with its code (`"invalid"` by default), a value that is not a string or is longer than `URLValidator.max_length` (2,048, `MAX_URL_LENGTH`); that holds a tab, carriage return, newline or null; whose scheme, before `"://"` and lower-cased, is not in `URLValidator.schemes` (by default `"http"`, `"https"`, `"ftp"` and `"ftps"`); that `urllib.parse.urlsplit` cannot split; that fails the pattern, which takes as host an IPv4 address, an IPv6 address in brackets, a host name or `"localhost"`; whose address in brackets `validate_ipv6_address` refuses; and whose host name is missing or longer than 253 characters, RFC 1034's limit (`django/core/validators.py:URLValidator.__call__`).

`EmailValidator` splits the address and checks its parts in methods a subclass may replace. `EmailValidator.parse_address` refuses a value that is empty, has no `"@"` or is longer than 320 characters, and splits it at the last `"@"`. `EmailValidator.validate` has the user part checked by `EmailValidator.validate_username`, as a dot-atom or a quoted string, and the domain by `EmailValidator.validate_domain`, which passes one in the allowlist (by default `["localhost"]`), one that matches the host-name pattern without the final dot a URL may have, or an address in brackets that `validate_ipv46_address` accepts (`django/core/validators.py:EmailValidator.validate_domain`).

> **Changed in 6.2.** The four methods are new, and an error of the user part or the domain carries it as the parameter `"username"` or `"domain"`.

> **Deprecated.** `EmailValidator.validate_domain_part` is to go (`RemovedInDjango2029Warning`). A subclass that defines it warns when the class is made, and `validate` calls it in place of `validate_domain`. A call to it warns too, unless its caller was itself called from Django (`django/core/validators.py:EmailValidator.__init_subclass__`, `django/core/validators.py:EmailValidator.validate_domain_part`).

## Limits: `BaseValidator` and its subclasses

`BaseValidator` compares a value with a limit. A call passes the value through `BaseValidator.clean`, calls the limit if it is callable, and raises if `BaseValidator.compare` of the two is true, with the parameters `"limit_value"`, `"show_value"` (the cleaned value) and `"value"` (`django/core/validators.py:BaseValidator.__call__`). In the base class `clean` returns the value and `compare` is `a is not b`. `MaxValueValidator` and `MinValueValidator` compare the value, and `MaxLengthValidator` and `MinLengthValidator` its length; their codes are `"max_value"`, `"min_value"`, `"max_length"` and `"min_length"`.

`StepValueValidator`, code `"step_size"`, wants a multiple of the limit, by `math.remainder` with a tolerance of 1e-9, so that 0.3 is a multiple of 0.1. Given an offset, it counts from there, and its message names the offset and the next two valid values. The form `IntegerField` makes one from `step_size=`, with `min_value=` as the offset (`django/forms/fields.py:IntegerField.__init__`).

> **Trap.** With an offset the parameters do not include `"value"`, so a field's message for `"step_size"` that names it raises `KeyError` when it is read (`django/core/validators.py:StepValueValidator.__call__`).

## Decimals, file extensions and null characters

`DecimalValidator` refuses an infinity or a NaN as `"invalid"`, then too many digits, decimal places or digits before the point, as `"max_digits"`, `"max_decimal_places"` and `"max_whole_digits"` (`django/core/validators.py:DecimalValidator.__call__`).

`FileExtensionValidator` refuses a file whose name's suffix, lower-cased, is not among the allowed extensions; with none given, it allows all (`django/core/validators.py:FileExtensionValidator.__call__`). `validate_image_file_extension` makes one at each call from the extensions Pillow registers; without Pillow that list is empty and every file is refused. The form `ImageField` has it by default (`django/forms/fields.py:ImageField`).

`ProhibitNullCharactersValidator` refuses a value whose string holds a null character. Every form `CharField` has one (`django/forms/fields.py:CharField.__init__`).

## The ready-made validators

| name | what it is |
|---|---|
| `validate_integer` | calls `integer_validator`, a `RegexValidator` for an optional minus and digits |
| `validate_slug`, `validate_unicode_slug` | `RegexValidator` instances: ASCII letters, digits, `"_"` and `"-"`; or Unicode word characters and `"-"` |
| `validate_email` | an `EmailValidator` |
| `validate_domain_name` | a `DomainNameValidator` |
| `validate_ipv4_address`, `validate_ipv6_address`, `validate_ipv46_address` | functions; the third tries the other two |
| `ip_address_validators` | the list of those for `"both"`, `"ipv4"` or `"ipv6"`, for the IP address fields; `ValueError` for another |
| `int_list_validator` | makes a `RegexValidator` for unsigned integers (signed, if asked) joined by a separator, `","` by default, as `validate_comma_separated_integer_list` is |

*The module's ready-made validators (`django/core/validators.py`).*
