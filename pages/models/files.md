---
django: main at 4fab678a0739d54401ccee7eb587553657c9f76e (2026-09-26), on its way to 6.2
---

# File fields

A `django.db.models.FileField` keeps a file's name in its column and leaves the file itself to a storage. What an instance has under the field's name is neither of them: it is a `FieldFile`, which `FileDescriptor` makes at a read out of the name or the file the instance holds, and which can open, save and delete the file of that name. `ImageField` is the same field with an image's width and height kept beside it.

A file does not go into a row the way a number does. Django keeps it in a **storage**, an object that saves bytes under a name and gives them back, which by default is a directory on the server's disk ([Caching, files, mail, signals and tasks](../services.md)). The row then needs only the name, and the column of a file field is a short string.

The attribute cannot be that string, though. Code with an instance in hand wants the file's URL for a template, or its contents, or wants to give the field a file that has just been uploaded and have it kept. So a file field is three classes, with the work divided among them (`django/db/models/fields/files.py`).

- `FileField` is the field. It has the column, the storage, and the rule for where in the storage a file goes, and it is the part that takes a hand when the model is saved.
- `FileDescriptor` is what the field leaves on the model class. Every read of the attribute and every assignment to it goes through it, and at a read it makes the third out of a name or a file.
- `FieldFile` is the value: a file object that knows the instance and the field it belongs to, and so can save a file and put the file's new name back on the instance.

The office keeps a scan of each manifest, in the last of that model's fields:

```python
# harbour/office/models.py
class Manifest(models.Model):
    serial = models.CharField(max_length=8, primary_key=True, default=serials.next_serial)
    voyage = models.ForeignKey("fleet.Voyage", on_delete=models.CASCADE)
    crates = models.PositiveIntegerField()
    kilos_each = models.PositiveIntegerField()
    kilos = models.GeneratedField(expression=F("crates") * F("kilos_each"), output_field=models.PositiveIntegerField(), db_persist=True)
    stamped = models.BooleanField(db_default=False)
    scan = models.FileField(upload_to="manifests/", blank=True)
```

What is recorded on this page was recorded with the project's default storage, a `FileSystemStorage` over an empty directory.

## The column holds a name

The column of a `FileField` is a string, as the table made for Manifest shows (`django/db/models/fields/files.py:FileField`):

```text recording=models
editor.create_model(Manifest)
  SQL CREATE TABLE "office_manifest" ("serial" varchar(8) NOT NULL PRIMARY KEY, "voyage_id" bigint NOT NULL REFERENCES "fleet_voyage" ("id") DEFERRABLE INITIALLY DEFERRED, "crates" integer unsigned NOT NULL CHECK ("crates" >= 0), "kilos_each" integer unsigned NOT NULL CHECK ("kilos_each" >= 0), "kilos" integer unsigned GENERATED ALWAYS AS (("crates" * "kilos_each")) STORED, "stamped" bool DEFAULT 0 NOT NULL, "scan" varchar(100) NOT NULL)
```

The last column of the manifests' table is `"scan" varchar(100) NOT NULL`. A file field asks the backend for the column type that goes with `"FileField"`, the word `FileField.get_internal_type` returns, and in every backend Django ships that is a character type of the field's `max_length`. `FileField.__init__` supplies a length of 100 when the model gives none (`django/db/models/fields/files.py:FileField.__init__`).

What the column holds is the file's **name**: a relative path, such as `"manifests/spring.txt"`, that means something only to the storage. It is not a path on a disk and it is not a URL: making either out of it is the storage's business. A field with no file has an empty name or `None`, and either way an empty string is what a save writes for it, since the value sent is the string of whatever the attribute gives. `blank=True` on the field changed nothing about the column, which is `NOT NULL` all the same (`django/db/models/fields/files.py:FileField.get_prep_value`).

The storage is settled when the field is made, once for the field and not for each file, and is kept as `FileField.storage`. Given none, the field takes `default_storage`, an object that stands for the project's default storage and looks it up the first time it is used (`django/core/files/storage/__init__.py:DefaultStorage`). It may be given a storage instead, or a callable that returns one: the callable is called there, in `__init__`, and a result that is not a `Storage` raises `TypeError`. The callable is kept as well, and `FileField.deconstruct` gives it, not the storage it returned, as the field's argument (`django/db/models/fields/files.py:FileField.deconstruct`).

```text recording=models
Manifest._meta.get_field('scan').upload_to, Manifest._meta.get_field('scan').max_length, type(Manifest.scan).__name__  ->  ('manifests/', 100, 'FileDescriptor')
Manifest._meta.get_field('scan').attr_class.__name__, Manifest._meta.get_field('scan').descriptor_class.__name__  ->  ('FieldFile', 'FileDescriptor')
type(Manifest._meta.get_field('scan').storage).__name__  ->  'DefaultStorage'
```

The other two classes are named by attributes of the field's class, `FileField.attr_class` and `FileField.descriptor_class`, which is how `ImageField` puts its own in their place.

Two mistakes in declaring a file field are left to the system checks. The keyword `"primary_key"` must not be among its arguments at all, and a `FileField.upload_to` that is a string must not begin with a slash (`django/db/models/fields/files.py:FileField.check`) ([The model checks](checks.md)).

## `FileDescriptor`: a read makes a `FieldFile`

`FileDescriptor` is what a file field leaves on its model class. A field with a column leaves a descriptor on the model class under its attname ([A field: the base class](fields.md)). For a field class that does not say otherwise it is a plain `DeferredAttribute`, which has no `__set__`. Python consults such a descriptor only when the instance has nothing under the name, and its one job is to fetch a value that was deferred ([An instance and its state](instances.md)). `FileDescriptor` is a subclass of it that adds a `__set__`. A descriptor with a `__set__` takes precedence over the instance's own `__dict__`, so every read of the attribute goes to `FileDescriptor.__get__` and every assignment to `FileDescriptor.__set__`, whether or not the instance holds a value (`django/db/models/fields/files.py:FileDescriptor`).

`Field.contribute_to_class` sets a descriptor of the field's `descriptor_class`, as it does for any field with a column, and `FileField.contribute_to_class` then sets another of the same class over it (`django/db/models/fields/files.py:FileField.contribute_to_class`).

**Assignment stores, and does nothing else.** `FileDescriptor.__set__` puts what it is given into the instance's `__dict__` under the attname, whatever it is. `Model.__init__` assigns that way the string from a row, or for a new instance the field's default, which for a field declared as Manifest's is an empty string. A form assigns an uploaded file. A program may assign a file it has opened, a name, or `None`. The source's comment in `__get__` says the method would be easy if assignment were strict, and that it is not. So the work is done on the way out.

**A read converts.** `FileDescriptor.__get__` first has `DeferredAttribute.__get__` produce what the instance holds, which fetches it if the field was deferred. Then it looks at what kind of thing that is. For a string, `None`, a `DatabaseDefault` or a `File`, what it leaves in the `__dict__` and returns is a `FieldFile` of this instance, so that the next read finds one there and has nothing to do. A value of any other kind it returns as it is (`django/db/models/fields/files.py:FileDescriptor.__get__`).

| under the attname | what a read leaves there, and returns |
|---|---|
| a string, or `None` | a new `FieldFile` with that for its name, taken to be in the storage already |
| a `DatabaseDefault` | a new `FieldFile` whose name is the field's `db_default` |
| a `File` that is not a `FieldFile` | a new `FieldFile` with the file's name, holding the file, and marked as not yet in the storage |
| a `FieldFile` that has no field, which the source's comment puts down to pickling | the same object, given this instance, the field and the field's storage |
| a `FieldFile` of another instance | the same object, with this instance as its instance |
| a `FieldFile` of this instance | the same object |

*What `FileDescriptor.__get__` does with a string, `None`, a `DatabaseDefault`, a `File` or a `FieldFile`. Anything else it returns as it is. A new object is of the field's `attr_class`.*

A Manifest that is given a file holds exactly that file until the attribute is read:

```text recording=models
second.scan = ContentFile(b'three crates of cod', name='spring.txt')
  FileDescriptor.__set__(<Manifest: Manifest object (M-0002)>, a ContentFile named 'spring.txt')  (Manifest.scan)
type(vars(second)['scan']).__name__  ->  'ContentFile'
second.scan is read
  FileDescriptor.__get__(<Manifest: Manifest object (M-0002)>)  (Manifest.scan)  ->  a FieldFile named 'spring.txt'
type(vars(second)['scan']).__name__, second.scan._committed, os.path.exists(os.path.join(MEDIA, 'manifests', 'spring.txt'))  ->  ('FieldFile', False, False)
```

It held a `ContentFile`, which is a `File` made from bytes or a string in memory. After one read it holds a `FieldFile` that has the file and has taken its name, `"spring.txt"`, and that is marked as not committed; the storage has nothing yet. A row that has just been fetched holds a string. This one is the same Manifest's, fetched after the save that is shown below:

```text recording=models
type(vars(again)['scan']).__name__, vars(again)['scan']  ->  ('str', 'manifests/spring.txt')
again.scan is read
  FileDescriptor.__get__(<Manifest: Manifest object (M-0002)>)  (Manifest.scan)  ->  a FieldFile named 'manifests/spring.txt'
type(vars(again)['scan']).__name__, again.scan == 'manifests/spring.txt', again.scan.instance is again  ->  ('FieldFile', True, True)
```

Where the field is a plain `FileField`, and not an `ImageField` that keeps a width or a height (below), a fetched row whose attribute is never read never has a `FieldFile` made for it. And the first line of the table is why an assigned string behaves as it does: the descriptor takes a string for the name of a file the storage already has, and nothing looks to see whether it is there.

## `FieldFile`: a file that knows its row

`FieldFile` inherits from `File`, the wrapper Django puts around any open file, and so it can be read, iterated over in chunks or by lines, and used in a `with` statement (`django/core/files/base.py:File`). It adds what ties it to a row. `FieldFile.instance` and `FieldFile.field` say whose it is, `FieldFile.storage` is the field's storage, and a flag, `FieldFile._committed`, says whether the file of this name is taken to be in the storage. The flag is true of a `FieldFile` made from a name, and false of one the descriptor made around an assigned file (`django/db/models/fields/files.py:FieldFile`).

It is made without opening anything. The underlying file is the property `FieldFile.file`, which asks the storage to open the name, for reading in binary mode, the first time something needs it, and keeps what it gets. So fetching a row with a plain `FileField` opens no file, and neither does reading the attribute. Reading from it does:

```text recording=models
again.scan.url, again.scan.size, type(again.scan.storage).__name__  ->  ('/manifests/spring.txt', 19, 'DefaultStorage')
again.scan.read()  ->  b'three crates of cod'
again.scan.close()  ->  None
```

The rest of what a `FieldFile` says about its file is the storage's answer for the name: `FieldFile.url`, `FieldFile.path`, and `FieldFile.size`, which asks the file itself for as long as it is not committed. A storage that keeps nothing on a local disk has no path to give, and its `Storage.path` raises `NotImplementedError`. `FieldFile.open` opens the name in the storage, or calls the `open` of the file it already holds, and returns the `FieldFile` itself.

An instance with no file has a `FieldFile` all the same, one whose name is empty or `None`. Its truth is its name's, so it is false, and `file`, `path`, `url`, `size` and `open` each begin with `FieldFile._require_file`, which raises `ValueError` for it:

```text recording=models
bool(first.scan), first.scan.name, type(first.scan).__name__  ->  (False, '', 'FieldFile')
first.scan.url  ->  raises ValueError: The 'scan' attribute has no file associated with it.
```

> **Changed in 6.1.** A plain `File` is now always true. `FieldFile` kept the older rule, as the classes for uploaded files did, and is true when it has a name.

A `FieldFile` compares by name. It equals another object that has a `name` when the two names are equal, and anything else when its name equals that thing, so it equals the string that names it, as the recording of the fetched row showed; its hash is its name's. The comment beside `__eq__` gives the reason: older code may expect the value of a file field to be a simple string.

A pickled `FieldFile` is its name, its instance and its field, which the comment in `FieldFile.__getstate__` gives as what it needs. The open file and the storage are left out and the flag is written as committed, and `__setstate__` takes the storage from the field again (`django/db/models/fields/files.py:FieldFile.__getstate__`).

Its methods `save`, `delete` and `open` carry `alters_data = True`, the mark by which a template refuses to call a method ([Templates](../templates.md)).

## `FieldFile.save` and `FieldFile.delete`

`FieldFile.save` and `FieldFile.delete` are the two methods of a file field's value that change what the storage holds, and each ends by putting the outcome on the instance.

`save` is given a name, the content, and whether to save the instance afterwards. Here a second file is saved under the field of the fetched Manifest, with `save=False`:

```text recording=models
again.scan.save('amended.txt', ContentFile(b'four crates of cod'), save=False)
  FileDescriptor.__get__(<Manifest: Manifest object (M-0002)>)  (Manifest.scan)  ->  a FieldFile named 'manifests/spring.txt'
  FieldFile.save('amended.txt', a ContentFile named None, save=False)
    FileField.generate_filename(instance, 'amended.txt')  ->  'manifests/amended.txt'
    Storage.save('manifests/amended.txt', content)  (a FileSystemStorage)
      Storage.get_available_name('manifests/amended.txt')  ->  'manifests/amended.txt'
      FileSystemStorage._save('manifests/amended.txt', content)  ->  'manifests/amended.txt'
      -> 'manifests/amended.txt'
    FileDescriptor.__set__(<Manifest: Manifest object (M-0002)>, 'manifests/amended.txt')  (Manifest.scan)
again.scan.name, Manifest.objects.get(pk=again.pk).scan.name  ->  ('manifests/amended.txt', 'manifests/spring.txt')
  SQL SELECT "office_manifest"."serial", "office_manifest"."voyage_id", "office_manifest"."crates", "office_manifest"."kilos_each", "office_manifest"."kilos", "office_manifest"."stamped", "office_manifest"."scan" FROM "office_manifest" WHERE "office_manifest"."serial" = %s LIMIT 21 with params ('M-0002',)
sorted(os.listdir(os.path.join(MEDIA, 'manifests')))  ->  ['amended.txt', 'spring.txt']
```

**The field makes the name.** `FileField.generate_filename` treats the two kinds of `FileField.upload_to` differently. A string is a directory: it is put through Python's strftime with the present moment, so that `"manifests/%Y/"` files by year, and joined in front of the name. A callable is called with the instance and the name, and what it returns is the whole name. It is handed the instance as it stands, which in the save of a new row is before the database has assigned an automatic key. Either result is refused, with `SuspiciousFileOperation`, if it is an absolute path or has `".."` among its parts. Then the storage's own `Storage.generate_filename` cleans the last part of it: `Storage.get_valid_name` turns spaces into underscores and drops every character that is not a letter, a digit, a dash, an underscore or a dot (`django/db/models/fields/files.py:FileField.generate_filename`, `django/core/files/storage/base.py:Storage.generate_filename`).

**The storage has the last word on it.** `Storage.save` is given the name and the field's `max_length`, and returns the name it used, which is the one `FieldFile.save` keeps. Unless it was made to overwrite, a storage does not: where the name is taken, `Storage.get_available_name` puts an underscore and seven random characters before the extension, and it shortens a name that would not fit the column ([Caching, files, mail, signals and tasks](../services.md)). So the name that will be in the row is known only once the file has been written (`django/core/files/storage/base.py:Storage.save`).

**The name goes back on the instance, as a string.** The method sets the attribute through the descriptor, so what the instance holds after a save is not this `FieldFile` but the bare name, and the next read makes a new `FieldFile` from it. The one whose `save` was called is marked committed.

**The instance is saved**, unless `save=False`: a call of `Model.save` with no arguments, so a save of the whole instance and not of this field alone ([Saving an instance](saving.md)). In the recording it was not, and the last three lines show what that leaves: the instance has the new name, the row still has the old one, and the directory has both files (`django/db/models/fields/files.py:FieldFile.save`).

The other method takes the file away:

```text recording=models
again.scan.delete(save=False)
  FileDescriptor.__get__(<Manifest: Manifest object (M-0002)>)  (Manifest.scan)  ->  a FieldFile named 'manifests/amended.txt'
  FieldFile.delete(save=False)
    FileSystemStorage.delete('manifests/amended.txt')
    FileDescriptor.__set__(<Manifest: Manifest object (M-0002)>, None)  (Manifest.scan)
again.scan.name, bool(again.scan), sorted(os.listdir(os.path.join(MEDIA, 'manifests')))  ->  (None, False, ['spring.txt'])
```

`FieldFile.delete` returns at once for a `FieldFile` with no name. Otherwise it closes the file if it was opened, asks the storage to delete the name, sets its own name and the instance's attribute to `None`, clears the flag, and saves the instance unless told not to (`django/db/models/fields/files.py:FieldFile.delete`). The file the row still names, `"spring.txt"`, was not touched.

## Saving the model saves the file

A program need not call `FieldFile.save` itself. It can assign a file to the attribute and save the instance, which is what a model form does. The file reaches the storage through a hook a field has in a save: for a field it is going to write, `Model._save_table` gets the value, unless the save is raw, by calling the field's `Field.pre_save` ([Saving an instance](saving.md)). `FileField.pre_save` reads the attribute, and if the `FieldFile` that the read gives has a name and is not committed it calls that object's `save`, with the name and the file it already holds and with `save=False`. It returns the `FieldFile`, and `FileField.get_prep_value` makes the column's value of that by taking its string, which is its name (`django/db/models/fields/files.py:FileField.pre_save`). This is the save of the Manifest that was given a `ContentFile` above. It came straight after that, before the row was fetched and before the two calls recorded in the section above:

```text recording=models
second.save()
  Model.save()  (a Manifest)
    Model._save_table(cls=Manifest)
      FileField.pre_save(add=True)  (Manifest.scan)
        FileDescriptor.__get__(<Manifest: Manifest object (M-0002)>)  (Manifest.scan)  ->  a FieldFile named 'spring.txt'
        FieldFile.save('spring.txt', a ContentFile named 'spring.txt', save=False)
          FileField.generate_filename(instance, 'spring.txt')  ->  'manifests/spring.txt'
          Storage.save('manifests/spring.txt', content)  (a FileSystemStorage)
            Storage.get_available_name('manifests/spring.txt')  ->  'manifests/spring.txt'
            FileSystemStorage._save('manifests/spring.txt', content)  ->  'manifests/spring.txt'
            -> 'manifests/spring.txt'
          FileDescriptor.__set__(<Manifest: Manifest object (M-0002)>, 'manifests/spring.txt')  (Manifest.scan)
        -> a FieldFile named 'manifests/spring.txt'
      FileField.pre_save(add=True)  (Manifest.scan)
        FileDescriptor.__get__(<Manifest: Manifest object (M-0002)>)  (Manifest.scan)  ->  a FieldFile named 'manifests/spring.txt'
        -> a FieldFile named 'manifests/spring.txt'
      FileField.get_prep_value(<FieldFile: manifests/spring.txt>)  (Manifest.scan)  ->  'manifests/spring.txt'
      SQL INSERT INTO "office_manifest" ("serial", "voyage_id", "crates", "kilos_each", "scan") VALUES (%s, %s, %s, %s, %s) RETURNING "office_manifest"."kilos", "office_manifest"."stamped" with params ('M-0002', 1, 3, 25, 'manifests/spring.txt')
      -> updated: False
second.scan.name, second.scan._committed, os.path.exists(os.path.join(MEDIA, 'manifests', 'spring.txt'))  ->  ('manifests/spring.txt', True, True)
```

**The file is written before the row.** `pre_save` runs while the values for the statement are being gathered, so the storage had `"manifests/spring.txt"` before the `"INSERT"` was sent, and the name among the statement's parameters is the one the storage returned. Nothing joins the two writes: the storage takes no part in the database's transaction, so a file whose row the database then refuses is in the storage all the same.

**`pre_save` was called twice.** For an insert that is not raw, `_save_table` calls the `pre_save` of each field to be inserted, and the insert's compiler calls it again, so a `pre_save` that does something has to bear being repeated (`django/db/models/sql/compiler.py:SQLInsertCompiler.pre_save_val`). The file field bears it through the flag. The first call found a `FieldFile` that was not committed, and saved it. That save left the name on the instance as a string, so the read in the second call made a new `FieldFile` from a name, and one made from a name starts out committed: the second call returned it and saved nothing. An update that is not raw calls `pre_save` once for each field it writes, before its statement, and a newly assigned file is saved then in the same way. In an update, a field that `"update_fields"` leaves out is not among those, so the update saves no file assigned to it.

What a save does with the field therefore depends on what was assigned to it, by the lines of the table above. A file is saved, under a name made from its own. A string is written to the column as it stands, with no directory put in front of it and no look at the storage. A file whose name is `None` cannot be saved: `pre_save` raises `FieldError` before that file is saved and before the statement is sent, with a note, where the file is a `ContentFile`, saying to pass it a name. And a raw save, which calls no field's `pre_save`, writes the name the attribute has and saves no file.

A model form does its assigning through `FileField.save_form_data`, which sets the attribute to what the form's field cleaned unless that is `None`, a form's way of saying that no new file came and the old one stands; any other false value empties the field (`django/db/models/fields/files.py:FileField.save_form_data`) ([Forms](../forms.md)). How an uploaded file comes off the request is in [Multipart parsing and upload handlers](../http/uploads.md).

## A file that nothing names any more

Deleting a row does nothing to the file that a file field of the row names, and neither does giving the field another file. Here another Manifest, whose scan is `"manifests/rope.txt"`, is deleted, with the collector's own steps left out:

```text recording=models
papers.scan.name, sorted(os.listdir(os.path.join(MEDIA, 'manifests')))  ->  ('manifests/rope.txt', ['rope.txt', 'spring.txt'])
papers.delete()
  Model.delete()  (a Manifest)
...
      DeleteQuery.delete_batch(['M-0005'])  (Manifest)
        SQL DELETE FROM "office_manifest" WHERE "office_manifest"."serial" IN (%s) with params ('M-0005',)
...
Manifest.objects.filter(pk='M-0005').exists(), papers.scan.name, sorted(os.listdir(os.path.join(MEDIA, 'manifests')))  ->  (False, 'manifests/rope.txt', ['rope.txt', 'spring.txt'])
```

The row is gone, the directory holds the same two files after the statement as before it, and the instance, which outlives its row, still has the name.

Within `django/db/models/fields/files.py` the storage's `delete` is called in one place, `FieldFile.delete`. `Model.delete` and the `Collector` work on rows: `django/db/models/deletion.py` names no file and no storage, and a file field connects no receiver to the signals a delete sends ([Deleting: the `Collector`](deleting.md)). Assignment only stores. And `FieldFile.save` writes a new file without a look at the one the field named before, which is how the directory in the earlier recording came to hold `"amended.txt"` beside `"spring.txt"`.

So a file leaves the storage when something calls `FieldFile.delete`, or goes to the storage itself.

## Image fields: a width and a height kept in the row

`ImageField` is a `FileField` whose value and whose descriptor are subclasses of the file field's: its `attr_class` is `ImageFieldFile` and its `descriptor_class` is `ImageFileDescriptor`. The column is the same, since it inherits `get_internal_type`. An `ImageFieldFile` is a `FieldFile` that is also an `ImageFile`, which adds `ImageFile.width` and `ImageFile.height`: reading either opens the file and feeds it to Pillow's parser a piece at a time until the size is known, and the answer is kept on the object (`django/db/models/fields/files.py:ImageField`, `django/core/files/images.py:get_image_dimensions`).

The field takes two arguments of its own, `ImageField.width_field` and `ImageField.height_field`: the names of two other fields of the model, in which the image's size is kept as columns of the row. Keeping those right is the work of `ImageField.update_dimension_fields`, which sets both from the file, or to `None` when there is no file. It is reached from two places.

The first is assignment. `ImageFileDescriptor.__set__` stores the value as its base class does and then, if the instance already held something under the attname, calls the method with `force=True`. The condition leaves out the assignments `Model.__init__` makes, when the instance holds nothing yet. The source's comment cites ticket 11084: it is to keep the dimensions from being worked out again each time an object is made from a row (`django/db/models/fields/files.py:ImageFileDescriptor.__set__`).

The second is the signal `post_init`. `ImageField.contribute_to_class` connects the method to it with the model class as sender, when that class is not abstract and the field names at least one of the two fields. The comment there cites ticket 11196: a dimension field declared after its image field would otherwise stay cleared by `Model.__init__`, which sets the fields in order (`django/db/models/fields/files.py:ImageField.contribute_to_class`).

So the method runs at the end of `Model.__init__` for every instance made of that class itself, each row a queryset turns into such an instance included. The receiver is connected for that class alone: an instance of a proxy of it, or of a child with a table of its own, does not run it. It is written to do little then. It returns at once if the image field is deferred. It reads the attribute, which makes the `ImageFieldFile`, and returns if there is no file. And it returns if each dimension field it knows of already holds a true value, as it does for a row whose image was measured before the row was saved. Only past all three does it read the width and the height, which opens the file. The cost to know about is the case that gets that far: an instance made from a row that has an image, and a dimension column that is empty or zero, opens its image in the storage as it is made (`django/db/models/fields/files.py:ImageField.update_dimension_fields`).

`ImageFieldFile` changes one step of `FieldFile.save`, the one that puts the name on the instance. It assigns the content through the descriptor first, which, where the content is a `File`, brings the dimension fields up to date from it, and then writes the name into the `__dict__` directly; the comment says this is to avoid reading the file again. So the width and the height are the content's, not those of what the storage kept, and a storage that alters an image as it saves it leaves them not matching the stored image. The update reads the content back through the descriptor, which wraps it under the content's own name and not the name it was saved under. A `File` with no name of its own, such as a `ContentFile` made without one, is false there, is taken for no file, and leaves both fields `None` (`django/db/models/fields/files.py:ImageFieldFile._set_instance_attribute`).

Measuring needs Pillow, which `get_image_dimensions` imports when it is called. A project that declares an `ImageField` without Pillow installed is told so by a system check of the field's own, beside the two it inherits (`django/db/models/fields/files.py:ImageField.check`) ([The model checks](checks.md)).
