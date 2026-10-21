---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# Full-text search: `SearchVector`, `SearchQuery` and `SearchRank`

Full-text search in `django.contrib.postgres`: the lookup `"search"` and the expressions `SearchVector`, `SearchQuery`, `Lexeme`, `SearchRank` and `SearchHeadline` that write PostgreSQL's text-search functions, with the trigram functions and lookups and `"unaccent"` beside them.

PostgreSQL searches text with two types of its own. A document becomes a `"tsvector"`, its words reduced to **lexemes**, their normalized forms, under a **text search configuration** such as `"english"`; a search becomes a `"tsquery"`, lexemes joined by operators; and the operator `"@@"` says whether a query matches a vector. Django computes none of it: each expression and lookup here writes PostgreSQL's functions or operators into the SQL or its parameters, and the server stems, matches and ranks. The examples were compiled for the `"postgres"` alias with no server behind it.

## The `"search"` lookup

`PostgresConfig.ready` registers `SearchLookup` as `"search"` on `django.db.models.CharField` and `django.db.models.TextField`, for every database ([The PostgreSQL application: `PostgresConfig`, operations and aggregates](postgres.md)). It adds one step to `SearchVectorExact`: its `process_lhs` wraps the left side in a `SearchVector`, with the right side's configuration if it has one; the inherited `process_rhs` wraps a right side that is not already a query in a `SearchQuery` with the vector's configuration; and `SearchVectorExact.as_sql` puts `"@@"` between them (`django/contrib/postgres/lookups.py:SearchLookup.process_lhs`, `django/contrib/postgres/search.py:SearchVectorExact`):

```text
Bulletin.objects.filter(body__search="pilot boat").values("title")
WHERE to_tsvector(COALESCE("notes_bulletin"."body", %s)) @@ (plainto_tsquery(%s))
params: ('', 'pilot boat')
```

Neither call names a configuration, so the server applies its default to both. Sent to the example's SQLite database, the same filter was refused: unrecognized token: "@".

`SearchVectorField` is a column of type `"tsvector"`, with the system check that `django.contrib.postgres` is installed. The lookup registered on it as `"exact"` is `SearchVectorExact`, so a filter by a plain string on a vector field, or on an annotation whose output is one, compares it with a `SearchQuery` in the vector's configuration, if it has one (`django/contrib/postgres/search.py:SearchVectorExact.process_rhs`). `SearchQueryField`, `"tsquery"`, is a query's output field. Nothing in the module fills a vector column; the documentation suggests a trigger or a `GeneratedField` (`docs/ref/contrib/postgres/search.txt`), and an index over the vector ([PostgreSQL indexes and `ExclusionConstraint`](postgres-indexes.md)).

## `SearchVector`: the document

`SearchVector` is a `Func` whose function is `"to_tsvector"` and whose output field is a `SearchVectorField`. It joins its field names or expressions with its `arg_joiner`, `" || ' ' || "`, so that several columns make one document. Each is first cast to text, unless its output field is a `django.db.models.CharField` or `django.db.models.TextField`, and wrapped in a `Coalesce` with an empty string, so that a null column adds nothing instead of making the whole document null. A weight, one of PostgreSQL's labels A to D, wraps the call in `"setweight"`, which labels that part's lexemes for the ranking (`django/contrib/postgres/search.py:SearchVector.as_sql`). A configuration, a name or an expression such as an `F` of a column that holds one, becomes a `SearchConfig`, written cast to `"regconfig"` as the first argument of `"to_tsvector"` (`django/contrib/postgres/search.py:SearchConfig`).

Vectors combine with `+`, and only with each other. `SearchVectorCombinable` sets `ADD` to `"||"`, PostgreSQL's concatenation of vectors, and its `_combine` makes a `CombinedSearchVector` that keeps the left side's configuration, or raises `TypeError`: "SearchVector can only be combined with other SearchVector instances, got SearchQuery." (`django/contrib/postgres/search.py:SearchVectorCombinable._combine`). The combination's type comes from the table of combinable fields, where the module registers at import `"||"` between two `SearchVectorField`s as giving a `SearchVectorField` ([Expressions: `resolve_expression` and `as_sql`](../expressions/protocol.md)).

## `SearchQuery` and `Lexeme`: the search

`SearchQuery` is a `Func` whose function its search type picks from `SearchQuery.SEARCH_TYPES`: `"plainto_tsquery"` for `"plain"`, the default, which requires every word; `"phraseto_tsquery"` for `"phrase"`, which requires them as a phrase; `"to_tsquery"` for `"raw"`, which reads tsquery's own syntax; and `"websearch_to_tsquery"` for `"websearch"`, which reads quoted phrases, "or" and a leading dash. Any other type raises `ValueError` (`django/contrib/postgres/search.py:SearchQuery.__init__`). A configuration becomes the function's first argument. `invert=True`, or `~`, which flips that flag on a copy, writes the call into `"!!(%s)"`, PostgreSQL's negation of a tsquery. `Combinable` refuses `&` and `|` unless both sides are conditions (`django/db/models/expressions.py:Combinable.__and__`); `SearchQueryCombinable` defines them again to make a `CombinedSearchQuery` with PostgreSQL's `"&&"` or `"||"` between (`django/contrib/postgres/search.py:SearchQueryCombinable`).

`Lexeme` is for words a user typed that must not be read as operators. It is a `Value` of one string, and its `as_sql` writes one parameter: the string with each character of `spec_chars_re` (the apostrophe, the backslash, the null character and `"[]()|&:*!@<>"`) made a space, spaces collapsed, and quoted as a string literal by the driver; then, after a colon, `"*"` for a prefix and the weight's letter, and `"!"` in front when inverted (`django/contrib/postgres/search.py:Lexeme.as_sql`, `django/contrib/postgres/search.py:psql_escape`, `django/contrib/postgres/search.py:quote_lexeme`). Lexemes combine with `&` and `|` into a `CombinedLexeme`, which writes both sides into one string, so a whole tree is still one parameter; `~` on a combination applies De Morgan's theorem, as its comment says, swapping the operator and inverting both sides (`django/contrib/postgres/search.py:CombinedLexeme.__invert__`). A `SearchQuery` given a lexeme takes the type `"raw"`, whatever it was given, an unknown one included, and `"to_tsquery"` reads the operators the lexemes wrote.

```text
Bulletin.objects.filter(body__search=query).values("title"): the right side of @@, and the parameters

SearchQuery('breakwater -closed "pilot boat"', search_type="websearch")
    (websearch_to_tsquery(%s))    ('', 'breakwater -closed "pilot boat"')
SearchQuery("pilot") & ~SearchQuery("closed") | SearchQuery("customs")
    ((plainto_tsquery(%s) && !!(plainto_tsquery(%s))) || plainto_tsquery(%s))    ('', 'pilot', 'closed', 'customs')
SearchQuery(Lexeme("break", prefix=True) & ~Lexeme("closed", weight="A"))
    (to_tsquery(%s))    ('', "('break':* & !'closed':A)")
SearchQuery(Lexeme("pilot's & boat:*"))
    (to_tsquery(%s))    ('', "'pilot s boat'")
```

> **Trap.** `~` on a combination of queries is no negation. `CombinedSearchQuery` declares no `__invert__`, and the `NegatedExpression` that `Combinable.__invert__` makes needs an output field that no combination of two queries has (`django/db/models/expressions.py:NegatedExpression.resolve_expression`): filtering by `~(SearchQuery("pilot") & SearchQuery("boat"))` raised `FieldError`.

> **Changed in 6.0.** `Lexeme` is new (`docs/releases/6.0.txt`).

## `SearchRank` and `SearchHeadline`

`SearchRank` writes `"ts_rank"`, or with `cover_density=True` `"ts_rank_cd"`, and its output is a float. Weights, four numbers for the labels D, C, B and A in that order, go first, cast to `"float4[]"` by a `Cast` to an `ArrayField`; a normalization, an integer of flags, goes last (`django/contrib/postgres/search.py:SearchRank.__init__`). Without weights the server uses its own, which the documentation gives as 0.1, 0.2, 0.4 and 1.0 (`docs/ref/contrib/postgres/search.txt`). Bulletins ranked by a vector weighting the title above the body:

```text
vector = SearchVector("title", weight="A", config="english") + SearchVector("body", weight="B", config="english")
query = SearchQuery("pilot boat", config="english")
Bulletin.objects.annotate(rank=SearchRank(vector, query)).order_by("-rank").values("title", "rank")

SELECT "notes_bulletin"."title" AS "title", ts_rank((setweight(to_tsvector(%s::regconfig, COALESCE("notes_bulletin"."title", %s)), %s) || setweight(to_tsvector(%s::regconfig, COALESCE("notes_bulletin"."body", %s)), %s)), plainto_tsquery(%s::regconfig, %s)) AS "rank"
FROM "notes_bulletin"
ORDER BY 2 DESC
params: ('english', '', 'A', 'english', '', 'B', 'english', 'pilot boat')
```

`SearchHeadline` writes `"ts_headline"`, the document with the query's matches marked. Its options, kept under PostgreSQL's names (`"StartSel"`, `"MaxWords"` and the rest) when given, are written by `SearchHeadline.as_sql` into one string parameter with the connection's `compose_sql`, which on PostgreSQL has the driver format each value through a cursor (`django/contrib/postgres/search.py:SearchHeadline.as_sql`, `django/db/backends/postgresql/psycopg_any.py:mogrify`). So a headline with options cannot be compiled without a connection: the example's guard stopped one at the cursor.

## Trigrams and `Unaccent`

Trigram similarity compares strings by spelling rather than by words, through PostgreSQL's pg_trgm extension, which the migration operation `TrigramExtension` installs and no system check looks for. `TrigramSimilarity` writes `"SIMILARITY"` of an expression and a string; `TrigramWordSimilarity` and `TrigramStrictWordSimilarity` write `"WORD_SIMILARITY"` and `"STRICT_WORD_SIMILARITY"` with the string first; the distances, `TrigramDistance`, `TrigramWordDistance` and `TrigramStrictWordDistance`, are written by their `arg_joiner` as the operators `"<->"`, `"<<->"` and `"<<<->"` (`django/contrib/postgres/search.py:TrigramBase`, `django/contrib/postgres/search.py:TrigramWordBase`). The lookups `"trigram_similar"`, `"trigram_word_similar"` and `"trigram_strict_word_similar"`, registered by `PostgresConfig.ready` on the same two fields, are `PostgresOperatorLookup`s whose operators, `"%%"`, `"%%>"` and `"%%>>"`, are PostgreSQL's with the percent sign doubled for the driver (`django/contrib/postgres/lookups.py:TrigramSimilar`, [Lookups: `Lookup`, `BuiltinLookup` and the standard comparisons](../expressions/lookups.md)).

```text
Bulletin.objects.annotate(similarity=TrigramSimilarity("title", "Brakewater")).filter(similarity__gt=0.3).values("title")
WHERE SIMILARITY("notes_bulletin"."title", %s) > %s
params: ('Brakewater', 0.3)
```

`Unaccent`, the lookup `"unaccent"`, is a `Transform` writing `"UNACCENT"`, from the extension that `UnaccentExtension` installs. It is bilateral, so the value compared goes through the same function (`django/contrib/postgres/lookups.py:Unaccent`, [Transforms and database functions: `Transform` and `Func`](../expressions/functions.md)):

```text
Bulletin.objects.filter(title__unaccent="Café").values("title")
WHERE UNACCENT("notes_bulletin"."title") = (UNACCENT(%s))
params: ('Café',)
```
