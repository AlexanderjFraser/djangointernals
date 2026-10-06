"""The museum's root URLconf."""
from django.urls import include, path, re_path, register_converter

from . import converters, views

register_converter(converters.MonthConverter, "month")

shop_patterns = [
    path("", views.shop, name="shop"),
    path("<slug:item>/", views.item, name="item"),
]

urlpatterns = [
    path("", views.entrance, name="entrance"),
    path("tickets/<int:year>/", views.tickets, name="tickets"),
    path("tickets/<int:year>/<month:month>/", views.tickets, name="tickets"),
    path("east/", include("museum.gallery.urls", namespace="east"), {"wing": "east"}),
    path("west/", include("museum.gallery.urls", namespace="west"), {"wing": "west"}),
    path("shop/", include(shop_patterns)),
    re_path(r"^plans/(?P<floor>[0-9])(?:\.(?P<format>pdf|svg))?$", views.plan, name="plan"),
    path("files/<path:name>", views.download, name="download"),
]
