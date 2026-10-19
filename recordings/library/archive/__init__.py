"""An application whose package imports its own models module, so that its entry in
INSTALLED_APPS runs a model's class statement during phase one of Apps.populate."""
from library.archive.models import Box  # noqa: F401
