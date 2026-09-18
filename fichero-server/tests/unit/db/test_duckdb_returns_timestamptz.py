"""DuckDB needs pytz to hand a TIMESTAMPTZ value to Python.

pytz is declared in pyproject.toml for this reason alone. It once arrived
with pandas; pandas 3 dropped it, and every read of `workflow_runs` (whose
`started_at`/`completed_at` are timezone-aware) failed with a 500.
"""

import duckdb


def test_a_timezone_aware_timestamp_reaches_python():
    (now,) = duckdb.sql("select now()").fetchone()
    assert now.tzinfo is not None
