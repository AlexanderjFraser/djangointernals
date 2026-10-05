from django.urls import path

from . import views

urlpatterns = [
    path("entries/<int:year>/", views.by_year, name="entries-by-year"),
]
