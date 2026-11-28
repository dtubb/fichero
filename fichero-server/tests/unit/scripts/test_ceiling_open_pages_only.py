"""The ceiling run reads open pages only (#6978, `hands.ceiling.open-pages-only`). A fake provider: nothing is sent."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from fichero_server import llm
from fichero_server.llm import EgressRefusedError, LLMConfig, egress, usage

REPO_ROOT = Path(__file__).resolve().parents[4]


_spec = importlib.util.spec_from_file_location("blind_hands_ceiling", REPO_ROOT / "scripts" / "blind_hands" / "ceiling.py")
c = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(c)
m = c.manifest  # the script's own load of manifest.py: its ManifestError is the one raised

CLOUD = LLMConfig(provider="openai", model="gpt-test", api_key="sk-test")
IMAGE = "data:image/png;base64,AAAA"


def _hand(hid, licence="CC-BY-4.0", may_leave=True):
    return {"id": hid, "script": "caroline", "period": "12th c.", "licence": licence, "may_leave_this_mac": may_leave,
            "pool": [f"{hid}-p1"], "held_out": [f"{hid}-p2"], "manuscripts": {f"{hid}-p1": f"{hid}-msA", f"{hid}-p2": f"{hid}-msB"}}


def _manifest(tmp_path: Path, *hands, name="manifest.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps({"version": 0, "page_list_sha256": m.page_list_digest(list(hands)), "hands": list(hands)}))
    return path


def _project(tmp_path: Path, answers: str) -> Path:
    folder = tmp_path / "Scratch.fichero" / "recipe"
    folder.mkdir(parents=True)
    (folder / "setup.yaml").write_text(answers, encoding="utf-8")
    return folder.parent


@pytest.fixture
def requests(monkeypatch):
    """Every request that reaches the fake provider; a refused read builds no model, so the list stays empty."""
    made: list = []

    class _Answer:
        content = "the reading"
        usage_metadata = {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}
        response_metadata: dict = {}

    class _Model:
        async def ainvoke(self, messages, *a, **k):
            made.append(messages)
            return _Answer()

    monkeypatch.setenv("FICHERO_LOCAL_ONLY", "0")
    egress._CACHE.clear()
    llm._LLM_RESULT_CACHE.clear()
    monkeypatch.setattr(llm, "_build_langchain_model", lambda config: _Model())
    # the engine's spending cap refuses an unpriced model: the test model carries a listed price
    monkeypatch.setattr(usage, "_registry_entry", lambda model, provider="": {
        "input_cost_per_token": 1e-6, "output_cost_per_token": 1e-5})
    return made


def _read(hand_id, manifest_path, project, **kw):
    return c.read_hand(hand_id, {f"{hand_id}-p2": IMAGE}, project=project, config=CLOUD, prompt="Read this page",
                       manifest_path=manifest_path, **kw)


@pytest.mark.parametrize("row", [
    _hand("nc", "CC-BY-NC-4.0", may_leave=False),
    _hand("nc-marked-leaving", "CC-BY-NC-4.0", may_leave=True),
    _hand("private", "all-rights-reserved", may_leave=False),
    _hand("open-kept-here", "CC-BY-4.0", may_leave=False),
], ids=lambda h: h["id"])
def test_a_row_that_is_not_open_and_free_to_leave_refuses(row):
    with pytest.raises(c.CeilingRefused, match=row["id"]):
        c.refuse_unless_open(row)


def test_an_open_row_that_may_leave_does_not_refuse():
    assert c.refuse_unless_open(_hand("open")) is None


def test_a_non_commercial_hand_refuses_with_no_request_made(tmp_path, requests):
    path = _manifest(tmp_path, _hand("open"), _hand("nc", "CC-BY-NC-4.0", may_leave=False))
    with pytest.raises(c.CeilingRefused, match="CC-BY-NC-4.0"):
        _read("nc", path, _project(tmp_path, "cloud_allowed: true\n"))
    assert requests == []


def test_a_private_manifest_refuses_with_no_request_made(tmp_path, requests):
    path = _manifest(tmp_path, _hand("private", "all-rights-reserved", may_leave=False))
    with pytest.raises(m.ManifestError, match="private"):
        _read("private", path, _project(tmp_path, "cloud_allowed: true\n"))
    assert requests == []


def test_the_private_manifest_named_in_the_environment_is_not_read(tmp_path, requests, monkeypatch):
    private = _manifest(tmp_path, _hand("private", "all-rights-reserved", may_leave=False), name="private.json")
    monkeypatch.setenv("FICHERO_BLIND_HANDS_PRIVATE_MANIFEST", str(private))
    read: list[str] = []
    real = Path.read_text
    monkeypatch.setattr(Path, "read_text", lambda self, *a, **k: read.append(str(self)) or real(self, *a, **k))
    with pytest.raises(c.CeilingRefused, match="not in the manifest"):
        c.read_hand("private", {"private-p2": IMAGE}, project=_project(tmp_path, "cloud_allowed: true\n"),
                    config=CLOUD, prompt="Read this page")
    assert str(private) not in read and str(m.COMMITTED) in read
    assert requests == []


def test_an_open_hand_is_read_under_a_scratch_project_that_said_yes(tmp_path, requests):
    path = _manifest(tmp_path, _hand("open"))
    assert _read("open", path, _project(tmp_path, "cloud_allowed: true\n")) == {"open-p2": "the reading"}
    assert len(requests) == 1


def test_the_egress_gate_refuses_a_scratch_project_that_said_no(tmp_path, requests):
    path = _manifest(tmp_path, _hand("open"))
    with pytest.raises(EgressRefusedError, match="keeps its pages on this Mac"):
        _read("open", path, _project(tmp_path, "cloud_allowed: false\n"))
    assert requests == []
