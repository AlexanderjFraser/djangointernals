from django.apps import AppConfig


class TreesConfig(AppConfig):
    name = "trees"

    def ready(self):
        from . import checks  # noqa: F401  importing the module registers its check
