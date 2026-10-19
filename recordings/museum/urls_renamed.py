"""The museum's visits by year, for a site in two languages: one route, a translated string,
whose Dutch translation names its parameter differently ("visits/<int:year>/" becomes
"bezoeken/<int:jaar>/" in the catalogue the recording compiles)."""
from django.conf.urls.i18n import i18n_patterns
from django.urls import path
from django.utils.translation import gettext_lazy as _

from . import views

urlpatterns = i18n_patterns(
    path(_("visits/<int:year>/"), views.tickets, name="visits"),
)
