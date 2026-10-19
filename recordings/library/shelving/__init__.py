"""An application whose package imports the models of another application, catalogue, which
is entered before it in INSTALLED_APPS: catalogue's configuration is made when this package
is imported, in phase one of Apps.populate. The case the documentation's "Strictly speaking"
describes."""
from library.catalogue.models import Book  # noqa: F401
