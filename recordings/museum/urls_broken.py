"""A URLconf that cannot be imported: it imports a module the project does not have. The
recording makes it the root URLconf for one request, to write down what the handler does."""
from django.urls import path

from . import cloakroom  # noqa: F401  there is no such module

urlpatterns = [
    path("", cloakroom.counter, name="cloakroom"),
]
