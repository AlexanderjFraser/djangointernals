"""A URLconf with one of each mistake that the system checks tagged `urls` look for. It is
never served: the recording runs the checks over it and writes down what they say."""
from django.urls import include, path, re_path

from . import views

cafe_patterns = [
    path("", views.shop, name="cafe"),
]

terrace_patterns = [
    path("/seats", views.shop, name="seats"),
]

urlpatterns = [
    path("/lost", views.entrance, name="lost"),
    path("cloakroom/", views.entrance, name="cloak:room"),
    path("^lifts/$", views.entrance, name="lifts"),
    path("stairs/<int:floor/", views.entrance, name="stairs"),
    path("tour/", views.Tour, name="tour"),
    ("garden/", "museum.views.entrance"),
    re_path(r"^cafe/$", include(cafe_patterns)),
    re_path(r"^terrace/$", include(terrace_patterns)),
    path("north/", include("museum.gallery.urls", namespace="annexe")),
    path("south/", include("museum.gallery.urls", namespace="annexe")),
]

handler403 = views.lost
handler404 = "museum.views.nowhere"
