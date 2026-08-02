"""#4471 part 1: `fichero export` — a thin wrapper over /api/export/*.

The server's export family worked live while the CLI had no way to reach
it. One implementation (server-side); the CLI adds a command, not a path.
"""

import httpx
import pytest

from fichero_cli import FicheroClient
from fichero_cli.client import FicheroError


def _capture(seen):
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200, json={"output_path": "/tmp/out", "files": [], "bytes_written": 0}
        )

    return httpx.MockTransport(handler)


def test_export_posts_the_format_route_with_output_path():
    seen = []
    client = FicheroClient(
        base_url="http://127.0.0.1:8765",
        token="t",
        library_path="/tmp/lib.fichero",
        transport=_capture(seen),
    )
    client.export_library("parquet", "/tmp/out")
    req = seen[0]
    assert req.url.path == "/api/export/parquet"
    assert b'"output_path": "/tmp/out"' in req.content or b'"output_path":"/tmp/out"' in req.content


@pytest.mark.parametrize(
    "fmt", ["parquet", "jsonl", "markdown-folder", "word", "excel", "eleventy-site"]
)
def test_every_supported_format_routes(fmt):
    seen = []
    client = FicheroClient(
        base_url="http://127.0.0.1:8765",
        token="t",
        library_path="/tmp/lib.fichero",
        transport=_capture(seen),
    )
    client.export_library(fmt, "/tmp/out")
    assert seen[0].url.path == f"/api/export/{fmt}"


def test_unknown_format_is_a_loud_error_naming_the_options():
    client = FicheroClient(
        base_url="http://127.0.0.1:8765",
        token="t",
        library_path="/tmp/lib.fichero",
        transport=_capture([]),
    )
    with pytest.raises(FicheroError) as caught:
        client.export_library("csv", "/tmp/out")
    assert "parquet" in str(caught.value), "the error must name what IS supported"
