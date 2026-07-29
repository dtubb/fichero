"""Unit tests for scripts/check_silent_write_swallow.py (#2507)."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "check_silent_write_swallow.py"
_SPEC = importlib.util.spec_from_file_location("check_silent_write_swallow", _SCRIPT)
assert _SPEC and _SPEC.loader
_mod = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _mod
_SPEC.loader.exec_module(_mod)  # type: ignore[attr-defined]

scan = _mod.scan


def _src(tmp_path: Path, body: str) -> Path:
    d = tmp_path / "fichero_server"
    d.mkdir(parents=True, exist_ok=True)
    (d / "m.py").write_text(body)
    return d


def test_flags_silent_swallow_in_write_func(tmp_path):
    src = _src(tmp_path, """
def save_document(doc):
    try:
        db.save(doc)
    except Exception:
        pass
""")
    assert scan(src), "silent except Exception in a save_* func must be flagged"


def test_flags_bare_return_none(tmp_path):
    src = _src(tmp_path, """
def update_entity(e):
    try:
        db.update(e)
    except Exception:
        return None
""")
    assert scan(src), "return None with no log/raise still hides the failure"


def test_accepts_logged_swallow(tmp_path):
    src = _src(tmp_path, """
def save_document(doc):
    try:
        db.save(doc)
    except Exception as exc:
        logger.warning("save failed: %s", exc)
        return None
""")
    assert not scan(src), "log-warn-and-skip is the sanctioned pattern"


def test_accepts_raise(tmp_path):
    src = _src(tmp_path, """
def save_document(doc):
    try:
        db.save(doc)
    except Exception:
        raise
""")
    assert not scan(src)


def test_accepts_error_payload_return(tmp_path):
    # Surfacing the error to the caller (browser_save / _ingest_one shape).
    src = _src(tmp_path, """
def create_thing(req):
    try:
        return do(req)
    except Exception as e:
        return Response(success=False, error=str(e))
""")
    assert not scan(src), "returning an error payload surfaces the failure"


def test_accepts_narrow_except(tmp_path):
    src = _src(tmp_path, """
def delete_schedule(sid):
    try:
        scheduler.remove_job(sid)
    except JobLookupError:
        pass
""")
    assert not scan(src), "a narrow expected exception is fine"


def test_ignores_read_func(tmp_path):
    src = _src(tmp_path, """
def get_thing(tid):
    try:
        return db.get(tid)
    except Exception:
        return None
""")
    assert not scan(src), "only write-named functions are in scope"


def test_real_tree_clean():
    assert not scan(), "no silent write swallows in the shipped engine"
