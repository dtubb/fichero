"""A page a person stops alone is not a page that failed (#5935, `activity.stop.page-skips-run-stops-children`).

`process_vision`'s per-file handlers turned any `Exception` into that file's `{"error": ...}` result; `PageStopped`
(a `JobCancelled`) was caught there, so the stopped page was recorded failed and could fail the run. Both handlers
must let it through, as they do `WorkflowCancelled` and `WorkflowPaused`, to reach `_read_one_page`'s cancelled result.
"""
from __future__ import annotations

import re
from pathlib import Path

from fichero_server.workflows.tools import vision_base


def test_per_file_handlers_let_a_stopped_page_through():
    src = Path(vision_base.__file__).read_text()
    handlers = re.findall(r"except \(([^)]*WorkflowPaused[^)]*)\):", src)
    assert len(handlers) == 2
    for names in handlers:
        assert "JobCancelled" in names, "a PageStopped would be recorded as this file's error"
