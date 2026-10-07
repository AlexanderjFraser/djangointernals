"""The project the recording of chapter 8 runs: a shipping line, in three applications.

`fleet` has the ports, the ships and their voyages; `crew` the sailors; `office` the
paperwork. The models are few, and between them they use each thing the chapter explains:
an abstract base, a child with a table of its own, a proxy, foreign keys in both directions
between two applications, a one-to-one relation, a many-to-many relation with a table Django
makes and one with a model of the project's, a manager made from a queryset class, a
constraint of each kind, an index, a generated column, a default the database supplies, a
file, and a primary key of two columns.
"""
