"""The URLs of the members' site, which shares the museum's process and has a host of its
own. The recording's middleware gives this URLconf to each request for that host."""
from django.urls import path

from . import views

urlpatterns = [
    path("", views.members, name="entrance"),
    path("renew/<int:year>/", views.tickets, name="renew"),
]
