from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Presses apples into juice."
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument("--kilos", type=int, default=0, help="The weight of apples to press.")

    def handle(self, *args, **options):
        kilos = options["kilos"]
        if kilos == 0:
            raise CommandError("The press is empty.", returncode=5)
        if kilos < 0:
            raise ValueError("a weight cannot be negative")
        return f"{kilos * 0.6:.1f} litres"
