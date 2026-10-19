"""The application's signal, and a receiver of it defined at the level of the module."""
from django.dispatch import Signal

book_returned = Signal()


def send_notice(**kwargs):
    pass
