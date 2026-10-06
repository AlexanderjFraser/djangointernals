"""The museum's URLs for a site in two languages. The entrance has one address; the two
patterns given to `i18n_patterns` are served under a language's prefix, and the route of the
first is itself a translated string."""
from django.conf.urls.i18n import i18n_patterns
from django.urls import path
from django.utils.translation import gettext_lazy as _

from . import views

urlpatterns = [
    path("", views.entrance, name="entrance"),
] + i18n_patterns(
    path(_("opening-hours/"), views.hours, name="hours"),
    path("shop/", views.shop, name="shop"),
)
