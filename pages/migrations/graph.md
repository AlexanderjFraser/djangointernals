---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# The migration graph: `MigrationGraph`

The migration graph, a `MigrationGraph`, has a node for each migration the loader keeps and an edge for each dependency the loader gives it, and it is what orders migrations. `MigrationGraph.forwards_plan` and `MigrationGraph.backwards_plan` walk it for an order in which migrations can be applied and unapplied, `MigrationGraph.root_nodes` and `MigrationGraph.leaf_nodes` find where an application's history begins and ends, and `MigrationGraph.make_state` builds the project state at a node.

Migrations have to be applied in an order, and the numbers in their files' names do not give it: the numbering is a convention that helps in listing the files, and makes no migration depend on another (`django/db/migrations/graph.py:MigrationGraph`). What gives the order is each migration's dependencies, which name the migrations that must be applied before it, and its `Migration.run_before`, which names those to be applied after it, a dependency declared from the other end (`django/db/migrations/migration.py:Migration`).

The **graph** is those declarations as a structure that can be asked. The loader makes it, in `MigrationLoader.build_graph` ([Finding migrations: `MigrationLoader`](loader.md)), and nothing in Django changes it once that has returned. The executor makes its plans from it, and the autodetector asks it where an application's history ends. A graph holds no connection, and none of its methods asks which migrations are applied.

## Two dictionaries by key: `nodes` and `node_map`

A `MigrationGraph` is two dictionaries with the same keys, a **key** being the pair of an application's label and a migration's name (`django/db/migrations/graph.py:MigrationGraph.__init__`). `MigrationGraph.nodes` maps a key to its migration, which is how a key becomes the migration to run. `MigrationGraph.node_map` maps a key to a **node**, a `Node`, which holds the edges (`django/db/migrations/graph.py:Node`): `Node.parents` is the set of the nodes this one depends on, its **parents**, and `Node.children` the set of those that depend on it, so that an edge can be followed from either end. A `Node` compares, hashes and sorts as its key.

`MigrationGraph.add_node` enters a key in both dictionaries, and `MigrationGraph.add_dependency`, given a child's key and a parent's key, puts each of the two nodes in the other's set (`django/db/migrations/graph.py:MigrationGraph.add_dependency`). Here is the loader's graph of harbour, the chapter's example project of four applications ([Migrations](../migrations.md)), after its first makemigrations. The recordings are of a running Django: a line of Python is as it was run; a line that names a method by its declaring class is a call, set in under what made it, with the migration it was called on in square brackets; `->` is followed by a value or by the exception raised; only the lines a passage is about are written, and what ran between them is left out.

```text recording=migrations
str(graph)  ->  'Graph: 5 nodes, 7 edges'
...
graph.nodes['yard', '0001_initial']  ->  yard.0001_initial
graph.node_map['yard', '0001_initial']  ->  the node ('yard', '0001_initial')
...
sorted(node.key for node in graph.node_map['fleet', '0001_initial'].parents)  ->  [('crew', '0001_initial')]
sorted(node.key for node in graph.node_map['fleet', '0001_initial'].children)  ->  [('crew', '0002_initial'), ('office', '0001_initial'), ('yard', '0001_initial')]
```

```text figure=harbours-graph
harbour's graph after the first makemigrations: 5 nodes, 7 edges
an arrow runs from a migration to one it depends on, its parent

crew.0001_initial
fleet.0001_initial    ->  crew.0001_initial
office.0001_initial   ->  crew.0001_initial, fleet.0001_initial
crew.0002_initial     ->  crew.0001_initial, fleet.0001_initial, office.0001_initial
yard.0001_initial     ->  fleet.0001_initial
```

*Harbour's first five migrations, with the one that depends on nothing at the top. Each of the others depends on it, yard's only through fleet's.*

## Plans: `forwards_plan` and `backwards_plan`

`MigrationGraph.forwards_plan` answers what must be applied before a migration can be: it takes a key and returns the keys of everything the migration depends on, directly or through others, each after everything it depends on, ending with the key given. `MigrationGraph.backwards_plan` answers what must be unapplied before a migration can be: the keys of everything that depends on it, directly or through others, each after its own dependents, ending again with the key given. Both call `MigrationGraph.iterative_dfs`, which follows `Node.parents` for the first and, with `forwards=False`, `Node.children` for the second (`django/db/migrations/graph.py:MigrationGraph.iterative_dfs`).

```text recording=migrations
graph.forwards_plan(('crew', '0002_initial'))  ->  [('crew', '0001_initial'), ('fleet', '0001_initial'), ('office', '0001_initial'), ('crew', '0002_initial')]
...
graph.backwards_plan(('fleet', '0001_initial'))  ->  [('yard', '0001_initial'), ('crew', '0002_initial'), ('office', '0001_initial'), ('fleet', '0001_initial')]
```

`iterative_dfs` is a depth-first walk that lists a node on the way back from it. It keeps a stack of its own: a node taken off the stack for the first time is put back with a mark and its parents (for a backwards plan, its children) are put on top of it, and when the marked node comes off again everything that has to come before it has been listed, and it is listed. A set of the nodes already listed keeps a node reached by several paths from being listed twice. The method loops and does not call itself, so a long chain of dependencies makes a long list and not a deep call stack.

What orders such a list, then, is the edges and, where they leave a choice, the keys. The set the walk follows has no order; the walk sorts it, puts its nodes on the stack in the order of their keys and takes them off in the reverse, and so goes first into the one whose key sorts last. That is how yard's migration comes first in the backwards plan for fleet's: of fleet's three children it sorts last. So the same nodes and edges give the same plan.

`MigrationExecutor.migration_plan` makes the executor's plan from these lists and the migrations it counts as applied: of a forwards plan it keeps the migrations not among them, of a backwards plan those that are ([Applying a plan: `MigrationExecutor`](executor.md)).

## Root nodes and leaf nodes

`MigrationGraph.root_nodes` and `MigrationGraph.leaf_nodes` say where an application's history begins and ends, and look at edges within the application only: a **root node** has no parent in its own application, a **leaf node** no child in its own (`django/db/migrations/graph.py:MigrationGraph.leaf_nodes`). Each returns a sorted list of keys, for every application or, given a label, for one.

```text recording=migrations
graph.root_nodes()  ->  [('crew', '0001_initial'), ('fleet', '0001_initial'), ('office', '0001_initial'), ('yard', '0001_initial')]
graph.leaf_nodes()  ->  [('crew', '0002_initial'), ('fleet', '0001_initial'), ('office', '0001_initial'), ('yard', '0001_initial')]
```

Fleet's one migration is fleet's root and its leaf, though it has a parent in crew and children in three applications. A dependency may have `"__first__"` or `"__latest__"` in place of a migration's name; where the loader makes a key of one, the key is the first of the root nodes, or of the leaf nodes, of the application it names (`django/db/migrations/loader.py:MigrationLoader.check_key`; [Finding migrations: `MigrationLoader`](loader.md)). The leaf nodes, each the most current version of its application's schema, are migrate's targets when it is given no migration's name ([The migrate command, showmigrations and sqlmigrate](migrate.md)), and the autodetector has an application's first new migration depend on its first leaf node ([From operations to migrations: dependencies, order and names](dependencies.md)).

More than one leaf node in an application is an error, usually the result of a merge in version control, and the graph accepts it. Later in yard's history a migration from a colleague's branch stands beside one that makemigrations wrote, both depending on the same migration of yard:

```text recording=migrations
loader.graph.leaf_nodes('yard')  ->  [('yard', '0006_dock_covered'), ('yard', '0006_long_dock')]
```

`MigrationLoader.detect_conflicts` reports such an application, and `makemigrations --merge` writes a migration that depends on both leaves ([The makemigrations command](makemigrations.md)).

## The project state at a node: `make_state`

`MigrationGraph.make_state` builds the project state as it stands once a node's migration has run: it makes a `ProjectState` with no model states ([Project state: `ProjectState` and its model states](state.md)) and calls `Migration.mutate_state` of each migration of the node's forwards plan on it, in order, with `preserve=False`, which changes that one state in place (`django/db/migrations/graph.py:MigrationGraph.make_state`, `django/db/migrations/migration.py:Migration.mutate_state`). Only the operations' state halves run, and no database is touched. Given several keys, or none and so every leaf node, `make_state` has `MigrationGraph._generate_plan` join their forwards plans into one list with no key twice. With `at_end=False` the key given is left out of the list, and the state is the one before its migration:

```text recording=migrations
before = graph.make_state(('yard', '0001_initial'), at_end=False)
  MigrationGraph.make_state(nodes=('yard', '0001_initial'), at_end=False)
    MigrationGraph._generate_plan(nodes=[('yard', '0001_initial')], at_end=False)  ->  [('crew', '0001_initial'), ('fleet', '0001_initial')]
    Migration.mutate_state(preserve=False)  [crew.0001_initial]
    Migration.mutate_state(preserve=False)  [fleet.0001_initial]
    -> a ProjectState of 5 model states, its registry not rendered
```

The state before a migration is what sqlmigrate starts from ([The migrate command, showmigrations and sqlmigrate](migrate.md)). `make_state` gives the new state the labels it is passed as `ProjectState.real_apps`, the applications whose models are to come from the main registry when the state is rendered; its one caller in Django, `MigrationLoader.project_state`, passes the unmigrated applications, those with no package of migrations (`django/db/migrations/loader.py:MigrationLoader.project_state`). For a graph with no nodes `make_state` returns a `ProjectState` made without them.

## A dependency on a migration that is not there

`MigrationGraph.add_dependency`, given a key that is no node, first makes a `DummyNode` for it and links it like any other: a node whose migration in `MigrationGraph.nodes` is `None`, carrying the message of the error it stands for and the migration that named it, which is what `add_dependency` is passed a migration for (`django/db/migrations/graph.py:MigrationGraph.add_dependency`, `django/db/migrations/graph.py:DummyNode`). `MigrationGraph.validate_consistency` raises that error for a dummy node still in the graph: a `NodeNotFoundError`, a `LookupError` whose `NodeNotFoundError.node` is the missing key and `NodeNotFoundError.origin` the migration (`django/db/migrations/exceptions.py:NodeNotFoundError`). `add_dependency` calls it once it has linked the two nodes, unless it is passed `skip_validation=True`. Here small is a graph of the recording's own with one node, and yard_first is that node's migration, yard.0001_initial:

```text recording=migrations
small.add_dependency(yard_first, ('yard', '0001_initial'), ('fleet', '0009_missing'), skip_validation=True)
small.node_map['fleet', '0009_missing']  ->  the DummyNode ('fleet', '0009_missing')
small.nodes['fleet', '0009_missing']  ->  None
small.validate_consistency()  ->  raises NodeNotFoundError: Migration yard.0001_initial dependencies reference nonexistent parent node ('fleet', '0009_missing')
```

The loader passes `skip_validation=True` with every edge and makes the check once, after the last of them (`django/db/migrations/loader.py:MigrationLoader.build_graph`; [Finding migrations: `MigrationLoader`](loader.md)). By then a dummy node may be gone. A migration that replaces others (a squashed one) may stand in the graph in their place, and where one of them is a dummy node, having no file, the loader then takes that node out and gives its place in the dependency to the replacing migration: a migration can go on naming a replaced migration whose file is deleted. [Squashed migrations: `replaces` and the squashmigrations command](squashing.md) has that.

## A cycle: `ensure_not_cyclic`

Dependencies that lead back to where they began can be given no order, and the walks assume there are none: `MigrationGraph.iterative_dfs` counts a node as seen only once it has listed it, and in a cycle each node waits for another, so a walk that came to one would not end. `MigrationGraph.ensure_not_cyclic` looks for one, and is the last thing `MigrationLoader.build_graph` does ([Finding migrations: `MigrationLoader`](loader.md)), so a missing dependency is reported before a cycle. It follows children from each node it has not yet visited, keeping the path it is on, and when a child is already on the path it raises `CircularDependencyError` (`django/db/migrations/graph.py:MigrationGraph.ensure_not_cyclic`). The message is the cycle: the migrations from that child to the end of the path, each depending on the one before it.
