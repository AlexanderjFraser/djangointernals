#!/usr/bin/env python3
"""The pin: the one place the source a book describes is written down, for every tool.

`pin.json`, at the book's root, names each tree the book is verified against (the subject,
and the libraries the subject leans on) by repository and commit. Every other tool asks this
module where a tree is and which commit it is at, so a re-pin starts here: this file, the
documents it lists, and whatever of the book's own configuration the new tree has outgrown.

    python tools/pin.py                        what is pinned, and whether each tree on disk is that
    python tools/pin.py fetch [NAME ...]       fetch each tree at its pinned commit
    python tools/pin.py fetch --replace NAME   fetch it afresh: a tree on disk that is not the pin is deleted first,
                                               if it is a tree fetched from the same repository, and nothing else is
    python tools/pin.py check                  fail unless the trees on disk are the ones pinned
    python tools/pin.py --probe                prove that fetch and check do what this says

Every command takes `--root DIR`, the book's root; the default is $BOOK_ROOT, else the
directory above this file.

The shape of pin.json:

    {
      "subject": "django",              the tree the book is about; a key of "trees"
      "python": "3.12",                 the oldest Python that parses and runs the subject
      "trees": {
        "<name>": {
          "repository": "https://...",  where the tree is fetched from
          "commit": "<40 hex digits>",  the pin: what fetch fetches and check compares
          "path": "reference/<name>",   where the tree lives, from the book's root: a directory
                                        of its own, in plain names, at least two levels down,
                                        inside no other tree
          "imports": ["yaml"],          optional: the top-level names the tree is imported by,
                                        when they are not the tree's name
          "evidence": {"file": "...", "contains": "..."},
                                        optional: a line the tree must hold, so that what the
                                        entry says of the tree in words is checked too
          ...                           every other key is for the reader: a date, a version, why
        }
      },
      "named_in": ["CLAUDE.md"]         documents that must spell out the subject's commit
    }

A tree is fetched by commit, never by branch, so `fetch` gets the pin and not the branch as it
stands that day. And `fetch` asks for the bytes the commit holds, over the machine's own git
settings and the tree's own attributes: no conversion of line endings or encoding, no keyword
expansion, no filter, no hook, and a symbolic link written as the small file git stores for
it. Sizes and fingerprints are taken from those bytes, so they are the same on every machine.
What makes that sure is `check`, which hashes every file on disk against the commit and
refuses a tree that differs, however it came to differ: a tree cloned by hand with a git that
converts line endings measures larger, hashes differently, and is refused. The
files of a tree are the files its commit holds (`files()`), never what a directory walk
finds: running the subject leaves caches and build metadata behind.

What `check` does not do: it does not compare a tree with its remote (a pin is a commit, and
a commit cannot change); it ignores untracked files, file modes and submodules; and in a
document it looks only for the commit.

Vendored: the copy in a book's repository is written by a command and is not edited there.
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PIN_FILE = "pin.json"
FLOOR = (3, 12)  # what the tools themselves use: rmtree's onexc, the tokenizer's f-string tokens
# In .git/info/attributes, which outranks every .gitattributes: nothing is converted at checkout.
ATTRIBUTES = "* -text -ident -filter -working-tree-encoding\n"
# On every git command the tools run, outranking the machine's files and its environment.
OWN = ("-c", "core.autocrlf=false", "-c", "core.symlinks=false", "-c", "core.hooksPath=.git/no-hooks")
PART = re.compile("[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?")  # of a tree's path: no dot first, no dot or space last


def root(book: str | None = None) -> str:
    """The book's root: an explicit path, else $BOOK_ROOT, else the directory above this file."""
    return os.path.abspath(book or os.environ.get("BOOK_ROOT") or os.path.join(HERE, ".."))


def load(book: str | None = None) -> dict:
    """pin.json, checked for the keys every tool relies on."""
    path = os.path.join(root(book), PIN_FILE)
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    trees = data.get("trees") or {}
    if data.get("subject") not in trees:
        raise SystemExit(f'{path}: "subject" must name one of "trees"')
    for name, entry in trees.items():
        missing = [k for k in ("repository", "commit", "path") if not entry.get(k)]
        if missing:
            raise SystemExit(f"{path}: tree {name} has no {', '.join(missing)}")
        if not re.fullmatch("[0-9a-f]{40}", entry["commit"]):
            raise SystemExit(f"{path}: tree {name}: the commit must be 40 hex digits, not a branch or a tag")
        # fetch --replace deletes what the path names: plain names only, two levels down
        parts = entry["path"].split("/")
        if len(parts) < 2 or not all(PART.fullmatch(p) for p in parts):
            raise SystemExit(f"{path}: tree {name}: its path must be a directory of its own at least two "
                             f"levels below the book's root, in plain names, such as reference/{name}")
    paths = sorted(e["path"].casefold() for e in trees.values())  # one directory, where case does not count
    for a, b in zip(paths, paths[1:]):
        if b == a or b.startswith(a + "/"):
            raise SystemExit(f"{path}: two trees share the directory {a}")
    return data


def tree(name: str | None = None, book: str | None = None) -> str:
    """Where a tree is on disk; the subject's when no name is given."""
    data = load(book)
    return os.path.join(root(book), *data["trees"][name or data["subject"]]["path"].split("/"))


def commit(name: str | None = None, book: str | None = None) -> str:
    data = load(book)
    return data["trees"][name or data["subject"]]["commit"]


def libraries(book: str | None = None) -> dict[str, str]:
    """{the name a library is imported by: its tree}, for every tree but the subject."""
    data = load(book)
    return {imported: name for name, entry in data["trees"].items() if name != data["subject"]
            for imported in entry.get("imports", [name])}


def files(path: str) -> list[str]:
    """Every file the commit holds, as paths from the tree's root with forward slashes, sorted."""
    out = git(path, "-c", "core.quotepath=false", "ls-files", "-z")
    return sorted(p for p in out.split("\0") if p)


def require_python(book: str | None = None, pinned: bool = True) -> None:
    """Stop unless this Python can run the tools and, when `pinned`, parse the book's subject:
    an older one fails on newer syntax."""
    want = FLOOR
    if pinned:
        want = max(want, tuple(int(x) for x in str(load(book).get("python", "3")).split(".")))
    if sys.version_info[:len(want)] < want:
        have = ".".join(str(x) for x in sys.version_info[:3])
        raise SystemExit(f"this is Python {have}; the tools and the pin need {'.'.join(map(str, want))} or "
                         f"later (run them with the project's virtual environment)")


def git(cwd: str, *args: str, check: bool = True, env: dict | None = None) -> str:
    p = subprocess.run(("git", "-C", cwd) + OWN + args, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env)
    if check and p.returncode:
        raise RuntimeError(f"git {' '.join(args)}: {p.stderr.strip() or p.stdout.strip()}")
    return p.stdout.strip("\n")


def unfaithful(path: str, known: set[str]) -> list[str]:
    """How the files on disk are not the bytes the commit holds, where git itself reports no
    change. `known` holds the files git does report, which are not counted again."""
    index = {}
    for item in git(path, "-c", "core.quotepath=false", "ls-files", "-s", "-z").split("\0"):
        if item:
            meta, name = item.split("\t", 1)
            mode, blob, _stage = meta.split()
            if mode != "160000" and name not in known:  # a submodule's entry is a commit, not a file
                index[name] = blob
    on_disk = [n for n in index if os.path.isfile(os.path.join(path, *n.split("/")))]
    differing = [n for n in index if n not in set(on_disk)]
    if on_disk:
        done = subprocess.run(("git", "-C", path, "hash-object", "--no-filters", "--stdin-paths"),
                              input=("\n".join(on_disk) + "\n").encode("utf-8"), capture_output=True)
        if done.returncode:
            raise RuntimeError(f"git hash-object: {done.stderr.decode('utf-8', 'replace').strip()}")
        differing += [n for n, found in zip(on_disk, done.stdout.decode("ascii").split()) if found != index[n]]
    converted = 0
    for name in differing:
        full = os.path.join(path, *name.split("/"))
        if os.path.isfile(full):
            with open(full, "rb") as f:
                data = f.read().replace(b"\r\n", b"\n")
            kind = "sha1" if len(index[name]) == 40 else "sha256"
            converted += hashlib.new(kind, b"blob %d\0" % len(data) + data).hexdigest() == index[name]
    out = []
    if converted:
        out.append(f"{converted} files were checked out with converted line endings; their bytes are not "
                   f"the repository's")
    if len(differing) > converted:
        out.append(f"{len(differing) - converted} files on disk are not the bytes the commit holds, though "
                   f"git reports no change (a filter, an expanded keyword, a symbolic link, a file marked "
                   f"unchanged)")
    return out


def problems(entry: dict, path: str) -> list[str]:
    """Why the tree at `path` is not the one `entry` pins; empty when it is."""
    if not os.path.isdir(path):
        return ["missing"]
    # Asked of a plain directory, git answers for whatever repository encloses it: the book's own.
    if not os.path.exists(os.path.join(path, ".git")):
        return ["not a git repository"]
    out = []
    head = git(path, "rev-parse", "-q", "--verify", "HEAD", check=False)
    if head != entry["commit"]:
        out.append(f"HEAD is {head[:12] if head else 'no commit'}, the pin is {entry['commit'][:12]}")
    if not head:
        return out
    status = git(path, "-c", "core.quotepath=false", "status", "--porcelain", "-z", "--untracked-files=no")
    changed = {item[3:] for item in status.split("\0") if item}
    if changed:
        out.append(f"{len(changed)} tracked files differ from the commit")
    out += unfaithful(path, changed)
    evidence = entry.get("evidence")
    if evidence:
        target = os.path.join(path, *evidence["file"].split("/"))
        text = ""
        if os.path.isfile(target):
            with open(target, encoding="utf-8", errors="replace") as f:
                text = f.read()
        if evidence["contains"] not in text:
            out.append(f"{evidence['file']} does not contain {evidence['contains']!r}")
    return out


def check(book: str | None = None) -> list[str]:
    """Everything that keeps the trees on disk from being the ones pin.json names."""
    data = load(book)
    out = []
    for name, entry in data["trees"].items():
        out += [f"{name}: {why}" for why in problems(entry, tree(name, book))]
    pinned = data["trees"][data["subject"]]["commit"]
    for doc in data.get("named_in", ()):
        path = os.path.join(root(book), *doc.split("/"))
        text = ""
        if os.path.isfile(path):
            with open(path, encoding="utf-8", errors="replace") as f:
                text = f.read()
        if pinned not in text:
            out.append(f"{doc} does not name the pinned commit {pinned}")
    return out


def remove(path: str) -> None:
    """Delete a tree. Git's objects are read-only, which on Windows stops a plain rmtree."""
    def writable(func, target, _exc):
        os.chmod(target, stat.S_IWRITE)
        func(target)
    shutil.rmtree(path, onexc=writable)


def prepare(path: str) -> None:
    """A repository at `path` whose checkouts are the commit's own bytes on any machine."""
    os.makedirs(path, exist_ok=True)
    subprocess.run(("git", "init", "-q", path), check=True)
    git(path, "config", "core.autocrlf", "false")
    git(path, "config", "core.symlinks", "false")
    os.makedirs(os.path.join(path, ".git", "info"), exist_ok=True)
    with open(os.path.join(path, ".git", "info", "attributes"), "w", encoding="utf-8", newline="\n") as f:
        f.write(ATTRIBUTES)


def fetch(name: str, entry: dict, path: str, replace: bool = False) -> bool:
    """Bring the tree at `path` to the pinned commit. Never overwrites a tree unless told to."""
    if os.path.exists(path):
        why = problems(entry, path)
        if not why:
            print(f"{name}: already at {entry['commit'][:12]}")
            return True
        if not replace:
            print(f"{name}: {path} is not the pin ({'; '.join(why)}). "
                  f"`fetch --replace {name}` deletes it and fetches again.")
            return False
        # Only a tree this pin fetched is ever deleted: a repository whose origin is the entry's.
        fetched = (os.path.isdir(os.path.join(path, ".git"))
                   and git(path, "config", "--get", "remote.origin.url", check=False) == entry["repository"])
        if fetched:
            remove(path)
        elif not os.path.isdir(path) or os.listdir(path):
            print(f"{name}: {path} is not a tree fetched from {entry['repository']}; it is not deleted.")
            return False
    prepare(path)
    git(path, "remote", "add", "origin", entry["repository"])
    git(path, "fetch", "-q", "--depth", "1", "origin", entry["commit"])
    git(path, "checkout", "-q", "--detach", "FETCH_HEAD")
    why = problems(entry, path)
    print(f"{name}: fetched {entry['commit'][:12]} into {path}" if not why
          else f"{name}: fetched, but {'; '.join(why)}")
    return not why


def status(book: str | None = None) -> int:
    data = load(book)
    code = 0
    for name, entry in data["trees"].items():
        why = problems(entry, tree(name, book))
        role = "subject" if name == data["subject"] else "library"
        label = entry.get("version") or entry.get("branch") or ""
        print(f"{role:8}{name:10}{entry['commit'][:12]}  {label:8}{entry['path']:20}"
              f"{'at the pin' if not why else 'NOT THE PIN: ' + '; '.join(why)}")
        code = code or (2 if why else 0)
    return code


# ----------------------------------------------------------------------------
# the probe, and what the other tools' probes build their scratch trees with

def _write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def _commit_all(repo: str, message: str) -> str:
    """A commit made by plumbing: no hooks, no signing, no user configuration needed."""
    env = dict(os.environ, GIT_AUTHOR_NAME="probe", GIT_AUTHOR_EMAIL="probe@example.invalid",
               GIT_COMMITTER_NAME="probe", GIT_COMMITTER_EMAIL="probe@example.invalid")
    git(repo, "add", "-A")
    parent = git(repo, "rev-parse", "-q", "--verify", "HEAD", check=False)
    made = git(repo, "commit-tree", git(repo, "write-tree"), "-m", message,
               *(("-p", parent) if parent else ()), env=env)
    git(repo, "update-ref", "refs/heads/main", made)
    return made


def _scratch(repo: str, message: str = "probe") -> str:
    """Make the files under `repo` a tree as fetch would leave it, and return its commit."""
    prepare(repo)
    made = _commit_all(repo, message)
    git(repo, "checkout", "-q", "--detach", made)
    return made


def probe() -> int:
    import tempfile
    work = tempfile.mkdtemp(prefix="pinprobe-")
    failed = []
    # A machine whose git converts line endings, makes links, runs a filter and a hook that edits a file.
    settings = {"core.autocrlf": "true", "core.eol": "crlf", "core.symlinks": "true",
                "filter.upper.smudge": "tr a-z A-Z", "core.hooksPath": os.path.join(work, "hooks")}
    hostile = {"GIT_CONFIG_COUNT": str(len(settings))}
    for i, (key, value) in enumerate(settings.items()):
        hostile.update({f"GIT_CONFIG_KEY_{i}": key, f"GIT_CONFIG_VALUE_{i}": value})
    _write(os.path.join(work, "hooks", "post-checkout"), "#!/bin/sh\necho hooked >> pkg/mod.py\n")

    def expect(label: str, found: list[str], needle: str | None) -> None:
        """`found` must be empty when needle is None, and otherwise hold a line containing it."""
        ok = (not found) if needle is None else any(needle in line for line in found)
        if not ok:
            failed.append(f"{label}: wanted {needle or 'no problem'}, got {found}")

    try:
        # An upstream that asks for everything a checkout can do to a file: line endings left to
        # the machine, a keyword to expand, and a symbolic link.
        upstream = os.path.join(work, "upstream")
        source = "# $Id$\nVERSION = 1\n\n\ndef f():\n    return 1\n"
        attributes = "* text=auto\n*.py ident\n*.txt working-tree-encoding=UTF-16\n*.dat filter=upper\n"
        _write(os.path.join(upstream, ".gitattributes"), attributes)
        _write(os.path.join(upstream, "pkg", "mod.py"), source)
        _write(os.path.join(upstream, "pkg", "notes.txt"), "plain text\n")
        _write(os.path.join(upstream, "pkg", "data.dat"), "lower\n")
        _write(os.path.join(upstream, "pkg", "link"), "mod.py")
        prepare(upstream)
        # the upstream is committed as written whatever `prepare` is made to do: its attributes are
        # spelt out here, so that a fault in the tool's own shows in the fetch and not in the fixture
        _write(os.path.join(upstream, ".git", "info", "attributes"), "* -text -ident -working-tree-encoding -filter\n")
        git(upstream, "symbolic-ref", "HEAD", "refs/heads/main")
        git(upstream, "config", "uploadpack.allowAnySHA1InWant", "true")
        git(upstream, "update-index", "--add", "--cacheinfo",
            "120000," + git(upstream, "hash-object", "-w", "pkg/link") + ",pkg/link")
        one = _commit_all(upstream, "one")
        _write(os.path.join(upstream, "pkg", "mod.py"), source.replace("1", "2"))
        two = _commit_all(upstream, "two")

        book = os.path.join(work, "book")
        pin = {"subject": "lib", "python": "3.12", "named_in": ["README.md"],
               "trees": {"lib": {"repository": upstream, "commit": one, "path": "reference/lib",
                                 "evidence": {"file": "pkg/mod.py", "contains": "VERSION = 1"}},
                         "other": {"repository": upstream, "commit": one, "path": "reference/other",
                                   "imports": ["yaml", "_yaml"]}}}
        _write(os.path.join(book, PIN_FILE), json.dumps(pin))
        _write(os.path.join(book, "README.md"), f"pinned at `{one}`\n")
        entry, where = pin["trees"]["lib"], tree("lib", book)
        mod = os.path.join(where, "pkg", "mod.py")
        if libraries(book) != {"yaml": "other", "_yaml": "other"}:
            failed.append(f"libraries() gave {libraries(book)}")

        def quiet(**options) -> bool:
            with contextlib.redirect_stdout(io.StringIO()):
                return fetch("lib", entry, where, **options)

        def here() -> list[str]:
            return [line for line in check(book) if line.startswith("lib:") or "does not name" in line]

        def read(name: str) -> bytes:
            with open(os.path.join(where, *name.split("/")), "rb") as f:
                return f.read()

        # fetch lands on the pinned commit although the branch has moved on, and writes the
        # commit's own bytes although this git is told to convert line endings
        os.environ.update(hostile)
        try:
            quiet()
        finally:
            for key in hostile:
                del os.environ[key]
        if git(where, "rev-parse", "HEAD") != one:
            failed.append("fetch did not land on the pinned commit")
        expect("a tree at the pin", here(), None)
        if read("pkg/mod.py") != source.encode() or read(".gitattributes") != attributes.encode():
            failed.append("fetch converted line endings, expanded a keyword or let a hook run")
        if read("pkg/notes.txt") != b"plain text\n" or read("pkg/data.dat") != b"lower\n":
            failed.append("fetch re-encoded a file or ran a filter")
        if os.path.islink(os.path.join(where, "pkg", "link")) or read("pkg/link") != b"mod.py":
            failed.append("fetch did not write the symbolic link as the file git stores")
        # whether a machine can make a link at all varies, so what fetch asks of git is checked too:
        # on its own commands, and in the tree's own configuration for a git run there by hand
        if (git(where, "config", "--local", "--get", "core.symlinks", check=False) != "false"
                or "core.symlinks=false" not in OWN):
            failed.append("fetch left symbolic links to the machine")
        if files(where) != [".gitattributes", "pkg/data.dat", "pkg/link", "pkg/mod.py", "pkg/notes.txt"]:
            failed.append(f"files() listed {files(where)}")

        # an untracked file is not a difference; a changed tracked file is, even one git is told to overlook
        _write(os.path.join(where, "pkg", "cache.pyc"), "left behind by a run\n")
        expect("an untracked file", here(), None)
        if "pkg/cache.pyc" in files(where):
            failed.append("files() listed an untracked file")
        with open(mod, "a", encoding="utf-8", newline="\n") as f:
            f.write("# edited\n")
        if here() != ["lib: 1 tracked files differ from the commit"]:  # and not counted a second time
            failed.append(f"a modified tree: {here()}")
        git(where, "update-index", "--assume-unchanged", "pkg/mod.py")
        expect("a change git is told to overlook", here(), "not the bytes the commit holds")
        git(where, "update-index", "--no-assume-unchanged", "pkg/mod.py")
        git(where, "checkout", "-q", "--", ".")
        expect("the change undone", here(), None)

        # the same commit checked out by a git left to itself: converted line endings, an expanded keyword
        os.remove(os.path.join(where, ".git", "info", "attributes"))
        for name in (".gitattributes", "pkg/mod.py"):
            os.remove(os.path.join(where, *name.split("/")))
        subprocess.run(("git", "-C", where, "-c", "core.autocrlf=true", "checkout", "-q", "--",
                        ".gitattributes", "pkg/mod.py"), check=True, capture_output=True)
        if git(where, "status", "--porcelain", "--untracked-files=no"):
            failed.append("the probe's converted checkout is one git itself reports as changed")
        expect("converted line endings", here(), "1 files were checked out with converted line endings")
        expect("an expanded keyword", here(), "1 files on disk are not the bytes the commit holds")
        if not quiet(replace=True):
            failed.append("fetch --replace did not mend a converted tree")
        expect("the tree fetched again", here(), None)

        # the tree at another commit: fetch refuses to overwrite it, and replaces it when told to
        git(where, "fetch", "-q", "--depth", "1", "origin", two)
        git(where, "checkout", "-q", "--detach", two)
        expect("a tree at another commit", here(), "HEAD is")
        expect("its evidence", here(), "does not contain")
        if quiet() or git(where, "rev-parse", "HEAD") != two:
            failed.append("fetch overwrote a tree it was not told to replace")
        if not quiet(replace=True) or git(where, "rev-parse", "HEAD") != one:
            failed.append("fetch --replace did not bring the tree back to the pin")

        # a document that does not name the pin; no tree; a plain directory; a repository with no commit
        _write(os.path.join(book, "README.md"), f"pinned at `{one[:12]}`\n")
        expect("a document without the commit", here(), "does not name the pinned commit")
        _write(os.path.join(book, "README.md"), f"pinned at `{one}`\n")
        remove(where)
        expect("a missing tree", here(), "missing")
        os.makedirs(where)
        expect("a plain directory", here(), "not a git repository")
        # fetch --replace deletes only a tree fetched from the entry's repository
        keep = os.path.join(where, "keep.txt")
        _write(keep, "not the pin's to delete\n")
        if quiet(replace=True) or not os.path.exists(keep):
            failed.append("fetch --replace took over a directory it had not fetched")
        subprocess.run(("git", "init", "-q", where), check=True)
        expect("a repository with no commit", here(), "HEAD is no commit")
        if quiet(replace=True) or not os.path.exists(keep):
            failed.append("fetch --replace deleted a repository it had not fetched")

        # a path that fetch --replace must never be given
        for bad in (".", "trees", "reference", "../elsewhere", "reference/lib/../..", os.path.abspath(work),
                    "/abs/elsewhere", "reference/other/in", ".git/objects", "Q:x/y", "reference/OTHER",
                    "reference/lib.", "reference/lib ", "reference\\lib"):
            pin["trees"]["lib"]["path"] = bad
            _write(os.path.join(book, PIN_FILE), json.dumps(pin))
            try:
                load(book)
                failed.append(f"the path {bad!r} was accepted")
            except SystemExit:
                pass
    finally:
        remove(work)
    if failed:
        print("PROBE FAILED:\n  " + "\n  ".join(failed))
        return 1
    print("probe ok: fetch lands on the pinned commit and not the branch's head; writes the commit's own "
          "bytes under a git told to convert line endings, re-encode, filter, make links and run a hook; "
          "overwrites no tree unless told to, and deletes only a tree it fetched; check fails a modified "
          "tree, a change git is told to overlook, converted line endings, an expanded keyword, a tree at "
          "another commit, missing evidence, a document that does not name the pin, a plain directory, "
          "an empty repository and a missing tree; an untracked file is neither a difference nor a file "
          "of the tree; a path that is not a directory of the tree's own, in plain names, is refused")
    return 0


def main(argv: list[str]) -> int:
    args = list(argv)
    book = None
    if "--root" in args:
        at = args.index("--root")
        book = args[at + 1]
        del args[at:at + 2]
    require_python(pinned=False)
    if "--probe" in args:
        return probe()
    require_python(book)
    command = args[0] if args else "status"
    if command == "status":
        return status(book)
    if command == "check":
        found = check(book)
        for line in found:
            print(line)
        print("the pin: " + ("FAILED" if found else f"ok, {commit(book=book)}"))
        return 1 if found else 0
    if command == "fetch":
        replace = "--replace" in args
        names = [a for a in args[1:] if a != "--replace"]
        data = load(book)
        unknown = [n for n in names if n not in data["trees"]]
        if unknown:
            raise SystemExit(f"not in {PIN_FILE}: {', '.join(unknown)}")
        if replace and not names:
            raise SystemExit("--replace needs the tree named")
        ok = True
        for name in names or data["trees"]:
            ok = fetch(name, data["trees"][name], tree(name, book), replace) and ok
        return 0 if ok else 1
    raise SystemExit(__doc__)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1:]))
