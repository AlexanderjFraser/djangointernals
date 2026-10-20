"""A development URLconf: the view `desk.forged`, and the pattern `static()` makes for Django's
static file view, as a project's URLconf adds it for the files in `files/`.

`static()` makes its pattern only while DEBUG is on, so the recording imports this module in a
block that has turned DEBUG on.
"""
import os

from django.conf.urls.static import static
from django.urls import path

from .desk import forged

FILES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "files")

urlpatterns = [
    path("forged/", forged, name="forged"),
    *static("/media/", document_root=FILES),
]
