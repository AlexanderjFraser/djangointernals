---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# A child in two rows

An instance of a model whose parent has a table is one object kept in a row of each table: the fields it inherits are the parent's field objects, a query for its inherited fields joins the tables, a save writes the parent's row first, and its key is ordinarily held under two names.

## At run time

A class that inherits from an abstract base has its fields as its own, and its instances are like those of a class that declared every field itself. The other two kinds show their parentage, in what an instance holds and in the statements sent for it.

### A child's fields are its parent's field objects

`Options.fields` of a model with parents is put together by `Options._get_fields`: for each entry of `parents` the list that parent's options give, and after those the model's own local fields (`django/db/models/options.py:Options._get_fields`). The parent's list holds the parent's own objects. Nothing is copied, for a child with a table or for a proxy:

```text recording=models
names(Officer._meta.fields)  ->  [id, name, ship, signed_on, sailor_ptr, rank]
```

```text recording=models
Officer._meta.get_field('name') is Sailor._meta.get_field('name'), Officer._meta.get_field('name').model  ->  (True, <class 'harbour.crew.models.Sailor'>)
```

So `Field.model` of an inherited field is the parent, where that of a field copied from an abstract base is the child (`django/db/models/fields/__init__.py:Field`). The rest of the ORM steers by this: a field's model says which table its column is in.

The descriptors are shared likewise, by plain inheritance, and the one for `"ship"` is a single object on both classes:

```text recording=models
isinstance(master, Sailor), Officer._meta.get_field('ship').model, Officer.ship is Sailor.ship  ->  (True, <class 'harbour.crew.models.Sailor'>, True)
```

### A query for the child joins the two tables

The compiler that writes a `"SELECT"` goes through the concrete fields of the model being queried. For a field whose model is another model, it has `Query.join_parent_model` join that model's table, by way of the link (`django/db/models/sql/compiler.py:SQLCompiler.get_default_columns`, `django/db/models/sql/query.py:Query.join_parent_model`):

```text recording=models
master = Officer.objects.get(name='Cora')
  SQL SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on", "crew_officer"."sailor_ptr_id", "crew_officer"."rank" FROM "crew_officer" INNER JOIN "crew_sailor" ON ("crew_officer"."sailor_ptr_id" = "crew_sailor"."id") WHERE "crew_sailor"."name" = %s LIMIT 21 with params ('Cora',)
  Model.from_db('default', ['id', 'name', 'ship_id', 'signed_on', 'sailor_ptr_id', 'rank'], (3, 'Cora', 2, datetime(2011, 6, 1, 8, 0, tzinfo=UTC), 3, 'master'), fetch_mode=FETCH_ONE)  (Officer)
    Model.__init__(3, 'Cora', 2, datetime(2011, 6, 1, 8, 0, tzinfo=UTC), 3, 'master')  (a new Officer)
```

The statement selects the columns of both tables and joins them on the link. Its condition names the parent's table, since `"name"` is a field of Sailor: a filter that names a field of an ancestor has the joins to that ancestor put into its path (`django/db/models/sql/query.py:Query.names_to_path`). The row then goes to `Model.from_db` whole, six values in the order of the model's concrete fields with the parent's first, and the instance holds all of them. This is its `__dict__` after its link and its ship had also been read:

```text recording=models
What the Officer holds in its __dict__
    _state: a ModelState
    id: 3
    name: 'Cora'
    ship_id: 2
    signed_on: datetime(2011, 6, 1, 8, 0, tzinfo=UTC)
    sailor_ptr_id: 3
    rank: 'master'
    and its _state: adding=False, db='default', fields_cache={'sailor_ptr': <Sailor: Cora>, 'ship': <Ship: Gannet>}
```

A query for the parent does not go the other way. A queryset of Sailor selects from Sailor's table and makes instances of Sailor, whichever of those rows also have a row in a child's table. A queryset of a proxy reads its base's table and makes instances of the proxy, since the class a row becomes is the queryset's model:

```text recording=models
[(type(v).__name__, v.name) for v in Veteran.objects.order_by('id')]  ->  [('Veteran', 'Ada'), ('Veteran', 'Cora')]
  SQL SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on" FROM "crew_sailor" WHERE "crew_sailor"."signed_on" < %s ORDER BY "crew_sailor"."id" ASC with params ('2020-01-01 00:00:00',)
Veteran.objects.get(name='Ada')._meta.concrete_model.__name__  ->  'Sailor'
```

The condition on `"signed_on"` in that statement is the doing of VeteranManager, whose `get_queryset` filters on the year a sailor signed on, not of Veteran's being a proxy ([Managers](../models/managers.md)).

### A save writes the parent's table first

`Model._save_parents` runs before the model's own table is written. It saves each parent in `parents`, a grandparent before a parent, and after each copies the parent's key into the link's attribute (`django/db/models/base.py:Model._save_parents`). `Model.save_base` puts the statements of such a save in one transaction, and for a proxy it exchanges the class for its concrete model before anything is written, keeping the proxy only as the sender of the signals (`django/db/models/base.py:Model.save_base`) ([Saving an instance](saving.md)).

### From the child to the parent, and back

Reading the link on a child gives the parent as an object of its own, and unless one of the parent's fields is deferred on the child it sends no query: `ForwardOneToOneDescriptor.get_object` makes the object from the values the child already holds (`django/db/models/fields/related_descriptors.py:ForwardOneToOneDescriptor.get_object`) ([Reading and setting related objects](../relations/related-objects.md)).

Starting from a Sailor is different. Nothing in a row of the parent's table says whether a child's table has a row for it, so the accessor for the other end of the link has to ask. Cora is an officer and Bram is not. The first read is quoted as far as its statement, and the second, which sends the same statement for Bram's key, without it:

```text recording=models
plain.officer is read
  ReverseOneToOneDescriptor.__get__(<Sailor: Cora>)  (the rel of Officer.sailor_ptr)
    FetchOne.fetch(a ReverseOneToOneDescriptor for the rel of Officer.sailor_ptr, <Sailor: Cora>)
      ReverseOneToOneDescriptor.fetch_one(<Sailor: Cora>)  (the rel of Officer.sailor_ptr)
        SQL SELECT "crew_sailor"."id", "crew_sailor"."name", "crew_sailor"."ship_id", "crew_sailor"."signed_on", "crew_officer"."sailor_ptr_id", "crew_officer"."rank" FROM "crew_officer" INNER JOIN "crew_sailor" ON ("crew_officer"."sailor_ptr_id" = "crew_sailor"."id") WHERE "crew_officer"."sailor_ptr_id" = %s LIMIT 21 with params (3,)
...
bram.officer is read
  ReverseOneToOneDescriptor.__get__(<Sailor: Bram>)  (the rel of Officer.sailor_ptr)
    raises RelatedObjectDoesNotExist
  the caller catches Sailor.officer.RelatedObjectDoesNotExist: Sailor has no officer.
```

The accessor's query is a query for the child, so it joins both tables again, and when no row comes back it raises an exception that is a subclass of the child's `Model.DoesNotExist` (`django/db/models/fields/related_descriptors.py:ReverseOneToOneDescriptor`).

### One key under two names

The recorded `__dict__` of the Officer has its key twice: under `"id"`, the attname of the parent's primary key, and under `"sailor_ptr_id"`, the attname of the link, which is the child's own. `Model.pk` reads and writes the second, since the primary key of Officer is the link.

Nothing makes the two agree by force: they are two entries of a dictionary. They agree because of how they are filled. A row fetched for the child has one value in both columns, the join having matched them. `Model._save_parents` copies in both directions around each parent's save: before it, a link that is set fills a parent's key that is `None`, and after it the parent's key, which the database may just have assigned, goes into the link. And assigning a parent object to a link that is the primary key sets the inherited key as well as the link's own attribute (`django/db/models/fields/related_descriptors.py:ForwardOneToOneDescriptor.__set__`).

The link also stands in for the inherited key when that one is missing. A child fetched without its parent's key column answers a read of that key from the link, and sends no query (`django/db/models/query_utils.py:DeferredAttribute._check_parent_chain`).

Assigning `Model.pk` does less than these. `Model._set_pk_val` sets the attribute of the model's own primary key, and besides that the key of a parent only where the link to that parent is not the primary key, as when the child declares a key of its own or has a second parent (`django/db/models/base.py:Model._set_pk_val`). For an Officer, whose link is its key, nothing but the link is set. Here ivo is an Officer just made and not yet saved, asked for its key under the three names: as made, after its `pk` is set, and after its `"id"` is:

```text recording=models
ivo.pk, ivo.id, ivo.sailor_ptr_id  ->  (None, None, None)
setattr(ivo, 'pk', 99) or (ivo.pk, ivo.id, ivo.sailor_ptr_id)  ->  (99, None, 99)
setattr(ivo, 'id', 77) or (ivo.pk, ivo.id, ivo.sailor_ptr_id)  ->  (99, 77, 99)
```

Clearing `Model.pk` on a child therefore leaves the inherited key where it was. Django's documentation of copying an instance has both `Model.pk` and the attribute `"id"` set to `None` for a model that inherits. And the source allows for the two keys differing: asked for the inherited key of a child whose link is its primary key, `ForeignObject.get_instance_value_for_fields` returns `Model.pk` in its place, and its comment gives the loading of a fixture as a case where the two values are not the same (`django/db/models/fields/related.py:ForeignObject.get_instance_value_for_fields`).

### Equality across the three kinds

`Model.__eq__` holds two instances equal when their concrete models are the same and their keys, being set, are equal (`django/db/models/base.py:Model.__eq__`). The class of an instance does not enter into it. A Veteran and a Sailor made from one row are equal, the concrete model of a proxy being the model it stands for. An Officer and the Sailor of the same row are not, though their keys are the same, since a child with a table is its own concrete model ([An instance and its state](state.md)). The parent object that an Officer's own link gives is unequal to the Officer in the same way:

```text recording=models
type(master.sailor_ptr).__name__, master.sailor_ptr == master, master.sailor_ptr.pk == master.pk  ->  ('Sailor', False, True)
```

### Deleting

Deleting an Officer deletes both of its rows: `Collector.collect` follows each link in `parents` and collects the parent's instance too, unless it is called with `keep_parents=True`, which leaves the Sailor's row in place. In the other direction, the link the metaclass makes is a relation with `on_delete=CASCADE`, so deleting the Sailor takes the Officer's row with it (`django/db/models/deletion.py:Collector.collect`) ([Deleting: the `Collector`](deleting.md)).
