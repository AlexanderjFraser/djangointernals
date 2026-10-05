from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Says how many trees a number of rows will hold."

    def add_arguments(self, parser):
        parser.add_argument("rows", type=int, help="How many rows are planted.")
        parser.add_argument("--per-row", type=int, help="Trees in a row, if not settings.TREES_PER_ROW.")

    def handle(self, *args, **options):
        per_row = options["per_row"] or settings.TREES_PER_ROW
        self.stdout.write(f"{options['rows'] * per_row} trees in {options['rows']} rows")
