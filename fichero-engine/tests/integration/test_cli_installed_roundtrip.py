"""First-class hermetic CLI leg (#4250): the INSTALLED ``fichero`` CLI.

Where test_cli_engine_contract.py drives the in-process ``FicheroClient``,
this leg exercises the actual console entry point (``.venv/bin/fichero``) as a
subprocess against a spawned engine + seeded disposable library — the exact
surface a user or agent shell script hits. Round trip: list -> import a real
shared fixture file -> search seeded content -> export JSONL.

Hermetic: ephemeral port, temp HOME, temp library, shared seeder — nothing
touches a real library or the app's :8765.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tests.fixture_paths import sample_file
from tests.integration._cli_live import cli_live_engine  # noqa: F401  (fixture)

REPO_ROOT = Path(__file__).resolve().parents[3]
CLI = Path(sys.executable).parent / "fichero"

pytestmark = pytest.mark.skipif(
    not CLI.exists(), reason=f"installed fichero CLI not found at {CLI}"
)


def run_cli(engine: dict, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    env = {
        **os.environ,
        "PYTHONPATH": str(REPO_ROOT / "fichero-engine" / "src"),
        "FICHERO_API_URL": engine["base_url"],
        "FICHERO_LIBRARY_PATH": str(engine["library"]),
        "FICHERO_DISABLE_AUTH": "1",
    }
    result = subprocess.run(
        [str(CLI), "--json", *args],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if check and result.returncode != 0:
        raise AssertionError(
            f"fichero {' '.join(args)} failed ({result.returncode}):\n"
            f"stdout: {result.stdout[-2000:]}\nstderr: {result.stderr[-2000:]}"
        )
    return result


def docs_names(engine: dict) -> list[str]:
    out = run_cli(engine, "docs", "list").stdout
    payload = json.loads(out)
    items = payload["items"] if isinstance(payload, dict) and "items" in payload else payload
    return [d["name"] for d in items]


def test_health(cli_live_engine):  # noqa: F811
    result = run_cli(cli_live_engine, "health")
    assert "healthy" in result.stdout


def test_list_shows_seeded_documents(cli_live_engine):  # noqa: F811
    names = docs_names(cli_live_engine)
    assert "Letter 1933" in names
    assert "Photo 1965" in names


def test_import_search_export_round_trip(cli_live_engine):  # noqa: F811
    engine = cli_live_engine

    # -- import a REAL shared specimen --------------------------------------
    fixture = sample_file("sample.txt")
    run_cli(engine, "import", str(fixture))

    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if "sample.txt" in docs_names(engine):
            break
        time.sleep(1.0)
    else:
        raise AssertionError("imported sample.txt never appeared in docs list")

    # -- search finds seeded content -----------------------------------------
    result = run_cli(engine, "search", "Eugenio")
    assert "Letter 1933" in result.stdout or "test-doc-letter" in result.stdout

    # -- export round trip (JSONL) -------------------------------------------
    export_path = engine["library"].parent / "export.jsonl"
    result = run_cli(
        engine, "export", "jsonl-route",
        "--output-path", str(export_path), "--overwrite",
        check=False,
    )
    assert result.returncode == 0, (
        f"export jsonl-route failed:\n{result.stdout[-2000:]}\n{result.stderr[-2000:]}"
    )
    exported = [p for p in [export_path] if p.exists()] or sorted(
        export_path.parent.glob("export.jsonl*")
    )
    assert exported, f"export wrote nothing at {export_path}"
    body = exported[0].read_text()
    assert "Letter 1933" in body, "export is missing seeded document content"
