"""Per-run scratch folders for image tools (#5386).

Image tools wrote their derived files to fixed folders under the system temp directory
(`fichero-split-images`, ...) that nothing ever cleaned: a 374-photo corpus left gigabytes behind on
a nearly full disk. Each run now gets its own folder, `<tmp>/fichero-runs/<run id>/<tool>`, and the
runner removes the run's folder when the run ends (a paused run keeps it, since a resume may still
read the files). Files a run keeps are copied into the library by the tool itself before then.
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any

ROOT = "fichero-runs"


def run_scratch_dir(state: dict[str, Any] | None, name: str) -> str:
    """This run's scratch folder for ``name`` (a tool), created on use by the tool."""
    run_id = str((state or {}).get("task_id") or "no-run")
    return str(Path(tempfile.gettempdir()) / ROOT / run_id / name)


def remove_run_scratch(run_id: str) -> None:
    """Delete everything this run wrote to its scratch folders."""
    shutil.rmtree(Path(tempfile.gettempdir()) / ROOT / str(run_id), ignore_errors=True)  # noqa: S108 -- the run's own folder
