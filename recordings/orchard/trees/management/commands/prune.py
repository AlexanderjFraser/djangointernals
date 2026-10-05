from django.core.checks import Tags
from django.core.management.base import LabelCommand


class Command(LabelCommand):
    help = "Prunes the named rows."
    label = "row"
    requires_system_checks = [Tags.models, "trees"]

    def handle_label(self, label, **options):
        return f"row {label} pruned"
