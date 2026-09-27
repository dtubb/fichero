"""`fichero export page` (`source.format.everywhere`, `source.format.export-choices`).

Thin over `GET /api/documents/{id}/export/{format}`. What is pinned: the request is the one route,
the file is written, and -- the point -- the person is SHOWN the choices and the loss report.
"""

import httpx
from typer.testing import CliRunner

from fichero_cli import FicheroClient
from fichero_cli.__main__ import app

PAYLOAD = {
    "format": "tei",
    "filename": "folio.tei.xml",
    "content": "<TEI/>",
    "choices": {
        "document_id": "d1", "pass_id": "p1", "pass_basis": "chosen", "pass_name": "kraken",
        "order_id": None, "order_name": "as-written", "reading_kind": "transcription",
        "segment_count": 4, "notes": ["no named reading order is recorded for this pass; box order was written"],
    },
    "losses": [{"what": "named reading orders", "count": 1, "why": "TEI has one"}],
}


def test_export_page_calls_the_one_route_with_the_choices():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=PAYLOAD)

    client = FicheroClient(base_url="http://127.0.0.1:8765", token="t", library_path="/tmp/l.fichero",
                           transport=httpx.MockTransport(handler))
    client.export_page("d1", "tei", pass_id="p1", order_id="o1", reading_kind="normalised")
    assert seen[0].url.path == "/api/documents/d1/export/tei"
    assert dict(seen[0].url.params) == {"pass_id": "p1", "order_id": "o1", "reading_kind": "normalised"}


def test_the_file_is_written_and_the_person_sees_the_choices_and_the_losses(tmp_path, monkeypatch):
    from fichero_cli import __main__ as cli

    class FakeClient:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def export_page(self, *a, **k): return PAYLOAD

    monkeypatch.setattr(cli, "_client", lambda ctx: FakeClient())
    result = CliRunner().invoke(app, ["export", "page", "d1", "--format", "tei", "-o", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "folio.tei.xml").read_text() == "<TEI/>"
    for needed in ("pass: kraken (chosen)", "order: as-written", "reading: transcription",
                   "NOT CARRIED by tei", "named reading orders x1", "box order was written"):
        assert needed in result.output, f"the person must be shown {needed!r}"


def test_a_lossless_export_says_so_rather_than_saying_nothing(tmp_path, monkeypatch):
    from fichero_cli import __main__ as cli

    payload = dict(PAYLOAD, losses=[])

    class FakeClient:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def export_page(self, *a, **k): return payload

    monkeypatch.setattr(cli, "_client", lambda ctx: FakeClient())
    result = CliRunner().invoke(app, ["export", "page", "d1", "--format", "tei", "-o", str(tmp_path)])
    assert "nothing was lost" in result.output
