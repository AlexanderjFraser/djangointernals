"""An application whose apps module imports its own models module, so that making its
AppConfig, in phase one of Apps.populate, runs a model's class statement."""
from django.apps import AppConfig

from library.reading_room.models import Seat  # noqa: F401


class ReadingRoomConfig(AppConfig):
    name = "library.reading_room"
