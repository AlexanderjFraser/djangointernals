---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# `filter`, `exclude` and `Q` objects

`QuerySet.filter` and `QuerySet.exclude` gather their arguments into one `Q` object, a tree of conditions that can be joined with `&`, `|` and `^` and negated with `~`, and hand it to the query through `Query.add_q`. `FilteredRelation` puts a `Q` into the condition of a join.

A condition has to be written down before there is anything to test it against: a model's `Meta` holds one for a check constraint, and a relation field may hold one that narrows the rows it can point at, with no query in sight. So a condition is written as a **`Q` object**: a node with a list of children, a word that joins them, `"AND"`, `"OR"` or `"XOR"`, and a mark that negates the whole. A child is a pair of a name and a value, `("tonnage__gt", 1000)`, or another `Q`, or an expression that is true or false. A `Q` matches no name against a model: that waits until a query is given the tree.

The examples are the shipping line of the chapter's opening page, [QuerySets](../querysets.md): a Sailor has a name, a ship and the moment it signed on, and a Ship has a name, a tonnage, a home port and perhaps a captain.

## From arguments to one tree

`QuerySet.filter` and `QuerySet.exclude` each call `QuerySet._filter_or_exclude` with their positional arguments, their keyword arguments and a flag that says whether to negate: false from `filter`, true from `exclude` (`django/db/models/query.py:QuerySet.filter`, `django/db/models/query.py:QuerySet.exclude`). Before that, each refuses a queryset whose query is a combination made by `QuerySet.union`, `QuerySet.intersection` or `QuerySet.difference` ([Combining querysets: the operators and `union`](combining.md)).

Given any argument at all, `_filter_or_exclude` refuses a queryset whose query has been sliced, with `TypeError` ([Evaluation and the result cache](evaluation.md)). It takes a queryset from `QuerySet._chain`, a clone unless cloning has been switched off. And it calls `QuerySet._filter_or_exclude_inplace` on that queryset, then returns it (`django/db/models/query.py:QuerySet._filter_or_exclude`). One kind of queryset puts the last step off: where a related manager has marked its queryset, the three arguments are stored on the queryset that `_chain` returned, and nothing is built until the query is first read ([Clones: how a queryset is built](chaining.md)).

`_filter_or_exclude_inplace` is where the tree is made. It builds `Q(*args, **kwargs)`, inverts it with `~` when the flag is set, and hands the result to the query with `Query.add_q` (`django/db/models/query.py:QuerySet._filter_or_exclude_inplace`, `django/db/models/sql/query.py:Query.add_q`).

What follows was recorded from a running Django, on SQLite: a line at the left is Python that was run, with its value or the exception it raised after `->` where it is an expression; under it are the calls it set going, nested as they were made, with only the calls this passage is about written down; and a line that begins `SQL` is a statement as Django handed it to its cursor.

```text recording=querysets
others = Sailor.objects.exclude(name='Ada', ship=petrel)
  QuerySet.exclude(name='Ada', ship=<Ship: Petrel>)
    QuerySet._filter_or_exclude(negate=True, args=(), kwargs={'name': 'Ada', 'ship': <Ship: Petrel>})
      QuerySet._filter_or_exclude_inplace(negate=True, args=(), kwargs={'name': 'Ada', 'ship': <Ship: Petrel>})
        Query.add_q(q_object=<Q: (NOT (AND: ('name', 'Ada'), ('ship', <Ship: Petrel>)))>)
list(others)  ->  [<Sailor: Bram>, <Sailor: Cora>, <Sailor: Dag>]
  SQL SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" WHERE NOT ("crew_sailor"."name" = %s AND "crew_sailor"."ship_id" = %s) with params ('Ada', 1)
```

The two keyword arguments became two pairs in one `Q`, and the `Q` was negated as a whole. So the statement says that not both conditions hold: `exclude` with two conditions leaves out the rows that meet both, here Ada of the Petrel, and keeps Bram, who meets one.

`add_q` adds what it makes of the tree to the where clause the query already has, under `"AND"`. A condition is never replaced, so each call of `filter` or `exclude` narrows what the calls before it left.

## Where the queryset's part ends

`Query.add_q` is the end of the queryset's part. The query walks the tree in `Query._add_q`: for each `Q` it makes a node of its where clause, a `WhereNode`, with the `Q`'s connector and negation, and passes each child to `Query.build_filter`, which goes by the child's kind. A dictionary is refused with `FieldError`. A `Q` goes back to `_add_q`. Something that has a method `resolve_expression` is resolved as an expression, and refused with `TypeError` unless it is conditional. Anything else is unpacked as a pair, a name and a value (`django/db/models/sql/query.py:Query._add_q`, `django/db/models/sql/query.py:Query.build_filter`).

Only then is a name read: split at each `"__"`, matched against the model's fields, turned into joins and a comparison. That is the subject of [From QuerySet to SQL](../sql.md); the last part of a name, `"gt"` or `"startswith"`, is found in the registry of [The lookup registry: `RegisterLookupMixin`](lookups.md).

Since nothing before `build_filter` examines a child, a wrong argument is found late, and a call with none is not an error at all:

```text recording=querysets
Sailor.objects.filter(Q(name='Ada'), 5)  ->  raises TypeError: cannot unpack non-iterable int object
Sailor.objects.filter().query.where, Sailor.objects.exclude().query.where  ->  (<WhereNode: (AND: )>, <WhereNode: (AND: )>)
```

The first message is Python's own, from the line that unpacks a pair: `Q` took the 5 as a child without complaint. In the second line `QuerySet.filter` and `QuerySet.exclude` were given no arguments: each made an empty `Q`, the query made an empty node of it, and `add_q`, finding the node empty, left the where clause as it was.

## `complex_filter`

`QuerySet.complex_filter` takes one argument, a `Q` or a dictionary of keyword arguments, and returns a filtered queryset. It is there for `ForeignObjectRel.limit_choices_to`, the option of a relation field that narrows the rows it may point at, which a project may write in either form: the docstring says that the method exists to support features of the framework such as that one, and that other methods will usually be more natural (`django/db/models/query.py:QuerySet.complex_filter`).

A dictionary goes to `QuerySet._filter_or_exclude` as the keyword arguments of an ordinary `QuerySet.filter`. A `Q` is added with `Query.add_q` directly, without the test for a slice that `_filter_or_exclude` makes:

```text recording=querysets
list(Sailor.objects.order_by('id')[:2].complex_filter(Q(name='Dag')))  ->  [<Sailor: Dag>]
  SQL SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" WHERE "crew_sailor"."name" = %s ORDER BY "crew_sailor"."id" ASC LIMIT 2 with params ('Dag',)
```

The statement has the condition and the limit both, where `filter` on a sliced queryset is refused ([Evaluation and the result cache](evaluation.md)).

## A `Q` is a node of a tree

`Q` is a subclass of `Node`, a small class of `django/utils/tree.py` that the where clause of a query is built on too (`django/utils/tree.py:Node`, `django/db/models/query_utils.py:Q`). Its list of children is `Node.children`, the word that joins them is `Node.connector`, and the mark that negates the whole is `Node.negated`. `Node.__len__` is the number of children and `Node.__bool__` is whether there are any, so an empty `Q` is false.

`Q.__init__` makes the list from its arguments: the positional ones as they were given, and then the keyword ones as pairs, sorted by name (`django/db/models/query_utils.py:Q.__init__`). The sorting is why two `Q` objects written with the same keywords in another order are equal. Beside the conditions it takes two keyword arguments of its own, written `_connector="OR"` and `_negated=True`.

A connector is one of `Q.AND`, `Q.OR` and `Q.XOR`, which are the strings `"AND"`, `"OR"` and `"XOR"`. A `Q` made with none takes `Q.default`, which is `"AND"`. `Q._check_connector` refuses any other value with `ValueError`, both when a `Q` is made by its constructor and when one is made by `Q.create`, the class method that the operators use.

```text recording=querysets
Q(name='Ada', ship=1)  ->  <Q: (AND: ('name', 'Ada'), ('ship', 1))>
Q(ship=1, name='Ada') == Q(name='Ada', ship=1), hash(Q(ship=1, name='Ada')) == hash(Q(name='Ada', ship=1))  ->  (True, True)
...
Q(Q(name='Ada') | Q(name='Dag'), ship=1).children  ->  [<Q: (OR: ('name', 'Ada'), ('name', 'Dag'))>, ('ship', 1)]
...
Q(name='Ada', _connector='OR', _negated=True)  ->  <Q: (NOT (OR: ('name', 'Ada')))>
Q(name='Ada', _connector='NAND')  ->  raises ValueError: connector must be one of 'AND', 'OR', 'XOR', or None.
...
Q.default, Q.conditional, Q.connectors  ->  ('AND', True, (None, 'AND', 'OR', 'XOR'))
```

The line that asks for the children shows a positional `Q` kept whole as the first child, a node inside the node, ahead of the pair. In the last, `Q.connectors` is the tuple that `_check_connector` tests against, and `Q.conditional` is the mark by which the rest of Django knows something that is true or false of a row: `Query.build_filter` asks it of an expression, and a `CheckConstraint` asks it of its condition.

## The two keyword arguments that are refused

Before it builds the `Q`, `QuerySet._filter_or_exclude_inplace` looks among the keyword arguments for the two that `Q.__init__` keeps for itself, `"_connector"` and `"_negated"`, the members of `PROHIBITED_FILTER_KWARGS`, and raises `TypeError` if it finds either (`django/db/models/query.py:QuerySet._filter_or_exclude_inplace`, `django/db/models/query_utils.py:PROHIBITED_FILTER_KWARGS`).

```text recording=querysets
Sailor.objects.filter(name='Ada', _connector='OR')  ->  raises TypeError: The following kwargs are invalid: '_connector'
```

Every other keyword given to `QuerySet.filter` becomes a condition; without the test, one of these two would pass through `Q(*args, **kwargs)` and set the connector or the negation of the whole tree. `When.__init__`, which also makes a `Q` of its keyword arguments, makes the same test (`django/db/models/expressions.py:When.__init__`).

> **Why.** A program that expands a dictionary it did not write into a call of `filter` lets the dictionary's author choose the keywords, and the connector of a `Q` ends as text in the statement: it is given to the node of the where clause made from the `Q`, which writes it out (`django/db/models/sql/where.py:WhereNode.as_sql`). The release notes of 5.2.8 record that `filter`, `QuerySet.exclude`, `QuerySet.get` and `Q` were open to SQL injection through `"_connector"` in this way (`docs/releases/5.2.8.txt`).

## Combining and negating

The operators `&`, `|` and `^` are `Q.__and__`, `Q.__or__` and `Q.__xor__`, and each calls `Q._combine` with the other operand and a connector (`django/db/models/query_utils.py:Q._combine`). `_combine` first asks whether the other operand is conditional, by its attribute of that name, and raises `TypeError` with the operand itself as the message when the attribute is `False` or missing: a `Q` combines with another `Q`, and with an expression whose output is a boolean, such as `Exists(...)`, and with nothing else.

Where the `Q` on the left is empty, the result is a copy of the other operand, and where the other is an empty `Q`, a copy of the left one. Neither of these two short cuts takes the operator's connector. Otherwise `_combine` makes a new, empty node with the operator's connector and adds the two operands to it. The node is made by `Q.create`, which tests the connector and hands on to `Node.create`, a method that makes a plain `Node` and then sets the object's class to the class it was called on (`django/utils/tree.py:Node.create`).

`Node.add` is what keeps the tree shallow (`django/utils/tree.py:Node.add`). As `_combine` calls it, with the receiving node's own connector, it does one of two things. A node that is not negated, and that has that connector or one child only, has its children moved up into the receiver's list and is itself dropped; the method's docstring calls this squashing. Anything else is appended whole: a negated node, a node of several children under another connector, a pair, an expression.

```text recording=querysets
Q(name='Ada') | Q(name='Dag')  ->  <Q: (OR: ('name', 'Ada'), ('name', 'Dag'))>
Q(name='Ada') & Q(ship=1) & Q(pk__gt=0)  ->  <Q: (AND: ('name', 'Ada'), ('ship', 1), ('pk__gt', 0))>
(Q(name='Ada') | Q(name='Dag')) & Q(ship=1)  ->  <Q: (AND: (OR: ('name', 'Ada'), ('name', 'Dag')), ('ship', 1))>
...
Q() & Q(name='Ada'), Q(name='Ada') | Q(), bool(Q()), len(Q(name='Ada', ship=1))  ->  (<Q: (AND: ('name', 'Ada'))>, <Q: (AND: ('name', 'Ada'))>, False, 2)
```

In the first line each operand was a node of one pair, and both were squashed into the new node. In the second, three `Q` objects joined by `&` came out as one node of three pairs, the second `&` having taken the two children of the node the first one made. In the third the node made by `|` kept its place as a child, having another connector and two children. The last line is the short cuts, with an empty node's falsity and a node's length: the `|` with an empty `Q` returned the left operand with its own `"AND"`.

`~` is `Q.__invert__`: a copy of the `Q` with `Node.negated` flipped by `Node.negate`. Negation belongs to a node and never to a pair: `~Q(name='Ada')` is a negated node that holds one pair, and `Node.add` will not squash it. The negated copy has the very list of children that its original has, `Node.__copy__` giving the new node that list and not a copy of it (`django/utils/tree.py:Node.__copy__`). The shared list is safe with the operators, none of which changes an operand: `_combine` adds to a node it has just made, and `__invert__` changes only the flag of its copy.

Between two querysets `&`, `|` and `^` are methods of `QuerySet` that merge two queries ([Combining querysets: the operators and `union`](combining.md)). Between two boolean expressions they make a `Q` of the pair: `Combinable.__and__` and its two fellows wrap each side in a `Q` when both are conditional (`django/db/models/expressions.py:Combinable.__and__`).

## Equality, hashing and `deconstruct`

`Q.deconstruct` returns what would make the `Q` again: its path, which for `Q` itself is `"django.db.models.Q"`; the children, as positional arguments; and as keyword arguments the connector, if it is not the default, and the negation, if it is set (`django/db/models/query_utils.py:Q.deconstruct`). The keywords a `Q` was written with do not come back as keywords: they became pairs when it was made, and a pair given positionally is a child like any other.

```text recording=querysets
Q(name='Ada').deconstruct(), (~Q(name='Ada') | Q(ship=1)).deconstruct()  ->  (('django.db.models.Q', (('name', 'Ada'),), {}), ('django.db.models.Q', (<Q: (NOT (AND: ('name', 'Ada')))>, ('ship', 1)), {'_connector': 'OR'}))
```

`Q.identity` is a tuple of the path, those keyword arguments and the children, with the value of each pair passed through `make_hashable` (`django/db/models/query_utils.py:Q.identity`, `django/utils/hashable.py:make_hashable`). `Q.__eq__` compares the identities of two `Q` objects and `Q.__hash__` hashes the identity. Children are compared in order, and only keyword arguments are sorted.

Migrations are what need a `Q` to take itself apart. A `Q` in the condition of a constraint is written into a migration file by a serializer that calls `deconstruct` and writes a call of the path with those arguments (`django/db/migrations/serializer.py:DeconstructibleSerializer.serialize`). And the autodetector notices a changed condition by equality: a `CheckConstraint` compares its condition with `==` (`django/db/migrations/autodetector.py:MigrationAutodetector.create_altered_constraints`) ([Constraints and indexes](../models/constraints.md), [Migrations](../migrations.md)).

## Looking inside a tree

A `Q` can be read without a query. `Q.flatten` is a generator over the tree, depth first: the `Q` itself, and then for each child what the child flattens to, where a pair counts as its value alone (`django/db/models/query_utils.py:Q.flatten`). `CheckConstraint.check` looks through what a condition flattens to for a `RawSQL`, to warn that such a constraint will not be validated (`django/db/models/constraints.py:CheckConstraint.check`).

`Q.replace_expressions` serves a `Q` that stands inside an expression which is to be worked out for one instance. It takes a dictionary from expressions to their replacements and, unless the dictionary is empty, returns a new `Q` in which each pair it can replace has become a comparison (`django/db/models/query_utils.py:Q.replace_expressions`). `Model._get_field_expression_map` builds such a dictionary, from an `F` of each field's name to the instance's value, and calls `replace_expressions` on the expression of a generated field; `UniqueConstraint.validate` does so with a constraint's expressions; and an expression that holds a `Q` passes the call down to it (`django/db/models/base.py:Model._get_field_expression_map`, `django/db/models/expressions.py:BaseExpression.replace_expressions`) ([Validating an instance](../models/validation.md)).

```text recording=querysets
Q(tonnage__gt=0).replace_expressions({F('tonnage'): Value(480)}).children  ->  [IntegerGreaterThan(Value(480), 0)]
```

The pair `("tonnage__gt", 0)` became an instance of a lookup class, with the value where the name was.

## A `Q` as an expression

A `Q` can stand where an expression is wanted: as an annotation, or as the condition of a `When`. Anything in such a place is asked to resolve itself against the query, and `Q.resolve_expression` is the method that answers (`django/db/models/query_utils.py:Q.resolve_expression`). It calls `Query._add_q`, the method `Query.add_q` is built on, which returns the node of a where clause that the tree makes, and with it the joins that the tree's conditions had it settle as inner joins. It has those joins promoted by `Query.promote_joins`, and returns the node for the query to use as an expression; nothing is added to the query's own where clause (`django/db/models/sql/query.py:Query._add_q`).

> **Why.** A comment in the method gives the reason for the promotion: new joins have to be made left outer joins so that, when a `Q` is used as an expression, rows are not filtered out by the joins. `promote_joins` makes a join outer where the join is marked nullable, or where the join it hangs from is outer already (`django/db/models/sql/query.py:Query.promote_joins`).

A ship's captain may be null. Here one condition on the captain is given as an annotation and then as a filter:

```text recording=querysets
[(ship.name, ship.cora) for ship in Ship.objects.annotate(cora=Q(captain__name='Cora')).order_by('name')]  ->  [('Gannet', True), ('Petrel', None)]
  SQL SELECT "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id", "crew_sailor"."name" = %s AS "cora" FROM "fleet_ship" LEFT OUTER JOIN "crew_sailor" ON ("fleet_ship"."captain_id" = "crew_sailor"."id") ORDER BY "fleet_ship"."name" ASC with params ('Cora',)
[ship.name for ship in Ship.objects.filter(captain__name='Cora')]  ->  ['Gannet']
  SQL SELECT "fleet_ship"."id", "fleet_ship"."name", "fleet_ship"."tonnage", "fleet_ship"."home_id", "fleet_ship"."captain_id" FROM "fleet_ship" INNER JOIN "crew_sailor" ON ("fleet_ship"."captain_id" = "crew_sailor"."id") WHERE "crew_sailor"."name" = %s ORDER BY "fleet_ship"."name" ASC with params ('Cora',)
```

As an annotation the comparison is selected as a column, the table of sailors is joined with a left outer join, and both ships are in the result, the Petrel with `None` for its answer. As a filter the join is an inner join, the condition is in the where clause, and the Gannet alone comes back.

A `When` reaches `Q.resolve_expression` through its own resolving, which resolves each expression it is made of; `When.__init__` accepts a `Q`, a boolean expression, or keyword arguments of which it makes a `Q`, and refuses an empty `Q` with `ValueError` (`django/db/models/expressions.py:When.__init__`).

## `Q.check`: a condition put to the database

`Q.check` answers one question: do these values meet this condition? It takes a dictionary from names to values and the alias of a database, and it does not work the answer out in Python: it has the database evaluate the condition, in a statement that selects from no table of its own (`django/db/models/query_utils.py:Q.check`).

The method makes a `Query` with no model. Each entry of the dictionary becomes an annotation of that name which is not selected, a plain value being wrapped in a `Value` first, and one more annotation, the constant 1 under the name `"_check"`, is the one thing selected (`django/db/models/sql/query.py:Query.add_annotation`, `django/db/models/expressions.py:Value`). Then the `Q` is added as the query's filter, with `Query.add_q`. A query with no model has no fields, so a name in the condition can only find the annotation of that name, and the condition is compiled with the values where columns would have been. The statement is run for a single row: a row means the condition held, and no row that it did not.

```text recording=querysets
Q.check: the condition is put to the database, with values in place of columns
    Q(tonnage__gt=0).check({'tonnage': 480})  ->  True
      SQL SELECT %s AS "_check" WHERE %s > %s with params (1, 480, 0)
    Q(tonnage__gt=0).check({'tonnage': 0})  ->  False
      SQL SELECT %s AS "_check" WHERE %s > %s with params (1, 0, 0)
    Q(tonnage__gt=F('crates')).check({'tonnage': 480, 'crates': 40})  ->  True
      SQL SELECT %s AS "_check" WHERE %s > %s with params (1, 480, 40)
    Q(tonnage__gt=0).check({})  ->  raises FieldError: Cannot resolve keyword 'tonnage' into field. Choices are: _check
```

None of the three statements has a table in it. In the third the condition compares one name with another through an `F`, and both were found among the annotations. In the fourth line the dictionary lacks the name: `add_q` raises `FieldError`, and the one choice it can offer is `"_check"`.

Where the connection is inside an `atomic` block, `check` runs the statement in an `atomic` block of its own, and outside one it opens nothing (`django/db/transaction.py:atomic`) ([Database backends](../backends.md)).

```text recording=querysets
with transaction.atomic(): checked = Q(tonnage__gt=0).check({'tonnage': 480})
  SQL BEGIN
  SQL SAVEPOINT "s(the thread)_x2"
  SQL SELECT %s AS "_check" WHERE %s > %s with params (1, 480, 0)
  SQL RELEASE SAVEPOINT "s(the thread)_x2"
checked  ->  True
```

The outer block began a transaction, and the block that `check` opened inside it was a savepoint, made before the statement and released after it. A `DatabaseError` raised by the statement does not leave the method: it is logged as a warning to the logger `"django.db.models"`, and the answer is `True`.

The callers are constraints, validating an instance. `CheckConstraint.validate` wraps its condition in a `Q` and checks it against the instance's values; `UniqueConstraint.validate`, for a constraint that has a condition of its own, joins the condition with `&` to a test for another such row, as the exclusion constraint of `django.contrib.postgres` does (`django/db/models/constraints.py:CheckConstraint.validate`, `django/db/models/constraints.py:UniqueConstraint.validate`, `django/contrib/postgres/constraints.py:ExclusionConstraint.validate`). Where the values come from, and what `Model.full_clean` makes of the answer, is in [Validating an instance](../models/validation.md) ([Constraints and indexes](../models/constraints.md)).

## `FilteredRelation`: a condition in the join

`FilteredRelation` puts a condition into the `"ON"` of a join, where a filter puts one into the where clause. In the where clause a condition removes rows from the result; in a join it decides which related rows are joined to each row, and under an outer join a row left with none stays in the result. The object is a relation's name and a `Q`, given to `QuerySet.annotate` under a new name by which the narrowed relation is known from then on (`django/db/models/query_utils.py:FilteredRelation`).

```text recording=querysets
list(Ship.objects.annotate(veterans=FilteredRelation('crew', condition=Q(crew__signed_on__year__lt=2020))).values_list('name', 'veterans__name'))  ->  [('Gannet', 'Cora'), ('Petrel', 'Ada')]
  SQL SELECT "fleet_ship"."name" AS "name", "veterans"."name" AS "veterans__name" FROM "fleet_ship" LEFT OUTER JOIN "crew_sailor" "veterans" ON ("fleet_ship"."id" = "veterans"."ship_id" AND ("veterans"."signed_on" < %s)) ORDER BY 1 ASC with params ('2020-01-01 00:00:00',)
```

The table of sailors is joined under the alias `"veterans"`, the name given to `annotate`, and the condition stands inside the `"ON"`, written against that alias. Each ship is paired with those of its crew who signed on before 2020, in these rows one sailor for each ship.

`QuerySet._annotate` does not treat a `FilteredRelation` as an annotation: it passes it, with the name, to `Query.add_filtered_relation` ([Annotations, ordering and the other methods that change the query](methods.md)). That method sets the name on the object it was given, as `FilteredRelation.alias`. It refuses, with `ValueError`, a name in the condition that has more than one field beyond the relation name's, as `"crew__ship__name"` has for the relation `"crew"`. Then it stores, in `Query._filtered_relations` under the name, a clone whose condition has been rewritten to start from the alias (`django/db/models/sql/query.py:Query.add_filtered_relation`, `django/db/models/sql/query.py:rename_prefix_from_q`).

```text recording=querysets
with_veterans = Ship.objects.annotate(veterans=FilteredRelation('crew', condition=Q(crew__signed_on__year__lt=2020)))
list(with_veterans.query._filtered_relations), with_veterans.query._filtered_relations['veterans'].alias, with_veterans.query._filtered_relations['veterans'].condition, sorted(with_veterans.query.alias_map)  ->  (['veterans'], 'veterans', <Q: (AND: ('veterans__signed_on__year__lt', 2020))>, [])
```

After `annotate` the query holds the one filtered relation, with its alias and with its condition rewritten, and has joined nothing: its map of aliases is empty. A later name that begins with the alias brings the join in, as `"veterans__name"` did in the statement above. Resolving such a name, the query finds the alias among its filtered relations, takes the relation from the stored object, and has the join carry a clone of that object (`django/db/models/sql/query.py:Query.names_to_path`, `django/db/models/sql/query.py:Query.setup_joins`). As the join is added, `Query.join` has the clone resolve itself, and `Join.as_sql` compiles it into the `"ON"` after the join's own columns (`django/db/models/sql/query.py:Query.join`, `django/db/models/sql/datastructures.py:Join.as_sql`) ([From QuerySet to SQL](../sql.md)).

`FilteredRelation.resolve_expression` returns a clone with `FilteredRelation.resolved_condition` set to what `Query.build_filter` makes of the condition, a node of a where clause, and `FilteredRelation.as_sql` compiles that node (`django/db/models/query_utils.py:FilteredRelation.resolve_expression`).

> **Why.** The condition is kept twice, as a `Q`, in `FilteredRelation.condition`, and as the resolved node. A comment in the constructor says why: the first has to stay unchanged so that `Join.__eq__` stays stable, and a join can be reused, once the filtered relation has been resolved. A join's identity includes its filtered relation, and `FilteredRelation.__eq__` compares the relation's name, the alias and the `Q` (`django/db/models/sql/datastructures.py:Join.identity`).

`QuerySet.prefetch_related` and `QuerySet.only` each compare the first part of what they are given with the query's filtered relations, and raise `ValueError` on a match ([`prefetch_related`: related objects in a second query](prefetch.md), [Deferred fields and fetch modes in a queryset](deferred.md)).
