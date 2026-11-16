"""The performance sweep's corpus manifest (#6600 Step 3, `perf-sweep.workload.corpus`; stdlib only).

`scripts/perf_corpus.json` pins every corpus a workload measures by name, licence, source, sha256 and page count. A corpus is held
in a folder named by the corpus and the first 12 hex digits of its hash, made once by `builder install --corpus` and verified by hash
again before every run: a corpus whose hash differs is refused, so two runs measure one corpus. The entry's schema is closed: it has
no field for an archive, a box or a place. Nothing here fetches by itself: a `download` entry goes through the `fetch` the caller
passes."""
from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

KINDS = ("repo", "generated", "download")
FIELDS = {"name", "kind", "licence", "source", "file", "pages", "sha256", "args"}
REQUIRED = ("name", "kind", "licence", "source", "file", "pages", "sha256")
OPEN_LICENCES = {"CC0-1.0", "CC-BY-4.0", "CC-BY-SA-4.0", "MIT", "Apache-2.0", "AGPL-3.0-only"}  # the repo's own files are AGPL-3.0
OPEN_HOSTS = {"zenodo.org", "github.com", "raw.githubusercontent.com", "huggingface.co"}


class CorpusMismatch(ValueError):
    """A corpus's bytes are not the ones the manifest pins."""


def load(doc: dict) -> list[dict]:
    """The manifest's entries, or ValueError naming the first entry that is not open, hashed and closed-schema."""
    entries = doc.get("corpora")
    if not isinstance(entries, list) or not entries:
        raise ValueError("perf_corpus.json: `corpora` is empty")
    seen = set()
    for e in entries:
        n = e.get("name", "<unnamed>")
        for k in ("name", "file"):
            v = e.get(k)
            if isinstance(v, str) and (Path(v).name != v or v in (".", "..")):
                raise ValueError(f"corpus {n}: {k} is a bare file name, not a path")
        if extra := sorted(set(e) - FIELDS):
            raise ValueError(f"corpus {n}: field(s) {extra} are not allowed (a corpus has no archive, box or place field)")
        for k in REQUIRED:
            if e.get(k) in (None, "", 0):
                raise ValueError(f"corpus {n}: {k} is required")
        if isinstance(e.get("name"), str) and not re.fullmatch(r"[a-z0-9-]+", e["name"]):
            raise ValueError(f"corpus {n}: name is lowercase letters, digits and hyphens only")
        if n in seen:
            raise ValueError(f"corpus {n}: declared twice")
        seen.add(n)
        if e["kind"] not in KINDS:
            raise ValueError(f"corpus {n}: kind is one of {KINDS}")
        if e["licence"] not in OPEN_LICENCES:
            raise ValueError(f"corpus {n}: licence {e['licence']!r} is not one of {sorted(OPEN_LICENCES)}")
        if len(e["sha256"]) != 64 or any(c not in "0123456789abcdef" for c in e["sha256"]):
            raise ValueError(f"corpus {n}: sha256 is 64 lowercase hex digits")
        if e["kind"] == "download" and urlparse(e["source"]).hostname not in OPEN_HOSTS:
            raise ValueError(f"corpus {n}: host of {e['source']!r} is not one of {sorted(OPEN_HOSTS)}")
    return entries


def _sha(path: Path) -> str:
    with open(path, "rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def held_dir(e: dict, dest) -> Path:
    return Path(dest) / (e["name"] + "-" + e["sha256"][:12])


def materialise(e: dict, root, out_dir, fetch=None) -> Path:
    """Make the entry's file in `out_dir` and return it (not yet verified)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / e["file"]
    if e["kind"] == "repo":
        shutil.copyfile(Path(root) / e["source"], out)
    elif e["kind"] == "generated":
        env = {"PYTHONPATH": str(Path(root) / "fichero-server" / "src"), "PATH": "/usr/bin:/bin"}
        argv = [sys.executable, str(Path(root) / e["source"]), *map(str, e.get("args", [])), str(out)]
        r = subprocess.run(argv, capture_output=True, text=True, env=env, cwd=root)
        if r.returncode:
            raise CorpusMismatch(f"corpus {e['name']}: its generator failed: {r.stderr.strip()[-300:]}")
    else:
        if fetch is None:
            raise CorpusMismatch(f"corpus {e['name']}: a download needs a fetch")
        fetch(e["source"], out)
    return out


def install(entries: list[dict], root, dest, fetch=None) -> dict[str, Path]:
    """Make each corpus, verify its hash, and only then put it under its held name; a mismatch is refused and leaves nothing."""
    held: dict[str, Path] = {}
    Path(dest).mkdir(parents=True, exist_ok=True)
    for e in entries:
        with tempfile.TemporaryDirectory(dir=dest) as tmp:
            made = materialise(e, root, tmp, fetch)
            if (got := _sha(made)) != e["sha256"]:
                raise CorpusMismatch(f"corpus {e['name']}: sha256 is {got[:12]}, the manifest pins {e['sha256'][:12]}")
            target = held_dir(e, dest)
            own = re.compile(re.escape(e["name"]) + r"-[0-9a-f]{12}")
            for old in Path(dest).iterdir():  # an earlier hash's folder of this corpus is not kept; no other folder is touched
                if old.is_dir() and own.fullmatch(old.name):
                    shutil.rmtree(old, ignore_errors=True)
            target.mkdir(parents=True)
            shutil.move(str(made), str(target / e["file"]))
        held[e["name"]] = target
    return held


def verify_held(e: dict, dest) -> Path:
    """Before every run: the held file exists and its hash is the pinned one, else CorpusMismatch naming the corpus."""
    f = held_dir(e, dest) / e["file"]
    if not f.is_file():
        raise CorpusMismatch(f"corpus {e['name']}: not installed (run `builder install --corpus`)")
    if (got := _sha(f)) != e["sha256"]:
        raise CorpusMismatch(f"corpus {e['name']}: sha256 is {got[:12]}, the manifest pins {e['sha256'][:12]}")
    return f.parent
