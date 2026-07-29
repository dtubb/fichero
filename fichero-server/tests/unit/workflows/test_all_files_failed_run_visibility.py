"""#4283 — a run where every file failed must be VISIBLE as a failure.

Vision tools isolate per-file errors (one bad page never aborts siblings) by
appending ``{"file", "error"}`` result rows and carrying on. The runner's
empty-output detector counted ANY non-empty ``results`` list as real output —
so a paleography run where every page failed (non-vision provider, missing
key, open circuit breaker) sailed through as a green ``status="completed"``
with no artifacts, no text, and no error anywhere: "ran but nothing
observable happened".

Pins: error-only results are NOT output; the reason names the failure; the
runner escalates such runs to ``status="failed"`` in the activity record.
"""

import inspect

from fichero_server.execution.runner import (
    _ALL_FILES_FAILED_MARKER,
    _detect_empty_text_output,
)


def _state(results, **node_extra):
    node = {"text": "", "results": results, **node_extra}
    return {"files": ["/tmp/p1.jpg", "/tmp/p2.jpg"], "outputs": {"transcribe": node}}


class TestErrorOnlyResultsAreNotOutput:
    def test_all_error_results_flag_the_run_as_empty(self):
        is_empty, reason = _detect_empty_text_output(
            _state(
                [
                    {"file": "/tmp/p1.jpg", "text": "", "error": "no vision-capable model"},
                    {"file": "/tmp/p2.jpg", "text": "", "error": "no vision-capable model"},
                ],
                error="2/2 failed: no vision-capable model",
            )
        )
        assert is_empty
        assert _ALL_FILES_FAILED_MARKER in reason
        assert "no vision-capable model" in reason

    def test_one_successful_result_means_real_output(self):
        is_empty, _ = _detect_empty_text_output(
            _state(
                [
                    {"file": "/tmp/p1.jpg", "text": "", "error": "rate limited"},
                    {"file": "/tmp/p2.jpg", "text": "El acta", "value": "El acta"},
                ]
            )
        )
        assert not is_empty

    def test_error_free_results_still_count_as_output(self):
        # Pre-#4283 behaviour preserved: e.g. entity-extraction results
        # without error rows are output even with empty node text.
        is_empty, _ = _detect_empty_text_output(
            _state([{"entity": "García"}])
        )
        assert not is_empty

    def test_empty_without_node_errors_keeps_plain_reason(self):
        is_empty, reason = _detect_empty_text_output(
            {"files": ["/tmp/a.jpg"], "outputs": {"n": {"text": "  "}}}
        )
        assert is_empty
        assert _ALL_FILES_FAILED_MARKER not in reason


class TestRunnerEscalatesToFailed:
    def test_runner_records_all_failed_runs_as_failed(self):
        from fichero_server.execution import runner

        source = inspect.getsource(runner)
        assert 'status="failed" if _all_files_failed else "completed"' in source, (
            "an every-file-failed run must be recorded status='failed' in the "
            "activity store — never a green 'completed' (#4283)"
        )
        assert "error=_empty_reason if _all_files_failed else None" in source, (
            "the aggregated per-file error must land on the run record (#4283)"
        )
