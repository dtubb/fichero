"""`fichero import-page` (`source.format.everywhere`).

Thin over `POST /api/documents/{id}/import`. What is pinned: the request is that one
route, the person is told which format was RECOGNISED and how many shapes were
repaired, and a re-import of the same bytes leaves with **status 0** — the library
already holding a file is an answer, not a failure, and a nightly script must not
break on it.
"""

import httpx
from typer.testing import CliRunner

from fichero_cli import FicheroClient
from fichero_cli.__main__ import app
from fichero_cli.client import FicheroError

PAYLOAD = {
    "pass_id": "p9",
    "format": "pagexml",
    "segments": 812,
    "readings": 806,
    "order_entries": 812,
    "checksum": "abc123def456789",
    "geometry_problems": 0,
}


def _file(tmp_path, name="folio.xml"):
    path = tmp_path / name
    path.write_text("<PcGts/>", encoding="utf-8")
    return path


def test_import_page_posts_the_file_to_the_one_route(tmp_path):
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=PAYLOAD)

    client = FicheroClient(
        base_url="http://127.0.0.1:8765", token="t", library_path="/tmp/l.fichero",
        transport=httpx.MockTransport(handler),
    )
    client.import_page("d1", _file(tmp_path), import_format="pagexml", name="somebody else's")

    assert seen[0].url.path == "/api/documents/d1/import"
    assert dict(seen[0].url.params) == {"format": "pagexml", "name": "somebody else's"}
    assert seen[0].method == "POST"
    # Multipart, not a JSON body: the engine takes the file.
    assert b"folio.xml" in seen[0].content


def test_the_person_is_told_what_was_recognised_and_what_landed(tmp_path, monkeypatch):
    from fichero_cli import __main__ as cli

    class FakeClient:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def import_page(self, *a, **k): return PAYLOAD

    monkeypatch.setattr(cli, "_client", lambda ctx: FakeClient())
    path = _file(tmp_path)
    result = CliRunner().invoke(app, ["import-page", "d1", str(path)])

    assert result.exit_code == 0, result.output
    for needed in ("as pagexml", "pass: p9", "segments: 812", "readings: 806"):
        assert needed in result.output, f"the person must be shown {needed!r}"


def test_a_repaired_shape_is_reported_not_buried(tmp_path, monkeypatch):
    """`geometry_problems` is the count of shapes the file could not express and the
    engine repaired. Forty repairs is a page somebody should look at, and a repair
    nobody is told about is a swallowed problem wearing a different coat."""
    from fichero_cli import __main__ as cli

    class FakeClient:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def import_page(self, *a, **k): return dict(PAYLOAD, geometry_problems=40)

    monkeypatch.setattr(cli, "_client", lambda ctx: FakeClient())
    result = CliRunner().invoke(app, ["import-page", "d1", str(_file(tmp_path))])

    assert result.exit_code == 0, result.output
    assert "REPAIRED 40" in result.output


def test_a_name_that_disagrees_with_the_bytes_is_said_out_loud(tmp_path, monkeypatch):
    """A renamed eScriptorium export still reads as PAGE XML. The person who chose the
    file is the one who needs to know their `.alto` was not ALTO."""
    from fichero_cli import __main__ as cli

    class FakeClient:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def import_page(self, *a, **k): return PAYLOAD

    monkeypatch.setattr(cli, "_client", lambda ctx: FakeClient())
    result = CliRunner().invoke(app, ["import-page", "d1", str(_file(tmp_path, "folio.alto"))])

    assert result.exit_code == 0, result.output
    assert "the name says 'alto' and the bytes read as pagexml" in result.output


def test_reimporting_the_same_bytes_is_an_answer_with_status_zero(tmp_path, monkeypatch):
    """`source.format.reimport-recognised`. The 409 says the library already holds
    these bytes and nothing was written — the caller did nothing wrong. Exiting
    non-zero would break a nightly import script for a non-problem, and would make
    "you already have this" indistinguishable from "this file was refused"."""
    from fichero_cli import __main__ as cli

    already = FicheroError(
        "'folio.xml' is already on this document as pass p9 (same content, sha256 abc123def456…)."
        " Nothing was written."
    )
    already.status_code = 409

    class FakeClient:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def import_page(self, *a, **k): raise already

    monkeypatch.setattr(cli, "_client", lambda ctx: FakeClient())
    result = CliRunner().invoke(app, ["import-page", "d1", str(_file(tmp_path))])

    assert result.exit_code == 0, result.output
    assert "already imported" in result.output
    assert "pass p9" in result.output


def test_a_refused_file_still_fails(tmp_path, monkeypatch):
    """The other half: a file nothing recognises must NOT be a success. The 409 is the
    only refusal that leaves with 0."""
    from fichero_cli import __main__ as cli

    refused = FicheroError("nothing recognises 'notes.txt'. This build reads: pagexml, alto, hocr, yolo")
    refused.status_code = 422

    class FakeClient:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def import_page(self, *a, **k): raise refused

    monkeypatch.setattr(cli, "_client", lambda ctx: FakeClient())
    result = CliRunner().invoke(app, ["import-page", "d1", str(_file(tmp_path))])

    assert result.exit_code == 1
    assert "This build reads" in result.output


def test_a_missing_file_is_refused_before_the_engine_is_called(tmp_path, monkeypatch):
    from fichero_cli import __main__ as cli

    def explode(ctx):
        raise AssertionError("the engine must not be called for a file that is not there")

    monkeypatch.setattr(cli, "_client", explode)
    result = CliRunner().invoke(app, ["import-page", "d1", str(tmp_path / "nope.xml")])

    assert result.exit_code == 1
    assert "No such file" in result.output


def _capture():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=PAYLOAD)

    client = FicheroClient(
        base_url="http://127.0.0.1:8765", token="t", library_path="/tmp/l.fichero",
        transport=httpx.MockTransport(handler),
    )
    return client, seen


def test_a_yolo_file_goes_with_its_datasets_class_names(tmp_path):
    """#5138: a YOLO class number means what `classes.txt` says, and the engine may not share this
    disk, so the class file travels WITH the labels. Without it a drop capital (class 2 in
    SegmOnto's list) was stored as a `word`."""
    labels = tmp_path / "000.txt"
    labels.write_text("2 0.1 0.3 0.1 0.1\n", encoding="utf-8")
    (tmp_path / "classes.txt").write_text("MainZone\nDefaultLine\nDropCapitalZone\n", encoding="utf-8")
    client, seen = _capture()
    client.import_page("d1", labels, import_format="yolo")
    assert b'name="dataset"; filename="classes.txt"' in seen[0].content
    assert b"DropCapitalZone" in seen[0].content


def test_a_data_yaml_two_folders_up_is_found_as_the_engine_would(tmp_path):
    (tmp_path / "data.yaml").write_text("names: [MainZone]\n", encoding="utf-8")
    labels = tmp_path / "labels" / "train" / "000.txt"
    labels.parent.mkdir(parents=True)
    labels.write_text("0 0.5 0.5 0.5 0.5\n", encoding="utf-8")
    client, seen = _capture()
    client.import_page("d1", labels)  # recognised as YOLO by its `.txt`
    assert b'filename="data.yaml"' in seen[0].content


def test_an_xml_file_sends_no_dataset_even_beside_a_classes_file(tmp_path):
    (tmp_path / "classes.txt").write_text("MainZone\n", encoding="utf-8")
    client, seen = _capture()
    client.import_page("d1", _file(tmp_path), import_format="pagexml")
    assert b'name="dataset"' not in seen[0].content


def test_file_import_and_page_import_both_resolve():
    """#4943 mounted page import as an `import` GROUP, which shadowed the top-level
    `fichero import <file>` command: `fichero import book.pdf` answered "No such command"
    and every script that imports files broke. Both spellings must resolve to a command,
    never one eating the other."""
    import click
    import typer.main

    group = typer.main.get_command(app)
    ctx = click.Context(group)
    file_import = group.get_command(ctx, "import")
    page_import = group.get_command(ctx, "import-page")
    assert file_import is not None and not isinstance(file_import, click.Group)
    assert [p.name for p in file_import.params if p.param_type_name == "argument"] == ["path"]
    assert page_import is not None
    assert [p.name for p in page_import.params if p.param_type_name == "argument"] == ["doc_id", "path"]
