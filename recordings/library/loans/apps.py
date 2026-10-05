from django.apps import AppConfig

from library import probe


class LoansConfig(AppConfig):
    name = "library.loans"

    def ready(self):
        probe.ask("in LoansConfig.ready, the first ready of phase 3")
