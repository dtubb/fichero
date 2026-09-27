#!/usr/bin/env python3
"""Download real HTR/OCR ground truth, WITH its page images, into a local library.

    python3 scripts/fetch_sample_corpus.py --list
    python3 scripts/fetch_sample_corpus.py                  # every set
    python3 scripts/fetch_sample_corpus.py biblia-hebrew greek-vatgr2228

**For exploring by hand, never for tests or CI, and never for the repository.** The
small pages the tests use are vendored in
`fichero-server/tests/unit/formats/fixtures/corpus/`, under licences an AGPL history
can carry. This library is personal research use on one disk, so it may also hold
NonCommercial and ShareAlike sets (BiblIA, OpenITI MAKHZAN, IRHAS): each set's licence
is in its manifest entry and in the README that `make_test_corpus_folder.py` writes.
Everything is FETCHED from its publisher; nothing here is mirrored anywhere.

For each set this writes `sample_corpus/<set>/pages/`: up to `pages` XML files, each
beside the page image it names, both under the IMAGE's stem (`0041_00000056.jpg` and
`0041_00000056.xml`) -- the layout eScriptorium and Transkribus export, and the one a
folder import pairs by (#5132). The XML is renamed, never edited, so the file name it
references stays true.

Nothing is taken on trust; every byte is checked against something recorded:

* a whole archive      -- its size and md5 (`MANIFEST`);
* a remote zip member  -- the archive's total size, and the member's CRC-32 from the
                          zip's own central directory (fetched with HTTP Range, so a
                          20-page sample of a 5 GB deposit costs 20 pages);
* a GitHub file        -- its git blob sha, from the tree of a PINNED commit;
* a IIIF image         -- its pixel size must equal the size the XML states, or the
                          page's coordinates would not land on it.

`sample_corpus/` is git-ignored. Stdlib only.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import shutil
import subprocess
import struct
import sys
import urllib.parse
import urllib.error
import urllib.request
import zipfile
import zlib
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / "sample_corpus"
AGENT = {"User-Agent": "fichero-sample-corpus (research test library)"}
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".jp2")


# ---------------------------------------------------------------------------
# Sources: where XML and images come from, each verifiable
# ---------------------------------------------------------------------------


def _http(url: str, rng: str | None = None) -> tuple[bytes, dict]:
    headers = dict(AGENT)
    if rng:
        headers["Range"] = rng
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=300) as r:
            if rng and r.status != 206:
                raise OSError(f"{url}: the server ignored a Range request (status {r.status})")
            return r.read(), r.headers  # case-insensitive: servers differ in header case
    except urllib.error.URLError as exc:
        # Some servers (the Getty's) send an incomplete certificate chain, which
        # Python's OpenSSL cannot complete and macOS's own trust store can. Retry with
        # the system curl -- still verifying TLS, never with verification off.
        if rng or "CERTIFICATE_VERIFY_FAILED" not in str(exc) or not shutil.which("curl"):
            raise
        done = subprocess.run(["curl", "-sSfL", "-A", AGENT["User-Agent"], url], capture_output=True, timeout=300)
        if done.returncode:
            raise OSError(f"{url}: {done.stderr.decode(errors='replace').strip()}") from exc
        return done.stdout, {}


class Store:
    """A set of named files: `names()` lists them, `read(name)` returns verified bytes."""

    def names(self) -> list[str]:
        raise NotImplementedError

    def read(self, name: str) -> bytes:
        raise NotImplementedError


@dataclass
class Archive(Store):
    """A whole archive, downloaded once and checked against its size and md5."""

    url: str
    size: int
    md5: str
    _zip: zipfile.ZipFile | None = None
    folder: Path | None = None

    def open(self, folder: Path) -> "Archive":
        path = folder / "archive.zip"
        if not (path.exists() and path.stat().st_size == self.size and _md5(path) == self.md5):
            print(f"  fetching {self.url} ({self.size / 1e6:.1f} MB)")
            partial = path.with_suffix(".part")
            with urllib.request.urlopen(urllib.request.Request(self.url, headers=AGENT), timeout=300) as r, partial.open("wb") as out:
                while chunk := r.read(1 << 20):
                    out.write(chunk)
            got = (partial.stat().st_size, _md5(partial))
            if got != (self.size, self.md5):
                partial.unlink()
                raise SystemExit(
                    f"{self.url}: expected {self.size} bytes md5 {self.md5}, got {got} -- the "
                    "upstream file changed; re-check its licence before updating the manifest"
                )
            partial.replace(path)
        self._zip = zipfile.ZipFile(path)
        return self

    def names(self) -> list[str]:
        return [n for n in self._zip.namelist() if not n.endswith("/")]

    def read(self, name: str) -> bytes:
        return self._zip.read(name)  # zipfile checks each member's CRC-32


class RemoteZip(Store):
    """Members of a remote zip, fetched by HTTP Range and checked by CRC-32.

    The archive's total size must equal the recorded one, so a republished deposit is
    refused rather than sampled. ZIP64 is handled: several of these are over 4 GB.
    """

    def __init__(self, url: str, size: int) -> None:
        self.url = url
        tail, headers = _http(url, "bytes=-65600")
        total = int(headers["Content-Range"].rsplit("/", 1)[1])
        if total != size:
            raise SystemExit(f"{url}: {total} bytes, the manifest records {size} -- changed upstream")
        i = tail.rfind(b"PK\x05\x06")
        if i < 0:
            raise OSError(f"{url}: no end of central directory")
        entries, cd_size, cd_off = struct.unpack("<HII", tail[i + 10:i + 20])
        j = tail.rfind(b"PK\x06\x07")
        if j >= 0:
            (eocd64,) = struct.unpack("<Q", tail[j + 8:j + 16])
            rec, _ = _http(url, f"bytes={eocd64}-{eocd64 + 55}")
            cd_size, cd_off = struct.unpack("<QQ", rec[40:56])
        cd, _ = _http(url, f"bytes={cd_off}-{cd_off + cd_size - 1}")
        self.members: dict[str, tuple[int, int, int, int]] = {}
        p = 0
        while cd[p:p + 4] == b"PK\x01\x02":
            method, = struct.unpack("<H", cd[p + 10:p + 12])
            crc, csize, usize = struct.unpack("<III", cd[p + 16:p + 28])
            nlen, xlen, clen = struct.unpack("<HHH", cd[p + 28:p + 34])
            off, = struct.unpack("<I", cd[p + 42:p + 46])
            name = cd[p + 46:p + 46 + nlen].decode("utf-8", "replace")
            extra, q = cd[p + 46 + nlen:p + 46 + nlen + xlen], 0
            while q + 4 <= len(extra):
                hid, hlen = struct.unpack("<HH", extra[q:q + 4])
                if hid == 1:  # ZIP64: only the fields that overflowed are present, in order
                    vals, k = extra[q + 4:q + 4 + hlen], 0
                    if usize == 0xFFFFFFFF:
                        usize, = struct.unpack("<Q", vals[k:k + 8]); k += 8
                    if csize == 0xFFFFFFFF:
                        csize, = struct.unpack("<Q", vals[k:k + 8]); k += 8
                    if off == 0xFFFFFFFF:
                        off, = struct.unpack("<Q", vals[k:k + 8])
                q += 4 + hlen
            self.members[name] = (method, crc, csize, off)
            p += 46 + nlen + xlen + clen

    def names(self) -> list[str]:
        return [n for n in self.members if not n.endswith("/") and not n.startswith("__MACOSX")]

    def read(self, name: str) -> bytes:
        method, crc, csize, off = self.members[name]
        head, _ = _http(self.url, f"bytes={off}-{off + 29}")
        nlen, xlen = struct.unpack("<HH", head[26:30])
        start = off + 30 + nlen + xlen
        data = _http(self.url, f"bytes={start}-{start + csize - 1}")[0] if csize else b""
        if method == 8:
            data = zlib.decompress(data, -15)
        elif method != 0:
            raise OSError(f"{name}: compression method {method} is not supported")
        if zlib.crc32(data) & 0xFFFFFFFF != crc:
            raise OSError(f"{name}: CRC-32 mismatch -- not the file the archive lists")
        return data


class NestedZips(Store):
    """Inner zips of a remote zip (OpenITI MAKHZAN packs one zip per document)."""

    def __init__(self, outer: RemoteZip, inner: list[str]) -> None:
        self.zips = {name: zipfile.ZipFile(io.BytesIO(outer.read(name))) for name in inner}

    def names(self) -> list[str]:
        return [f"{z}!{n}" for z, archive in self.zips.items() for n in archive.namelist() if not n.endswith("/")]

    def read(self, name: str) -> bytes:
        z, _, inner = name.partition("!")
        return self.zips[z].read(inner)


class GitHub(Store):
    """Files of a repository at a PINNED commit, each checked against its git blob sha."""

    def __init__(self, repo: str, commit: str, prefix: str) -> None:
        self.repo, self.commit = repo, commit
        tree = json.loads(_http(f"https://api.github.com/repos/{repo}/git/trees/{commit}?recursive=1")[0])
        self.blobs = {
            t["path"]: t["sha"] for t in tree["tree"] if t["type"] == "blob" and t["path"].startswith(prefix)
        }

    def names(self) -> list[str]:
        return list(self.blobs)

    def read(self, name: str) -> bytes:
        url = f"https://raw.githubusercontent.com/{self.repo}/{self.commit}/{urllib.parse.quote(name)}"
        data = _http(url)[0]
        if hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest() != self.blobs[name]:
            raise OSError(f"{name}: git blob sha mismatch")
        return data


@dataclass
class IIIF:
    """Page images from a library's IIIF Image API.

    `resolve(store)` maps an image stem to its full-size image URL -- from a template,
    a table the dataset ships, or the library's manifest. The pixel-size check in
    `fetch_set` is what proves the mapping: an image of another size is another page
    or another scan, and is refused.
    """

    resolve: object  # callable(store) -> dict[stem, url]
    _urls: dict | None = None

    def fetch(self, stem: str, store: Store) -> tuple[bytes, str]:
        if self._urls is None:
            self._urls = self.resolve(store)
        if stem not in self._urls:
            raise OSError("no IIIF image is mapped to this page")
        return _http(self._urls[stem])[0], ".jpg"


def _bulac_ids(store: Store) -> dict[str, str]:
    """Calfa ships `list-images.tsv`: file name -> BULAC BiNA IIIF image id."""
    name = next(n for n in store.names() if n.endswith("/list-images.tsv"))
    rows = store.read(name).decode("utf-8").splitlines()
    header = rows[0].split("\t")
    col_name, col_id = header.index("FileName"), header.index("IIIF image ID")
    return {
        cells[col_name]: f"https://bina.bulac.fr/iiif/2/{cells[col_id]}/full/full/0/default.jpg"
        for cells in (row.split("\t") for row in rows[1:]) if len(cells) > col_id
    }


def _onb_phil_gr_130(store: Store) -> dict[str, str]:
    """ONB Cod. Phil. gr. 130: folio N recto is canvas 2N+12, verso 2N+13.

    The offset was read off the pencilled foliation photographed on canvases 184
    (fol. 86) and 192 (fol. 90); the pixel-size check guards every other page.
    """
    manifest = json.loads(_http("https://api.onb.ac.at/iiif/presentation/v3/manifest/13228923")[0])
    by_label = {}
    for canvas in manifest["items"]:
        body = canvas["items"][0]["items"][0]["body"]
        service = body["service"][0] if isinstance(body["service"], list) else body["service"]
        by_label[next(iter(canvas["label"].values()))[0]] = (service.get("id") or service["@id"]) + "/full/max/0/default.jpg"
    urls = {}
    for n in store.names():
        m = re.search(r"(Phil\.gr\.130_(\d{4})([rv]))\.xml$", n)
        if m:
            label = str(2 * int(m.group(2)) + (12 if m.group(3) == "r" else 13))
            if label in by_label:
                urls[m.group(1)] = by_label[label]
    return urls


# ---------------------------------------------------------------------------
# The manifest
# ---------------------------------------------------------------------------


@dataclass
class Set:
    folder: str  # the subfolder name in the test corpus folder
    language: str
    script: str
    direction: str
    producer: str
    licence: str
    licence_read: str
    source: str
    exercises: str
    xml: object  # a callable returning a Store
    xml_pattern: str = r"\.xml$"
    images: object = None  # None = same store as the XML; an IIIF; or a callable -> Store
    no_images: str = ""  # why there are no images, when there are none
    pages: int = 20
    skip: tuple[str, ...] = (".chocomufin.xml", "METS.xml", "mets.xml", "metadata.xml")
    custom: object = None  # callable(set, pages_dir, report) for a source that is not XML


def _florentine_codex(s: "Set", pages: Path, report: dict) -> None:
    """The Getty's Digital Florentine Codex: Nahuatl and Spanish per folio, with its image.

    No layout exists -- the edition transcribes columns, not lines -- so each folio is
    its image beside a same-stem `.txt` holding the Nahuatl column and the Spanish one.
    Not the #5132 shape; the only page-aligned Nahuatl found anywhere. Walks the
    edition's own next-folio chain from Book 12, fol. 1r (the Conquest).
    """
    book, folio = "12", "1r"
    while report["pages"] < s.pages and folio:
        stem = f"Florentine_Codex_book{book}_{folio}"
        html = _http(f"https://florentinecodex.getty.edu/book/{book}/folio/{folio}")[0].decode("utf-8")
        blob = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
        data = json.loads(blob.group(1))["props"]["pageProps"]["data"]
        texts = data["texts"]
        # Each column holds a transcription AND an English translation; only the
        # transcriptions are what the page says.
        text = "\n\n".join(
            f"=== {label} {t.get('subtitle', '')} ===\n\n{t.get('markdown') or ''}"
            for label, col in (("Nahuatl", "nahuatl_col"), ("Spanish", "spanish_col"))
            for t in texts.get(col) or [] if t.get("type") == "transcription"
        )
        if not (pages / f"{stem}.jpg").exists():
            image = _http(data["iiif_urls"]["full"])[0]
            info = json.loads(_http(data["iiif_urls"]["info_json"])[0])
            if image_size(image) != (info["width"], info["height"]):
                raise OSError(f"{stem}: image is {image_size(image)}, IIIF says {info['width']}x{info['height']}")
            (pages / f"{stem}.jpg").write_bytes(image)
        (pages / f"{stem}.txt").write_text(text, encoding="utf-8")
        report["pages"] += 1
        report["with_image"] += 1
        print(f"  {stem} with image")
        nxt = data["navigation"].get("next") or {}
        book, folio = nxt.get("book"), nxt.get("folio")


ZENODO = "https://zenodo.org/records/{}/files/{}?download=1"


def _tesseract_hocr(pages: Path, report: dict) -> None:
    """hocr-tools' `tess.hocr` beside the scan it names (`alice_1.png`)."""
    repo = GitHub("ocropus/hocr-tools", "c093088da0863cfe5242c0d79a4ac067c991c192", "test/testdata/")
    (pages / "alice_1.hocr").write_bytes(repo.read("test/testdata/tess.hocr"))
    image = repo.read("test/testdata/alice_1.png")
    if image_size(image) != (2488, 3507):  # the hOCR page's own bbox
        raise OSError(f"alice_1.png is {image_size(image)}, the hOCR bbox says 2488x3507")
    (pages / "alice_1.png").write_bytes(image)
    report["pages"], report["with_image"] = 1, 1


def _makhzan(*docs: str):
    def store():
        outer = RemoteZip(ZENODO.format(19861912, "OpenITI-Makhzan_Data_2026-1-2.zip"), 6109859716)
        return NestedZips(outer, [f"Doc{d}.zip" for d in docs])
    return store


MAKHZAN_LICENCE = dict(
    licence="CC-BY-NC-SA-4.0 (NonCommercial: personal research use only)",
    licence_read="Zenodo record 19861912, licence field",
    source="OpenITI MAKHZAN, https://doi.org/10.5281/zenodo.19861912",
    producer="eScriptorium (OpenITI), ALTO 4",
)

SETS: dict[str, Set] = {
    "syriac-onb-syr1": Set(
        folder="Syriac - Vienna Cod. Syr. 1 (right-to-left)",
        language="Syriac", script="Syriac (Serto)", direction="right-to-left",
        producer="eScriptorium, PAGE 2019", licence="CC-BY-4.0",
        licence_read="Zenodo record 14714089 licence field (GitHub mirror says CC-BY-SA-4.0)",
        source="HTR Winter School 2024, https://doi.org/10.5281/zenodo.14714089",
        exercises="a right-to-left manuscript that never states its direction",
        xml=lambda: Archive(ZENODO.format(14714089, "page.zip"), 1113171, "1e06e5814a3c08daf4e9158289231dc1"),
        images=lambda: RemoteZip(ZENODO.format(14714089, "images.zip"), 468604566),
    ),
    "syriac-smmj36-page": Set(
        folder="Syriac - Jerusalem MS 36, Transkribus PAGE (right-to-left)",
        language="Syriac", script="Syriac", direction="right-to-left",
        producer="Transkribus export of eScriptorium work, PAGE 2013", licence="CC-BY-4.0",
        licence_read="Zenodo record 18157525 licence field",
        source="HTR Winter School 2025, https://doi.org/10.5281/zenodo.18157525",
        exercises="PAGE 2013 with TranskribusMetadata; a dummy region with no Coords (#5130)",
        xml=lambda: Archive(ZENODO.format(18157525, "page.zip"), 2457701, "b88c33b0dd0117db0f88b24e5e26cb6e"),
        images=lambda: RemoteZip(ZENODO.format(18157525, "images.zip"), 970176428), pages=12,
    ),
    "syriac-smmj36-alto": Set(
        folder="Syriac - Jerusalem MS 36, eScriptorium ALTO (right-to-left)",
        language="Syriac", script="Syriac", direction="right-to-left",
        producer="eScriptorium, ALTO 4", licence="CC-BY-4.0",
        licence_read="Zenodo record 18157525 licence field",
        source="HTR Winter School 2025, https://doi.org/10.5281/zenodo.18157525",
        exercises="the SAME pages as the PAGE folder, from a different producer and format",
        xml=lambda: Archive(ZENODO.format(18157525, "alto.zip"), 2618558, "1d0e3430e8fd96f921c603e1d728c10f"),
        images=lambda: RemoteZip(ZENODO.format(18157525, "images.zip"), 970176428), pages=12,
    ),
    "biblia-hebrew": Set(
        folder="Hebrew - BiblIA medieval Bibles (right-to-left)",
        language="Hebrew (Biblical, medieval)", script="Hebrew (Ashkenazi, Italian, Sephardi hands)",
        direction="right-to-left", producer="eScriptorium + Kraken, ALTO 4",
        licence="CC-BY-NC-SA-4.0 (NonCommercial: personal research use only)",
        licence_read="Zenodo record 5167263 licence field (HTR-United's catalogue says CC-BY-SA; the record governs)",
        source="BiblIA, https://doi.org/10.5281/zenodo.5167263",
        exercises="Hebrew (and Aramaic Targum) with Title, Main and Commentary zones, three regional hands; no Latin",
        xml=lambda: RemoteZip(ZENODO.format(5167263, "BiblIA_dataset.zip"), 546198414), pages=18,
    ),
    "makhzan-persian": Set(
        folder="Persian - nastaliq manuscripts (right-to-left, with English on the page)",
        language="Persian", script="Arabic (nastaliq)", direction="right-to-left",
        exercises="nastaliq's sloping baselines; Doc 136 carries English and Western digits ('Herbert LLoyd', '1773') beside the Persian -- mixed direction on one page",
        xml=_makhzan("136", "2299", "47", "79"), **MAKHZAN_LICENCE,
    ),
    "makhzan-ottoman": Set(
        folder="Ottoman Turkish (right-to-left)",
        language="Ottoman Turkish", script="Arabic (naskh)", direction="right-to-left",
        exercises="Ottoman Turkish print and manuscript", xml=_makhzan("2939"), **MAKHZAN_LICENCE,
    ),
    "makhzan-urdu": Set(
        folder="Urdu (right-to-left)",
        language="Urdu", script="Arabic (nastaliq)", direction="right-to-left",
        exercises="Urdu nastaliq print with commentary margins", xml=_makhzan("7751", "7219"), **MAKHZAN_LICENCE,
    ),
    "makhzan-interlinear": Set(
        folder="Arabic with interlinear Persian (right-to-left, two hands)",
        language="Arabic, Persian", script="Arabic (naskh with nastaliq interlinear)", direction="right-to-left",
        exercises="two scripts interleaved line by line -- several readings per page area",
        xml=_makhzan("1461"), **MAKHZAN_LICENCE,
    ),
    "makhzan-jawi": Set(
        folder="Malay in Jawi script (right-to-left)",
        language="Malay", script="Arabic (Jawi)", direction="right-to-left",
        exercises="a non-Arabic language in Arabic script", xml=_makhzan("3355", "3357"), **MAKHZAN_LICENCE,
    ),
    "irhas-aljamiado": Set(
        folder="Aljamiado - Spanish in Arabic script (right-to-left)",
        language="Old Spanish / Aragonese", script="Arabic (Aljamiado)", direction="right-to-left",
        producer="eScriptorium, ALTO 4", licence="CC-BY-NC-SA-4.0 (NonCommercial: personal research use only)",
        licence_read="Zenodo record 21824878 licence field (API license.id)",
        source="IRHAS, https://doi.org/10.5281/zenodo.21824878",
        exercises="a Romance language written right to left: the direction belongs to the script, not the language",
        xml=lambda: RemoteZip(ZENODO.format(21824878, "IRHAS_v.1_zenodo.zip"), 5662405552),
        xml_pattern=r"madrid-bne-mss-530[12]/.*\.xml$", skip=(), pages=16,
    ),
    "greek-phil-gr-130": Set(
        folder="Greek - polytonic, Vienna Phil. gr. 130",
        language="Ancient/medieval Greek", script="Greek (polytonic)", direction="left-to-right",
        producer="Transkribus, PAGE 2013",
        licence="CC-BY-SA-4.0 (ground truth); images: Austrian National Library, attribution required",
        licence_read="Zenodo record 20705757 licence field; ONB IIIF manifest requiredStatement",
        source="https://doi.org/10.5281/zenodo.20705757; images https://viewer.onb.ac.at/13228923",
        exercises="breathings and accents; images from the library's IIIF server, not the dataset. "
        "(The same deposit's Vat. gr. 2228 pages are NOT here: DigiVatLib serves a 1552x2210 scan "
        "and the XML was drawn on 2174x2996, a different image.)",
        xml=lambda: Archive(ZENODO.format(20705757, "dataset.zip"), 892881, "e6637a2da8d2b33b8e8bafa80201c950"),
        xml_pattern=r"phil_gr_130/.*\.xml$", images=IIIF(_onb_phil_gr_130),
    ),
    "pracalit-newa": Set(
        folder="Newa - Pracalit script, Sanskrit and Newar",
        language="Sanskrit, Newar", script="Newa (Pracalit), outside the BMP", direction="left-to-right",
        producer="Transkribus (CITlab), PAGE 2013", licence="CC-BY-4.0",
        licence_read="Zenodo record 6967421 licence field",
        source="https://doi.org/10.5281/zenodo.6967421",
        exercises="a Brahmic script whose code points need surrogate pairs in UTF-16",
        xml=lambda: RemoteZip(ZENODO.format(6967421, "export_job_3435367.zip"), 503947549),
        xml_pattern=r"/page/MS B Vetala.*\.xml$",
    ),
    "devanagari-diksita1895": Set(
        folder="Hindi - Devanagari print",
        language="Hindi / Braj", script="Devanagari", direction="left-to-right",
        producer="Transkribus, ALTO 4", licence="CC-BY-4.0",
        licence_read="heiDATA doi:10.11588/data/EGOKEI, dataset licence field",
        source="https://doi.org/10.11588/data/EGOKEI",
        exercises="Devanagari conjuncts; Transkribus's ALTO rather than eScriptorium's",
        xml=lambda: Archive("https://heidata.uni-heidelberg.de/api/access/datafile/7316", 3058611, "c3f5ea8ef80a5f18897fc503adff105e"),
    ),
    "malayalam-telisseri": Set(
        folder="Malayalam - Tellicherry records",
        language="Malayalam", script="Malayalam", direction="left-to-right",
        producer="Transkribus, ALTO 4", licence="CC-BY-4.0",
        licence_read="heiDATA doi:10.11588/data/L2KRZO, dataset licence field",
        source="https://doi.org/10.11588/data/L2KRZO",
        exercises="a Dravidian script, colonial correspondence with Latin numerals embedded",
        xml=lambda: Archive("https://heidata.uni-heidelberg.de/api/access/datafile/11744", 6872981, "a5eabde1cb44fb2ad2be83228e534b41"),
    ),
    "cremma-latin": Set(
        folder="Medieval Latin (MUFI) - Clm 13027",
        language="Medieval Latin", script="Latin, with MUFI private-use characters", direction="left-to-right",
        producer="eScriptorium, ALTO 4", licence="CC-BY-4.0",
        licence_read="repository htr-united.yml license block",
        source="https://github.com/HTR-United/CREMMA-Medieval-LAT",
        exercises="private-use-area abbreviation glyphs (U+F1AC)",
        xml=lambda: GitHub("HTR-United/CREMMA-Medieval-LAT", "292525969ad98380b398e6606a9c2a36d51913ae", "data/CLM13027/"),
        pages=12,
    ),
    "cremma-oldfrench": Set(
        folder="Old French - BnF fr. 412",
        language="Old French", script="Latin (Gothic bookhand)", direction="left-to-right",
        producer="eScriptorium, ALTO 4", licence="CC-BY-4.0",
        licence_read="repository htr-united.yml and README",
        source="https://github.com/HTR-United/cremma-medieval",
        exercises="two columns, marginal zones, drop capitals",
        xml=lambda: GitHub("HTR-United/cremma-medieval", "bc4a105f6e8316a9b30d9ce5d98dda2ba947d7d4", "data/bnf_fr_412-wauchier/"),
        pages=12,
    ),
    "htrogene-occitan": Set(
        folder="Old Occitan - Roman de Flamenca",
        language="Old Occitan", script="Latin", direction="left-to-right",
        producer="eScriptorium, ALTO 4", licence="CC-BY-4.0",
        licence_read="repository htr-united.yml and README",
        source="https://github.com/HTRogene/occitan",
        exercises="UUID line ids that are not valid xsd:IDs",
        xml=lambda: GitHub("HTRogene/occitan", "9983c1bb41e1d0e7f179b90352ebbaeec79b1ecb", "data/carcassonne-34/"),
        pages=12,
    ),
    "htrogene-spanish": Set(
        folder="Medieval Spanish - BnF Espagnol 33",
        language="Medieval Castilian", script="Latin", direction="left-to-right",
        producer="eScriptorium, ALTO 4", licence="CC-BY-4.0",
        licence_read="repository htr-united.yml and README",
        source="https://github.com/HTRogene/spanish",
        exercises="medieval Spanish manuscript with SegmOnto zones",
        xml=lambda: GitHub("HTRogene/spanish", "febc846c3d54bd1465c61e78fbdaa28529cd9178", "data/paris-bnf-esp-33/"),
        pages=12,
    ),
    "endp-registers": Set(
        folder="Latin and French - Notre-Dame chapter registers (marginalia)",
        language="Medieval Latin, Middle French", script="Latin (cursive)", direction="left-to-right",
        producer="PAGE XML (e-NDP)", licence="CC-BY-4.0",
        licence_read="Zenodo record 7575693 licence field",
        source="e-NDP, https://doi.org/10.5281/zenodo.7575693",
        exercises="marginal entries beside the main frame; split page images (Left/Right/Main frame)",
        xml=lambda: RemoteZip(ZENODO.format(7575693, "e-NDP_dataset.zip"), 913791912),
        xml_pattern=r"page_xml/.*\.xml$", pages=16,
    ),
    "chi-know-po": Set(
        folder="Chinese - classical, vertical columns",
        language="Classical Chinese", script="Han (traditional)", direction="top-to-bottom, columns right to left",
        producer="Calfa, PAGE 2013", licence="CC-BY-4.0",
        licence_read="Zenodo record 14452717 licence field (the GitHub copy of the XML is Apache-2.0)",
        source="CHI-KNOW-PO, https://doi.org/10.5281/zenodo.14452717",
        exercises="vertical text the file never states as vertical",
        xml=lambda: RemoteZip(ZENODO.format(14452717, "GT-chiknowpo.zip"), 1352988053),
        xml_pattern=r"^BULAC_BIULO_CHI_1087_1_.*\.xml$",
    ),
    "rasam-arabic": Set(
        folder="Arabic - Maghrebi manuscripts (right-to-left)",
        language="Arabic", script="Arabic (Maghrebi)", direction="right-to-left",
        producer="Calfa, PAGE 2013", licence="Apache-2.0 (ground truth); images: BULAC, public domain",
        licence_read="repository LICENSE (GitHub licence API); BiNA record ark:/73193/b2bw1q says 'Domaine public'",
        source="https://github.com/calfa-co/rasam-dataset; images https://bina.bulac.fr",
        exercises="baseline-only lines with empty polygons (#5130); images via the dataset's own IIIF table",
        xml=lambda: Archive("https://codeload.github.com/calfa-co/rasam-dataset/zip/c670eb6e6b3292899873d8b98c6575b8defce96f", 10104489, "4087f30cfed3f701421ccf5b564d9531"),
        xml_pattern=r"page/rasam1/BULAC_MS_ARA_417_.*\.xml$", images=IIIF(_bulac_ids), pages=16,
    ),
    "florentine-nahuatl": Set(
        folder="Nahuatl - Florentine Codex, Book 12 (transcription beside image, no layout)",
        language="Nahuatl (Classical), with Spanish", script="Latin", direction="left-to-right",
        producer="Getty Research Institute, Digital Florentine Codex (edition text, not HTR)",
        licence="CC BY-NC-ND 4.0 (NonCommercial, NoDerivatives: personal research use only)",
        licence_read="the IIIF manifest's requiredStatement (Biblioteca Medicea Laurenziana, Firenze)",
        source="https://florentinecodex.getty.edu",
        exercises="an Indigenous language of the Americas, page-aligned; two languages in two columns",
        xml=None, custom=_florentine_codex, pages=16,
    ),
    "kraken-spanish-notarial": Set(
        folder="Spanish - early modern notarial register (Transkribus)",
        language="Spanish (early modern), Catalan", script="Latin", direction="left-to-right",
        producer="Transkribus (TRP), PAGE 2013", licence="Apache-2.0",
        licence_read="kraken repository LICENSE (GitHub licence API)",
        source="https://github.com/mittagessen/kraken/tree/main/tests/resources",
        exercises="the transcribers' inline abbreviation tags ($ofi:, dho$.dicho); text on regions and lines",
        xml=lambda: GitHub("mittagessen/kraken", "0d07314ba0e6fa31d786bf3f88b20dd93597f591", "tests/resources/170025120000003,0074"),
        xml_pattern=r"0074\.xml$", pages=1,
    ),
    "tesseract-hocr": Set(
        folder="English - Tesseract hOCR",
        language="English", script="Latin", direction="left-to-right",
        producer="tesseract 3.03, hOCR", licence="Apache-2.0",
        licence_read="hocr-tools LICENSE file",
        source="https://github.com/ocropus/hocr-tools/tree/master/test/testdata",
        exercises="real engine hOCR: areas, paragraphs, lines, words with bbox and x_wconf",
        xml=None, custom=lambda s, pages, report: _tesseract_hocr(pages, report), pages=1,
    ),
    "cree-syllabics": Set(
        folder="Cree - handwritten syllabics (Tesseract box files, no XML)",
        language="Cree", script="Canadian Aboriginal Syllabics", direction="left-to-right",
        producer="Tesseract .box files (one line per character: glyph and box, origin bottom-left)",
        licence="CC-BY-4.0", licence_read="Zenodo record 6915296 licence field",
        source="Handwritten Cree Syllabics, https://doi.org/10.5281/zenodo.6915296",
        exercises="an Indigenous syllabary of the Americas; character boxes, no lines or regions. "
        "Not PAGE/ALTO: the image imports, the .box file does not pair (yet)",
        xml=lambda: RemoteZip(ZENODO.format(6915296, "GHSam/handwritten-Cree-v1.0.0.zip"), 218204819),
        xml_pattern=r"samples/.*\.box$", pages=16,
    ),
    "pagantibet-tibetan": Set(
        folder="Tibetan - layout only (Transkribus TEI)",
        language="Tibetan", script="Tibetan", direction="left-to-right",
        producer="Transkribus, TEI", licence="CC-BY-SA-4.0",
        licence_read="Zenodo record 19205598 licence field",
        source="PaganTibet, https://doi.org/10.5281/zenodo.19205598",
        exercises="66 pages in one TEI file; xml:ids that are image file names (#5130)",
        xml=None, pages=1,
        no_images="the deposit holds layout XML only; its images are not published",
    ),
}
# The Tibetan TEI is a single file, not an archive: fetched by `_single`.
SINGLE = {"pagantibet-tibetan": (ZENODO.format(19205598, "Manual1-20230809_GT_layout.xml"), 165473, "48334278b49dab19c8326faa7a00778d")}


# ---------------------------------------------------------------------------
# Pairing: every XML beside the image it names, under the image's stem
# ---------------------------------------------------------------------------

_IMAGE_REF = (
    re.compile(rb'imageFilename="([^"]+)"'),  # PAGE
    re.compile(rb"<fileName>([^<]+)</fileName>"),  # ALTO
)


def image_named_by(xml: bytes) -> str | None:
    head = xml[:20000]
    for pattern in _IMAGE_REF:
        m = pattern.search(head)
        if m:
            return m.group(1).decode("utf-8", "replace").strip().replace("\\", "/").rsplit("/", 1)[-1]
    return None


def image_size(data: bytes) -> tuple[int, int] | None:
    """(width, height) from a JPEG SOF or PNG IHDR header, without decoding."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return struct.unpack(">II", data[16:24])
    if data[:2] == b"\xff\xd8":
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                h, w = struct.unpack(">HH", data[i + 5:i + 9])
                return w, h
            i += 2 + struct.unpack(">H", data[i + 2:i + 4])[0]
    return None


def stated_size(xml: bytes) -> tuple[int, int] | None:
    m = re.search(rb'imageWidth="(\d+)"\s+imageHeight="(\d+)"', xml[:20000]) or re.search(
        rb'<Page[^>]*?HEIGHT="(\d+)"[^>]*?WIDTH="(\d+)"', xml[:20000]
    )
    if not m:
        return None
    a, b = int(m.group(1)), int(m.group(2))
    return (a, b) if b"imageWidth" in m.group(0) else (b, a)


def fetch_set(key: str, s: Set) -> dict:
    folder = DEST / key
    pages = folder / "pages"
    pages.mkdir(parents=True, exist_ok=True)
    print(f"{key}: {s.folder}")
    report = {"key": key, "pages": 0, "with_image": 0, "missing": []}

    if s.custom:
        s.custom(s, pages, report)
        return _save(folder, report)

    if key in SINGLE:
        url, size, md5 = SINGLE[key]
        path = pages / "Manual1-20230809_GT_layout.tei.xml"
        if not (path.exists() and _md5(path) == md5):
            data = _http(url)[0]
            if (len(data), hashlib.md5(data).hexdigest()) != (size, md5):
                raise SystemExit(f"{url}: changed upstream")
            path.write_bytes(data)
        report["pages"] = 1
        report["missing"].append(s.no_images)
        return _save(folder, report)

    store = s.xml()
    if isinstance(store, Archive):
        store.open(folder)
    images = s.images() if callable(s.images) else s.images
    image_index: dict[str, str] = {}
    for name in (images if isinstance(images, Store) else store).names():
        if name.lower().endswith(IMAGE_EXTS):
            image_index.setdefault(name.rsplit("/", 1)[-1].rsplit("!", 1)[-1], name)

    candidates = sorted(
        n for n in store.names()
        if re.search(s.xml_pattern, n) and not any(n.endswith(x) or n.rsplit("/", 1)[-1] == x for x in s.skip)
    )
    seen: set[str] = set()
    for name in candidates:
        if report["pages"] >= s.pages:
            break
        xml = store.read(name)
        suffix = "." + name.rsplit(".", 1)[-1].lower()
        if suffix == ".xml" and b"PcGts" not in xml[:3000] and b"<alto" not in xml[:3000]:
            continue
        ref = image_named_by(xml)
        stem = (ref.rsplit(".", 1)[0] if ref else name.rsplit("/", 1)[-1].rsplit(".", 1)[0])
        if stem in seen:  # a second XML for the same image (an export with alto/ AND page/)
            continue
        seen.add(stem)
        if (pages / f"{stem}{suffix}").exists():
            report["pages"] += 1
            report["with_image"] += any((pages / f"{stem}{e}").exists() for e in IMAGE_EXTS)
            continue
        image, ext = None, ""
        # The image the XML names; failing that (an ALTO with no <fileName>), the image
        # with the XML's own stem, which is how Transkribus's ALTO export pairs them.
        found = image_index.get(ref or "") or next(
            (image_index[stem + e] for e in (".jpg", ".jpeg", ".png", ".tif", ".JPG") if stem + e in image_index), None
        )
        if s.no_images:
            pass
        elif isinstance(images, IIIF):
            try:
                image, ext = images.fetch(stem, store)
            except OSError as exc:
                report["missing"].append(f"{stem}: IIIF {exc}")
        elif found:
            image = (images if isinstance(images, Store) else store).read(found)
            ext = "." + found.rsplit(".", 1)[-1].lower()
        else:
            report["missing"].append(f"{stem}: the XML names {ref!r}, which the source does not hold")
        if image is not None:
            want, got = stated_size(xml), image_size(image)
            if want and got and want != got:
                # Not the image the regions were drawn on (a different scan or crop):
                # pairing it would put every region in the wrong place. Say so, once,
                # and stop fetching images for this set.
                report["missing"].append(
                    f"{stem}: the source's image is {got[0]}x{got[1]} and the XML was drawn on "
                    f"{want[0]}x{want[1]} -- a different scan, so no image is paired"
                )
                s.no_images = s.no_images or "the available images are a different scan from the one the XML was drawn on"
                image = None
        if image is not None:
            (pages / f"{stem}{ext}").write_bytes(image)
            report["with_image"] += 1
        (pages / f"{stem}{suffix}").write_bytes(xml)
        report["pages"] += 1
        print(f"  {stem} {'with image' if image is not None else 'XML only'}")
    if s.no_images:
        report["missing"].append(s.no_images)
    return _save(folder, report)


def _save(folder: Path, report: dict) -> dict:
    (folder / "SET.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def _md5(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        while chunk := handle.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("names", nargs="*", help="set keys (default: all)")
    parser.add_argument("--list", action="store_true", help="show the manifest and exit")
    args = parser.parse_args(argv)
    if args.list:
        for key, s in SETS.items():
            print(f"{key:<24} {s.direction:<14} {s.licence[:28]:<28} {s.folder}")
        return 0
    unknown = [n for n in args.names if n not in SETS]
    if unknown:
        print(f"not in the manifest: {unknown}; see --list", file=sys.stderr)
        return 2
    failed = []
    for key in args.names or SETS:
        try:
            r = fetch_set(key, SETS[key])
            print(f"  -> {r['pages']} pages, {r['with_image']} with images")
        except (OSError, SystemExit) as exc:
            failed.append(key)
            print(f"  FAILED {key}: {exc}", file=sys.stderr)
    print(f"done: {DEST}" + (f"; failed: {failed}" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
