"""Live CLI contract for the handwritten `import-iiif` command."""

from __future__ import annotations

import os
import socket

import httpx
import pytest
from typer.testing import CliRunner

os.environ.setdefault("FICHERO_FEATURE_TIER", "dev")
os.environ.setdefault("FICHERO_SKIP_DEFAULT_WORKFLOWS", "1")
os.environ.setdefault("FICHERO_DISABLE_AUTH", "1")

from fichero_server import __main__ as cli  # noqa: E402
from tests.integration._cli_live import cli_live_engine as _cli_live_engine_fixture  # noqa: E402,F401
from tests.unit.test_iiif_import import _write_tiny_iiif  # noqa: E402

runner = CliRunner()


def _cli_importers_ready() -> bool:
    if os.getenv("FICHERO_RUN_CLI_IMPORTER_WRITES") != "1":
        return False
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
    except OSError:
        return False
    return True


pytestmark = pytest.mark.skipif(
    not _cli_importers_ready(),
    reason="CLI importer contracts are opt-in and require loopback socket access",
)


def _get_json(base_url: str, library, path: str) -> dict:
    response = httpx.get(
        f"{base_url}{path}",
        headers={"X-Fichero-Library-Path": str(library)},
        timeout=5,
    )
    response.raise_for_status()
    return response.json()


def test_import_iiif_cli_round_trips_fixture_into_live_engine(
    cli_live_engine,
    tmp_path,
) -> None:
    iiif_root = tmp_path / "iiif"
    iiif_root.mkdir()
    iiif_root = _write_tiny_iiif(iiif_root)
    library = tmp_path / "Tiny.fichero"

    result = runner.invoke(
        cli.app,
        [
            "--base-url",
            cli_live_engine["base_url"],
            "import-iiif",
            "--iiif",
            str(iiif_root),
            "--library",
            str(library),
            "--ingest",
            "copy",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "manifests_seen: 1" in result.output
    assert "pages_seen: 1" in result.output
    assert "documents_created: 2" in result.output

    docs = _get_json(
        cli_live_engine["base_url"],
        library,
        "/api/documents?limit=500",
    )["items"]
    page = next(doc for doc in docs if doc["name"] == "Page 001")
    assert page["page_content"] == "Marshall went to Istmina."

    artifacts = _get_json(
        cli_live_engine["base_url"],
        library,
        f"/api/artifacts/document/{page['id']}?artifact_type=transcription&include_descendants=false",
    )["items"]
    assert len(artifacts) == 1
    assert artifacts[0]["provider"] == "iiif-import"
    assert artifacts[0]["data"]["source"] == "iiif_w3c"

    entities = _get_json(
        cli_live_engine["base_url"],
        library,
        f"/api/entities?document_id={page['id']}&limit=500",
    )["items"]
    assert [entity["canonical_name"] for entity in entities] == ["Marshall"]
