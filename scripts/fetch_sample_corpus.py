#!/usr/bin/env python3
"""Download larger real HTR/OCR ground-truth sets into a local, git-ignored library.

    python3 scripts/fetch_sample_corpus.py --list
    python3 scripts/fetch_sample_corpus.py                # everything in the manifest
    python3 scripts/fetch_sample_corpus.py syriac-smmj36-page greek-vatgr2228

**For exploring by hand, never for tests or CI.** The small pages the tests use are
vendored in `fichero-server/tests/unit/formats/fixtures/corpus/`; these are the sets
they were taken from, too large to commit. Provenance, and the candidates refused for
their licence, are in that directory's `CORPUS.md`.

Every entry was licence-checked BEFORE it was listed (NonCommercial and unlicensed sets
are not here), and every download is checked against the size and md5 recorded below
-- a changed upstream file is refused, not silently accepted. Zip archives are
unpacked next to themselves. Stdlib only.

Files land in `sample_corpus/<name>/` at the repository root, which `.gitignore`
excludes: several of these are CC-BY-SA, and none of them belongs in git history.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / "sample_corpus"

#: name -> (url, bytes, md5, licence, what it is). GitHub archives are pinned to a
#: commit so the hash cannot drift.
MANIFEST: dict[str, tuple[str, int, str, str, str]] = {
    "chi-know-po": (
        "https://codeload.github.com/calfa-co/chi-know-po/zip/5047c5a2e5abe7264a27bfe6a02459df3ccf702c",
        2345249, "d2b27924c2a9f4ae9e6497403ee1000c", "Apache-2.0",
        "Classical Chinese manuscripts, vertical columns, PAGE 2013 (Calfa)",
    ),
    "rasam": (
        "https://codeload.github.com/calfa-co/rasam-dataset/zip/c670eb6e6b3292899873d8b98c6575b8defce96f",
        10104489, "4087f30cfed3f701421ccf5b564d9531", "Apache-2.0",
        "547 Maghrebi Arabic manuscript pages, PAGE 2013 (Calfa, BULAC)",
    ),
    "syriac-smmj36-page": (
        "https://zenodo.org/records/18157525/files/page.zip?download=1",
        2457701, "b88c33b0dd0117db0f88b24e5e26cb6e", "CC-BY-4.0",
        "Syriac, St Mark's Monastery Jerusalem MS 36 -- PAGE (Transkribus)",
    ),
    "syriac-smmj36-alto": (
        "https://zenodo.org/records/18157525/files/alto.zip?download=1",
        2618558, "1d0e3430e8fd96f921c603e1d728c10f", "CC-BY-4.0",
        "the same Syriac pages as ALTO (eScriptorium) -- one source, two producers",
    ),
    "syriac-onb-syr1-page": (
        "https://zenodo.org/records/14714089/files/page.zip?download=1",
        1113171, "1e06e5814a3c08daf4e9158289231dc1", "CC-BY-4.0",
        "Syriac, ONB Cod. Syr. 1, 140 folios, PAGE 2019 (eScriptorium)",
    ),
    "greek-vatgr2228": (
        "https://zenodo.org/records/20705757/files/dataset.zip?download=1",
        892881, "e6637a2da8d2b33b8e8bafa80201c950", "CC-BY-SA-4.0",
        "medieval polytonic Greek, Vat. gr. 2228 + Phil. gr. 130, 46 PAGE files (Transkribus)",
    ),
    "tibetan-pagantibet-manual1": (
        "https://zenodo.org/records/19205598/files/Manual1-20230809_GT_layout.xml?download=1",
        165473, "48334278b49dab19c8326faa7a00778d", "CC-BY-SA-4.0",
        "Transkribus TEI export, 66 surfaces, Tibetan layout ground truth",
    ),
    "devanagari-diksita1895": (
        "https://heidata.uni-heidelberg.de/api/access/datafile/7316",
        3058611, "c3f5ea8ef80a5f18897fc503adff105e", "CC-BY-4.0",
        "printed Hindi/Braj in Devanagari, ALTO + images (Transkribus; heiDATA EGOKEI)",
    ),
    "malayalam-telisseri": (
        "https://heidata.uni-heidelberg.de/api/access/datafile/11744",
        6872981, "a5eabde1cb44fb2ad2be83228e534b41", "CC-BY-4.0",
        "Tellicherry records in Malayalam, ALTO + images (Transkribus; heiDATA L2KRZO)",
    ),
}


def fetch(name: str) -> Path:
    url, size, md5, _licence, _what = MANIFEST[name]
    folder = DEST / name
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / (name + (".xml" if "_layout.xml" in url else ".zip"))
    if target.exists() and target.stat().st_size == size and _md5(target) == md5:
        print(f"have     {name}")
        return target
    print(f"fetching {name} ({size / 1e6:.1f} MB) from {url}")
    partial = target.with_suffix(target.suffix + ".part")
    with urllib.request.urlopen(url, timeout=120) as response, partial.open("wb") as out:
        while chunk := response.read(1 << 20):
            out.write(chunk)
    got_size, got_md5 = partial.stat().st_size, _md5(partial)
    if (got_size, got_md5) != (size, md5):
        partial.unlink()
        raise SystemExit(
            f"{name}: expected {size} bytes md5 {md5}, got {got_size} bytes md5 {got_md5} "
            "-- the upstream file changed; re-check its licence before updating the manifest"
        )
    partial.replace(target)
    if zipfile.is_zipfile(target):
        with zipfile.ZipFile(target) as archive:
            archive.extractall(folder)
    return target


def _md5(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        while chunk := handle.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("names", nargs="*", help="manifest entries (default: all)")
    parser.add_argument("--list", action="store_true", help="show the manifest and exit")
    args = parser.parse_args(argv)

    if args.list:
        for name, (_url, size, _md5sum, licence, what) in MANIFEST.items():
            print(f"{name:<28} {size / 1e6:6.1f} MB  {licence:<13} {what}")
        return 0
    unknown = [name for name in args.names if name not in MANIFEST]
    if unknown:
        print(f"not in the manifest: {unknown}; see --list", file=sys.stderr)
        return 2
    for name in args.names or MANIFEST:
        fetch(name)
    print(f"done: {DEST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
