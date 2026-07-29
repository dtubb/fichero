"""Unit tests for scripts/check_no_raw_urlsession.py (#2393)."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "check_no_raw_urlsession.py"
_SPEC = importlib.util.spec_from_file_location("check_no_raw_urlsession", _SCRIPT)
assert _SPEC and _SPEC.loader
_mod = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _mod
_SPEC.loader.exec_module(_mod)  # type: ignore[attr-defined]

scan = _mod.scan


def _w(tmp_path: Path, name: str, body: str) -> Path:
    (tmp_path / name).write_text(body)
    return tmp_path


def test_planted_raw_session_goes_red(tmp_path):
    _w(tmp_path, "BadMiddleware.swift", "let (d, _) = try await URLSession.shared.data(for: req)\n")
    assert scan(tmp_path), "raw URLSession.shared in the package must be flagged"


def test_planted_ctor_goes_red(tmp_path):
    _w(tmp_path, "Sneaky.swift", "let s = URLSession(configuration: .default)\n")
    assert scan(tmp_path), "raw URLSession( in the package must be flagged"


def test_allowlisted_pinning_file_is_green(tmp_path):
    _w(tmp_path, "RemoteCertificatePinning.swift", "return URLSession(configuration: cfg, delegate: self, delegateQueue: nil)\n")
    assert not scan(tmp_path), "the pinned-session owner is allowlisted"


def test_non_transport_code_is_green(tmp_path):
    _w(tmp_path, "Model.swift", "struct Foo { let bar: String }\n")
    assert not scan(tmp_path)


def test_comment_is_not_a_violation(tmp_path):
    _w(tmp_path, "Doc.swift", "// do not use URLSession.shared here\nlet x = 1\n")
    assert not scan(tmp_path), "mention in a comment must not count"


def test_real_package_clean():
    assert not scan(), "only RemoteCertificatePinning.swift may touch raw URLSession"
