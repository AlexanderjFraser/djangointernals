"""A page's id is its URL: `pages/orm/queries.md` is `orm/queries` and is served at `/orm/queries`."""
from django.urls import path

from . import views

urlpatterns = [
    path("", views.page, {"id": ""}, name="home"),
    path("robots.txt", views.robots, name="robots"),
    path("<path:id>", views.page, name="page"),
]

handler404 = views.not_found
