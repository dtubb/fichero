"""The performance sweep's corpus manifest (#6600, Step 3): `perf-sweep.workload.corpus`. Offline: no fetch, no model, no app."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import re
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
_spec = importlib.util.spec_from_file_location("perf_corpus", REPO_ROOT / "fichero-builder" / "fichero_builder" / "perf_corpus.py")
corpus = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(corpus)

MANIFEST = REPO_ROOT / "scripts" / "perf_corpus.json"
RULES = tomllib.loads((REPO_ROOT / "harness.toml").read_text())
BOUNDARY = [re.compile(p) for p in RULES["land"]["boundary"]]


def _entry(**kw):
    base = {"name": "tiny", "kind": "repo", "licence": "CC0-1.0", "source": "scripts/perf_trial_fixture.json",
            "file": "perf_trial_fixture.json", "pages": 1, "sha256": "0" * 64}
    base.update(kw)
    return base


def test_the_corpus_manifest_is_open_hashed_and_names_no_archive(tmp_path):
    entries = corpus.load(json.loads(MANIFEST.read_text()))
    assert entries and len(entries) == len({e["name"] for e in entries})
    assert sum(e["kind"] == "download" for e in entries) <= 1  # at most one open HTR set
    for e in entries:
        assert re.fullmatch(r"[0-9a-f]{64}", e["sha256"]) and e["licence"] in corpus.OPEN_LICENCES and e["pages"] >= 1
    # a repo or generated entry's pinned hash is the hash of what it makes, today
    for e in entries:
        if e["kind"] in ("repo", "generated"):
            made = corpus.materialise(e, REPO_ROOT, tmp_path / e["name"])
            assert hashlib.sha256(made.read_bytes()).hexdigest() == e["sha256"], e["name"]

    # the boundary grep (the land gate's own patterns) covers the manifest and the workload table
    text = MANIFEST.read_text() + json.dumps(RULES["perf"]["workloads"])
    assert not [p.pattern for p in BOUNDARY if p.search(text)]

    # the schema is closed: there is no field to put an archive, a box or a place in
    with pytest.raises(ValueError, match="tiny.*archive"):
        corpus.load({"corpora": [_entry(archive="somewhere")]})
    # an entry without a licence or a hash is refused, naming it
    for missing in ("licence", "sha256"):
        e = _entry()
        del e[missing]
        with pytest.raises(ValueError, match=rf"tiny.*{missing}"):
            corpus.load({"corpora": [e]})
    with pytest.raises(ValueError, match="tiny.*licence"):
        corpus.load({"corpora": [_entry(licence="all-rights-reserved")]})
    with pytest.raises(ValueError, match="tiny.*host"):
        corpus.load({"corpora": [_entry(kind="download", source="https://example.invalid/x.zip", file="x.zip")]})
    # a fixture manifest carrying a local path is red under the boundary grep
    bad = json.dumps({"corpora": [_entry(source="/" + "Users/someone/box-12/scans")]})
    assert [p.pattern for p in BOUNDARY if p.search(bad)]


def test_a_held_corpus_is_hash_verified_and_a_mismatch_is_refused_by_name(tmp_path):
    src = tmp_path / "root" / "page.txt"
    src.parent.mkdir()
    src.write_bytes(b"page one\n")
    e = _entry(source="page.txt", file="page.txt", sha256=hashlib.sha256(b"page one\n").hexdigest())
    held = tmp_path / "held"
    dest = corpus.install([e], tmp_path / "root", held)["tiny"]
    assert dest.name == f"tiny-{e['sha256'][:12]}" and (dest / "page.txt").read_bytes() == b"page one\n"
    corpus.verify_held(e, held)  # silent when it matches
    (dest / "page.txt").write_bytes(b"page one, edited\n")
    with pytest.raises(corpus.CorpusMismatch, match="tiny"):
        corpus.verify_held(e, held)
    # install over a changed source refuses and leaves nothing under the hash's name
    src.write_bytes(b"page two\n")
    other = tmp_path / "held2"
    with pytest.raises(corpus.CorpusMismatch, match="tiny"):
        corpus.install([copy.deepcopy(e)], tmp_path / "root", other)
    assert not list(other.glob("tiny-*"))
    # a download is never fetched by the verifier: the fetch is injected, and a wrong body is refused
    d = _entry(name="open-htr", kind="download", source="https://zenodo.org/records/1/files/x.zip", file="x.zip",
               sha256=hashlib.sha256(b"zip").hexdigest())
    got = corpus.install([d], tmp_path / "root", tmp_path / "held3", fetch=lambda url, to: to.write_bytes(b"zip"))
    assert (got["open-htr"] / "x.zip").read_bytes() == b"zip"
    with pytest.raises(corpus.CorpusMismatch, match="open-htr"):
        corpus.install([d], tmp_path / "root", tmp_path / "held4", fetch=lambda url, to: to.write_bytes(b"not zip"))


def test_a_name_or_file_that_is_a_path_is_refused_and_an_old_hash_folder_is_replaced(tmp_path):
    for k in ("name", "file"):
        with pytest.raises(ValueError, match="bare file name"):
            corpus.load({"corpora": [_entry(**{k: "../x"})]})
    root = tmp_path / "root"
    root.mkdir()
    (root / "p.txt").write_bytes(b"v1")
    e1 = _entry(source="p.txt", file="p.txt", sha256=hashlib.sha256(b"v1").hexdigest())
    corpus.install([e1], root, tmp_path / "held")
    (root / "p.txt").write_bytes(b"v2")
    e2 = dict(e1, sha256=hashlib.sha256(b"v2").hexdigest())
    corpus.install([e2], root, tmp_path / "held")
    assert [d.name for d in (tmp_path / "held").iterdir()] == [f"tiny-{e2['sha256'][:12]}"]


def test_an_install_removes_only_its_own_old_hash_folders_and_refuses_glob_names(tmp_path):
    for bad in ("*", "a?", "[a]", "A"):
        with pytest.raises(ValueError, match="lowercase"):
            corpus.load({"corpora": [_entry(name=bad)]})
    root = tmp_path / "root"
    root.mkdir()
    (root / "p.txt").write_bytes(b"v1")
    held = tmp_path / "held"
    other = held / ("tiny-page-" + "a" * 12)
    other.mkdir(parents=True)
    corpus.install([_entry(source="p.txt", file="p.txt", sha256=hashlib.sha256(b"v1").hexdigest())], root, held)
    assert other.is_dir()
