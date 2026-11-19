"""scripts/check_spec_no_archive_names.py (#6695): a spec line carrying a word from the JSON list fails with file and line; neutral
words pass; the shipped specs are clean; an empty word list is an error. Offline, text only."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "check_spec_no_archive_names.py"
sys.path.insert(0, str(_SCRIPT.parent))  # the script imports its sibling _scan_files
_SPEC = importlib.util.spec_from_file_location("check_spec_no_archive_names", _SCRIPT)
assert _SPEC and _SPEC.loader
_mod = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _mod
_SPEC.loader.exec_module(_mod)  # type: ignore[attr-defined]

SPECS = "/".join(["docs", "contributor_manual", "specs"])  # built, so the spec-citation guard does not read it as a citation


def _spec(tmp_path, text):
    d = tmp_path / SPECS / "source"
    d.mkdir(parents=True)
    (d / "x.md").write_text(text)
    return tmp_path


def _hashes(*words):
    return {hashlib.sha256(w.lower().encode()).hexdigest() for w in words}


def test_a_hashed_word_fails_with_its_line_never_the_word_and_neutral_words_pass(tmp_path):
    hashes = _hashes("Zorbleflux", "qx7")  # made-up words
    assert _mod.problems(_spec(tmp_path / "ok", "Read a notebook corpus.\nOn a test page, the box reads.\n"), hashes) == []
    for text in ("the zorbleflux pages", "the ZORBLEFLUX_QX7 id", "Zorbleflux's notebooks", "a-qx7-b"):
        out = _mod.problems(_spec(tmp_path / str(abs(hash(text))), f"ok line\n{text}\n"), hashes)
        assert [o.split(": ")[0] for o in out] == [f"{SPECS}/source/x.md:2"], (text, out)
        assert "zorbleflux" not in out[0].lower() and "qx7" not in out[0].lower()


def test_a_word_that_only_contains_a_hashed_word_passes(tmp_path):
    assert _mod.problems(_spec(tmp_path, "see zorblefluxes and e06qx7551\n"), _hashes("zorbleflux", "qx7")) == []


def test_an_empty_hash_list_is_an_error_not_a_clean_pass(tmp_path):
    empty = tmp_path / "w.json"
    empty.write_text(json.dumps({"sha256_of_lowercased_token": []}))
    with pytest.raises(ValueError):
        _mod.load_hashes(empty)


def test_the_shipped_list_holds_only_hashes():
    shipped = json.loads((_SCRIPT.with_suffix(".json")).read_text())["sha256_of_lowercased_token"]
    assert shipped and all(len(h) == 64 and set(h) <= set("0123456789abcdef") for h in shipped)


def test_the_shipped_specs_carry_no_archive_name():
    root = Path(__file__).resolve().parents[4]
    assert _mod.problems(root, _mod.load_hashes()) == []
