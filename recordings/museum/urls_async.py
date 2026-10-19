"""The museum's URLs for a server that runs its entrance on the event loop: the entrance is a
coroutine, and the tickets are the museum's own."""
from django.urls import path

from . import views, views_async

urlpatterns = [
    path("", views_async.entrance, name="entrance"),
    path("tickets/<int:year>/", views.tickets, name="tickets"),
]
