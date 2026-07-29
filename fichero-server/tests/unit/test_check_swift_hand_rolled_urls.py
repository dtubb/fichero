"""Unit tests for scripts/check_swift_hand_rolled_urls.py (§6b guardrail suite)."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "check_swift_hand_rolled_urls.py"
_SPEC = importlib.util.spec_from_file_location("check_swift_hand_rolled_urls", _SCRIPT)
assert _SPEC and _SPEC.loader
_mod = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _mod
_SPEC.loader.exec_module(_mod)  # type: ignore[attr-defined]

scan = _mod.scan


def _write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

def test_flags_urlsession(tmp_path):
    _write(tmp_path, "Views/V.swift", "let (d, r) = try await URLSession.shared.data(for: req)\n")
    assert scan(tmp_path)


def test_flags_urlrequest(tmp_path):
    _write(tmp_path, "Views/V.swift", "var request = URLRequest(url: someURL)\n")
    assert scan(tmp_path)


def test_flags_api_path_literal(tmp_path):
    _write(tmp_path, "App/V.swift", 'let path = "/api/documents/\\(id)"\n')
    assert scan(tmp_path)


def test_flags_engine_url_string(tmp_path):
    _write(tmp_path, "App/V.swift", 'let u = URL(string: "http://localhost:8765/api/x")\n')
    assert scan(tmp_path)


def test_ignores_external_url_string(tmp_path):
    # An external provider/docs link is NOT engine transport.
    _write(tmp_path, "App/V.swift", 'return URL(string: "https://ollama.com/download")\n')
    assert not scan(tmp_path)


def test_services_dir_is_sanctioned(tmp_path):
    # The transport layer legitimately builds requests.
    _write(tmp_path, "Services/FooServiceGenerated.swift", "let r = URLRequest(url: u)\nURLSession.shared\n")
    assert not scan(tmp_path)


def test_comment_not_flagged(tmp_path):
    _write(tmp_path, "Views/V.swift", "// the old code used URLSession here\nText(\"hi\")\n")
    assert not scan(tmp_path)


def test_preview_block_not_flagged(tmp_path):
    _write(tmp_path, "Views/V.swift", "#Preview {\n  let r = URLRequest(url: u)\n}\n")
    assert not scan(tmp_path)


# ---------------------------------------------------------------------------
# Real repo gate
# ---------------------------------------------------------------------------

def test_repo_has_no_new_hand_rolled_urls():
    found = scan()
    known = set(_mod.KNOWN_VIOLATIONS)
    new = set(found) - known
    assert not new, (
        "New hand-rolled engine-transport site(s) (route through a store / the "
        "generated client, or add to KNOWN_VIOLATIONS):\n"
        + "\n".join(f"  {k}: {found[k]}" for k in sorted(new))
    )


def test_hand_rolled_known_violations_are_not_stale():
    found = scan()
    stale = set(_mod.KNOWN_VIOLATIONS) - set(found)
    assert not stale, (
        f"Stale KNOWN_VIOLATIONS entries (site fixed — remove them): {stale}"
    )
