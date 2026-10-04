"""Publish the baked book to Cloudflare Pages, refusing on any failed gate.

    python manage.py deploy                      pages/ to production (the branch main)
    python manage.py deploy --book DIR           another directory of pages instead
    python manage.py deploy --branch skeleton    a preview deployment, at https://skeleton.<project>.pages.dev
    python manage.py deploy --dry-run            everything but the upload and the fetch-back
    python manage.py deploy --probe              prove it stops where it should, without the network

In order, stopping at the first failure and saying which step it was:

1. `python tools/pointers.py --check BOOK`: every page's pointer report, beside the page, is
   what the gate writes now. A stale one means a pointer lands on changed bytes, or a page was
   changed and the gate not run; a missing one, that it was never run. When the book is inside
   this repository, a report that is not committed, or changed since, stops it too: the
   reports are what a re-pin compares, and must be in the history.
2. `python manage.py bake` of the same book: the loader's refusals, the two gates on every
   page, the agent's files, and the link gate over what was written. The book is the one
   named here (`--book`, else `pages/`), whatever `$BOOK` says.
3. `wrangler pages deploy dist --project-name PROJECT --branch BRANCH --commit-dirty=true`.
4. Every file the bake wrote, but the static files, fetched back from the deployment and
   compared byte for byte with dist/: the pages at their addresses, the twins, the agent's
   files, robots.txt; and an address with no file, which must answer 404 with 404.html. A
   file that comes back different is fetched again until it matches or two minutes have
   passed since the first fetch: a deployment takes a moment to answer at its address.

The token and the account come from the environment, never from the repository:
CLOUDFLARE_API_TOKEN (or `--token-file FILE`, whose quotes and white space are stripped) and
CLOUDFLARE_ACCOUNT_ID. The token goes to wrangler in its environment and is never on a command
line or in a message. The project is settings.PAGES_PROJECT; the production address is
settings.SITE_URL, and a branch's is https://ALIAS.PROJECT.pages.dev, the alias being the
branch's name as Pages makes it (lower case, every other character a hyphen, at most
twenty-eight). Wrangler is the wrangler.js that $WRANGLER names, run with node; else the npm
global's wrangler.js, which on this machine is what works under Git Bash; else `wrangler` on
PATH.

The fetch-back uses curl, which every machine this runs on has and whose trust store is the
system's (Python's is not always); where a host does not resolve (a `*.pages.dev` address on a
network whose resolver filters it), its address is looked up at 1.1.1.1 over DNS over HTTPS
and curl is told to resolve it there. Production is fetched through the proxied custom domain:
a zone feature that rewrites HTML (an injected beacon, email obfuscation) would make every
deploy stop here, which is the point.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

NOT_FETCHED = (".baked", "_headers", "_redirects")
RETRY_FOR = 120  # seconds a file may take to come back as uploaded


class Stopped(Exception):
    """The deploy stopped: at which step, and why."""

    def __init__(self, step: str, why: str):
        super().__init__(f"deploy: stopped at {step}: {why}")
        self.step, self.why = step, why


def wrangler_command() -> list[str]:
    named = os.environ.get("WRANGLER")
    if named:
        return ["node", named]
    global_js = Path.home() / "AppData" / "Roaming" / "npm" / "node_modules" / "wrangler" / "bin" / "wrangler.js"
    if global_js.is_file():
        return ["node", str(global_js)]
    found = shutil.which("wrangler")
    if found:
        return [found]
    raise Stopped("the upload", "no wrangler: install it (npm install -g wrangler), or name its wrangler.js in $WRANGLER")


def strip_token(text: str) -> str:
    """A token as stored: white space and quotes of either kind around it stripped, however nested."""
    stripped = text.strip()
    while stripped != stripped.strip("\"'").strip():
        stripped = stripped.strip("\"'").strip()
    return stripped


def token_from(file: str | None) -> str | None:
    if os.environ.get("CLOUDFLARE_API_TOKEN"):
        return strip_token(os.environ["CLOUDFLARE_API_TOKEN"])
    if file:
        path = Path(file).expanduser()
        if not path.is_file():
            raise Stopped("the start", f"no token file at {path}")
        return strip_token(path.read_text(encoding="utf-8"))
    return None


def alias(branch: str) -> str:
    """A branch's subdomain as Pages makes it."""
    return re.sub(r"[^a-z0-9]", "-", branch.lower())[:28]


def address_of(path: str) -> str:
    """The address a file in dist/ is served at."""
    if path == "index.html":
        return "/"
    return "/" + (path[:-len(".html")] if path.endswith(".html") else path)


def fetched_files(out: Path) -> list[str]:
    """What the fetch-back compares: everything but the static files and Pages's own files."""
    return sorted(p.relative_to(out).as_posix() for p in out.rglob("*")
                  if p.is_file() and not p.relative_to(out).parts[0] == "static" and p.name not in NOT_FETCHED)


def uncommitted_reports(book_dir: Path) -> list[str]:
    """Pointer reports under the book that are not in the repository's history as they stand,
    when the book is inside this repository; [] otherwise."""
    try:
        relative = book_dir.resolve().relative_to(Path(settings.BASE_DIR).resolve()).as_posix()
    except ValueError:
        return []
    done = subprocess.run(["git", "-C", str(settings.BASE_DIR), "status", "--porcelain", "--untracked-files=all", "--", relative],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    if done.returncode:
        return []
    return sorted(line[3:] for line in done.stdout.splitlines() if line[3:].endswith(".pointers.json"))


def resolve_with_doh(host: str) -> str | None:
    """An A record from 1.1.1.1 over DNS over HTTPS, for a host the machine's resolver does not answer."""
    try:
        done = subprocess.run(["curl", "-sS", "-H", "accept: application/dns-json",
                               f"https://cloudflare-dns.com/dns-query?name={host}&type=A"],
                              capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
        answers = [a["data"] for a in json.loads(done.stdout).get("Answer", []) if a.get("type") == 1]
        return answers[0] if answers else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def curl_fetch(url: str) -> tuple[int, dict, bytes]:
    """(status, headers, body) for a URL, through curl."""
    host = url.split("/", 3)[2]
    resolve = []
    try:
        socket.getaddrinfo(host, 443)
    except OSError:
        found = resolve_with_doh(host)
        if found:
            resolve = ["--resolve", f"{host}:443:{found}"]
    with tempfile.TemporaryDirectory() as scratch:
        body, heads = os.path.join(scratch, "body"), os.path.join(scratch, "heads")
        done = subprocess.run(["curl", "-sS", "-o", body, "-D", heads, "-w", "%{http_code}", *resolve, url],
                              capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
        if done.returncode:
            raise Stopped("the fetch-back", f"curl could not fetch {url}: {done.stderr.strip()}")
        headers = {}
        for line in Path(heads).read_text(encoding="utf-8", errors="replace").splitlines():
            name, colon, value = line.partition(":")
            if colon:
                headers[name.strip().lower()] = value.strip()
        return int(done.stdout.strip() or 0), headers, Path(body).read_bytes()


def deploy(book: str | None, out: Path, branch: str, dry_run: bool, token: str | None, account: str | None,
           say, run=subprocess.run, fetch=curl_fetch, wrangler: list[str] | None = None, retry_for: int = RETRY_FOR,
           clock=time.monotonic, sleep=time.sleep) -> str:
    """The four steps. `run` runs a command (subprocess.run's shape); `fetch` fetches a URL
    (curl_fetch's shape); `wrangler` is the command that is wrangler; `clock` and `sleep` are
    the fetch-back's; all are stood in for by the probe. Returns the site's address."""
    book_dir = (settings.BASE_DIR / (book or "pages")).resolve()
    project = settings.PAGES_PROJECT
    if not dry_run:
        if not token:
            raise Stopped("the start", "no token: set CLOUDFLARE_API_TOKEN, or give --token-file")
        if not account:
            raise Stopped("the start", "no account: set CLOUDFLARE_ACCOUNT_ID")
    # 1. the pointer reports: fresh, and in the history
    gate = [sys.executable, str(settings.BASE_DIR / "tools" / "pointers.py"), "--check", str(book_dir)]
    done = run(gate, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(settings.BASE_DIR))
    if done.returncode:
        raise Stopped("the pointer reports", f"`python tools/pointers.py --check {book_dir.name}` failed:\n{done.stdout}{done.stderr}".rstrip()
                      + f"\n(run `python tools/pointers.py {book_dir.name}` and commit the reports)")
    loose = uncommitted_reports(book_dir)
    if loose:
        raise Stopped("the pointer reports", "not committed, or changed since: " + ", ".join(loose))
    say(f"deploy: the pointer reports of {book_dir.name}/ are fresh")
    # 2. the bake of the same book: the loader, both gates, the agent's files, the link gate
    try:
        call_command("bake", book=str(book_dir), out=str(out), **({"stdout": say.stream} if hasattr(say, "stream") else {}))
    except CommandError as why:
        raise Stopped("the bake", str(why)) from None
    say(f"deploy: baked {book_dir.name}/ to {out.name}/")
    if dry_run:
        say("deploy: dry run, nothing uploaded")
        return ""
    # 3. the upload
    command = (wrangler or wrangler_command()) + ["pages", "deploy", str(out), "--project-name", project, "--branch", branch, "--commit-dirty=true"]
    env = dict(os.environ, CLOUDFLARE_API_TOKEN=token, CLOUDFLARE_ACCOUNT_ID=account)
    done = run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, cwd=str(settings.BASE_DIR))
    if done.returncode:
        raise Stopped("the upload", f"wrangler exited {done.returncode}:\n{done.stdout}{done.stderr}".rstrip())
    say(f"deploy: uploaded to the project {project}, branch {branch}")
    # 4. the fetch-back
    site = settings.SITE_URL.rstrip("/") if branch == "main" else f"https://{alias(branch)}.{project}.pages.dev"
    started = clock()
    for path in fetched_files(out):
        wanted = (out / path).read_bytes()
        while True:
            status, headers, body = fetch(site + address_of(path))
            if status == 200 and body == wanted:
                break
            if clock() - started > retry_for:
                raise Stopped("the fetch-back", f"{site}{address_of(path)} did not come back as uploaded within {retry_for} seconds "
                                                f"(last: {status}, {len(body)} bytes; {len(wanted)} in {out.name}/{path})")
            sleep(5)
        if path.endswith(".md") and not headers.get("content-type", "").startswith("text/markdown"):
            say(f"deploy: note: {site}{address_of(path)} is served as {headers.get('content-type', 'no content type')}, "
                f"not text/markdown (the _headers file was not applied)")
    status, _headers, body = fetch(site + "/an-address-with-no-page")
    if status != 404 or body != (out / "404.html").read_bytes():
        raise Stopped("the fetch-back", f"an address with no page answered {status}, not 404 with 404.html")
    say(f"deploy: ok, {len(fetched_files(out))} files fetched back from {site} and identical to {out.name}/; an address with no page answers 404")
    return site


class Command(BaseCommand):
    help = "Run the gates, bake, publish to Cloudflare Pages, and fetch every page back; stop on any failure."

    def add_arguments(self, parser):
        parser.add_argument("--book", help="the directory of pages to publish (default: pages)")
        parser.add_argument("--branch", default="main", help="the Pages branch: main is production (default)")
        parser.add_argument("--dry-run", action="store_true", help="the gates and the bake, no upload")
        parser.add_argument("--token-file", help="a file holding the API token, if CLOUDFLARE_API_TOKEN is not set")
        parser.add_argument("--probe", action="store_true", help="prove the deploy stops where it should, without the network")

    def handle(self, *args, **options):
        if options["probe"]:
            return self.probe()

        def say(line: str) -> None:
            self.stdout.write(line)
        say.stream = self.stdout
        try:
            deploy(options["book"], settings.DIST_DIR, options["branch"], options["dry_run"],
                   token_from(options["token_file"]), os.environ.get("CLOUDFLARE_ACCOUNT_ID"), say)
        except Stopped as stopped:
            raise CommandError(str(stopped)) from None

    def probe(self):
        """A scratch book, deployed with wrangler, curl and the clock stood in for: the deploy
        stops at a missing or stale pointer report, at a missing token or account, at a wrangler
        that fails, at a page that comes back changed past the deadline, at an address with no
        page that is not a 404; goes through when all is well, waiting for a page that comes
        back as uploaded late; bakes the book named and not $BOOK; keeps the token off the
        command line and in wrangler's environment; and uploads nothing on a dry run."""
        failed = []
        said: list[str] = []
        calls: list[tuple[list[str], dict]] = []
        now = [0.0]

        class Done:
            def __init__(self, returncode: int, stdout: str = "", stderr: str = ""):
                self.returncode, self.stdout, self.stderr = returncode, stdout, stderr

        def runner(exit_code: int):
            def run(command, **kwargs):
                calls.append((list(command), kwargs.get("env") or {}))
                if "pointers.py" in str(command[1]):
                    return subprocess.run(command, **kwargs)  # the real gate: the first step is its check
                return Done(exit_code, "https://abc123.project.pages.dev\n", "")
            return run

        def fetcher(served: Path, change: str | None = None, missing_status: int = 404, stale_until: int = 0):
            fetches = [0]

            def fetch(url: str):
                fetches[0] += 1
                address = url.split("/", 3)[3] if url.count("/") >= 3 else ""
                if address == "an-address-with-no-page":
                    return missing_status, {}, (served / "404.html").read_bytes()
                path = "index.html" if address == "" else address
                file = served / path
                if not file.is_file():
                    file = served / f"{path}.html"
                if not file.is_file():
                    return 404, {}, b""
                data = file.read_bytes()
                if (change and path == change) or fetches[0] <= stale_until:
                    data += b"the deployment before this one\n"
                return 200, {"content-type": "text/markdown; charset=utf-8" if path.endswith(".md") else "text/html"}, data
            return fetch

        def clock() -> float:
            return now[0]

        def sleep(seconds: float) -> None:
            now[0] += seconds

        def say(line: str) -> None:
            said.append(line)

        def expect_stop(label: str, step: str, **kwargs) -> None:
            try:
                deploy(**kwargs)
                failed.append(f"{label}: the deploy went through")
            except Stopped as stopped:
                if stopped.step != step:
                    failed.append(f"{label}: stopped at {stopped.step}, not {step}: {stopped.why}")

        with tempfile.TemporaryDirectory() as scratch:
            pin = json.loads(Path(settings.PIN_FILE).read_text(encoding="utf-8"))
            commit = pin["trees"][pin["subject"]]["commit"]
            head = f"---\ndjango: main at {commit}\n---\n"
            book = Path(scratch) / "book"
            book.mkdir()
            (book / "index.md").write_text(head.replace("---\n", "---\ncontents: a\n", 1) + "# A book\n\nIts lede.\n\n## One\n\nText.\n",
                                           encoding="utf-8", newline="\n")
            (book / "a.md").write_text(head + "# A\n\nLede.\n\n## First\n\nText, and `django/core/handlers/base.py:BaseHandler.load_middleware`.\n",
                                       encoding="utf-8", newline="\n")
            other = Path(scratch) / "other"
            other.mkdir()
            (other / "index.md").write_text(head + "# Another book\n\nIts lede.\n\n## One\n\nText.\n", encoding="utf-8", newline="\n")
            out = Path(scratch) / "out"
            relative = str(book)  # an absolute path: `bake --book` takes one as it takes a name under the repository
            gate = [sys.executable, str(settings.BASE_DIR / "tools" / "pointers.py"), str(book)]
            common = dict(out=out, branch="main", dry_run=False, token="t-o-k-e-n", account="a", say=say, retry_for=20,
                          wrangler=["a-wrangler-stood-in-for"], clock=clock, sleep=sleep)
            # no report yet: the check fails before anything is baked or uploaded
            expect_stop("a page with no pointer report", "the pointer reports", book=relative, run=runner(0), fetch=fetcher(out), **common)
            if any("pages" in c for c, _env in calls):
                failed.append("wrangler was run though the pointer reports failed")
            subprocess.run(gate, capture_output=True, check=True)
            report = book / "a.pointers.json"
            text = report.read_text(encoding="utf-8")
            report.write_text(text.replace('"fingerprint": "', '"fingerprint": "0', 1), encoding="utf-8", newline="\n")
            expect_stop("a stale pointer report", "the pointer reports", book=relative, run=runner(0), fetch=fetcher(out), **common)
            report.write_text(text, encoding="utf-8", newline="\n")
            # a token or an account missing
            expect_stop("no token", "the start", book=relative, run=runner(0), fetch=fetcher(out), **{**common, "token": None})
            expect_stop("no account", "the start", book=relative, run=runner(0), fetch=fetcher(out), **{**common, "account": None})
            # wrangler fails
            expect_stop("a wrangler that fails", "the upload", book=relative, run=runner(1), fetch=fetcher(out), **common)
            # a page comes back changed, past the deadline; an address with no page is not a 404
            expect_stop("a page changed on the way", "the fetch-back", book=relative, run=runner(0), fetch=fetcher(out, change="a.md"), **common)
            expect_stop("a page that is not a 404 where there is no page", "the fetch-back", book=relative, run=runner(0),
                        fetch=fetcher(out, missing_status=200), **common)
            # all well, the deployment answering late with what was uploaded
            calls.clear()
            said.clear()
            before, settings.BOOK_DIR = settings.BOOK_DIR, other  # $BOOK says another book: the one named must be baked
            try:
                site = deploy(book=relative, run=runner(0), fetch=fetcher(out, stale_until=3), **common)
                if site != settings.SITE_URL.rstrip("/"):
                    failed.append(f"production's address is {site}")
                if "A book" not in (out / "index.html").read_text(encoding="utf-8"):
                    failed.append("the book baked is $BOOK's, not the one named")
                upload = [(c, env) for c, env in calls if "pages" in c and "deploy" in c]
                if len(upload) != 1 or upload[0][0][-6:] != [str(out), "--project-name", settings.PAGES_PROJECT, "--branch", "main", "--commit-dirty=true"]:
                    failed.append(f"wrangler was not run as the head says: {[c for c, _ in upload]}")
                if upload and ("t-o-k-e-n" in " ".join(upload[0][0]) or upload[0][1].get("CLOUDFLARE_API_TOKEN") != "t-o-k-e-n"
                               or upload[0][1].get("CLOUDFLARE_ACCOUNT_ID") != "a"):
                    failed.append("the token is on wrangler's command line, or not in its environment with the account")
                if any("t-o-k-e-n" in line for line in said):
                    failed.append("the token was printed")
                if not any("fetched back" in line for line in said):
                    failed.append("a deploy that went through did not say so")
                if now[0] < 15:
                    failed.append(f"the fetch-back did not wait for the deployment to answer as uploaded (waited {now[0]}s)")
            except Stopped as stopped:
                failed.append(f"a sound book was stopped at {stopped.step}: {stopped.why}")
            finally:
                settings.BOOK_DIR = before
            # a branch is a preview address, named as Pages names it; a dry run uploads nothing
            calls.clear()
            try:
                site = deploy(book=relative, run=runner(0), fetch=fetcher(out), **{**common, "branch": "Feature/New_Chapter-of-the-book-2026"})
                if site != f"https://feature-new-chapter-of-the-b.{settings.PAGES_PROJECT}.pages.dev":
                    failed.append(f"a branch's address is {site}")
            except Stopped as stopped:
                failed.append(f"a branch deploy was stopped at {stopped.step}: {stopped.why}")
            calls.clear()
            try:
                deploy(book=relative, run=runner(0), fetch=fetcher(out), **{**common, "dry_run": True, "token": None, "account": None})
                if any("pages" in c for c, _env in calls):
                    failed.append("a dry run uploaded")
            except Stopped as stopped:
                failed.append(f"a dry run was stopped at {stopped.step}: {stopped.why}")
            if strip_token(" '\"abc\"' \n") != "abc":
                failed.append("a token's quotes are not stripped")
            try:
                token_from(str(Path(scratch) / "no-such-file"))
                failed.append("a missing token file was not a stop")
            except Stopped:
                pass
            report.unlink()
        if failed:
            raise CommandError("deploy --probe: FAILED\n  " + "\n  ".join(failed))
        self.stdout.write("deploy --probe: ok. The deploy stops at a page with no pointer report or a stale one, before anything is "
                          "baked or uploaded; at a missing token, token file or account; at a wrangler that fails; at a page that "
                          "comes back changed past the deadline; at an address with no page that is not a 404. A sound book goes "
                          "through to production, the book named and not $BOOK's, the token in wrangler's environment and on no "
                          "command line or message, waiting for the deployment to answer as uploaded; a branch goes to its "
                          "alias as Pages makes it; a dry run uploads nothing.")
