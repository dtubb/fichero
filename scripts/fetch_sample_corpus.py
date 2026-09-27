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


def _github_token() -> str:
    """A GitHub token if one is at hand: the anonymous API allows 60 calls an hour, and
    a run over several GitHub-hosted sets lists a tree per set. `GITHUB_TOKEN`, else
    the `gh` CLI's stored login, else nothing (anonymous still works for a few sets)."""
    import os

    token = os.environ.get("GITHUB_TOKEN", "")
    if not token and shutil.which("gh"):
        done = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True)
        token = done.stdout.strip() if done.returncode == 0 else ""
    return token


_TOKEN: list[str | None] = [None]


def _http(url: str, rng: str | None = None) -> tuple[bytes, dict]:
    headers = dict(AGENT)
    if rng:
        headers["Range"] = rng
    if url.startswith("https://api.github.com/"):
        if _TOKEN[0] is None:
            _TOKEN[0] = _github_token()
        if _TOKEN[0]:
            headers["Authorization"] = f"Bearer {_TOKEN[0]}"
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


class ZenodoFiles(Store):
    """A Zenodo record whose pages are deposited as loose files, not a zip.

    Each file is checked against the size and md5 the record's own API lists; the
    listing itself is pinned by `listing_md5`, the md5 of its sorted "name size
    checksum" lines, so a republished record is refused rather than sampled.
    """

    def __init__(self, record: int, listing_md5: str) -> None:
        self.record = record
        data = json.loads(_http(f"https://zenodo.org/api/records/{record}")[0])
        self.files = {f["key"]: (f["size"], f["checksum"].removeprefix("md5:")) for f in data["files"]}
        lines = sorted(f"{k} {size} md5:{md5}" for k, (size, md5) in self.files.items())
        got = hashlib.md5("\n".join(lines).encode()).hexdigest()
        if got != listing_md5:
            raise SystemExit(f"zenodo {record}: the file listing changed upstream ({got}); re-check its licence")

    def names(self) -> list[str]:
        return list(self.files)

    def read(self, name: str) -> bytes:
        data = _http(ZENODO.format(self.record, urllib.parse.quote(name)))[0]
        size, md5 = self.files[name]
        if (len(data), hashlib.md5(data).hexdigest()) != (size, md5):
            raise OSError(f"{name}: not the bytes the record lists")
        return data


class HuggingFace(Store):
    """Files of a Hugging Face dataset at a PINNED commit.

    The hub lists every file with a git blob sha (small files) or an LFS sha256
    (large ones, which is how the images and most XML are stored); each download is
    checked against whichever it has.
    """

    def __init__(self, repo: str, commit: str, prefix: str) -> None:
        self.repo, self.commit = repo, commit
        listing = json.loads(_http(f"https://huggingface.co/api/datasets/{repo}/tree/{commit}/{prefix.rstrip('/')}?recursive=true")[0])
        self.files = {
            f["path"]: (f.get("lfs") or {}).get("oid") or f["oid"]
            for f in listing if f["type"] == "file" and f["path"].startswith(prefix)
        }

    def names(self) -> list[str]:
        return list(self.files)

    def read(self, name: str) -> bytes:
        data = _http(f"https://huggingface.co/datasets/{self.repo}/resolve/{self.commit}/{urllib.parse.quote(name)}")[0]
        want = self.files[name]
        got = hashlib.sha256(data).hexdigest() if len(want) == 64 else hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()
        if got != want:
            raise OSError(f"{name}: hash mismatch against the hub's listing")
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


def _bdd_urls(store: Store) -> dict[str, str]:
    """Burchards Dekret Digital ships `<sigil>.json`: PAGE file -> the library's IIIF
    URL at the very size the PAGE was drawn on (the images themselves are not in the
    repository, for copyright reasons its README states)."""
    urls = {}
    for name in store.names():
        if name.endswith(".json"):
            for row in json.loads(store.read(name)):
                urls[row["file_name"].rsplit(".", 1)[0]] = row["image_url"]
    return urls


def _reichsanzeiger_urls(store: Store) -> dict[str, str]:
    """`data/imageurls.list`: `<film path> <page>.jpg`, served by Mannheim's image
    server; the base URL is the one `download_images.sh` decodes."""
    base = "https://digi.bib.uni-mannheim.de/reichsanzeiger.fcgi?FIF=/reichsanzeiger/film/"
    urls = {}
    for line in store.read("data/imageurls.list").decode("utf-8").splitlines():
        if line.strip():
            path, name = line.rsplit(" ", 1)
            urls[name.rsplit(".", 1)[0]] = base + path
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
    want: object = None  # callable(xml bytes) -> bool: take only pages that show something
    unit: str = "pixel"  # what the XML's coordinates are in, when not pixels (mm10, inch1200)


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


LOC_NDNP = "https://tile.loc.gov/storage-services/service/ndnp/dlc/batch_dlc_misctopsn83020866_ver03/data/sn83020866/print"
LOC_IIIF = "https://tile.loc.gov/image-services/iiif/service:ndnp:dlc:batch_dlc_misctopsn83020866_ver03:data:sn83020866:print:{issue}:{page}"


def _cherokee_phoenix(s: "Set", pages: Path, report: dict) -> None:
    """The Cherokee Phoenix, 6 March 1828: Cherokee syllabary and English on one page.

    ALTO 2.0 from the Library of Congress's NDNP batch (`ver03`; `ver01`'s OCR read
    the Cherokee columns as Latin garbage), its coordinates in `inch1200` -- 1/1200
    inch, so pixels at the scan's 300 dpi are the value ÷ 4. The image is the batch's
    own scan through the IIIF Image API, at full size; its pixel size must equal the
    ALTO's page size ÷ 4, which is the whole check. `tile.loc.gov` answers plain
    scripts; `www.loc.gov` and `chroniclingamerica.loc.gov` do not.
    """
    issue = "1828030601"
    for page in ("0001", "0002", "0003", "0004")[: s.pages]:
        stem = f"cherokee-phoenix_{issue}_{page}"
        if (pages / f"{stem}.xml").exists() and (pages / f"{stem}.jpg").exists():
            report["pages"] += 1
            report["with_image"] += 1
            continue
        xml = _http(f"{LOC_NDNP}/{issue}/{page}.xml")[0]
        m = re.search(rb'<Page [^>]*?HEIGHT="(\d+)"[^>]*?WIDTH="(\d+)"', xml)
        want = (int(m.group(2)) // 4, int(m.group(1)) // 4)
        info = json.loads(_http(LOC_IIIF.format(issue=issue, page=page) + "/info.json")[0])
        if (info["width"], info["height"]) != want:
            raise OSError(f"{stem}: IIIF says {info['width']}x{info['height']}, the ALTO {want} at 300 dpi")
        image = _http(LOC_IIIF.format(issue=issue, page=page) + "/full/full/0/default.jpg")[0]
        if image_size(image) != want:
            raise OSError(f"{stem}: the full image is {image_size(image)}, expected {want}")
        (pages / f"{stem}.jpg").write_bytes(image)
        (pages / f"{stem}.xml").write_bytes(xml)
        report["pages"] += 1
        report["with_image"] += 1
        print(f"  {stem} with image")


def _genji_tei(s: "Set", pages: Path, report: dict) -> None:
    """Kōi Genji monogatari (Ikeda Kikan's 1942 variorum), chapter 1 Kiritsubo: one
    TEI file whose `<facsimile>` maps every page to a zone on the National Diet
    Library's IIIF scans (each canvas is a two-page spread, and each zone half of
    it). The TEI is written once, under the chapter's name; the first `pages`
    spreads it points at are fetched beside it, each checked against the pixel
    size the `<graphic>` states. The TEI names IIIF URLs, not files, so the images
    sit beside it by proximity, not by name.
    """
    repo = GitHub("kouigenjimonogatari/kouigenjimonogatari.github.io", "89a60fe7b18c1eebb91f160c068b31e857776022", "xml/master/01.xml")
    tei = repo.read("xml/master/01.xml")
    (pages / "kouigenji-01-kiritsubo.tei.xml").write_bytes(tei)
    graphics = re.findall(rb'<graphic height="(\d+)px" sameAs="([^"]+)" url="([^"]+)" width="(\d+)px"/>', tei)
    for height, image_id, url, width in graphics[: s.pages]:
        stem = image_id.decode().rsplit("/", 1)[-1]
        if not (pages / f"{stem}.jpg").exists():
            image = _http(url.decode())[0]
            if image_size(image) != (int(width), int(height)):
                raise OSError(f"{stem}: image is {image_size(image)}, the TEI says {width}x{height}")
            (pages / f"{stem}.jpg").write_bytes(image)
        report["pages"] += 1
        report["with_image"] += 1
        print(f"  {stem} with image")


def _yolo_pages(store_factory, prefix: str, classes: str, names_key: str = "names"):
    """YALTAi's layout: `<split>/images/X.jpg`, `<split>/labels/X.txt` (YOLO boxes)
    and `<split>/labels/X.xml` (the ALTO the boxes were cut from). All three go
    beside each other under X, and the class list beside them as `classes.txt`,
    read from the dataset's own YAML (`names: [...]` or one name per line)."""

    def fetch(s: "Set", pages: Path, report: dict) -> None:
        store = store_factory()
        names = store.names()
        text = store.read(classes).decode("utf-8")
        m = re.search(r"names:\s*\[([^\]]*)\]", text)
        labels = [x.strip().strip("'\"") for x in m.group(1).split(",")] if m else [
            x.strip().lstrip("- ").strip() for x in text.splitlines() if x.strip() and not x.startswith(("train", "val", "nc"))
        ]
        (pages / "classes.txt").write_text("\n".join(labels) + "\n", encoding="utf-8")
        images = sorted(n for n in names if n.startswith(prefix + "/images/") and n.lower().endswith(IMAGE_EXTS))
        for name in images:
            if report["pages"] >= s.pages:
                break
            stem = name.rsplit("/", 1)[-1].rsplit(".", 1)[0]
            label, alto = f"{prefix}/labels/{stem}.txt", f"{prefix}/labels/{stem}.xml"
            if label not in names:
                continue
            if not (pages / f"{stem}.txt").exists():
                image = store.read(name)
                xml = store.read(alto) if alto in names else None
                want = stated_size(xml) if xml else None
                if want and image_size(image) != want:
                    raise OSError(f"{stem}: image is {image_size(image)}, the ALTO says {want}")
                (pages / name.rsplit("/", 1)[-1]).write_bytes(image)
                (pages / f"{stem}.txt").write_bytes(store.read(label))
                if xml:
                    (pages / f"{stem}.xml").write_bytes(xml)
            report["pages"] += 1
            report["with_image"] += 1
            print(f"  {stem} with image, YOLO labels{' and ALTO' if alto in names else ''}")

    return fetch


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
    # --- the world-corpus round: striking pages, one per script, shape or continent ---
    "zenon-papyri": Set(
        folder="Greek papyri - Zenon archive, 3rd century BCE",
        language="Ancient Greek (Ptolemaic documentary)", script="Greek (papyrus cursive)", direction="left-to-right",
        producer="Transkribus, PAGE 2013 (D-Scribes, Basel)", licence="CC-BY-4.0",
        licence_read="Zenodo record 6565706 licence field",
        source="Ground-Truthed Data Set of Zenon Papyri, https://zenodo.org/records/6565706",
        exercises="a papyrus fragment with image-aligned lines: the oldest writing in the library, "
        "on a torn irregular support with damaged edges",
        xml=lambda: ZenodoFiles(6565706, "279d95aab7533ee34df01b9b9dd47197"), pages=44,
    ),
    "cherokee-phoenix": Set(
        folder="Cherokee and English - Cherokee Phoenix newspaper, 1828 (ALTO 2, inch1200)",
        language="Cherokee, English", script="Cherokee syllabary and Latin, on one page", direction="left-to-right",
        producer="CCS docWizz / ABBYY FineReader 8.1 machine OCR (NDNP), ALTO 2.0, MeasurementUnit inch1200",
        licence="Public domain (Library of Congress, Chronicling America: published 1828, over 95 years ago)",
        licence_read="Chronicling America rights and access page, "
        "https://www.loc.gov/collections/chronicling-america/about-this-collection/rights-and-access/, read "
        "2026-09-27 in a browser (the page refuses scripted reads): \"Newspapers published in the United States "
        "more than 95 years ago are in the public domain in their entirety.\" The Phoenix is from 1828.",
        source="https://tile.loc.gov/storage-services/service/ndnp/dlc/batch_dlc_misctopsn83020866_ver03/",
        exercises="a syllabary of the Americas beside English on the same page (TextBlock language=\"chr\" / \"eng\"); "
        "coordinates in 1/1200 inch, not pixels; machine OCR at a stated ~90%, not hand-corrected",
        xml=None, custom=_cherokee_phoenix, pages=4, unit="inch1200",
    ),
    "ajami-fulfulde": Set(
        folder="Fulfulde in Arabic script (Ajami) - West African manuscript (right-to-left)",
        language="Fulfulde (Pular), with Arabic", script="Arabic (Ajami)", direction="right-to-left",
        producer="eScriptorium, ALTO 4 (manual transcription; the sibling folders are model outputs and are not taken)",
        licence="CC-BY-4.0", licence_read="Zenodo record 20392539 licence field",
        source="Ajami Handwritten Text Recognition Dataset, https://zenodo.org/records/20392539 (Fulfulde.zip)",
        exercises="an African language in Arabic script, hand-drawn polygons; the only sub-Saharan set",
        xml=lambda: RemoteZip(ZENODO.format(20392539, "Fulfulde.zip"), 2583380633),
        xml_pattern=r"ELIT_WAN_00130/manual/.*\.xml$", pages=8,
    ),
    "armenian-nomos": Set(
        folder="Classical Armenian - BnF Arménien 172 (Hugging Face)",
        language="Classical Armenian (Grabar)", script="Armenian (bolorgir)", direction="left-to-right",
        producer="eScriptorium, PAGE 2019 (NOMOS project, LMU)",
        licence="CC-BY-4.0 (transcriptions and geometry); images: Gallica terms, non-commercial reuse free with the "
        "credit 'Source gallica.bnf.fr / Bibliothèque nationale de France' -- personal research use only",
        licence_read="the dataset's LICENSE.md on the Hub (two regimes, quoted there)",
        source="https://huggingface.co/datasets/nomikos-project/armenian-manuscript-htr",
        exercises="the Armenian alphabet; a dataset fetched from the Hugging Face hub with per-file LFS sha256 checks",
        xml=lambda: HuggingFace("nomikos-project/armenian-manuscript-htr", "a52076040c69c3dcbb6a7e86ef09e8b7ebccb8b4", "page-xml/bnf-armenien-172/"),
        images=lambda: HuggingFace("nomikos-project/armenian-manuscript-htr", "a52076040c69c3dcbb6a7e86ef09e8b7ebccb8b4", "images/bnf-armenien-172/"),
        pages=8,
    ),
    "genji-tei": Set(
        folder="Japanese - Tale of Genji, 1942 variorum, vertical print (TEI facsimile over NDL IIIF)",
        language="Classical Japanese", script="Japanese (kanji and kana), vertical, columns right to left", direction="top-to-bottom",
        producer="hand-encoded TEI P5 with <facsimile>/<surface>/<zone> (Digital Genji Monogatari, Tokyo)",
        licence="CC0-1.0 (TEI, stated in the teiHeader <availability> and the repository); images: Public Domain Mark "
        "('Access Restrictions = PDM' in the NDL IIIF manifest), attribution National Diet Library",
        licence_read="teiHeader of xml/master/01.xml; GitHub licence API CC-BY-4.0 for the repository; NDL manifest 3437686 metadata",
        source="https://github.com/kouigenjimonogatari/kouigenjimonogatari.github.io; images https://dl.ndl.go.jp/pid/3437686",
        exercises="vertical typeset Japanese from the most famous work in the language; one TEI for a whole chapter, "
        "zones are half-spreads (page level, not lines); the TEI names IIIF URLs, so images pair by proximity only",
        xml=None, custom=_genji_tei, pages=6,
    ),
    "yaltai-segmonto": Set(
        folder="YOLO layout - YALTAi SegmOnto, medieval manuscripts and early print (labels beside ALTO)",
        language="Latin, Old and Middle French, others", script="Latin (manuscript and early print)", direction="left-to-right",
        producer="YALTAi (Kraken/eScriptorium ALTO converted to YOLOv5 boxes), classes = SegmOnto zones",
        licence="CC-BY-4.0", licence_read="Zenodo record 6814770 licence field",
        source="YALTAi: Segmonto Manuscript and Early Printed Book Dataset, https://zenodo.org/records/6814770 (2.8 GB, sampled by HTTP Range)",
        exercises="a real YOLO case: `class cx cy w h` per zone, with `classes.txt` (DropCapitalZone, GraphicZone, MainZone, "
        "MarginTextZone...) and the ALTO the boxes came from beside each image. Class numbers here are ZONE TYPES, not the "
        "region/line/word granularity our YOLO reader assumes",
        xml=None, pages=8,
        custom=_yolo_pages(lambda: RemoteZip(ZENODO.format(6814770, "yaltai-segmonto-dataset.zip"), 2826543829),
                           "yaltai-segmonto-dataset/val", "yaltai-segmonto-dataset/medieyolo.yml"),
    ),
    "yaltai-table": Set(
        folder="YOLO layout - YALTAi tables (columns and headers of registers)",
        language="French", script="Latin (print and manuscript)", direction="left-to-right",
        producer="YALTAi, YOLOv5 boxes with ALTO beside them", licence="CC-BY-4.0",
        licence_read="Zenodo record 6827706 licence field",
        source="YALTAi: Tabular Dataset, https://zenodo.org/records/6827706 (376 MB, sampled by HTTP Range)",
        exercises="table layout as YOLO boxes: Header, Col, Marginal, text",
        xml=None, pages=6,
        custom=_yolo_pages(lambda: RemoteZip(ZENODO.format(6827706, "yaltai-table.zip"), 376190064),
                           "yaltai-table/val", "yaltai-table/config.yml"),
    ),
    "tq25-religious": Set(
        folder="Medieval vernacular religious texts - Old Irish, Old Swedish, Old Castilian, Bavarian, French",
        language="Old/Middle Irish with Latin (Lebor na hUidre), Old Swedish, Old Castilian, Early New High German, Old and Middle French",
        script="Latin (Insular Carolingian minuscule, Gothic textura and cursiva)", direction="left-to-right",
        producer="eScriptorium, ALTO 4 (TranscriboQuest 2025)", licence="CC-BY-4.0",
        licence_read="Zenodo record 17062963 licence field",
        source="https://zenodo.org/records/17062963",
        exercises="six decorated manuscripts from five countries in one set, 11th-15th c.; RIA 23 E 25 is the Lebor na hUidre, "
        "the oldest surviving manuscript in Irish",
        xml=lambda: Archive(ZENODO.format(17062963, "TranscriboQuest25_MedVernacReligio.zip"), 61486845, "da84c56505a57c923a1c64d3e796e1a5"),
        xml_pattern=r"/data/.*\.xml$", pages=18,
    ),
    "gallicorpora-15e": Set(
        folder="French - 15th-century illuminated manuscripts, BnF (SegmOnto zones)",
        language="Middle French", script="Latin (Gothic bâtarde)", direction="left-to-right",
        producer="eScriptorium, ALTO 4 (Gallicorpora / BnF DataLab)", licence="CC0-1.0 (repository); images Gallica",
        licence_read="repository LICENSE (GitHub licence API CC0-1.0); HTR-United catalogue says CC-BY 4.0",
        source="https://github.com/Gallicorpora/HTR-MSS-15e-Siecle",
        exercises="decorated pages with the SegmOnto vocabulary (MainZone, MarginTextZone, DropCapitalZone, GraphicZone...)",
        xml=lambda: GitHub("Gallicorpora/HTR-MSS-15e-Siecle", "707a106f7dfa12c463ef40ec5cb53eae5e1b5e63", "data/btv1b84260029/"),
        xml_pattern=r"data/btv1b84260029/[^/]+\.xml$", pages=8,
    ),
    "eutyches-glossed": Set(
        folder="Latin with interlinear glosses - Eutyches grammar, 9th-11th c. (Leiden VLO 41, BnF lat. 7499)",
        language="Medieval Latin (with Greek)", script="Latin (Caroline minuscule)", direction="left-to-right",
        producer="eScriptorium, ALTO 4", licence="Apache-2.0 (repository LICENSE); HTR-United lists CC-BY 4.0. Images: Leiden and BnF, terms unstated -- personal research use only",
        licence_read="repository LICENSE (GitHub licence API apache-2.0); HTR-United catalogue entry",
        source="https://github.com/malamatenia/Eutyches",
        exercises="THE glossed page: lines tagged InterlinearLine sit between the main lines, with MarginTextZone, "
        "DropCapitalZone and MusicZone -- reading order across main text and gloss",
        xml=lambda: GitHub("malamatenia/Eutyches", "4daf191b0018e65a6f918515406c38cf721c3b58", ""),
        xml_pattern=r"^VLO41/GT/alto/.*\.xml$", pages=12,  # Lat7499's JPEGs are ~88 px shorter than its ALTO states: a crop, not paired
        want=lambda xml: b"InterlinearLine" in xml,
    ),
    "bdd-decretum": Set(
        folder="Latin canon law - Burchard's Decretum, 11th c., Bamberg Msc.Can.6 (layout only, IIIF images)",
        language="Medieval Latin", script="Latin (Caroline minuscule)", direction="left-to-right",
        producer="Transkribus then eScriptorium, PAGE 2019 (Burchards Dekret Digital, Kassel)",
        licence="CC-BY-4.0 (PAGE); images: Staatsbibliothek Bamberg via MDZ, Public Domain Mark",
        licence_read="repository LICENSE file; MDZ IIIF manifest bsb00140701 'license' field",
        source="https://github.com/michaelscho/bdd-segmentation-data; images https://api.digitale-sammlungen.de",
        exercises="a two-column law book with inscriptions and chapter counts as region types; regions and baselines "
        "with NO text; images fetched at the exact size the PAGE was drawn on, from the library's own IIIF",
        xml=lambda: GitHub("michaelscho/bdd-segmentation-data", "39b47e1de9d5973ff5c839d1e52c3d530afb250c", "kraken/B/"),
        xml_pattern=r"kraken/B/B_00[1-2]\d\.xml$", images=IIIF(_bdd_urls), pages=8,
    ),
    "paderov-bible": Set(
        folder="Czech - Padeřov Bible, 1432-35 (Transkribus ALTO in mm10)",
        language="Old Czech", script="Latin (Gothic textura)", direction="left-to-right",
        producer="Transkribus, ALTO 4 with MeasurementUnit mm10", licence="CC-BY-4.0",
        licence_read="Zenodo record 7467034 licence field",
        source="https://zenodo.org/records/7467034",
        exercises="a Hussite illuminated Bible; coordinates in tenths of a millimetre, not pixels, so the pixel-size check "
        "cannot apply and the image is paired by name alone",
        xml=lambda: Archive(ZENODO.format(7467034, urllib.parse.quote("Padeřov-Bible-handwriting-ground-truth Initial release.zip")), 76281597, "a3018491ce27ebee7d809e93220356fe"),
        xml_pattern=r"/alto/.*\.xml$", pages=8, unit="mm10",
    ),
    "nzz-fraktur": Set(
        folder="German - Neue Zürcher Zeitung 1780-1946, Fraktur front pages (PAGE with language)",
        language="German", script="Latin (Fraktur, later Antiqua)", direction="left-to-right",
        producer="Transkribus, PAGE 2013 with primaryLanguage on lines and words", licence="CC-BY-4.0",
        licence_read="Zenodo record 3333627 licence field",
        source="https://zenodo.org/records/3333627 (472 MB, sampled by HTTP Range)",
        exercises="dense multi-column newspaper pages with a ReadingOrder, words with TextStyle, TIFF images; "
        "the XML names the image by Transkribus id (1199914.tif), not by the deposit's file name",
        xml=lambda: RemoteZip(ZENODO.format(3333627, "NZZ-black-letter-ground-truth-master.zip"), 472003256),
        xml_pattern=r"xml/NZZ_groundtruth/.*\.xml$", pages=6,
    ),
    "lectaurep-mariages": Set(
        folder="French - Paris notaries' marriage registers, printed form filled by hand",
        language="French", script="Latin (print and 19th-20th c. cursive)", direction="left-to-right",
        producer="eScriptorium, PAGE 2019 (and ALTO, not taken)", licence="CC-BY-4.0",
        licence_read="repository LICENSE (GitHub licence API CC-BY-4.0)",
        source="https://github.com/HTR-United/lectaurep-mariages-et-divorces",
        exercises="a FORM: printed labels (line type Print) beside handwritten answers (Handwritten) and signatures, "
        "in SegmOnto zones (MainZone, TableZone, NumberingZone)",
        xml=lambda: GitHub("HTR-United/lectaurep-mariages-et-divorces", "f0f65b7c3edc9cf21bb81c606c50f5370558d312", "data/lectaurep-cm1/"),
        xml_pattern=r"data/lectaurep-cm1/page/.*\.xml$", pages=8,
    ),
    "reichsanzeiger-tables": Set(
        folder="German - Reichsanzeiger newspaper tables (PAGE TableRegion and TableCell)",
        language="German", script="Latin (Fraktur and Antiqua)", direction="left-to-right",
        producer="Transkribus, PAGE 2013 with TableRegion/TableCell (UB Mannheim)",
        licence="CC0-1.0 (repository LICENSE and .zenodo.json); scans: Mannheim University Library",
        licence_read="repository LICENSE (CC0 text) and .zenodo.json 'license: cc-zero'",
        source="https://github.com/UB-Mannheim/reichsanzeiger-gt; images https://digi.bib.uni-mannheim.de",
        exercises="real tables: TableCell with row/col/rowSpan/colSpan and text, the Transkribus dialect; 10368x7104 scans",
        xml=lambda: GitHub("UB-Mannheim/reichsanzeiger-gt", "0a3a0daf03679dc1d206e17dfdabf62b762b0476", "data/"),
        xml_pattern=r"with-TableRegion/GT-PAGE/.*\.xml$", images=IIIF(_reichsanzeiger_urls), pages=4,
        want=lambda xml: b"<TableCell" in xml,
    ),
    "hisclima-tables": Set(
        folder="English - USS Albatross logbooks 1880s, ruled tables filled by hand (PAGE TableRegion)",
        language="English", script="Latin (19th-c. cursive on a printed form)", direction="left-to-right",
        producer="Transkribus, PAGE 2013 with TableRegion/TableCell", licence="CC-BY-4.0",
        licence_read="Zenodo record 6937608 licence field",
        source="HisClima (Information Extraction in Handwritten Historical Logbooks), https://zenodo.org/records/6937608",
        exercises="a ship's weather log: a printed table of ~435 cells per page filled in by hand -- form labels and answers as cells",
        xml=lambda: RemoteZip(ZENODO.format(6937608, "HisClima_table_IE.zip"), 291621205), pages=4,
    ),
    "benedict-bilingual": Set(
        folder="Latin and Old English - bilingual Rule of St Benedict, 10th-11th c. (line language tags)",
        language="Latin, Old English", script="Latin (Anglo-Saxon minuscule and Caroline)", direction="left-to-right",
        producer="eScriptorium, ALTO 4 (with an ns0: namespace prefix)", licence="CC-BY-4.0",
        licence_read="Zenodo record 21242748 licence field; images from the British Library, Corpus Christi Cambridge and "
        "Oxford digital collections ship inside the deposit under that record -- personal research use",
        source="https://zenodo.org/records/21242748 (bilingual_RSB_GT.zip, 7 GB, sampled by HTTP Range)",
        exercises="two languages tagged LINE BY LINE (LatinLine / EnglishLine, plus InterlinearLine) in a monastic rule; "
        "three witnesses, TIFF and JPEG images",
        xml=lambda: RemoteZip(ZENODO.format(21242748, "bilingual_RSB_GT.zip"), 7055398671),
        xml_pattern=r"annotations/(BL-CTAiv_02[89]|BL-CTAiv_03[0-1]|CCCCMS178_p33[89]|OCCC197_57[rv])\.xml$", pages=8,
    ),
}
# The Tibetan TEI is a single file, not an archive: fetched by `_single`.
SINGLE = {"pagantibet-tibetan": (ZENODO.format(19205598, "Manual1-20230809_GT_layout.xml"), 165473, "48334278b49dab19c8326faa7a00778d")}


# ---------------------------------------------------------------------------
# Pairing: every XML beside the image it names, under the image's stem
# ---------------------------------------------------------------------------

_IMAGE_REF = (
    re.compile(rb'imageFilename="([^"]+)"'),  # PAGE
    re.compile(rb"<(?:\w+:)?fileName>([^<]+)</(?:\w+:)?fileName>"),  # ALTO, prefixed or not (ns0:fileName)
)


def image_named_by(xml: bytes) -> str | None:
    head = xml[:20000]
    for pattern in _IMAGE_REF:
        m = pattern.search(head)
        if m:
            return m.group(1).decode("utf-8", "replace").strip().replace("\\", "/").rsplit("/", 1)[-1]
    return None


def image_size(data: bytes) -> tuple[int, int] | None:
    """(width, height) from a JPEG SOF, PNG IHDR or TIFF IFD header, without decoding."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return struct.unpack(">II", data[16:24])
    if data[:4] in (b"II*\x00", b"MM\x00*"):
        order = "<" if data[:2] == b"II" else ">"
        (ifd,) = struct.unpack(order + "I", data[4:8])
        (count,) = struct.unpack(order + "H", data[ifd:ifd + 2])
        found = {}
        for i in range(count):
            tag, kind, n, value = struct.unpack(order + "HHII", data[ifd + 2 + 12 * i:ifd + 14 + 12 * i])
            if tag in (256, 257):  # ImageWidth, ImageLength; SHORT values sit in the field's first two bytes
                found[tag] = value if kind == 4 else struct.unpack(order + "H", data[ifd + 10 + 12 * i:ifd + 12 + 12 * i])[0]
        return (found[256], found[257]) if len(found) == 2 else None
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
    """The pixel size the XML says its image has -- or None when it says none, or when
    its coordinates are not in pixels (ALTO `mm10`, `inch1200`), since then the page
    size is not a pixel size and cannot be compared with one."""
    head = xml[:20000]
    if re.search(rb"<(?:\w+:)?MeasurementUnit>\s*(mm10|inch1200)\s*<", head):
        return None
    m = re.search(rb'imageWidth="(\d+)"\s+imageHeight="(\d+)"', head)
    if m:
        return int(m.group(1)), int(m.group(2))
    page = re.search(rb"<(?:\w+:)?Page\b[^>]*>", head)
    if page:
        w = re.search(rb'\bWIDTH="(\d+)"', page.group(0))
        h = re.search(rb'\bHEIGHT="(\d+)"', page.group(0))
        if w and h:
            return int(w.group(1)), int(h.group(1))
    return None


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
    mismatches = 0
    for name in candidates:
        if report["pages"] >= s.pages:
            break
        xml = store.read(name)
        suffix = "." + name.rsplit(".", 1)[-1].lower()
        if suffix == ".xml" and b"PcGts" not in xml[:3000] and b"alto" not in xml[:3000]:
            continue
        if s.want and not s.want(xml):
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
        # Failing both, an image whose name ENDS with the XML's stem (NZZ ships
        # `0001_nzz_17800719_..tif` for `nzz_17800719_...xml`, and names a Transkribus
        # id inside the XML).
        xml_stem = name.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        found = image_index.get(ref or "") or next(
            (image_index[stem + e] for e in (".jpg", ".jpeg", ".png", ".tif", ".JPG", ".JPEG") if stem + e in image_index), None
        ) or next((v for k, v in image_index.items() if k.rsplit(".", 1)[0].endswith("_" + xml_stem)), None)
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
            if want and got and want != got and max(abs(want[0] - got[0]), abs(want[1] - got[1])) <= 2:
                # The same scan, resized by the library with a different rounding
                # (MDZ serves 1500x1847 for a PAGE drawn on 1500x1848): every region
                # still lands within a pixel. Paired, and said.
                report["missing"].append(f"{stem}: the image is {got[0]}x{got[1]}, the XML says {want[0]}x{want[1]} -- the same scan, rounded differently; paired")
            elif want and got and want != got:
                # Not the image the regions were drawn on (a different scan or crop):
                # pairing it would put every region in the wrong place. Say so, and after
                # three such pages stop fetching images for this set.
                report["missing"].append(
                    f"{stem}: the source's image is {got[0]}x{got[1]} and the XML was drawn on "
                    f"{want[0]}x{want[1]} -- a different scan, so no image is paired"
                )
                mismatches += 1
                if mismatches >= 3:
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
