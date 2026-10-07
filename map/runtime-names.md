# Names made at runtime

Verified against Django at `4fab678a0739d54401ccee7eb587553657c9f76e`.

Some of Django's names are in no file's syntax tree: a metaclass, a
descriptor or a call to `setattr` makes them as the code runs. The name gate
(`python tools/names.py`) accepts such a name only where it is declared with
the pointer to the code that makes it. A document may declare names for
itself in a block like the one below; the entries here hold for every
document. One entry a line: the name, the pointer, and after `#` anything.
Each entry is a claim and is verified like one.

```runtime-names
ROOT_URLCONF                 django/conf/__init__.py:Settings.__init__                   # the defaults do not define it; a project's settings module does, and each of its upper-case names is set here
MAILERS                      django/conf/__init__.py:Settings.__init__                   # the same: the defaults hold it only as a comment, until the mail settings it replaces are removed
SERIALIZATION_MODULES        django/conf/__init__.py:Settings.__init__                   # the same: the serializers read it only where a project has set it
process_exception            django/core/handlers/base.py:BaseHandler.load_middleware    # a method the handler looks for on a middleware instance; no class in Django declares one
process_template_response    django/core/handlers/base.py:BaseHandler.load_middleware    # the same
HttpRequest.session          django/contrib/sessions/middleware.py:SessionMiddleware.process_request        # set on each request by the session middleware: the session store for the request's cookie
HttpRequest.user             django/contrib/auth/middleware.py:AuthenticationMiddleware.process_request    # set on each request by the authentication middleware: a lazy object that finds the user on first use
HttpRequest.auser            django/contrib/auth/middleware.py:AuthenticationMiddleware.process_request    # the same, as a coroutine function
HttpRequest._messages        django/contrib/messages/middleware.py:MessageMiddleware.process_request       # set on each request by the message middleware: the storage for the request's messages
Model.DoesNotExist           django/db/models/base.py:ModelBase.__new__    # made for each concrete model class, a subclass of ObjectDoesNotExist
Model.MultipleObjectsReturned  django/db/models/base.py:ModelBase.__new__  # the same, of MultipleObjectsReturned
Model.NotUpdated             django/db/models/base.py:ModelBase.__new__    # the same, of ObjectNotUpdated and DatabaseError
Model._meta                  django/db/models/options.py:Options.contribute_to_class    # bound there to each model class it is handed: the class's Options. Model itself has none
Model.objects                django/db/models/base.py:ModelBase._prepare   # the manager given to a concrete model class that declares none, under this name
BaseManagerFromQuerySet      django/db/models/manager.py:BaseManager.from_queryset    # the class Manager inherits from: made by a call of type as the manager module is imported, and named from the two classes it is made of
resolve_related_class        django/db/models/fields/related.py:RelatedField.contribute_to_class    # a function defined inside that method, and handed to the app registry to call when both models of a relation exist
resolve_through_model        django/db/models/fields/related.py:ManyToManyField.contribute_to_class    # the same, for the model between the two sides of a many-to-many relation
set_managed                  django/db/models/fields/related.py:create_many_to_many_intermediary_model    # the same, to settle whether the model Django makes for the table between is managed
RelatedManager               django/db/models/fields/related_descriptors.py:create_reverse_many_to_one_manager    # the class of the manager at the far end of a foreign key: defined inside that function, on the class it is given
ManyRelatedManager           django/db/models/fields/related_descriptors.py:create_forward_many_to_many_manager    # the class of the manager at either end of a many-to-many relation: defined inside that function
_apply_rel_filters           django/db/models/fields/related_descriptors.py:create_reverse_many_to_one_manager    # a method of RelatedManager, and of ManyRelatedManager
_add_base                    django/db/models/fields/related_descriptors.py:create_forward_many_to_many_manager    # a method of ManyRelatedManager
_add_items                   django/db/models/fields/related_descriptors.py:create_forward_many_to_many_manager    # the same
_get_target_ids              django/db/models/fields/related_descriptors.py:create_forward_many_to_many_manager    # the same
_get_add_plan                django/db/models/fields/related_descriptors.py:create_forward_many_to_many_manager    # the same
_get_missing_target_ids      django/db/models/fields/related_descriptors.py:create_forward_many_to_many_manager    # the same
_remove_items                django/db/models/fields/related_descriptors.py:create_forward_many_to_many_manager    # the same
set_base                     django/db/models/fields/related_descriptors.py:create_forward_many_to_many_manager    # the same
```
