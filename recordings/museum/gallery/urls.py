"""The URLs of one wing of the museum. The root URLconf includes this module twice."""
from django.urls import include, path

from .. import views

app_name = "gallery"

audio_patterns = [
    path("<slug:track>/", views.track, name="track"),
]

urlpatterns = [
    path("", views.wing, name="wing"),
    path("rooms/<int:room>/", views.room, name="room"),
    path("rooms/<int:room>/audio/", include((audio_patterns, "audio"))),
]
