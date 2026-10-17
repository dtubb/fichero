"""An imported file's language lands as the canonical name, and a line that says nothing inherits Set Up's script
and direction (#5517), tested to the spec: `source.lang.imported-language-is-a-name` and
`source.lang.project-facts-from-setup` (docs/contributor_manual/specs/source/languages-scripts-signs.md).

WHY: the corpus run of 2026-10-06 imported six scripts through the CLI. PAGE's language arrived as "German" and
ALTO's as "de", two spellings of one language; and every imported line resolved no script or direction, even in a
project set up for Syriac. Through the routes the app calls (`POST /api/documents/{id}/import`,
`PUT /api/recipes/project`, `GET /api/source-settings/resolve`).
"""

from __future__ import annotations

from PIL import Image

from fichero_server.models import DocType, Document, FileType
from fichero_server.models.segments import Segment

ALTO = """<?xml version="1.0" encoding="UTF-8"?>
<alto xmlns="http://www.loc.gov/standards/alto/ns-v4#">
 <Description><MeasurementUnit>pixel</MeasurementUnit></Description>
 <Layout><Page ID="p1" WIDTH="1000" HEIGHT="1000" PHYSICAL_IMG_NR="1"><PrintSpace>
  <TextBlock ID="b1" HPOS="10" VPOS="10" WIDTH="900" HEIGHT="300">
   <TextLine ID="l1" HPOS="10" VPOS="10" WIDTH="900" HEIGHT="50" LANG="de">
    <String CONTENT="Guten" HPOS="10" VPOS="10" WIDTH="100" HEIGHT="50"/></TextLine>
   <TextLine ID="l2" HPOS="10" VPOS="80" WIDTH="900" HEIGHT="50" LANG="xyzzy">
    <String CONTENT="Tag" HPOS="10" VPOS="80" WIDTH="100" HEIGHT="50"/></TextLine>
   <TextLine ID="l3" HPOS="10" VPOS="150" WIDTH="900" HEIGHT="50">
    <String CONTENT="" HPOS="10" VPOS="150" WIDTH="100" HEIGHT="50"/></TextLine>
  </TextBlock></PrintSpace></Page></Layout></alto>
"""

PAGE = """<?xml version="1.0" encoding="UTF-8"?>
<PcGts xmlns="http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15">
 <Page imageFilename="page.png" imageWidth="1000" imageHeight="1000">
  <TextRegion id="r1"><Coords points="10,10 900,10 900,300 10,300"/>
   <TextLine id="l1" primaryLanguage="German"><Coords points="10,10 900,10 900,60 10,60"/>
    <TextEquiv><Unicode>Guten</Unicode></TextEquiv></TextLine>
  </TextRegion>
 </Page>
</PcGts>
"""


def _page(db, tmp_path, name="page.png") -> Document:
    path = tmp_path / name
    Image.new("RGB", (1000, 1000), (235, 230, 220)).save(path)
    doc = Document(name=name, doc_type=DocType.file, file_type=FileType.image, path=str(path))
    db.save(doc)
    return doc


def _import(client, doc, text: str, filename: str) -> None:
    r = client.post(f"/api/documents/{doc.id}/import", files={"file": (filename, text.encode(), "application/xml")})
    assert r.status_code == 200, r.text


def _lines(db, doc) -> dict[str, Segment]:
    rows = [s for s in db.query(Segment, document_id=doc.id) if s.kind == "line"]
    return {str((s.metadata or {}).get("source_id")): s for s in rows}


def test_alto_and_page_languages_land_as_one_name_and_an_unknown_is_kept(client, db, tmp_path):
    """"ALTO's LANG="de" and PAGE XML's primaryLanguage="German" both land as German; a value no language
    answers to is kept as written … A segment the file says nothing about stays empty"."""
    alto_page, page_page = _page(db, tmp_path, "a.png"), _page(db, tmp_path, "b.png")
    _import(client, alto_page, ALTO, "a.alto.xml")
    _import(client, page_page, PAGE, "b.page.xml")

    alto = _lines(db, alto_page)
    assert alto["l1"].language == "German"
    assert alto["l2"].language == "xyzzy"
    assert alto["l3"].language is None and alto["l3"].script is None and alto["l3"].direction is None
    assert _lines(db, page_page)["l1"].language == "German"


def test_alto_still_writes_the_tag_back(client, db, tmp_path):
    """"Each writer gives its format's form back: … ALTO the tag (de), so both still round-trip"."""
    from fichero_server.page_export import export_page

    doc = _page(db, tmp_path)
    _import(client, doc, ALTO, "a.alto.xml")
    written = export_page(db, doc.id, "alto").data.decode("utf-8")
    assert 'LANG="de"' in written


def test_a_line_that_says_nothing_resolves_to_set_ups_script_and_its_direction(client, db, tmp_path):
    """"A project that answered Syriac resolves an imported line that says nothing as Syriac, right to left"."""
    answers = {"purposes": ["transcribe"], "languages": ["syr"], "scripts": ["Syrc"], "materials": ["handwriting"]}
    recipe = client.post("/api/recipes/assemble", json={**answers, "mac_memory_gb": 32}).json()
    assert client.put("/api/recipes/project", json={"answers": answers, "recipe": recipe}).status_code == 200
    doc = _page(db, tmp_path)
    _import(client, doc, ALTO, "a.alto.xml")
    line = _lines(db, doc)["l3"]

    resolved = client.get("/api/source-settings/resolve", params={"segment_id": line.id}).json()
    facts = {s["key"]: s for s in resolved["settings"]}
    assert facts["script"]["value"] == "Syrc", facts["script"]
    assert facts["direction"]["value"] == "rtl", facts["direction"]
    assert facts["script"]["level"] == "project" and facts["direction"]["level"] == "project", facts


def test_a_page_with_no_language_resolves_to_set_ups_language_5756(client, db, tmp_path):
    """"Its one language (as its name) … at the project's level": Set Up said Spanish, so a page and a line that
    state nothing resolve Spanish from the project, never `never_determined` (#5756)."""
    answers = {"purposes": ["transcribe"], "languages": ["es"], "scripts": ["Latn"], "materials": ["print"]}
    recipe = client.post("/api/recipes/assemble", json={**answers, "mac_memory_gb": 32}).json()
    assert client.put("/api/recipes/project", json={"answers": answers, "recipe": recipe}).status_code == 200
    doc = _page(db, tmp_path)
    _import(client, doc, ALTO, "a.alto.xml")
    line = _lines(db, doc)["l3"]

    for params in ({"segment_id": line.id}, {"document_id": doc.id}):
        facts = {s["key"]: s for s in client.get("/api/source-settings/resolve", params=params).json()["settings"]}
        assert facts["language"]["value"] == "Spanish", facts["language"]
        assert facts["language"]["level"] == "project", facts["language"]
