"""A URLconf with a regular expression that does not compile: the group opened before the
floor's digit is never closed. The recording imports it, runs the URL checks over it, and
resolves and reverses with it."""
from django.urls import path, re_path

from . import views

urlpatterns = [
    path("", views.entrance, name="entrance"),
    re_path(r"^plans/(?P<floor>[0-9]/$", views.plan, name="plan"),
    path("shop/", views.shop, name="shop"),
]
