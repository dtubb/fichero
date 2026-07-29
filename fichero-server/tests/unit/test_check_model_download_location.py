"""Unit tests for scripts/check_model_download_location.py (§6b guardrail suite)."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "check_model_download_location.py"
_SPEC = importlib.util.spec_from_file_location("check_model_download_location", _SCRIPT)
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
# MODELS_BASE definition equivalence
# ---------------------------------------------------------------------------

def test_canonical_models_base_not_flagged(tmp_path):
    _write(tmp_path, "ok.py", 'MODELS_BASE = server_state_dir() / "models"\n')
    assert not scan(tmp_path)


def test_hardcoded_models_base_flagged(tmp_path):
    _write(tmp_path, "bad.py", (
        "MODELS_BASE = (\n"
        '    Path.home() / "Library" / "Application Support" / "com.fichero.fichero" / "models"\n'
        ")\n"
    ))
    found = scan(tmp_path)
    assert found, "hardcoded MODELS_BASE not deriving from server_state_dir() must be flagged"


# ---------------------------------------------------------------------------
# Download path decisions
# ---------------------------------------------------------------------------

def test_canonical_cache_dir_not_flagged(tmp_path):
    _write(tmp_path, "ok.py", 'cache_dir = MODELS_BASE / "embeddings"\n')
    assert not scan(tmp_path)


def test_self_path_attr_not_flagged(tmp_path):
    _write(tmp_path, "ok.py", "download_root = str(self.whisper_path)\n")
    assert not scan(tmp_path)


def test_hardcoded_cache_dir_flagged(tmp_path):
    _write(tmp_path, "bad.py", 'cache_dir = "/tmp/my_models"\n')
    assert scan(tmp_path)


def test_dot_cache_flagged(tmp_path):
    _write(tmp_path, "bad.py", 'download_root = str(Path.home() / ".cache" / "whisper")\n')
    assert scan(tmp_path)


def test_kwarg_passthrough_not_flagged(tmp_path):
    # `download_root=download_root,` is a call kwarg, not a path decision.
    _write(tmp_path, "ok.py", (
        "model = whisper.load_model(\n"
        "    model_size,\n"
        "    download_root=download_root,\n"
        ")\n"
    ))
    assert not scan(tmp_path)


def test_generated_dir_skipped(tmp_path):
    _write(tmp_path, "generated/x.py", 'cache_dir = "/tmp/whatever"\n')
    assert not scan(tmp_path)


# ---------------------------------------------------------------------------
# Real repo gate
# ---------------------------------------------------------------------------

def test_repo_has_no_new_divergent_downloads():
    found = scan()
    known = set(_mod.KNOWN_VIOLATIONS)
    new = set(found) - known
    assert not new, (
        "New model download escaping the shared folder (derive from "
        "server_state_dir()/'models', or add to KNOWN_VIOLATIONS):\n"
        + "\n".join(f"  {k}: {found[k]}" for k in sorted(new))
    )


def test_model_known_violations_are_not_stale():
    found = scan()
    stale = set(_mod.KNOWN_VIOLATIONS) - set(found)
    assert not stale, (
        f"Stale KNOWN_VIOLATIONS entries (divergence fixed — remove them): {stale}"
    )
