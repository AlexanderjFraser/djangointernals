"""The members' URLs for a server that runs their entrance on the event loop: the entrance is a
coroutine, and the renewal is the members' own. The recording's middleware for that server
gives this URLconf to each request for the members' host."""
from django.urls import path

from . import views, views_async

urlpatterns = [
    path("", views_async.members, name="entrance"),
    path("renew/<int:year>/", views.tickets, name="renew"),
]
