"""A URLconf that reverses a name while it is being imported, above its own list of patterns.
The recording makes it the root URLconf for one question, to write down what that raises."""
from django.urls import path, reverse

from . import views

ENTRANCE = reverse("entrance")

urlpatterns = [
    path("", views.entrance, name="entrance"),
]
