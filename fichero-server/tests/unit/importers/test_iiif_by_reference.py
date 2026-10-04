"""A IIIF archive imported by reference (#5398 slice 2): documents that point at their Image API
services, no image downloaded.

The target is archives like the British Library's Endangered Archives Programme: millions of images
on someone else's server. Here a fake IIIF server answers manifests and collections, and counts every
request, so the tests can say exactly what crossed the network.
"""
from __future__ import annotations

import json

from fichero_server.importers.iiif_import import import_iiif_url, parse_iiif_url
from fichero_server.media.iiif_fetch import PoliteFetcher
from fichero_server.models import Document
from tests.unit.importers.test_iiif_import import _TestClientAdapter

HOST = "https://iiif.archive.example"


def _manifest3(name: str, canvases: int) -> dict:
    return {
        "@context": "http://iiif.io/api/presentation/3/context.json", "id": f"{HOST}/{name}/manifest", "type": "Manifest",
        "label": {"en": [name]}, "rights": "http://creativecommons.org/licenses/by-nc/4.0/",
        "requiredStatement": {"label": {"en": ["Attribution"]}, "value": {"en": ["Endangered Archives Programme"]}},
        "metadata": [{"label": {"en": ["Reference"]}, "value": {"en": [f"EAP000/{name}"]}}],
        "items": [{
            "id": f"{HOST}/{name}/canvas/{i}", "type": "Canvas", "label": {"none": [f"f. {i}"]},
            "width": 4000, "height": 6000,
            "items": [{"type": "AnnotationPage", "items": [{
                "type": "Annotation", "motivation": "painting",
                "body": {"id": f"{HOST}/img/{name}/{i}/full/max/0/default.jpg", "type": "Image", "format": "image/jpeg",
                         "width": 4000, "height": 6000,
                         "service": [{"id": f"{HOST}/img/{name}/{i}", "type": "ImageService3", "profile": "level1"}]},
            }]}],
        } for i in range(1, canvases + 1)],
    }


class FakeIIIFServer:
    def __init__(self, documents: dict[str, dict]) -> None:
        self.documents = documents
        self.requests: list[str] = []

    def get(self, url, timeout):
        self.requests.append(url)
        doc = self.documents.get(url)
        return (200, {}, json.dumps(doc).encode()) if doc else (404, {}, b"")


def test_a_thousand_canvas_manifest_becomes_a_thousand_pages_by_reference():
    """WHY: each page must keep what reading and viewing need (its canvas, its Image API service, the
    canvas's full size) and the manifest's metadata and rights, while nothing but the manifest is fetched."""
    manifest = _manifest3("vol1", 1000)
    server = FakeIIIFServer({manifest["id"]: manifest})
    parsed = parse_iiif_url(manifest["id"], fetcher=PoliteFetcher(get=server.get))

    pages = parsed.nodes[1:]
    assert len(pages) == 1000 and server.requests == [manifest["id"]]
    meta = pages[41]["metadata"]
    assert meta["iiif_id"] == f"{HOST}/vol1/canvas/42" and meta["iiif_service"] == f"{HOST}/img/vol1/42"
    assert (meta["width"], meta["height"]) == (4000, 6000) and meta["by_reference"] is True
    assert meta["iiif_rights"]["rights"].endswith("by-nc/4.0/")
    assert meta["iiif_rights"]["required_statement"]["value"] == "Endangered Archives Programme"
    assert meta["iiif_manifest_metadata"] == {"Reference": "EAP000/vol1"}
    assert pages[41]["images"][0]["source_path"] is None, "nothing local: the page is read by reference"


def test_a_collection_of_collections_is_followed_and_a_sample_stops_early():
    """WHY: an archive is a collection of collections of manifests; proving a recipe on a sample first
    means stopping after a few manifests, and saying so."""
    manifests = [_manifest3(f"vol{i}", 3) for i in range(1, 6)]
    inner = {"id": f"{HOST}/c/inner", "type": "Collection", "items": [{"id": m["id"], "type": "Manifest"} for m in manifests[2:]]}
    root = {"id": f"{HOST}/c/root", "type": "Collection", "label": {"en": ["EAP000"]},
            "items": [{"id": m["id"], "type": "Manifest"} for m in manifests[:2]] + [{"id": inner["id"], "type": "Collection"}]}
    server = FakeIIIFServer({root["id"]: root, inner["id"]: inner, **{m["id"]: m for m in manifests}})

    whole = parse_iiif_url(root["id"], fetcher=PoliteFetcher(get=server.get))
    assert whole.manifests_seen == 5 and len(whole.nodes) == 1 + 15
    sample = parse_iiif_url(root["id"], fetcher=PoliteFetcher(get=server.get), max_manifests=2)
    assert sample.manifests_seen == 2 and any("sample" in w for w in sample.warnings)


def test_presentation_2_manifests_are_read_too():
    """WHY: many archives still serve Presentation 2 (sequences, canvases, images, resource, service)."""
    v2 = {"@id": f"{HOST}/v2/manifest", "@type": "sc:Manifest", "label": "Old volume", "license": "http://rightsstatements.org/vocab/InC/1.0/",
          "attribution": "Some Library", "sequences": [{"canvases": [{
              "@id": f"{HOST}/v2/canvas/1", "@type": "sc:Canvas", "label": "1", "width": 3000, "height": 4000,
              "images": [{"resource": {"@id": f"{HOST}/v2/img/1/full/full/0/default.jpg", "service": {
                  "@id": f"{HOST}/v2/img/1", "profile": "http://iiif.io/api/image/2/level1.json"}}}]}]}]}
    server = FakeIIIFServer({v2["@id"]: v2})
    (page,) = parse_iiif_url(v2["@id"], fetcher=PoliteFetcher(get=server.get)).nodes[1:]
    assert page["metadata"]["iiif_service"] == f"{HOST}/v2/img/1"
    assert page["metadata"]["iiif_rights"] == {"rights": "http://rightsstatements.org/vocab/InC/1.0/", "attribution": "Some Library"}


def test_importing_by_reference_creates_image_pages_and_fetches_no_image(client, db, tmp_path):
    """WHY: a million canvases imported with a preview each would be a million requests to an archive's
    server before anyone looks at a page. Import fetches the manifests only; documents are image pages
    that carry their service, and have no file here."""
    manifest = _manifest3("vol1", 20)
    server = FakeIIIFServer({manifest["id"]: manifest})
    summary = import_iiif_url(_TestClientAdapter(client), manifest["id"], str(tmp_path / "Lib.fichero"),
                              fetcher=PoliteFetcher(get=server.get))

    assert summary.pages_seen == 20 and server.requests == [manifest["id"]]
    pages = [d for d in db.query(Document) if (d.metadata or {}).get("iiif_type") == "Canvas"]
    assert len(pages) == 20 and all(not p.path for p in pages)
    assert {p.metadata["iiif_service"] for p in pages} == {f"{HOST}/img/vol1/{i}" for i in range(1, 21)}


def test_a_page_is_fetched_once_at_display_size_when_it_is_viewed(tmp_path, monkeypatch):
    """WHY: viewing a page imported by reference needs one page-sized image, fetched on demand and
    kept; the second look must not ask the archive again."""
    from io import BytesIO

    from PIL import Image

    from fichero_server.db import storage
    from fichero_server.media.iiif_fetch import PoliteFetcher

    buf = BytesIO()
    Image.new("RGB", (800, 1200), (230, 225, 210)).save(buf, format="JPEG")
    asked: list[str] = []
    monkeypatch.setattr(storage, "_IIIF_FETCHER", PoliteFetcher(get=lambda url, t: asked.append(url) or (200, {}, buf.getvalue())))
    doc = Document(name="f. 1", metadata={"iiif_service": f"{HOST}/img/vol1/1", "iiif_type": "Canvas"})
    package = tmp_path / "Lib.fichero"

    thumb = storage.ensure_thumbnail(doc, package_path=package)
    again = storage.iiif_page_image(doc, package)
    assert thumb is not None and thumb.exists() and again.exists()
    assert asked == [f"{HOST}/img/vol1/1/full/!{max(storage.settings.display_size)},{max(storage.settings.display_size)}/0/default.jpg"]


def test_a_page_that_came_in_by_reference_exports_pointing_at_its_original(client, db, tmp_path):
    """`iiif.export.points-at-original`: a page that came in by reference exports pointing at its
    original image service; nothing is re-hosted. WHY: the archive owns its images and its rights;
    a manifest Fichero exports for an EAP page must send viewers to the archive, at the canvas's
    true size, with the service exactly as the archive described it (its type and profile are the
    archive's to state, not Fichero's to guess)."""
    manifest = _manifest3("vol2", 2)
    server = FakeIIIFServer({manifest["id"]: manifest})
    import_iiif_url(_TestClientAdapter(client), manifest["id"], str(tmp_path / "Lib.fichero"),
                    fetcher=PoliteFetcher(get=server.get))
    page = next(d for d in db.query(Document) if (d.metadata or {}).get("iiif_id") == f"{HOST}/vol2/canvas/1")

    r = client.get(f"/api/iiif/iiif/manifest/{page.id}")
    assert r.status_code == 200, r.text
    canvas = r.json()["items"][0]
    body = canvas["items"][0]["items"][0]["body"]
    assert (canvas["width"], canvas["height"]) == (4000, 6000)
    assert body["id"] == f"{HOST}/img/vol2/1/full/max/0/default.jpg"
    assert body["service"] == [{"id": f"{HOST}/img/vol2/1", "type": "ImageService3", "profile": "level1"}]
    assert r.json()["rights"].endswith("by-nc/4.0/")  # the archive's terms travel too
    assert r.json()["requiredStatement"]["value"] == {"none": ["Endangered Archives Programme"]}


def test_a_manifest_exported_and_imported_again_lands_on_the_same_pages(client, db, tmp_path):
    """`iiif.round-trip`: a manifest exported by Fichero and imported again, into the original library,
    lands on the same canvases with no duplicate pages. WHY: archives move between tools by manifest;
    re-importing one's own export must not double an archive of a million pages."""
    manifest = _manifest3("vol3", 3)
    server = FakeIIIFServer({manifest["id"]: manifest})
    import_iiif_url(_TestClientAdapter(client), manifest["id"], str(tmp_path / "Lib.fichero"),
                    fetcher=PoliteFetcher(get=server.get))
    pages = lambda: [d for d in db.query(Document)  # noqa: E731
                     if (d.metadata or {}).get("iiif_type") == "Canvas" and d.deleted_at is None]
    before = sorted(p.metadata["iiif_id"] for p in pages())
    page = next(p for p in pages() if p.metadata["iiif_id"] == f"{HOST}/vol3/canvas/2")

    exported = client.get(f"/api/iiif/iiif/manifest/{page.id}").json()
    exported["id"] = f"{HOST}/fichero-export/manifest"
    server.documents[exported["id"]] = exported
    import_iiif_url(_TestClientAdapter(client), exported["id"], str(tmp_path / "Lib.fichero"),
                    fetcher=PoliteFetcher(get=server.get))

    assert sorted(p.metadata["iiif_id"] for p in pages()) == before  # the same canvases, none doubled
