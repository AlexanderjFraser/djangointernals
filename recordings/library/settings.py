"""The settings of the project the recording of chapter 3 starts: three applications, entered
in INSTALLED_APPS in the three forms an entry can take, and nothing else a default would not
give. No database is named, because nothing in the recording runs a query. The other
applications in library/ are installed only by the parts of the recording that name them with
settings.configure."""

SECRET_KEY = "recording"

INSTALLED_APPS = [
    "library.loans",  # a package whose apps module defines one AppConfig subclass
    "library.catalogue.apps.CatalogueConfig",  # the dotted path of an AppConfig subclass
    "library.members",  # a package with no apps module
]
