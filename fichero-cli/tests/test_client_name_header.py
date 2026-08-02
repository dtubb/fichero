"""#4469: FicheroClient sends X-Fichero-Client when a surface name is set."""

import httpx

from fichero_cli import FicheroClient


def _capture_transport(seen: list[httpx.Request]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"status": "healthy"})

    return httpx.MockTransport(handler)


def test_client_name_rides_as_header():
    seen: list[httpx.Request] = []
    client = FicheroClient(
        base_url="http://127.0.0.1:8765",
        token="t",
        library_path="/tmp/lib.fichero",
        transport=_capture_transport(seen),
        client_name="fichero-mcp",
    )
    client.request("GET", "/api/health")
    assert seen[0].headers["X-Fichero-Client"] == "fichero-mcp"


def test_no_client_name_sends_no_header():
    seen: list[httpx.Request] = []
    client = FicheroClient(
        base_url="http://127.0.0.1:8765",
        token="t",
        library_path="/tmp/lib.fichero",
        transport=_capture_transport(seen),
    )
    client.request("GET", "/api/health")
    assert "X-Fichero-Client" not in seen[0].headers
