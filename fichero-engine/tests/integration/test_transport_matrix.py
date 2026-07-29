"""One round-trip matrix over every transport the engine serves (#4245).

`test_transport_round_trips.py` proves each transport binds, serves, and
enforces auth. This module proves each transport carries a REAL WORKFLOW —
the same round-trip set per transport, so a transport can never again "work"
in the health-check sense while silently failing the moment data moves:

    health                      -> 200 healthy
    library create + registry   -> the engine's known-library roots list
    ingest a tiny fixture       -> a .txt (searchable) and a .png (renderable)
    search the ingested text    -> full-text hit on the .txt document
    fetch a thumbnail           -> JPEG bytes for the .png document

Transports:
  * UDS   — subprocess uvicorn over fichero.api.uds_transport:app (reuses the
            round-trips module's fixture: own base path, auth enforced).
  * HTTPS — subprocess uvicorn with loopback TLS (same reuse).
  * in-memory ASGI — fichero.api.main:app driven in-process, the Python twin
            of the Swift `.inMemory` PythonKit transport. The Swift side of
            that claim (InMemoryEngineApp + InMemoryTransportSmokeTests /
            TransportMatrixRoundTripTests) runs under `swift test` via
            `scripts/gate transport`.

Wired into the gate: `scripts/gate transport` (and the transport leg of
`gate verify-all`) runs this file plus the round-trips module, so the matrix
is part of the releasable-green definition (#4251).
"""

from __future__ import annotations

import base64
import tempfile
from pathlib import Path

import httpx
import pytest

# Importing the fixture functions registers them for this module too.
from tests.integration.test_transport_round_trips import (  # noqa: F401
    https_engine,
    uds_engine,
)

HEALTH = "/api/health"

_ONE_PIXEL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j5tQAAAAASUVORK5CYII="
)


def _write_fixtures(root: Path) -> tuple[Path, Path]:
    """A tiny searchable text file and a tiny renderable image."""
    root.mkdir(parents=True, exist_ok=True)
    txt = root / "matrix-note.txt"
    txt.write_text("the quetzal perched on the transport matrix fixture")
    png = root / "matrix-pixel.png"
    png.write_bytes(_ONE_PIXEL_PNG)
    return txt, png


def _round_trip(client: httpx.Client, headers: dict[str, str], label: str) -> None:
    """The one shared round-trip every transport must carry.

    `headers` carries auth (subprocess engines enforce it; the in-process app
    runs under the suite's auth bypass, where the extra header is harmless).
    """
    # 1. health — unauthenticated reachability.
    health = client.get(HEALTH)
    assert health.status_code == 200, f"[{label}] health: {health.text}"
    assert health.json().get("status") in {"healthy", "ok"}

    # 2. library create, then the engine's known-library roots.
    work = Path(tempfile.mkdtemp(prefix=f"fichero-matrix-{label}-"))
    library = work / "Matrix.fichero"
    created = client.post("/api/library", json={"path": str(library)}, headers=headers)
    assert created.status_code == 200, f"[{label}] library create: {created.text}"

    registry = client.get("/api/registry", headers=headers)
    assert registry.status_code == 200, f"[{label}] registry: {registry.text}"

    lib_headers = {**headers, "X-Fichero-Library-Path": str(library)}

    # 3. ingest the tiny fixtures (copied in, auto_embed on: the full-text
    #    index lives in the LanceDB embeddings table, so search finds nothing
    #    without it. Embedding runs against the bundled local model — verified
    #    offline. The image has no text, so its embed is a silent no-op).
    txt, png = _write_fixtures(work / "fixtures")
    docs: dict[str, str] = {}
    for path in (txt, png):
        response = client.post(
            "/api/ingest/file",
            json={"path": str(path), "copy_mode": True, "auto_embed": True},
            headers=lib_headers,
        )
        assert response.status_code == 200, f"[{label}] ingest {path.name}: {response.text}"
        document = response.json()
        assert document.get("id"), f"[{label}] ingest returned no document id"
        docs[path.suffix] = document["id"]

    # 4. search finds the ingested text by content (full-text, thresholdless).
    search = client.post(
        "/api/search",
        json={"query": "quetzal", "search_type": "fulltext", "min_score": 0.0},
        headers=lib_headers,
    )
    assert search.status_code == 200, f"[{label}] search: {search.text}"
    hits = {r["document_id"] for r in search.json().get("results", [])}
    assert docs[".txt"] in hits, (
        f"[{label}] the ingested text document was not a search hit; "
        f"got {hits or 'no results'}"
    )

    # 5. thumbnail bytes for the image document (generated on demand).
    thumb = client.get(f"/api/storage/thumbnail/{docs['.png']}", headers=lib_headers)
    assert thumb.status_code == 200, f"[{label}] thumbnail: {thumb.text[:200]}"
    assert thumb.headers.get("content-type", "").startswith("image/"), thumb.headers
    assert len(thumb.content) > 0, f"[{label}] thumbnail body is empty"


@pytest.mark.parametrize("fixture_name", ["uds_engine", "https_engine"])
def test_full_round_trip_over_socket_transports(fixture_name, request):
    engine = request.getfixturevalue(fixture_name)
    label = "uds" if fixture_name == "uds_engine" else "https"
    with httpx.Client(timeout=60, **engine.client_kwargs) as client:
        _round_trip(client, engine.auth_header, label)


def test_full_round_trip_in_memory_asgi():
    """In-process ASGI — the Python twin of the Swift `.inMemory` transport.

    Reachability + the data path only: the suite conftest disables auth for
    in-process apps, so enforcement claims belong to the subprocess legs
    above (same reasoning as the round-trips module's in-memory test).
    """
    from starlette.testclient import TestClient

    from fichero.api.main import app

    # TestClient: the sync httpx.Client face over an in-process ASGI app —
    # lets the in-memory leg share the exact _round_trip the socket legs run.
    with TestClient(app) as client:
        _round_trip(client, {}, "inmemory")
