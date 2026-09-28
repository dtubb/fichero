"""Step 1: import a few pages of each hard shape the way the app does, one folder at a time.

The app's folder drop is `POST /api/ingest/folder` with copy_mode and recursive on
(`DocumentService.ingestFolder`), then polls `GET /api/ingest/status/{task_id}`. #5132
pairs each image with its layout file and imports the file as a pass on that page.

A few pages of each subfolder are STAGED (copied) into ACCEPTANCE_OUT/staging/<key>/ and
that folder is dropped, so each shape costs seconds rather than the whole subfolder. TEI
(an edition, not one file per image) and YOLO label files do not pair by design; they go
in through the one-file import (`POST /api/documents/{id}/import`, `fichero import page`)
onto the page they describe, which is what a person would do next.

Writes ACCEPTANCE_OUT/import.json. Starts and stops its own engine.
"""

from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _engine import CORPUS, IMAGE_SUFFIXES, LIBRARY, OUT, client, engine, load, save, wait_for_load  # noqa: E402

#: key -> (corpus subfolder, stems to take). One of each hard shape.
SELECTION: dict[str, tuple[str, list[str]]] = {
    "syriac-rtl": ("Syriac - Vienna Cod. Syr. 1 (right-to-left)", ["0002_00000017", "0006_00000021", "0012_00000027"]),
    "hebrew-rtl": ("Hebrew - BiblIA medieval Bibles (right-to-left)", ["btv1b10539501d", "btv1b10548378n"]),
    "chinese-vertical": ("Chinese - classical, vertical columns", ["BULAC_BIULO_CHI_1087_1_0065", "BULAC_BIULO_CHI_1087_1_0074"]),
    "genji-tei": (
        "Japanese - Tale of Genji, 1942 variorum, vertical print (TEI facsimile over NDL IIIF)",
        ["R0000022", "R0000023", "kouigenji-01-kiritsubo.tei"],
    ),
    "clm13027-mufi": ("Medieval Latin (MUFI) - Clm 13027", ["38r", "41v"]),
    "eutyches-glosses": (
        "Latin with interlinear glosses - Eutyches grammar, 9th-11th c. (Leiden VLO 41, BnF lat. 7499)",
        ["f02r", "f03v"],
    ),
    "reichsanzeiger-table": (
        "German - Reichsanzeiger newspaper tables (PAGE TableRegion and TableCell)",
        ["1857_132_0507", "1870_138_0554"],
    ),
    # The Reichsanzeiger scans are 61-64 megapixels and the ingest refuses anything over 50
    # (a finding), so the table shape is ALSO taken from a logbook page that does go in.
    "albatross-table": (
        "English - USS Albatross logbooks 1880s, ruled tables filled by hand (PAGE TableRegion)",
        ["Albatross_vol009of055-050-0"],
    ),
    "paderov-mm10": ("Czech - Padeřov Bible, 1432-35 (Transkribus ALTO in mm10)", ["00000013", "00000014"]),
    "cherokee-inch1200-densest": (
        "Cherokee and English - Cherokee Phoenix newspaper, 1828 (ALTO 2, inch1200)",
        ["cherokee-phoenix_1828030601_0002"],
    ),
    "benedict-lang-tags": (
        "Latin and Old English - bilingual Rule of St Benedict, 10th-11th c. (line language tags)",
        ["BL-CTAiv_028", "BL-CTAiv_029"],
    ),
    "yolo-segmonto": (
        "YOLO layout - YALTAi SegmOnto, medieval manuscripts and early print (labels beside ALTO)",
        ["000", "001", "classes"],
    ),
}

STAGING = OUT / "staging"


def stage(key: str) -> Path:
    folder, stems = SELECTION[key]
    src = CORPUS / folder
    dest = STAGING / key
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    for path in sorted(src.iterdir()):
        name = path.name
        if any(name == s or name.startswith(s + ".") for s in stems) and path.is_file():
            shutil.copy2(path, dest / name)
    return dest.resolve()


def import_folder(c, folder: Path) -> dict:
    t0 = time.perf_counter()
    task = c.request(
        "POST",
        "/api/ingest/folder",
        json={"path": str(folder), "copy_mode": True, "recursive": True},
    )
    task_id = task["task_id"]
    while True:
        status = c.request("GET", f"/api/ingest/status/{task_id}")
        if status["status"] in {"completed", "failed", "cancelled"}:
            break
        time.sleep(0.25)
    return {"task": status, "seconds": round(time.perf_counter() - t0, 2)}


def page_report(c, doc_ids: list[str]) -> list[dict]:
    pages = []
    for doc_id in doc_ids:
        doc = c.request("GET", f"/api/documents/{doc_id}")
        name = doc.get("name") or ""
        row = {"id": doc_id, "name": name, "doc_type": doc.get("doc_type")}
        if Path(name).suffix.lower() in IMAGE_SUFFIXES:
            segs = c.request("GET", f"/api/segments/document/{doc_id}")
            real = [p for p in segs["passes"] if not p.get("provisional")]
            row.update(image=True, passes=len(real), pass_ids=[p["id"] for p in real], segments=len(segs["segments"]))
        else:
            row["image"] = False
        pages.append(row)
    return pages


def import_one_file(c, doc_id: str, path: Path, fmt: str | None) -> dict:
    t0 = time.perf_counter()
    try:
        result = c.import_page(doc_id, path, import_format=fmt)
        ok = True
    except Exception as exc:  # noqa: BLE001 -- the engine's sentence IS the finding
        result, ok = {"error": f"{type(exc).__name__}: {exc}"}, False
    return {"file": path.name, "format": fmt, "ok": ok, "seconds": round(time.perf_counter() - t0, 2), "result": result}


def main() -> None:
    only = set(sys.argv[1:])
    # Resumable: a key already in import.json is never imported twice.
    try:
        results = load("import.json")
    except FileNotFoundError:
        results = []
    done = {r["key"] for r in results}
    with engine():
        with client() as c:
            created = c.request("POST", "/api/library", json={"path": str(LIBRARY)})
            print("library:", created, flush=True)
            for key in SELECTION:
                if (only and key not in only) or key in done:
                    continue
                wait_for_load()
                folder = stage(key)
                files = sorted(p.name for p in folder.iterdir())
                images = [n for n in files if Path(n).suffix.lower() in IMAGE_SUFFIXES]
                print(f"importing {key}: {files}", flush=True)
                run = import_folder(c, folder)
                ids = run["task"].get("document_ids") or []
                pages = page_report(c, ids)
                image_pages = [p for p in pages if p["image"]]
                row = {
                    "key": key,
                    "folder": SELECTION[key][0],
                    "staged_files": files,
                    "images_staged": len(images),
                    "seconds": run["seconds"],
                    "status": run["task"]["status"],
                    "error": run["task"].get("error"),
                    "failures": run["task"].get("failures"),
                    "task_keys": sorted(run["task"].keys()),
                    "documents_created": len(ids),
                    "pages_created": len(image_pages),
                    "pages_with_pass": sum(1 for p in image_pages if p["passes"] > 0),
                    "segments": sum(p["segments"] for p in image_pages),
                    "non_image_documents": [p["name"] for p in pages if not p["image"]],
                    "pages": pages,
                    "one_file_imports": [],
                }
                by_stem = {Path(p["name"]).stem: p for p in image_pages}
                tei_in_folder = any(
                    name.startswith("kouigenji-01-kiritsubo.tei.xml")
                    for name in run["task"].get("imported_as_passes") or []
                )
                row["imported_as_passes"] = run["task"].get("imported_as_passes") or []
                if key == "genji-tei" and tei_in_folder:
                    # The folder drop pairs a TEI edition's pages with its scans (#5143); importing
                    # the file again onto one of them is correctly a 409, not a finding.
                    row["one_file_imports"].append(
                        {"file": "kouigenji-01-kiritsubo.tei.xml", "skipped": "imported by the folder drop"}
                    )
                elif key == "genji-tei":
                    target = by_stem.get("R0000022")
                    if target:
                        row["one_file_imports"].append(
                            import_one_file(c, target["id"], folder / "kouigenji-01-kiritsubo.tei.xml", None)
                        )
                if key == "yolo-segmonto":
                    for stem in ("000", "001"):
                        target = by_stem.get(stem)
                        if target:
                            row["one_file_imports"].append(import_one_file(c, target["id"], folder / f"{stem}.txt", "yolo"))
                if row["one_file_imports"]:
                    row["pages"] = page_report(c, [p["id"] for p in image_pages])
                    row["pages_with_pass"] = sum(1 for p in row["pages"] if p.get("passes", 0) > 0)
                    row["segments"] = sum(p.get("segments", 0) for p in row["pages"])
                print(
                    f"  {row['status']} {row['seconds']}s pages={row['pages_created']} "
                    f"with_pass={row['pages_with_pass']} segments={row['segments']} "
                    f"other_docs={row['non_image_documents']} one_file={[(i['file'], i.get('ok', i.get('skipped'))) for i in row['one_file_imports']]}",
                    flush=True,
                )
                results.append(row)
                save("import.json", results)


if __name__ == "__main__":
    main()
