"""Serve the baked site on this machine as Cloudflare Pages serves it.

    python manage.py preview                      dist/ at http://127.0.0.1:8000/
    python manage.py preview --port 8080 --dir D  another port, another directory
    python manage.py preview --probe              prove the answers below on a scratch directory

Pages serves `a/b.html` at `/a/b` and answers `/a/b.html` and `/a/b/` with a
308 to `/a/b`; `index.html` is `/`, and `/index.html` is answered with a 308
to `/`; a directory with an `index.html` is served at its address with a
slash, and `/a/index` or `/a` is answered with a 308 to `/a/`; every other
file is served at its own path, a `.md` as `text/markdown`; an address with
no file is answered with `404.html` and the status 404, and so is one that
would only redirect to such an address. A file answers only under its
exact name: a difference of case or a trailing dot, which this machine's
file system forgives, is a 404 here as on Pages. Nothing outside the
directory is served: an address with a drive, a backslash, a NUL or a
colon in it is a 404, and `..` cannot climb above the root. `_headers`
and `_redirects` are Pages's own and are not served. `runserver` is the
other preview: the book as it stands, read again at each save. This one is
the baked files, as the deploy will publish them.

Not applied: `_headers` and `_redirects`. The two headers the bake writes
are the twins' media type, which this server sets by the extension anyway,
and `X-Robots-Tag` on a book that is not indexable, which a browser does not
show.
"""
from __future__ import annotations

import mimetypes
import os
import posixpath
import threading
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

TYPES = {".md": "text/markdown; charset=utf-8", ".html": "text/html; charset=utf-8", ".txt": "text/plain; charset=utf-8",
         ".json": "application/json; charset=utf-8", ".xml": "application/xml; charset=utf-8", ".css": "text/css; charset=utf-8",
         ".svg": "image/svg+xml", ".woff2": "font/woff2", ".js": "text/javascript; charset=utf-8"}
NOT_SERVED = {"_headers", "_redirects"}


def exact(root: Path, relative: str) -> Path | None:
    """The file at `relative` under `root`, each part of the path spelt exactly as the file
    system lists it, or None. A trailing dot or another case is not the file."""
    parts = [p for p in relative.split("/") if p]
    if not parts or any(p in (".", "..") for p in parts):
        return None
    here = root
    for part in parts:
        try:
            if part not in os.listdir(here):
                return None
        except OSError:
            return None
        here = here / part
    return here if here.is_file() else None


def answer(root: Path, address: str) -> tuple[int, str | None, Path | None]:
    """What Pages answers at an address: (status, a redirect's location, the file served).
    A 404 serves `404.html` when there is one."""
    missing = (404, None, exact(root, "404.html"))
    path = unquote(address)
    if not path.startswith("/") or any(ch in path for ch in "\\:\0"):
        return missing
    clean = posixpath.normpath(path)
    if path.endswith("/") and clean != "/":
        clean += "/"
    relative = clean.lstrip("/")
    if clean == "/":
        file = exact(root, "index.html")
        return (200, None, file) if file else missing
    if relative.rsplit("/", 1)[-1] in NOT_SERVED:
        return missing
    if clean.endswith("/index.html"):
        return (308, clean[:-len("index.html")], None) if exact(root, relative) else missing
    if clean.endswith(".html"):
        return (308, clean[:-len(".html")], None) if exact(root, relative) else missing
    if clean.endswith("/"):
        bare = clean.rstrip("/")
        file = exact(root, f"{bare.lstrip('/')}/index.html")
        if file:
            return 200, None, file
        return (308, bare, None) if exact(root, f"{bare.lstrip('/')}.html") else missing
    if clean.endswith("/index") and exact(root, f"{relative}.html"):
        return 308, clean[:-len("index")], None
    file = exact(root, relative) or exact(root, f"{relative}.html")
    if file:
        return 200, None, file
    if exact(root, f"{relative}/index.html"):
        return 308, clean + "/", None
    return missing


class Handler(SimpleHTTPRequestHandler):
    root: Path = Path(".")
    quiet = False

    def do_GET(self):
        self.answer(True)

    def do_HEAD(self):
        self.answer(False)

    def answer(self, body: bool) -> None:
        status, location, file = answer(self.root, urlsplit(self.path).path)
        if status == 308:
            self.send_response(HTTPStatus.PERMANENT_REDIRECT)
            self.send_header("Location", location)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        data = file.read_bytes() if file is not None else b"Not found\n"
        kind = TYPES.get(file.suffix.lower(), mimetypes.guess_type(str(file))[0] or "application/octet-stream") if file else "text/plain"
        self.send_response(HTTPStatus.OK if status == 200 else HTTPStatus.NOT_FOUND)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if body:
            self.wfile.write(data)

    def log_message(self, format, *args):
        if not self.quiet:
            super().log_message(format, *args)


def serve(root: Path, port: int, quiet: bool = False) -> ThreadingHTTPServer:
    handler = type("Preview", (Handler,), {"root": root, "quiet": quiet})
    return ThreadingHTTPServer(("127.0.0.1", port), handler)


class Command(BaseCommand):
    help = "Serve the baked site as Cloudflare Pages would, on this machine."

    def add_arguments(self, parser):
        parser.add_argument("--dir", help="the baked site (default: dist)")
        parser.add_argument("--port", type=int, default=8000)
        parser.add_argument("--probe", action="store_true", help="prove the server answers as Pages does")

    def handle(self, *args, **options):
        if options["probe"]:
            return self.probe()
        root = (settings.BASE_DIR / (options["dir"] or settings.DIST_DIR)).resolve()
        if not (root / "index.html").is_file():
            raise CommandError(f"preview: {root} holds no index.html: bake first (`python manage.py bake`)")
        server = serve(root, options["port"])
        self.stdout.write(f"preview: {root} at http://127.0.0.1:{options['port']}/ as Pages serves it; Ctrl-C stops it")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()

    def probe(self):
        import http.client
        import tempfile
        failed = []
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch) / "dist"
            for path, text in {"index.html": "<p>index</p>", "a/b.html": "<p>b</p>", "a/b.md": "# B\n", "a.html": "<p>a</p>",
                               "404.html": "<p>nothing here</p>", "static/site.css": "p{}", "d/index.html": "<p>d</p>",
                               "llms.txt": "# x\n", "index.json": "{}", "_headers": "/*\n  X: y\n"}.items():
                (root / path).parent.mkdir(parents=True, exist_ok=True)
                (root / path).write_text(text, encoding="utf-8", newline="\n")
            (Path(scratch) / "outside.txt").write_text("not served\n", encoding="utf-8")
            server = serve(root, 0, quiet=True)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                def get(address: str, method: str = "GET") -> tuple[int, str, str, bytes]:
                    connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
                    connection.request(method, address)
                    response = connection.getresponse()
                    data = response.read()
                    connection.close()
                    return response.status, response.getheader("Location") or "", response.getheader("Content-Type") or "", data

                nothing = (404, "", "text/html; charset=utf-8", b"<p>nothing here</p>")
                for address, want in (
                        ("/", (200, "", "text/html; charset=utf-8", b"<p>index</p>")),
                        ("/a/b", (200, "", "text/html; charset=utf-8", b"<p>b</p>")),
                        ("/a", (200, "", "text/html; charset=utf-8", b"<p>a</p>")),
                        ("/a/b.md", (200, "", "text/markdown; charset=utf-8", b"# B\n")),
                        ("/llms.txt", (200, "", "text/plain; charset=utf-8", b"# x\n")),
                        ("/index.json", (200, "", "application/json; charset=utf-8", b"{}")),
                        ("/static/site.css", (200, "", "text/css; charset=utf-8", b"p{}")),
                        ("/a/b.html", (308, "/a/b", "", b"")),
                        ("/a/b/", (308, "/a/b", "", b"")),
                        ("/a/", (308, "/a", "", b"")),
                        ("/index.html", (308, "/", "", b"")),
                        ("/index", (308, "/", "", b"")),
                        ("/d", (308, "/d/", "", b"")),
                        ("/d/index", (308, "/d/", "", b"")),
                        ("/d/index.html", (308, "/d/", "", b"")),
                        ("/d/", (200, "", "text/html; charset=utf-8", b"<p>d</p>")),
                        ("/a/b?x=1", (200, "", "text/html; charset=utf-8", b"<p>b</p>")),
                        ("/../a.html", (308, "/a", "", b"")),
                        ("/static/../a", (200, "", "text/html; charset=utf-8", b"<p>a</p>")),
                        # nothing is served, and no redirect to nothing
                        ("/nope", nothing), ("/a/nope.md", nothing), ("/nope/", nothing), ("/nope.html", nothing),
                        ("/a/b.md/", nothing), ("/a.html/", nothing), ("/_headers", nothing), ("/_redirects", nothing),
                        ("/A/B", nothing), ("/a/b.html.", nothing), ("/a/B.MD", nothing), ("/a/b.md::$DATA", nothing),
                        ("/a%5Cb", nothing), ("/C:/Windows/win.ini", nothing), ("/C%3A/Windows/win.ini", nothing),
                        ("/../outside.txt", nothing), ("/%2e%2e/outside.txt", nothing), ("/a/b%00", nothing)):
                    got = get(address)
                    if got != want:
                        failed.append(f"{address}: got {got}, wanted {want}")
                status, _location, kind, data = get("/a/b", "HEAD")
                if (status, kind, data) != (200, "text/html; charset=utf-8", b""):
                    failed.append(f"HEAD /a/b: got {(status, kind, data)}")
            finally:
                server.shutdown()
                server.server_close()
        if failed:
            raise CommandError("preview --probe: FAILED\n  " + "\n  ".join(failed))
        self.stdout.write("preview --probe: ok. A page is served at its address from its .html, the root from index.html, a file "
                          "at its own path with its media type (.md as text/markdown), each under its exact name only; .html, a "
                          "trailing slash, /index and /index.html are answered with a 308 to the address that serves; a directory's "
                          "index is served with the slash; what has no file, a redirect to nothing, Pages's own files, another "
                          "case, a trailing dot, a drive, a backslash, a NUL and a climb above the root are all answered with "
                          "404.html and 404; a query string is ignored; HEAD answers without a body.")
