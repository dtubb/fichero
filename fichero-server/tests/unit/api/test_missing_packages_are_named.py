"""A package the engine imports by name is reported when missing, not discovered as a bare 500 (#5384).

WHY: lxml (read by every PAGE/ALTO/TEI reader) was absent from an engine's venv; `health` said
healthy, and the first TEI import failed with "Internal Server Error". Health now lists the missing
required packages, and any route that hits a missing module answers 503 naming it and what it is for.
"""
from __future__ import annotations

import asyncio
import json

import fichero_server.api.main as main


def test_health_names_a_missing_required_package(client, monkeypatch):
    import importlib.util

    real = importlib.util.find_spec
    monkeypatch.setattr(importlib.util, "find_spec", lambda name, *a: None if name == "lxml" else real(name, *a))
    main._reset_dependency_report()
    try:
        body = client.get("/api/health").json()
    finally:
        main._reset_dependency_report()
    # Named with what needs it (#5493); the all-present case is test_health_names_missing_runtimes.
    assert [d for d in body["missing_dependencies"] if d.startswith("lxml")] == [
        "lxml (needed for reading and writing PAGE, ALTO and TEI)"
    ]


def test_a_missing_module_is_a_named_503():
    resp = asyncio.run(main._handle_missing_module(None, ModuleNotFoundError("No module named 'lxml'", name="lxml")))
    assert resp.status_code == 503
    detail = json.loads(resp.body)["detail"]
    assert "'lxml'" in detail and "PAGE, ALTO and TEI" in detail
