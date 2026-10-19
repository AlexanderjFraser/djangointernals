"""An application whose ready method calls django.setup() itself."""
import django
from django.apps import AppConfig


class ReopeningConfig(AppConfig):
    name = "library.reopening"

    def ready(self):
        django.setup()
