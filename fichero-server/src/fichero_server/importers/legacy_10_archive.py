"""Read a **Fichero 1.0** archive folder and convert it to ``fichero-corpus-import-v1``.

Fichero 1.0 processed a folder of page scans with the "00) default" workflow
and left the results *beside* the originals::

    <doc folder>/
    ├── documents/<doc folder name>/*.JPG        the originals
    ├── logs/workflow_00)_default_<ts>.log       the run's provenance
    └── assets/
        ├── manifests/documents_manifest.jsonl   the roll call (size + mtime)
        ├── crops|split|rotated|enhanced|background_removed/
        │       <stage>_manifest.jsonl + documents/…   one image per page
        ├── segmented|segmented_transcriptions/  strips — DEFERRED, see below
        ├── recombined|transcriptions/           documents/*.txt per page
        ├── word|llm_catalogue_word/             *.docx — no rendition role
        └── llm_catalogue/steps/documents/*.json folder-scoped catalogue

Every stage manifest is JSONL in one shape — ``{"source", "outputs": [...],
"details": {...}}`` — with paths relative to that stage's ``documents/`` root,
so the whole chain is walkable without reading a single image byte. This module
reads only those manifests plus the catalogue JSON.

**Nothing here writes to the archive.** The volume holds the only copy of a
300 GB corpus; the converter is pure reading plus one manifest written wherever
the caller asks (a scratch directory, never the archive).

What it does NOT carry, deliberately
------------------------------------
* **Segment bands.** ``segment_manifest.jsonl`` records ``[y_start, y_end]``
  full-width bands in the *background-removed PNG* space — i.e. after EXIF
  rotation, crop, split, rotate and enhance. Composing that chain back to
  original pixels belongs to the bbox program (Daniel, 2026-09-04: deferred).
  The strips are counted and reported as unmapped, and every folder records a
  ``legacy_deferred`` marker naming what was left behind, so the later pass can
  find them without re-deriving this scan.
* **``.docx`` renditions.** There is no non-image rendition role. Counted only.

Daniel's rulings (2026-09-04) that shape the output:
  1. ONE library; duplicate document folders across the two archives are
     deduped by **content identity**, not by path.
  2. Curation tiers ("04 Checked", "05 Posted") FLATTEN to metadata, not
     folder nesting.
  3. Segment geometry deferred, as above.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any, Iterator

from pydantic import BaseModel, Field

from fichero_server.errors import ValidationError

logger = logging.getLogger(__name__)

CANONICAL_VERSION = "fichero-corpus-import-v1"

#: Stamped on every artifact the 1.0 import produces, so a row can always be
#: traced back to the old pipeline rather than to today's engine.
LEGACY_PROVIDER = "fichero-1.0"

#: The file whose presence MAKES a directory a 1.0 document folder. Detection
#: is by marker, never by depth: a document folder sits 3 levels down in one
#: archive and 4 in the other.
MARKER = Path("assets") / "manifests" / "documents_manifest.jsonl"

#: How deep to hunt for the marker below a dropped folder before giving up.
#: 4 covers both observed archives (archive → tier → [batch] → doc folder).
MAX_MARKER_DEPTH = 5

#: Stage directory → the rendition role it produced, in pipeline order. These
#: role names are the ones ``manifest_import.IMAGE_ROLE_PREFERENCE`` already
#: prefers — the canonical format was drawn from this very pipeline.
STAGE_ROLES: dict[str, str] = {
    "crops": "crop",
    "split": "split",
    "rotated": "rotated",
    "enhanced": "enhanced",
    "background_removed": "background_removed",
}

#: Stage directory → its manifest filename (the 1.0 tools did not use one rule).
STAGE_MANIFESTS: dict[str, str] = {
    "crops": "crop_manifest.jsonl",
    "split": "split_manifest.jsonl",
    "rotated": "rotate_manifest.jsonl",
    "enhanced": "enhance_manifest.jsonl",
    "background_removed": "background_removed_manifest.jsonl",
    "transcriptions": "transcription_manifest.jsonl",
    "segmented": "segment_manifest.jsonl",
}

#: Catalogue result key → canonical entity_type. Anything unlisted becomes a
#: "concept" rather than being dropped: the 1.0 prompts were free to invent
#: buckets, and an unrecognised bucket is still evidence.
ENTITY_KINDS: dict[str, str] = {
    "personas": "person",
    "personas_clave": "person",
    "organizaciones": "organization",
    "ubicaciones": "location",
    "rios": "location",
    "minas": "location",
    "propiedades": "location",
    "eventos_clave": "event",
    "dragas": "concept",
    "animales": "concept",
    "plantas": "concept",
    "armas": "concept",
    "lesiones": "concept",
    "terminos_legales": "concept",
    "legales": "concept",
}

#: Buckets that are NOT entities. ``fechas`` entries are bare dates
#: ("1937-01-01") with the meaning in their ``contexto``; naming an entity
#: after one produces a name with no letters, which the entities route rightly
#: refuses (422, every single one, measured on the sample import). They are
#: dates, and they ride as folder metadata instead of being mangled into
#: entities.
_NON_ENTITY_BUCKETS = {"fechas"}

#: The name key an entity object might use, in order of preference.
_NAME_KEYS = ("nombre", "evento", "fecha_normalizada", "fecha", "termino", "titulo")

_YEAR_RE = re.compile(r"(1[5-9]\d{2}|20\d{2})")
_TRAILING_INDEX_RE = re.compile(r"-(\d+)$")


# ---------------------------------------------------------------------------
# Tolerant readers — a 15-year-old corpus is not clean, and pretending it is
# would silently drop evidence.
# ---------------------------------------------------------------------------


def read_jsonl(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    """Read a stage manifest. Returns ``(records, warnings)`` — never raises.

    A truncated final line is normal (the 1.0 tools appended as they worked and
    a killed run leaves a partial line), so a bad line is a warning, not a stop.
    """
    records: list[dict[str, Any]] = []
    warnings: list[str] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return [], [f"{path}: unreadable ({exc})"]
    for lineno, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            warnings.append(f"{path}:{lineno}: unparseable line ({exc.msg})")
            continue
        if isinstance(record, dict):
            records.append(record)
    return records, warnings


def salvage_json(text: str) -> tuple[Any | None, bool]:
    """Parse JSON, repairing a truncated document. ``(value, was_salvaged)``.

    The 1.0 catalogue steps hit a generation length cap: several
    ``extraer_entidades_*`` results are cut off mid-object around 15,000
    characters, so ``json.loads`` fails on the whole file and a naive reader
    loses every entity in it — dozens of real people and places per folder.

    The repair is deliberately dumb and therefore trustworthy: walk the text
    tracking string/escape state and the bracket stack, remember the last
    position at which a *complete* element closed, cut there, and close the
    still-open brackets. Nothing is invented — the result is a strict prefix of
    what the model actually emitted.
    """
    try:
        return json.loads(text), False
    except (json.JSONDecodeError, TypeError):
        pass
    if not isinstance(text, str):
        return None, False

    stack: list[str] = []
    in_string = False
    escaped = False
    cut = -1
    cut_stack: list[str] = []
    for index, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in "{[":
            stack.append(char)
        elif char in "}]":
            if not stack:
                break
            stack.pop()
            # An element that closed while still nested is a safe cut point:
            # everything up to here is a complete value inside its container.
            # The stack must be remembered AS IT STOOD HERE — closing with the
            # stack the scan ended on would close brackets opened after the cut.
            if stack:
                cut = index
                cut_stack = list(stack)
    if cut < 0 or not cut_stack:
        return None, False
    closers = "".join("}" if opener == "{" else "]" for opener in reversed(cut_stack))
    try:
        return json.loads(text[: cut + 1] + closers), True
    except json.JSONDecodeError:
        return None, False


def _as_mapping(result: Any) -> tuple[dict[str, Any], bool]:
    """Catalogue ``result`` is sometimes a dict, sometimes a JSON *string*."""
    if isinstance(result, dict):
        return result, False
    if isinstance(result, str):
        value, salvaged = salvage_json(result)
        if isinstance(value, dict):
            return value, salvaged
    return {}, False


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class LegacyPage(BaseModel):
    """One original page scan and every rendition 1.0 derived from it."""

    stem: str
    sequence: int
    original_path: str
    images: list[dict[str, Any]] = Field(default_factory=list)
    text_path: str | None = None
    size: int | None = None
    mtime: float | None = None
    segment_count: int = 0
    #: ``[y_start, y_end]`` bands in the background-removed frame, VERBATIM.
    #: Not imported (Daniel deferred the geometry) but carried so the bbox
    #: program never has to re-read 300 GB to get them back.
    segment_bands: list[list[int]] = Field(default_factory=list)


class LegacyFolder(BaseModel):
    """One 1.0 document folder — the unit of catalogue and of dedupe."""

    path: str
    archive: str
    stage: str | None = None
    tiers: list[str] = Field(default_factory=list)
    title: str
    year: str | None = None
    fingerprint: str
    pages: list[LegacyPage] = Field(default_factory=list)
    summary: str | None = None
    tags: list[str] = Field(default_factory=list)
    dates: list[dict[str, Any]] = Field(default_factory=list)
    entities: list[dict[str, Any]] = Field(default_factory=list)
    timeline: list[dict[str, Any]] = Field(default_factory=list)
    catalogue_model: str | None = None
    transcription_model: str | None = None
    source_folder_1_0: str | None = None
    workflow: str | None = None
    docx_count: int = 0
    segment_count: int = 0
    salvaged_steps: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    duplicate_of: str | None = None
    #: Quality signals, used ONLY to choose between copies of the same content.
    stages_completed: int = 0
    catalogue_steps: int = 0
    segment_text_count: int = 0
    run_timestamp: float = 0.0

    @property
    def external_id(self) -> str:
        return f"fichero10:{self.fingerprint[:16]}"

    @property
    def transcribed_pages(self) -> int:
        return sum(1 for page in self.pages if page.text_path)

    @property
    def quality(self) -> tuple[int, int, int, int, int]:
        """How complete this copy is — Daniel: "use the better one".

        The order is empirical, measured across the nine overlapping folders
        the two archives actually hold (2026-09-04):

        1. ``stages_completed`` decides two of the nine outright, and
           decisively — a "Big Files" copy is often ABANDONED mid-pipeline
           (6/12 stages, zero transcriptions) while its twin ran to 12/12.
           Nothing else matters if one copy was never transcribed.
        2. ``transcribed_pages`` — the page text is the point of the corpus.
        3. INTACT catalogue steps (present minus truncated). One pair differs
           only here: same 6 steps, but one copy's run truncated one of them.
        4. ``segment_text_count`` — more strips transcribed, more text read
           (pairs differ by 1-6 strips).
        5. ``entities`` recovered.

        Deliberately NOT a criterion: original resolution. Content identity is
        page-sequence + byte size, so overlapping copies hold byte-identical
        originals by construction — "higher resolution" cannot discriminate,
        and pretending it can would be a criterion that never fires.

        The run timestamp is the tiebreak, applied outside this tuple so that
        "identical except for when it ran" is reportable as identical.
        """
        return (
            self.stages_completed,
            self.transcribed_pages,
            self.catalogue_steps - len(self.salvaged_steps),
            self.segment_text_count,
            len(self.entities),
        )


class LegacyScan(BaseModel):
    """Everything a scan found, everything it refused, and why."""

    corpus_name: str
    roots: list[str] = Field(default_factory=list)
    folders: list[LegacyFolder] = Field(default_factory=list)
    duplicates: list[LegacyFolder] = Field(default_factory=list)
    unprocessed: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @property
    def page_count(self) -> int:
        return sum(len(folder.pages) for folder in self.folders)

    @property
    def rendition_count(self) -> int:
        return sum(len(page.images) for f in self.folders for page in f.pages)

    @property
    def transcription_count(self) -> int:
        return sum(1 for f in self.folders for p in f.pages if p.text_path)

    @property
    def entity_count(self) -> int:
        return sum(len(folder.entities) for folder in self.folders)

    @property
    def timeline_count(self) -> int:
        return sum(len(folder.timeline) for folder in self.folders)

    @property
    def segment_count(self) -> int:
        return sum(folder.segment_count for folder in self.folders)

    @property
    def docx_count(self) -> int:
        return sum(folder.docx_count for folder in self.folders)

    @property
    def overlap_tally(self) -> dict[str, int]:
        """Which archive won each overlap — Daniel sees this before the run."""
        tally: dict[str, int] = {}
        for loser in self.duplicates:
            winner = next(
                (f for f in self.folders if f.fingerprint == loser.fingerprint), None
            )
            if winner is None:
                continue
            key = (
                "identical"
                if winner.quality == loser.quality
                else (
                    winner.archive
                    if winner.archive != loser.archive
                    else f"{winner.archive} (internal copy)"
                )
            )
            tally[key] = tally.get(key, 0) + 1
        return tally


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def is_legacy_document_folder(path: Path) -> bool:
    """A directory is a 1.0 document folder when it carries the marker."""
    return (path / MARKER).is_file()


def find_legacy_document_folders(
    root: Path, *, max_depth: int = MAX_MARKER_DEPTH
) -> Iterator[Path]:
    """Yield 1.0 document folders under ``root``, by marker and not by depth.

    A document folder is never nested inside another, so the walk does not
    descend into one it has already matched — that is what keeps this from
    stat-ing its way through the ``assets/`` tree of a 21 GB folder.
    """
    if is_legacy_document_folder(root):
        yield root
        return
    if max_depth <= 0:
        return
    try:
        children = sorted(p for p in root.iterdir() if p.is_dir())
    except OSError as exc:
        logger.warning("legacy scan: cannot list %s (%s)", root, exc)
        return
    for child in children:
        if child.name.startswith("."):
            continue
        yield from find_legacy_document_folders(child, max_depth=max_depth - 1)


def looks_like_legacy_archive(path: Path, *, max_depth: int = MAX_MARKER_DEPTH) -> bool:
    """Cheap yes/no for the drop path: does this folder hold ANY 1.0 folder?"""
    return next(find_legacy_document_folders(path, max_depth=max_depth), None) is not None


# ---------------------------------------------------------------------------
# Reading one document folder
# ---------------------------------------------------------------------------


def _page_sequence(stem: str) -> int:
    """``…-99`` sorts before ``…-100``: the trailing index is a NUMBER."""
    match = _TRAILING_INDEX_RE.search(stem)
    return int(match.group(1)) if match else 0


def _fingerprint(entries: list[tuple[int, int]]) -> str:
    """Content identity for a document folder — Daniel's dedupe rule.

    Built from each page's *position and byte size* as the 1.0 manifest recorded
    them, so two copies of the same folder collapse to one document however they
    are nested OR RENAMED — the archive really does hold ``<name>`` beside
    ``<name>-1``, and page stems embed the folder name, so keying on the stem
    would have made those two different documents.

    ponytail: sequence+size, not a hash of 21 GB of pixels. Two folders would
    have to hold the same number of pages with byte-identical sizes in the same
    order to collide falsely, which for scanned originals means they ARE the
    same folder. Upgrade path if that ever bites: hash the first and last 64 KB
    of each original as well.
    """
    payload = "\n".join(
        f"{sequence}:{size}" for sequence, size in sorted(entries)
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _size_fields(size: Any) -> dict[str, int]:
    """``[w, h]`` from a 1.0 manifest as Rendition pixel fields, if sane."""
    try:
        width, height = int(size[0]), int(size[1])
    except (TypeError, ValueError, IndexError):
        return {}
    if width <= 0 or height <= 0:
        return {}
    return {"pixel_width": width, "pixel_height": height}


def _output_size(stage: str, details: dict[str, Any]) -> Any:
    """The pixel size a stage recorded for its OUTPUT (each tool named it differently)."""
    for key in ("cropped_size", "rotated_size", "output_size", "final_size"):
        if details.get(key):
            return details[key]
    rotation = details.get("rotation") or {}
    return rotation.get("final_dimensions")


def _stage_outputs(
    folder: Path, stage: str
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Map ``page stem -> {"path", "details"}`` for one pipeline stage.

    ``details`` is the stage's own record — for ``crops`` that is where the
    detected box and the pixel sizes live, and reading it here is what lets a
    rendition record its transform without opening a single image.
    """
    stage_dir = folder / "assets" / stage
    manifest = stage_dir / STAGE_MANIFESTS[stage]
    if not manifest.is_file():
        return {}, []
    records, warnings = read_jsonl(manifest)
    documents_root = stage_dir / "documents"
    outputs: dict[str, dict[str, Any]] = {}
    for record in records:
        source = record.get("source")
        produced = record.get("outputs") or []
        if not source or not produced:
            continue
        outputs[Path(str(source)).stem] = {
            "path": str(documents_root / str(produced[0])),
            "details": record.get("details") or {},
        }
    return outputs, warnings


def crop_transform(details: dict[str, Any]) -> dict[str, Any] | None:
    """The crop box as a normalized ``NodeRegion`` payload, or ``None``.

    1.0 recorded ``box`` in the pixel frame of the original *after EXIF
    rotation was applied* — the ``rotation`` sub-dict says so explicitly — and
    ``original_size`` is that same post-EXIF frame. Normalizing against it is
    therefore exact, and the note records which frame it is so a later reader
    does not have to re-derive that from the pipeline.
    """
    box = details.get("box") or {}
    size = details.get("original_size") or []
    try:
        x1, y1, x2, y2 = (
            float(box["x1"]), float(box["y1"]), float(box["x2"]), float(box["y2"])
        )
        width, height = float(size[0]), float(size[1])
    except (KeyError, TypeError, ValueError, IndexError):
        return None
    if width <= 0 or height <= 0 or x2 <= x1 or y2 <= y1:
        return None
    rect = [x1 / width, y1 / height, (x2 - x1) / width, (y2 - y1) / height]
    # Clamp: a padded box can overshoot the frame by a pixel or two, and the
    # model rightly refuses a normalized rect outside 0..1.
    rect = [min(max(value, 0.0), 1.0) for value in rect]
    if rect[0] + rect[2] > 1.0:
        rect[2] = 1.0 - rect[0]
    if rect[1] + rect[3] > 1.0:
        rect[3] = 1.0 - rect[1]
    method = str(details.get("method") or "crop")
    return {
        "rect": rect,
        "space": "normalized",
        "confidence": "measured",
        "method": f"fichero-1.0-{method}",
        "note": "box measured on the EXIF-rotated original frame",
    }


def _read_catalogue(folder: Path) -> dict[str, Any]:
    """Read ``assets/llm_catalogue`` — entities, timeline, summary, tags."""
    steps_dir = folder / "assets" / "llm_catalogue" / "steps" / "documents"
    out: dict[str, Any] = {
        "entities": [],
        "timeline": [],
        "summary": None,
        "tags": [],
        "dates": [],
        "salvaged": [],
        "warnings": [],
        "source_folder": None,
    }
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    if not steps_dir.is_dir():
        return out
    for step_file in sorted(steps_dir.glob("*.json")):
        step = step_file.stem
        try:
            document = json.loads(step_file.read_text(encoding="utf-8", errors="replace"))
        except (OSError, json.JSONDecodeError) as exc:
            out["warnings"].append(f"{step_file.name}: unreadable ({exc})")
            continue
        out["source_folder"] = out["source_folder"] or document.get("source")
        result, salvaged = _as_mapping(document.get("result"))
        if salvaged:
            out["salvaged"].append(step)
            out["warnings"].append(
                f"{step_file.name}: result truncated by the 1.0 run — "
                "recovered every complete entry before the cut"
            )
        if not result:
            if document.get("result"):
                out["warnings"].append(f"{step_file.name}: result unparseable, skipped")
            continue

        if step == "resumen":
            summary = result.get("resumen")
            if isinstance(summary, str):
                out["summary"] = summary.strip() or None
            continue
        if step == "linea_temporal":
            for event in result.get("linea_temporal") or []:
                if isinstance(event, dict) and event.get("evento"):
                    out["timeline"].append(
                        {
                            "fecha": event.get("fecha"),
                            "evento": str(event["evento"]).strip(),
                        }
                    )
            continue

        for key, value in result.items():
            if key == "etiquetas":
                if isinstance(value, str):
                    out["tags"] = [t.strip() for t in value.split(";") if t.strip()]
                elif isinstance(value, list):
                    out["tags"] = [str(t).strip() for t in value if str(t).strip()]
                continue
            if not isinstance(value, list):
                continue
            if key in _NON_ENTITY_BUCKETS:
                for item in value:
                    if isinstance(item, dict):
                        out["dates"].append(
                            {
                                "fecha": item.get("fecha"),
                                "fecha_normalizada": item.get("fecha_normalizada"),
                                "contexto": str(item.get("contexto") or "").strip()
                                or None,
                            }
                        )
                continue
            entity_type = ENTITY_KINDS.get(key, "concept")
            for item in value:
                if not isinstance(item, dict):
                    continue
                name = next(
                    (str(item[k]).strip() for k in _NAME_KEYS if item.get(k)), None
                )
                if not name:
                    continue
                aliases = [
                    str(a).strip()
                    for a in (item.get("ortografias_alternativas") or [])
                    if str(a).strip()
                ]
                description = str(item.get("contexto") or "").strip() or None
                # The same person arrives twice — once under `personas`, again
                # under `personas_clave`. One entity, both buckets recorded.
                existing = merged.get((name, entity_type))
                if existing is not None:
                    for alias in aliases:
                        if alias not in existing["aliases"]:
                            existing["aliases"].append(alias)
                    if description and not existing["description"]:
                        existing["description"] = description
                    buckets = existing["metadata"]["legacy_buckets"]
                    if key not in buckets:
                        buckets.append(key)
                    continue
                merged[(name, entity_type)] = {
                    "canonical_name": name,
                    "entity_type": entity_type,
                    "aliases": aliases,
                    "description": description,
                    "language": "es",
                    "metadata": {
                        "legacy_step": step,
                        "legacy_buckets": [key],
                        **(
                            {"fecha_normalizada": item["fecha_normalizada"]}
                            if item.get("fecha_normalizada")
                            else {}
                        ),
                    },
                }
    out["entities"] = list(merged.values())
    return out


def _read_models(folder: Path) -> tuple[str | None, str | None]:
    """Read the models the 1.0 run actually used — never assume them.

    A folder processed with a different model must say so, so both labels come
    off disk: the catalogue's from ``llm_process_manifest.jsonl``, the
    transcription's from the first ``segmented_transcriptions`` record.
    """
    catalogue_model: str | None = None
    manifest = folder / "assets" / "llm_catalogue" / "llm_process_manifest.jsonl"
    if manifest.is_file():
        records, _ = read_jsonl(manifest)
        for record in records:
            if record.get("model"):
                catalogue_model = str(record["model"])
                break

    transcription_model: str | None = None
    seg = folder / "assets" / "segmented_transcriptions" / (
        "segmented_transcription_manifest.jsonl"
    )
    if seg.is_file():
        records, _ = read_jsonl(seg)
        for record in records:
            model = (record.get("details") or {}).get("model")
            if model:
                transcription_model = str(model)
                break
    return catalogue_model, transcription_model


def _read_workflow_name(folder: Path) -> str | None:
    """The workflow name from the run log's header, for provenance."""
    logs = folder / "logs"
    if not logs.is_dir():
        return None
    for log in sorted(logs.glob("*.log")):
        try:
            with log.open(encoding="utf-8", errors="replace") as handle:
                for _ in range(20):
                    line = handle.readline()
                    if not line:
                        break
                    if "Workflow:" in line:
                        return line.split("Workflow:", 1)[1].strip() or None
        except OSError:
            continue
    return None


def read_document_folder(
    folder: Path, *, archive: str, stage: str | None
) -> LegacyFolder:
    """Read one 1.0 document folder into a :class:`LegacyFolder`. Never raises."""
    warnings: list[str] = []
    records, manifest_warnings = read_jsonl(folder / MARKER)
    warnings.extend(manifest_warnings)

    documents_root = folder / "documents"
    sized: list[tuple[str, int]] = []
    originals: dict[str, dict[str, Any]] = {}
    for record in records:
        if record.get("type") != "file":
            continue
        relative = str(record.get("path") or "")
        if not relative:
            continue
        stem = Path(relative).stem
        size = int(record.get("size") or 0)
        originals[stem] = {
            "path": str(documents_root / relative),
            "size": size,
            "mtime": record.get("mtime"),
        }
        sized.append((_page_sequence(stem), size))

    stage_outputs: dict[str, dict[str, str]] = {}
    for stage_dir in STAGE_ROLES:
        outputs, stage_warnings = _stage_outputs(folder, stage_dir)
        stage_outputs[stage_dir] = outputs
        warnings.extend(stage_warnings)
    texts, text_warnings = _stage_outputs(folder, "transcriptions")
    warnings.extend(text_warnings)

    segments_by_stem: dict[str, list[list[int]]] = {}
    segment_manifest = folder / "assets" / "segmented" / STAGE_MANIFESTS["segmented"]
    if segment_manifest.is_file():
        seg_records, _ = read_jsonl(segment_manifest)
        for record in seg_records:
            source = record.get("source")
            if not source:
                continue
            bands = []
            for segment in (record.get("details") or {}).get("segments") or []:
                box = segment.get("bounding_box")
                if isinstance(box, list) and len(box) == 2:
                    bands.append([int(box[0]), int(box[1])])
            segments_by_stem[Path(str(source)).stem] = bands

    pages: list[LegacyPage] = []
    for stem, original in sorted(originals.items(), key=lambda kv: _page_sequence(kv[0])):
        crop = stage_outputs.get("crops", {}).get(stem) or {}
        crop_details = crop.get("details") or {}
        original_size = crop_details.get("original_size") or []

        # The renditions CHAIN (models/anchors.py: "frames chain"): each stage
        # was derived from the previous one that actually ran, so the rows can
        # say so instead of all hanging off the original.
        images: list[dict[str, Any]] = [
            {
                "role": "original",
                "source_path": original["path"],
                "producer_tool": "fichero-1.0",
                **_size_fields(original_size),
            }
        ]
        previous_role = "original"
        for stage_dir, role in STAGE_ROLES.items():
            produced = stage_outputs.get(stage_dir, {}).get(stem)
            if not produced:
                continue
            details = produced.get("details") or {}
            image: dict[str, Any] = {
                "role": role,
                "source_path": produced["path"],
                "derived_from_role": previous_role,
                "producer_tool": f"fichero-1.0/{stage_dir}",
                **_size_fields(_output_size(stage_dir, details)),
            }
            if role == "crop":
                transform = crop_transform(details)
                if transform is not None:
                    image["transform"] = transform
            images.append(image)
            previous_role = role

        bands = segments_by_stem.get(stem, [])
        pages.append(
            LegacyPage(
                stem=stem,
                sequence=_page_sequence(stem),
                original_path=original["path"],
                images=images,
                text_path=(texts.get(stem) or {}).get("path"),
                size=original["size"] or None,
                mtime=original["mtime"],
                segment_count=len(bands),
                segment_bands=bands,
            )
        )
    if not pages:
        warnings.append("no pages found in documents_manifest.jsonl")

    catalogue = _read_catalogue(folder)
    warnings.extend(catalogue["warnings"])
    catalogue_model, transcription_model = _read_models(folder)

    # Quality signals — how far the 1.0 run actually got. Only ever used to
    # choose between two copies of the SAME content.
    stages_completed = sum(
        1
        for stage, manifest_name in STAGE_MANIFESTS.items()
        if (folder / "assets" / stage / manifest_name).is_file()
    )
    for extra in ("recombined/recombine_manifest.jsonl",
                  "word/convert_to_word_manifest.jsonl",
                  "llm_catalogue/llm_process_manifest.jsonl",
                  "llm_catalogue_word/json_to_word_manifest.jsonl",
                  "segmented_transcriptions/segmented_transcription_manifest.jsonl"):
        if (folder / "assets" / extra).is_file():
            stages_completed += 1
    segment_text = folder / "assets" / "segmented_transcriptions" / (
        "segmented_transcription_manifest.jsonl"
    )
    segment_text_count = 0
    if segment_text.is_file():
        segment_records, _ = read_jsonl(segment_text)
        segment_text_count = len(segment_records)
    catalogue_steps = len(
        list((folder / "assets" / "llm_catalogue" / "steps" / "documents").glob("*.json"))
    ) if (folder / "assets" / "llm_catalogue" / "steps" / "documents").is_dir() else 0
    run_timestamp = 0.0
    if (folder / "logs").is_dir():
        for log in (folder / "logs").glob("*.log"):
            try:
                run_timestamp = max(run_timestamp, log.stat().st_mtime)
            except OSError:
                continue

    title = folder.name.replace("-", " ").strip()
    year_match = _YEAR_RE.match(folder.name)
    docx = len(list((folder / "assets" / "word" / "documents").glob("*.docx"))) + len(
        list((folder / "assets" / "llm_catalogue_word" / "documents").glob("*.docx"))
    )

    return LegacyFolder(
        path=str(folder),
        archive=archive,
        stage=stage,
        title=title,
        year=year_match.group(1) if year_match else None,
        fingerprint=_fingerprint(sized),
        pages=pages,
        summary=catalogue["summary"],
        tags=catalogue["tags"],
        dates=catalogue["dates"],
        entities=catalogue["entities"],
        timeline=catalogue["timeline"],
        catalogue_model=catalogue_model,
        transcription_model=transcription_model,
        source_folder_1_0=catalogue["source_folder"],
        workflow=_read_workflow_name(folder),
        docx_count=docx,
        segment_count=sum(page.segment_count for page in pages),
        salvaged_steps=catalogue["salvaged"],
        warnings=warnings,
        stages_completed=stages_completed,
        catalogue_steps=catalogue_steps,
        segment_text_count=segment_text_count,
        run_timestamp=run_timestamp,
    )


# ---------------------------------------------------------------------------
# Scanning whole archives
# ---------------------------------------------------------------------------


def _tiers_of(folder: Path, root: Path) -> list[str]:
    """The directory tiers between the scan root and a document folder."""
    try:
        return list(folder.relative_to(root).parts[:-1])
    except ValueError:
        return []


def archive_and_stage(tiers: list[str], root_name: str) -> tuple[str, str | None]:
    """Which archive a folder belongs to, and its curation tier.

    Both are read from the tier chain rather than from the scan root, because
    the root is not always the archive: resolving an overlap by quality
    requires seeing both copies in ONE scan, so the useful scan root is the
    folder that CONTAINS both archives — and naming every document after that
    parent made the overlap tally read "Historical Archives Portable wins 9",
    which tells Daniel nothing.

    With two or more tiers the first is the archive and the second the tier
    ("Big Files" / "05 Posted"). With one, the root itself is the archive and
    the tier is that single directory. With none, the root is a document folder.

    Daniel's ruling: the tier FLATTENS to metadata — a filterable field, never
    a folder node.
    """
    if len(tiers) >= 2:
        return tiers[0], tiers[1]
    if len(tiers) == 1:
        return root_name, tiers[0]
    return root_name, None


def scan_archives(roots: list[Path], *, corpus_name: str) -> LegacyScan:
    """Scan one or more 1.0 archive roots into a single, deduped corpus."""
    if not roots:
        raise ValidationError("No archive root given to scan.")
    scan = LegacyScan(corpus_name=corpus_name, roots=[str(r) for r in roots])
    groups: dict[str, list[LegacyFolder]] = {}

    for root in roots:
        root = Path(root).expanduser()
        if not root.is_dir():
            raise ValidationError(f"Not a directory: {root}")
        found = False
        for folder in find_legacy_document_folders(root):
            found = True
            tiers = _tiers_of(folder, root)
            archive, stage = archive_and_stage(tiers, root.name)
            entry = read_document_folder(folder, archive=archive, stage=stage)
            entry.tiers = tiers
            groups.setdefault(entry.fingerprint, []).append(entry)
        if not found:
            scan.warnings.append(f"{root}: no Fichero 1.0 document folders found")

        # Folders of loose scans that 1.0 never processed: real material, but
        # nothing to convert. Named so they are not silently lost.
        for child in sorted(p for p in root.rglob("*") if p.is_dir()):
            if child.name.startswith(".") or is_legacy_document_folder(child):
                continue
            if any(part in {"assets", "documents", "logs"} for part in child.parts):
                continue
            if any(str(child).startswith(f.path) for f in scan.folders):
                continue
            has_images = any(
                p.suffix.lower() in {".jpg", ".jpeg", ".png", ".tif", ".tiff"}
                for p in child.iterdir()
                if p.is_file()
            )
            if has_images:
                scan.unprocessed.append(str(child))

    # Daniel: "which is better, big or small? Use the better one." The copies
    # hold identical originals, so the choice is about how far each RUN got —
    # `LegacyFolder.quality` documents the ranking and where it came from.
    for candidates in groups.values():
        winner = max(candidates, key=lambda f: (f.quality, f.run_timestamp))
        scan.folders.append(winner)
        for loser in candidates:
            if loser is winner:
                continue
            loser.duplicate_of = winner.path
            scan.duplicates.append(loser)

    scan.folders.sort(key=lambda f: (f.year or "", f.title))
    return scan


# ---------------------------------------------------------------------------
# Conversion to fichero-corpus-import-v1
# ---------------------------------------------------------------------------


def _folder_metadata(folder: LegacyFolder, scan: LegacyScan) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "legacy_source": "fichero-1.0",
        "legacy_archive": folder.archive,
        "legacy_path": folder.path,
        "legacy_fingerprint": folder.fingerprint,
        "legacy_workflow": folder.workflow,
        "legacy_source_folder": folder.source_folder_1_0,
        "legacy_catalogue_model": folder.catalogue_model,
        "legacy_transcription_model": folder.transcription_model,
    }
    if folder.stage:
        # Ruling 2: the curation tier is a FIELD, not a folder.
        metadata["legacy_stage"] = folder.stage
    if folder.tiers:
        metadata["legacy_tiers"] = folder.tiers
    if folder.summary:
        metadata["resumen"] = folder.summary
    if folder.tags:
        metadata["tags"] = folder.tags
    if folder.dates:
        metadata["legacy_dates"] = folder.dates
    if folder.timeline:
        # ALSO as metadata, not only as claims: /api/claims is tier-gated and a
        # release-tier engine does not expose it, so the claims phase skips with
        # a warning (measured: every timeline event silently dropped). The
        # claims still land wherever the surface exists; this is the copy that
        # always survives.
        metadata["legacy_timeline"] = folder.timeline
    if folder.salvaged_steps:
        metadata["legacy_truncated_steps"] = folder.salvaged_steps
    losers = [d for d in scan.duplicates if d.fingerprint == folder.fingerprint]
    if losers:
        # Which copy won, and why — visible on the document, not just in a log.
        metadata["legacy_chosen_copy"] = {
            "won": folder.archive,
            "quality": list(folder.quality),
            "over": [
                {
                    "path": loser.path,
                    "archive": loser.archive,
                    "quality": list(loser.quality),
                    "identical": loser.quality == folder.quality,
                }
                for loser in losers
            ],
            "ranking": (
                "stages_completed, transcribed_pages, intact_catalogue_steps, "
                "segment_texts, entities; run timestamp breaks ties"
            ),
        }
    # Ruling 3: say what was left behind, so the bbox program can find it
    # without re-deriving this scan.
    if folder.segment_count or folder.docx_count:
        metadata["legacy_deferred"] = {
            "segment_strips": folder.segment_count,
            "segment_geometry": "bands [y_start,y_end] in background_removed space",
            "segment_bands_on": "each page node's metadata.legacy_deferred_segments",
            "docx": folder.docx_count,
            "reason": "deferred to the bbox program (Daniel, 2026-09-04)",
        }
    return {k: v for k, v in metadata.items() if v not in (None, [], {})}


def _catalogue_artifacts(folder: LegacyFolder) -> list[dict[str, Any]]:
    """The 1.0 ficha as a ``catalogue`` artifact — the surface the app reads.

    The resumen is the catalogue: the prose the old pipeline wrote per folder.
    It was landing in ``metadata["resumen"]``, which no view reads, so it was
    present and invisible (Daniel, 2026-09-05: "I see Events, Keywords — but
    not the catalogue"). ``artifact_type="catalogue"`` is what ArtifactPanel
    already renders and what today's catalogue workflow writes.

    The tags ride in the same artifact's ``data`` rather than becoming their own
    artifact: they are the ficha's own keyword line, and folding them in adds no
    new machinery. ``legacy_dates`` and ``legacy_stage`` deliberately stay in
    metadata — they are structured fields, not prose, and where they belong in
    the UI is a separate decision.
    """
    if not folder.summary:
        return []
    return [
        {
            "artifact_type": "catalogue",
            "content": folder.summary,
            "data": {
                "source": "fichero-1.0",
                "tags": folder.tags,
                "legacy_path": folder.path,
                "legacy_steps": ["resumen", "personas_clave_y_etiquetas"],
            },
            "provider": LEGACY_PROVIDER,
            "model": folder.catalogue_model,
            "step_name": "catalogue_folder",
        }
    ]


def to_canonical_nodes(scan: LegacyScan) -> Iterator[dict[str, Any]]:
    """Emit ``fichero-corpus-import-v1`` nodes, parent before child."""
    # Dropping a single document folder should not produce a wrapper folder of
    # the same name around it (measured on the sample import: 10 folder rows
    # for 5 documents). A corpus root earns its place only when it groups.
    single = len(scan.folders) == 1 and scan.folders[0].path in scan.roots
    corpus_id: str | None = None
    if not single:
        corpus_id = f"fichero10:corpus:{scan.corpus_name}"
        yield {
            "canonical_version": CANONICAL_VERSION,
            "external_id": corpus_id,
            "node_type": "folder",
            "name": scan.corpus_name,
            "corpus": scan.corpus_name,
            "metadata": {
                "legacy_source": "fichero-1.0",
                "legacy_roots": scan.roots,
            },
        }

    for folder in scan.folders:
        folder_id = folder.external_id
        yield {
            "canonical_version": CANONICAL_VERSION,
            "external_id": folder_id,
            "parent_external_id": corpus_id,
            "node_type": "folder",
            "name": folder.title,
            "corpus": scan.corpus_name,
            "date": folder.year,
            "language": "es",
            "metadata": _folder_metadata(folder, scan),
            "entities": folder.entities,
            "claims": [
                {
                    "text": event["evento"],
                    "external_id": f"{folder_id}#timeline:{index}",
                    # ClaimType is an ENUM (fact/analysis/interpretation/
                    # argument/historiography/theory). "timeline_event" is not
                    # a member, and the route rightly 422s on it — which
                    # aborted a 6,866-page import at the claims phase. A dated
                    # event read off the page IS a fact; the 1.0 provenance
                    # keeps the finer label.
                    "claim_type": "fact",
                    "language": "es",
                    "metadata": {
                        "fecha": event.get("fecha"),
                        "legacy_step": "linea_temporal",
                        "legacy_claim_kind": "timeline_event",
                    },
                }
                for index, event in enumerate(folder.timeline)
            ],
            # Delta 1: the catalogue was a DIFFERENT model from the
            # transcription, so provenance is per node, not per import.
            "provider": LEGACY_PROVIDER,
            "model": folder.catalogue_model,
            "step_name": "catalogue_folder",
            "artifacts": _catalogue_artifacts(folder),
        }

        for page in folder.pages:
            text: str | None = None
            if page.text_path:
                try:
                    text = Path(page.text_path).read_text(
                        encoding="utf-8", errors="replace"
                    ).strip() or None
                except OSError:
                    text = None
            yield {
                "canonical_version": CANONICAL_VERSION,
                "external_id": f"{folder_id}:{page.stem}",
                "parent_external_id": folder_id,
                "node_type": "page",
                "name": page.stem,
                "corpus": scan.corpus_name,
                "page_label": str(page.sequence) if page.sequence else None,
                "sequence": page.sequence,
                "date": folder.year,
                "language": "es",
                "text": text,
                "images": page.images,
                "metadata": {
                    "legacy_source": "fichero-1.0",
                    "legacy_stem": page.stem,
                    "legacy_mtime": page.mtime,
                    "legacy_size": page.size,
                    # Deferred, not discarded: the bands ride VERBATIM so the
                    # bbox program can attach them later without re-reading
                    # 300 GB to recover a number the archive already knows.
                    **(
                        {
                            "legacy_deferred_segments": {
                                "count": page.segment_count,
                                "space": "background_removed",
                                "axis": "y",
                                "bands": page.segment_bands,
                            }
                        }
                        if page.segment_bands
                        else {}
                    ),
                },
                "provider": LEGACY_PROVIDER,
                "model": folder.transcription_model,
                "step_name": "transcribe_qwen_max_segments",
            }


def write_manifest(scan: LegacyScan, out_path: Path) -> int:
    """Write the manifest. Returns the node count.

    ``out_path`` must be a scratch location — this never writes to the archive,
    and refuses to if asked.
    """
    out_path = Path(out_path).expanduser()
    for root in scan.roots:
        if str(out_path).startswith(str(Path(root).expanduser())):
            raise ValidationError(
                f"Refusing to write the manifest inside the archive ({root}). "
                "The archive is the only copy of the corpus — choose a scratch path."
            )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with out_path.open("w", encoding="utf-8") as handle:
        for node in to_canonical_nodes(scan):
            handle.write(json.dumps(node, ensure_ascii=False) + "\n")
            count += 1
    return count


# ---------------------------------------------------------------------------
# The dry run
# ---------------------------------------------------------------------------


def dry_run_report(scan: LegacyScan) -> str:
    """What an import WOULD create — the whole point of running it first."""
    lines = [f"Fichero 1.0 archive → {scan.corpus_name}"]
    for root in scan.roots:
        lines.append(f"  root                  {root}")
    lines.append("")
    archives = sorted({f.archive for f in scan.folders})
    stages = sorted({f.stage for f in scan.folders if f.stage})
    lines.append(f"  document folders  {len(scan.folders):>9,}")
    if len(archives) > 1:
        lines.append(f"  archives          {len(archives):>9,}   {', '.join(archives)}")
    if stages:
        lines.append(
            f"  curation stages   {len(stages):>9,}   "
            f"{', '.join(stages)} (flattened to metadata)"
        )
    if scan.duplicates:
        lines.append(
            f"  overlaps          {len(scan.duplicates):>9,}   "
            "same content twice — the BETTER copy is imported"
        )
        for who, count in sorted(scan.overlap_tally.items()):
            label = "identical (later run kept)" if who == "identical" else f"{who} wins"
            lines.append(f"    {label:<28}{count:>5,}")
    lines.append(f"  pages             {scan.page_count:>9,}")
    lines.append(
        f"  renditions        {scan.rendition_count:>9,}   "
        "link mode — 0 bytes copied"
    )
    models = sorted({f.transcription_model for f in scan.folders if f.transcription_model})
    lines.append(
        f"  transcriptions    {scan.transcription_count:>9,}   "
        f"{', '.join(models) or 'model not recorded'}"
    )
    untranscribed = scan.page_count - scan.transcription_count
    if untranscribed:
        # Say it plainly: some 1.0 runs were abandoned before transcription,
        # and those pages arrive as images with no text.
        abandoned = sum(1 for f in scan.folders if not f.transcribed_pages)
        lines.append(
            f"    no page text    {untranscribed:>9,}   "
            f"in {abandoned} folder(s) the 1.0 run never transcribed"
        )
    catalogued = sum(1 for f in scan.folders if f.catalogue_steps)
    cat_models = sorted({f.catalogue_model for f in scan.folders if f.catalogue_model})
    lines.append(
        f"  catalogues        {catalogued:>9,}   "
        f"{', '.join(cat_models) or 'model not recorded'}"
    )
    if catalogued < len(scan.folders):
        lines.append(
            f"    no catalogue    {len(scan.folders) - catalogued:>9,}   "
            "folder(s) the 1.0 run never catalogued"
        )
    lines.append(f"    entities        {scan.entity_count:>9,}")
    lines.append(f"    timeline claims {scan.timeline_count:>9,}")
    lines.append("")
    lines.append("  NOT IMPORTED")
    lines.append(
        f"    segment strips  {scan.segment_count:>9,}   "
        "geometry deferred to the bbox program"
    )
    lines.append(f"    word documents  {scan.docx_count:>9,}   no non-image rendition role")
    if scan.unprocessed:
        lines.append(
            f"    unprocessed     {len(scan.unprocessed):>9,}   "
            "folders 1.0 never ran — loose scans"
        )

    truncated = [f for f in scan.folders if f.salvaged_steps]
    if truncated:
        lines.append("")
        lines.append(
            f"  RECOVERED: {len(truncated)} folder(s) had catalogue steps the 1.0 run "
            "truncated mid-JSON;"
        )
        lines.append(
            "  every complete entry before the cut was salvaged, the rest is gone "
            "from the archive."
        )

    warnings = list(scan.warnings) + [w for f in scan.folders for w in f.warnings]
    if warnings:
        lines.append("")
        lines.append(f"  WARNINGS ({len(warnings)})")
        for warning in warnings[:15]:
            lines.append(f"    {warning}")
        if len(warnings) > 15:
            lines.append(f"    … and {len(warnings) - 15} more")
    return "\n".join(lines)
