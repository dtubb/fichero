#!/usr/bin/env python3
"""Assemble a folder of real pages to drag into Fichero, one subfolder per script.

    python3 scripts/fetch_sample_corpus.py          # first: download the sets
    python3 scripts/make_test_corpus_folder.py      # then: ~/Fichero Test Corpus/
    python3 scripts/make_test_corpus_folder.py --dest /some/other/folder

Each subfolder holds page images each BESIDE its same-stem XML (`0041_00000056.jpg` +
`0041_00000056.xml`), the layout eScriptorium and Transkribus export. Dropped into
Fichero today, the images import as pages; once the folder importer pairs an image
with its PAGE/ALTO (#5132), the same drop brings their layout and text too -- so this
folder is that feature's acceptance test.

A `README.md` at the top lists every subfolder's source, licence (and where it was
read), direction, script and what it exercises. **Several sets are NonCommercial and
ShareAlike: the folder is personal research use on this disk and must never be
committed or shared.** Offline: it only copies from `sample_corpus/` and the vendored
fixtures. Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_sample_corpus import DEST as SAMPLES, SETS, image_named_by  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "fichero-server" / "tests" / "unit" / "formats" / "fixtures" / "corpus"
FIXTURE_FOLDER = "Repository test fixtures (the vendored corpus pages)"
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".tif", ".tiff")


def _copy(src: Path, dst: Path) -> None:
    if not (dst.exists() and dst.stat().st_size == src.stat().st_size):
        shutil.copy2(src, dst)


def build(dest: Path) -> list[dict]:
    dest.mkdir(parents=True, exist_ok=True)
    rows = []
    images_by_name: dict[str, Path] = {}

    for key, s in SETS.items():
        pages = SAMPLES / key / "pages"
        report_path = SAMPLES / key / "SET.json"
        row = {"key": key, "set": s, "pages": 0, "with_image": 0, "missing": []}
        if not pages.is_dir():
            row["missing"].append("not fetched -- run fetch_sample_corpus.py " + key)
            rows.append(row)
            continue
        target = dest / s.folder
        target.mkdir(exist_ok=True)
        for f in sorted(pages.iterdir()):
            _copy(f, target / f.name)
            if f.suffix.lower() in IMAGE_EXTS:
                images_by_name.setdefault(f.name, f)
        report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else {}
        row.update(pages=report.get("pages", 0), with_image=report.get("with_image", 0), missing=report.get("missing", []))
        rows.append(row)

    # The 17 vendored fixtures, each under the stem of the image it names, beside that
    # image when one of the sets above supplied it.
    target = dest / FIXTURE_FOLDER
    target.mkdir(exist_ok=True)
    fixture_row = {"key": "fixtures", "set": None, "pages": 0, "with_image": 0, "missing": []}
    for f in sorted(FIXTURES.iterdir()):
        if f.name == "CORPUS.md":
            continue
        data = f.read_bytes()
        ref = image_named_by(data) or (re.search(rb'image "([^"]+)"', data[:4000]) or [None, b""])[1].decode()
        stem = ref.rsplit(".", 1)[0] if ref else f.name.split(".", 1)[0]
        suffix = ".hocr" if f.name.endswith(".hocr") else ".xml"
        (target / f"{stem}{suffix}").write_bytes(data)
        fixture_row["pages"] += 1
        if ref and ref in images_by_name:
            _copy(images_by_name[ref], target / ref)
            fixture_row["with_image"] += 1
        else:
            fixture_row["missing"].append(f"{f.name}: no image for {ref or 'it'}")
    rows.append(fixture_row)
    (dest / "README.md").write_text(_readme(rows), encoding="utf-8")
    return rows


def _readme(rows: list[dict]) -> str:
    lines = [
        "# Fichero Test Corpus",
        "",
        "Real pages written by other people's software, in many scripts and directions, for",
        "exploring Fichero by hand. **Drag this folder (or any subfolder) into Fichero.** Each",
        "page image sits beside a same-stem XML (PAGE or ALTO; two folders carry YOLO `.txt`",
        "labels with a `classes.txt`, one a TEI whose facsimile zones point at the images",
        "beside it): today the images import as pages, and once image/XML pairing lands",
        "(#5132) the same drop brings layout and text.",
        "",
        "Built by `scripts/make_test_corpus_folder.py` from `scripts/fetch_sample_corpus.py`,",
        "which downloads each set from its publisher and checks every file against a recorded",
        "size, hash, CRC or pixel size. Rebuild any time; nothing here is hand-edited.",
        "",
        "**Personal research use only.** Several sets are NonCommercial (CC BY-NC-SA, BY-NC-ND)",
        "or ShareAlike. Keep this folder on this disk: never commit it, never share or mirror it.",
        "",
        "| Folder | Pages | With image | Direction | Script | Licence |",
        "|---|---|---|---|---|---|",
    ]
    for row in rows:
        s = row["set"]
        if s is None:
            lines.append(f"| {FIXTURE_FOLDER} | {row['pages']} | {row['with_image']} | mixed | mixed | see `CORPUS.md` in the repository |")
        else:
            lines.append(f"| {s.folder} | {row['pages']} | {row['with_image']} | {s.direction} | {s.script} | {s.licence} |")
    lines += ["", "## Each folder", ""]
    for row in rows:
        s = row["set"]
        if s is None:
            lines += [
                f"### {FIXTURE_FOLDER}",
                "",
                "The pages the engine's tests run on (`fichero-server/tests/unit/formats/fixtures/corpus/`),",
                "renamed to the stem of the image each names, beside that image where a set above",
                "supplied it. Provenance and licences: `CORPUS.md` beside them in the repository.",
                "",
            ]
        else:
            lines += [
                f"### {s.folder}",
                "",
                f"- **Language:** {s.language}; **script:** {s.script}; **direction:** {s.direction}",
                f"- **Producer:** {s.producer}",
                f"- **Source:** {s.source}",
                f"- **Licence:** {s.licence} -- read at: {s.licence_read}",
                f"- **Exercises:** {s.exercises}",
                f"- **Pages:** {row['pages']}, {row['with_image']} with their image",
            ]
        for note in dict.fromkeys(row["missing"]):
            lines.append(f"- **Note:** {note}")
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dest", type=Path, default=Path.home() / "Fichero Test Corpus")
    args = parser.parse_args(argv)
    rows = build(args.dest)
    size = sum(f.stat().st_size for f in args.dest.rglob("*") if f.is_file())
    for row in rows:
        name = row["set"].folder if row["set"] else FIXTURE_FOLDER
        print(f"{row['pages']:4} pages {row['with_image']:4} with image  {name}")
    print(f"{args.dest}: {size / 1e6:.0f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
