"""The blind-hands manifest (#6966, `hands.bench.manifest-is-fixed-and-versioned`). Offline: no engine, no model."""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
_spec = importlib.util.spec_from_file_location("blind_hands_manifest", REPO_ROOT / "scripts" / "blind_hands" / "manifest.py")
m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m)


def _hand(hid="h1", licence="CC-BY-4.0", **kw):
    h = {"id": hid, "script": "caroline", "period": "12th c.", "licence": licence, "may_leave_this_mac": True,
         "pool": [f"{hid}-p1"], "held_out": [f"{hid}-p2"], "manuscripts": {f"{hid}-p1": f"{hid}-msA", f"{hid}-p2": f"{hid}-msB"}}
    h.update(kw)
    return h


def _manifest(*hands, version=0):
    return {"version": version, "page_list_sha256": m.page_list_digest(list(hands)), "hands": list(hands)}


def test_a_good_manifest_loads():
    assert m.validate(_manifest(_hand("a"), _hand("b", "CC-BY-NC-4.0", may_leave_this_mac=False)))["version"] == 0


def test_the_committed_manifest_loads():
    assert m.load()["version"] == 0


def test_a_manuscript_on_both_sides_refuses():
    h = _hand(manuscripts={"h1-p1": "ms", "h1-p2": "ms"})
    with pytest.raises(m.ManifestError, match="both sides"):
        m.validate(_manifest(h))


def test_a_hand_without_a_held_out_page_refuses():
    with pytest.raises(m.ManifestError, match="no held-out"):
        m.validate(_manifest(_hand(held_out=[])))


def test_a_missing_licence_refuses():
    with pytest.raises(m.ManifestError, match="licence"):
        m.validate(_manifest(_hand(licence="")))
    with pytest.raises(m.ManifestError, match="licence"):
        m.validate(_manifest(_hand(licence="all-rights-reserved")))


def test_a_page_without_a_manuscript_refuses():
    h = _hand()
    del h["manuscripts"]["h1-p2"]
    with pytest.raises(m.ManifestError, match="no manuscript"):
        m.validate(_manifest(h))


def test_a_non_commercial_hand_may_not_leave_the_mac():
    with pytest.raises(m.ManifestError, match="may leave this Mac"):
        m.validate(_manifest(_hand(licence="CC-BY-NC-4.0", may_leave_this_mac=True)))


def test_a_private_id_in_the_committed_file_refuses():
    committed = m.validate(_manifest(_hand("a")))
    private = m.validate(_manifest(_hand("secret", "private", may_leave_this_mac=False)), private=True)
    m.check_committed(committed, private)
    leaked = copy.deepcopy(committed)
    leaked["hands"][0]["id"] = "secret"
    with pytest.raises(m.ManifestError, match="private hand"):
        m.check_committed(leaked, private)
    page_leak = copy.deepcopy(committed)
    page_leak["hands"][0]["held_out"] = ["secret-p2"]
    with pytest.raises(m.ManifestError, match="private hand"):
        m.check_committed(page_leak, private)


def test_a_private_licence_is_refused_in_the_committed_file():
    with pytest.raises(m.ManifestError, match="licence"):
        m.validate(_manifest(_hand(licence="private", may_leave_this_mac=False)))


def test_a_changed_page_list_without_a_new_version_refuses(tmp_path):
    doc = _manifest(_hand("a"))
    doc["hands"][0]["pool"].append("a-p3")
    doc["hands"][0]["manuscripts"]["a-p3"] = "a-msC"
    f = tmp_path / "m.json"
    f.write_text(json.dumps(doc))
    with pytest.raises(m.ManifestError, match="new version"):
        m.load(f)


def test_figures_of_two_versions_never_share_a_column():
    assert m.one_column([{"manifest_version": 1}, {"manifest_version": 1}]) == 1
    with pytest.raises(m.ManifestError, match="one column"):
        m.one_column([{"manifest_version": 0}, {"manifest_version": 1}])
