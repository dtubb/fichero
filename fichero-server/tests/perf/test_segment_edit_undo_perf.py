"""Slice 12: the ENGINE'S share of "one edit and its undo in under a tenth of a second" (#4940).

Measured on the trial's declared page (`scripts/perf_fixture.py`, 20,000 shapes on four
levels), imported through `format.import` as a real pass, then one word moved and undone
through the HTTP routes the app uses -- `PUT /api/segments/{id}` and
`POST /api/actions/audit/{id}/undo` -- one cold run and five measured runs of five edits.

A NECESSARY condition, not the gate: the app's UndoManager and redraw come on top, so it is
recorded as `engine-edit-undo`, build "engine". The result is written in the trial's format
and judged by `scripts/perf_trial.py`, which decides whether it counts:

* thermal state from `pmset -g therm`; unreadable -> REFUSED, not a pass;
* IDLE only when the person running it says so (`PERF_IDLE=1`), because a test cannot see
  other lanes' suites -- unset, the verdict is VOID, which is true;
* `PERF_TRIAL_OUT=<dir>` keeps the result file for `perf_trial.py --update`.

This test fails only on FAIL or REFUSED. VOID and INCONCLUSIVE are honest answers about the
machine, not about the code.
"""

from __future__ import annotations

import importlib.util
import json
import os
import platform
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

import pytest

import fichero_server.api.routes.document.format_import  # noqa: F401  (registers format.import)
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.models import ActionAudit, DocType, Document, FileType, Status
from fichero_server.models.segments import Segment, SegmentPass

pytestmark = [pytest.mark.timing, pytest.mark.slow, pytest.mark.source_model]

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _thermal_state() -> str | None:
    """nominal / serious from `pmset -g therm`, or None when it cannot be read."""
    try:
        out = subprocess.run(["pmset", "-g", "therm"], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    if "No thermal warning level has been recorded" in out and "CPU_Speed_Limit" not in out:
        return "nominal"
    for line in out.splitlines():
        if "CPU_Speed_Limit" in line:
            try:
                return "nominal" if int(line.split("=")[1]) >= 100 else "serious"
            except (IndexError, ValueError):
                return None
    return None


def _machine() -> dict:
    try:
        model = subprocess.run(["sysctl", "-n", "hw.model"], capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        model = ""
    return {"model": model, "os": f"macOS {platform.mac_ver()[0]}", "build_configuration": "engine"}


def test_one_edit_and_its_undo_on_the_dense_page(db, client, tmp_path):
    fixture = _load("perf_fixture")
    trial = _load("perf_trial")

    page_file = tmp_path / "dense.page.xml"
    from fichero_server.formats import write_page

    data, _ = write_page("pagexml", fixture.generate(20000))
    page_file.write_bytes(data)
    doc = Document(name="dense.jpg", doc_type=DocType.file, file_type=FileType.image,
                   path="/path/dense.jpg", status=Status.completed)
    db.save(doc)
    ctx = ActionContext(actor="historian", library_path=None, is_bootstrap=True)
    started = time.perf_counter()
    registry.invoke(db, "format.import", {"document_id": doc.id, "path": str(page_file)}, ctx)
    import_seconds = time.perf_counter() - started

    [pass_row] = [p for p in db.all(SegmentPass) if p.document_id == doc.id]
    segments = [s for s in db.all(Segment) if s.pass_id == pass_row.id]
    assert len(segments) >= 20000, "the trial must run on the ruled count"
    word = next(s for s in segments if s.kind == "word")

    def edit_and_undo(step: int) -> float:
        # Read outside the timed span: the version is on the stored row, not the read model.
        row = db.get(Segment, word.id)
        anchor = row.anchor.model_dump(mode="json")
        rect = list(anchor["rect"])
        rect[0] = min(0.98, rect[0] + 0.0001 * (step % 3 + 1))
        anchor["rect"] = rect
        body = {"segment_id": word.id, "expected_version": row.version, "anchor": anchor}
        t0 = time.perf_counter()
        r = client.put(f"/api/segments/{word.id}", json=body)
        assert r.status_code == 200, r.text
        audit = max(
            (a for a in db.all(ActionAudit) if a.action_name == "segment.update" and word.id in (a.target_ids or [])),
            key=lambda a: a.created_at,
        )
        u = client.post(f"/api/actions/audit/{audit.id}/undo")
        elapsed = (time.perf_counter() - t0) * 1000
        assert u.status_code == 200, u.text
        return elapsed

    runs = [{"values_ms": [edit_and_undo(i + 5 * r) for i in range(5)]} for r in range(6)]
    result = {
        "measurement": "engine-edit-undo",
        "fixture": "perf_trial_fixture.json@20000",
        "shape_count": len(segments),
        "machine": _machine(),
        "thermal_state": _thermal_state(),
        "idle": os.environ.get("PERF_IDLE") == "1",
        "date": date.today().isoformat(),
        "runs": runs,
        "import_seconds": round(import_seconds, 2),
    }
    out_dir = Path(os.environ.get("PERF_TRIAL_OUT") or tmp_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "engine-edit-undo.json").write_text(json.dumps(result, indent=2), encoding="utf-8")

    verdict = trial.judge(result, json.loads(trial.DEFAULT_BASELINE.read_text(encoding="utf-8")))
    print(f"\n{verdict.status} median {verdict.median_ms} ms worst {verdict.worst_ms} ms "
          f"import {import_seconds:.1f}s; {verdict.reasons}")
    assert verdict.status not in ("FAIL", "REFUSED"), verdict.reasons
