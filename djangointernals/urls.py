"""A page's id is its URL: `pages/orm/queries.md` is `orm/queries`, served at `/orm/queries`,
and its twin at `/orm/queries.md`. The agent's files stand at the root (doors.py)."""
from django.urls import path, re_path

from . import views

urlpatterns = [
    path("", views.page, {"id": ""}, name="home"),
    path("index.md", views.twin, {"id": ""}, name="home-twin"),
    path("robots.txt", views.robots, name="robots"),
    path("llms.txt", views.llms, name="llms"),
    path("llms-full.txt", views.llms_full, name="llms-full"),
    path("index.json", views.index_json, name="index-json"),
    path("names.json", views.names_json, name="names-json"),
    path("sitemap.xml", views.sitemap, name="sitemap"),
    re_path(r"^(?P<id>.+)\.md$", views.twin, name="twin"),
    path("<path:id>", views.page, name="page"),
]

handler404 = views.not_found
