"""Find Regions keeps Kraken's lines with its regions, so Read never segments a page again, and says how far it is
(#5689), tested to the spec: `prep.regions.open-default` (docs/contributor_manual/specs/source/image-preparation.md).

WHY: the onboarding run segmented every page twice, blla in Find Regions and again in the Transcribe (Kraken)
workflow, at about 40 s a page (an hour on 92 pages); and the run sat at "0 of 1 folder" for twenty minutes while
Find Regions worked. Kraken is stubbed at its one seam (`segment_lines`).
"""

from __future__ import annotations

from PIL import Image

from fichero_server.llm import kraken_runtime
from fichero_server.models import DocType, Document, FileType

PAYLOAD = {
    "width": 600, "height": 800,
    "regions": [{"id": "r1", "type": "text", "polygon": [[20, 20], [580, 20], [580, 400], [20, 400]]}],
    "lines": [{"id": "l1", "regions": ["r1"], "polygon": [[30, 30], [570, 30], [570, 70], [30, 70]],
               "baseline": [[30, 65], [570, 65]]},
              {"id": "l2", "regions": ["r1"], "polygon": [[30, 90], [570, 90], [570, 130], [30, 130]],
               "baseline": [[30, 125], [570, 125]]}],
}


def _pages(db, tmp_path, n: int = 2) -> list[Document]:
    out = []
    for i in range(n):
        path = tmp_path / f"{i + 1}_page.png"
        Image.new("RGB", (600, 800), (235, 230, 220)).save(path)
        doc = Document(name=path.name, doc_type=DocType.file, file_type=FileType.image, path=str(path))
        db.save(doc)
        out.append(doc)
    return out


def test_find_regions_keeps_krakens_lines_so_a_reader_reads_them_without_segmenting_again(db, tmp_path,
                                                                                         monkeypatch):
    from fichero_server.llm.working_lines import working_lines
    from fichero_server.recipes.regions import find_regions

    calls = []
    monkeypatch.setattr(kraken_runtime, "segment_lines", lambda path, **k: calls.append(path) or PAYLOAD)
    (page,) = _pages(db, tmp_path, 1)

    account = find_regions(db, [page.id], "run-1", "blla", provider="kraken")

    assert account["regions"] == 1 and len(calls) == 1
    found = working_lines(db, page.id)
    assert found is not None and len(found.lines) == 2  # the lines Read reads, from the same one pass


def test_find_regions_says_how_far_it_is_page_by_page(db, tmp_path, monkeypatch):
    from fichero_server.recipes.regions import find_regions, progress_words

    monkeypatch.setattr(kraken_runtime, "segment_lines", lambda path, **k: PAYLOAD)
    pages = _pages(db, tmp_path, 2)
    said = []

    find_regions(db, [p.id for p in pages], "run-1", "blla", provider="kraken", say=said.append)

    assert said == ["Finding regions: 0 of 2 pages", "Finding regions: 1 of 2 pages, about 1 min left",
                    "Finding regions: 2 of 2 pages"], said
    assert progress_words(23, 92, elapsed=230.0) == "23 of 92 pages, about 12 min left"
    assert progress_words(92, 92, elapsed=900.0) == "92 of 92 pages"
