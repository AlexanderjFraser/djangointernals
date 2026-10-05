from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Counts the bottles. The trees application is listed first and has a count too, so this one never runs."

    def handle(self, *args, **options):
        self.stdout.write("no bottles")
