"""Which layout file in a dropped folder belongs to which image (#5132).

An eScriptorium or Transkribus export is a folder of page images, each with a PAGE XML or
ALTO file describing it. Before this, a folder ingest turned every `.xml` into a raw text
document (`ingest.py`: `.xml -> FileType.text`), so the layout and transcription never
reached the image. This module decides the pairs, and nothing else: the pass is then
written by the existing audited `format.import` action, the same path as the one-file
menu import.

**The keys, strongest first:**

1. **The file's own `imageFilename`** (PAGE `Page@imageFilename`, ALTO `fileName`, hOCR
   `image`), matched by NAME against the images beside it. It is what the exporting tool
   wrote down, so it wins when stems differ -- Transkribus names its XML after the image
   *with* its extension (`0001.jpg.xml`), and exports are renamed.
2. **The same stem**, with the layout suffixes taken off (`.page.xml`, `.alto.xml`, `.xml`,
   `.hocr`, `.html`).

Looked for **in the same folder, then its parent**, because Transkribus puts the XML in a
`page/` subfolder beside the images and eScriptorium puts it flat.

**Never guessed.** A layout file with no image by either key, or with two images that
match equally, is UNPAIRED and named with the reason. It is then imported as an ordinary
file, as before, so nothing is lost; it just does not become a pass.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

#: The formats a folder of page images comes with. TEI is an edition, not one file per
#: image; YOLO labels have no image name to check against.
PAGED_FORMATS = ("pagexml", "alto", "hocr")

IMAGE_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".tif", ".tiff", ".jp2", ".webp", ".gif", ".bmp"})
LAYOUT_SUFFIXES = (".page.xml", ".alto.xml", ".xml", ".hocr", ".html", ".htm")


@dataclass
class PairingPlan:
    #: layout file -> the image it describes
    pairs: dict[Path, Path] = field(default_factory=dict)
    #: layout file -> why it could not be paired
    unpaired: dict[Path, str] = field(default_factory=dict)
    #: layout file -> its format name, for `format.import`
    formats: dict[Path, str] = field(default_factory=dict)


def _layout_stem(path: Path) -> str:
    name = path.name
    lowered = name.lower()
    for suffix in LAYOUT_SUFFIXES:
        if lowered.endswith(suffix):
            return name[: -len(suffix)]
    return path.stem


def _candidates(layout: Path, by_dir: dict[Path, list[Path]]) -> list[list[Path]]:
    """Images to look in, nearest first: the same folder, then its parent."""
    return [by_dir.get(layout.parent, []), by_dir.get(layout.parent.parent, [])]


def plan_pairs(files: list[Path]) -> PairingPlan:
    """Decide the pairs among `files` (every file of the dropped folder)."""
    from fichero_server.formats import format_for, read_page

    plan = PairingPlan()
    by_dir: dict[Path, list[Path]] = {}
    for path in files:
        if path.suffix.lower() in IMAGE_SUFFIXES:
            by_dir.setdefault(path.parent, []).append(path)

    for path in files:
        if path.suffix.lower() not in (".xml", ".hocr", ".html", ".htm"):
            continue
        try:
            data = path.read_bytes()
        except OSError:
            continue
        spec = format_for(path.name, data)
        if spec is None or spec.name not in PAGED_FORMATS:
            # NEVER SILENTLY TEXT when it looks like interchange (#5132): a file whose root is
            # ALTO, PAGE or TEI but which is not paged layout -- or which no format claims --
            # is still imported as an ordinary file, and NAMED, so a person knows its layout
            # did not reach any image. An XML that is not interchange at all stays unnamed.
            looks = _looks_like_interchange(data)
            if looks:
                plan.unpaired[path] = (
                    f"{looks}, but TEI is an edition, not one file per image: imported as an ordinary file"
                    if spec is not None and spec.name == "tei"
                    else f"{looks}, but no reader here classifies it: imported as an ordinary file"
                )
            continue
        plan.formats[path] = spec.name
        try:
            stated = read_page(spec.name, data).image_name
        except Exception as exc:  # noqa: BLE001 -- the reason is reported by name
            plan.unpaired[path] = f"{spec.name} file could not be read: {exc}"
            continue

        match = _match(path, stated, by_dir)
        if isinstance(match, Path):
            plan.pairs[path] = match
        else:
            plan.unpaired[path] = match
    return plan


#: Root namespaces and names that mark a file as interchange, whatever else it is.
_INTERCHANGE_NAMESPACE_HINTS = ("loc.gov/standards/alto", "primaresearch.org/page", "tei-c.org")
_INTERCHANGE_ROOTS = {"alto", "pcgts", "tei", "teicorpus"}


def _looks_like_interchange(data: bytes) -> str | None:
    """`"its root is <alto> (namespace ...)"` when the ROOT marks it as interchange, else None."""
    from fichero_server.formats.validation import root_element

    root = root_element(data)
    if root is None:
        return None
    namespace, local = root
    if local.lower() in _INTERCHANGE_ROOTS or any(h in namespace.lower() for h in _INTERCHANGE_NAMESPACE_HINTS):
        return f"its root is <{local}>" + (f" in {namespace}" if namespace else "")
    return None


def _match(layout: Path, stated: str | None, by_dir: dict[Path, list[Path]]) -> Path | str:
    """The image, or the reason there is none."""
    stated_name = Path(stated.replace("\\", "/")).name if stated else None
    stem = _layout_stem(layout)
    for images in _candidates(layout, by_dir):
        if stated_name:
            named = [image for image in images if image.name == stated_name]
            if len(named) == 1:
                return named[0]
        same_stem = [
            image for image in images
            if image.stem == stem or image.name == stem  # `0001.jpg.xml` -> `0001.jpg`
        ]
        if len(same_stem) == 1:
            return same_stem[0]
        if len(same_stem) > 1:
            return f"{len(same_stem)} images share the stem {stem!r}: " + ", ".join(
                sorted(image.name for image in same_stem)
            )
    said = f"names {stated_name!r}, which is not beside it" if stated_name else "names no image"
    return f"no image in the same or the parent folder: the file {said}, and none has the stem {stem!r}"
