"""An application whose ready method connects three receivers to one signal, each connected
weakly, as Signal.connect does by default: a function of a module, a method of this
AppConfig, and a function defined inside ready."""
from django.apps import AppConfig

from library.notices.signals import book_returned, send_notice


class NoticesConfig(AppConfig):
    name = "library.notices"

    def ready(self):
        def remind(**kwargs):
            pass

        book_returned.connect(send_notice)
        book_returned.connect(self.count_return)
        book_returned.connect(remind)

    def count_return(self, **kwargs):
        pass
