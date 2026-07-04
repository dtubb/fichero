"""Import Daniel's slipbox corpus into a Fichero library.

This is intentionally a local importer, not a live Tinderbox integration.  The
release-data workflow has two static sources: a filesystem note tree and a
Tinderbox ``.tbx`` XML file.  Parsing both directly avoids AppleScript/Tinderbox
availability and lets the CLI build a fresh catalogue without touching existing
libraries.
"""

from __future__ import annotations

import base64
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from html import unescape
from pathlib import Path
from typing import Iterable

from fichero.importers.http_client import (
    ImporterHttpClient,
    ensure_remote_document,
    reset_local_library_if_loopback,
)
from fichero.ingest import detect_file_type
from fichero.xml_security import iterparse_xml


DEFAULT_SLIPBOX_FILESYSTEM = Path("~/code/slipbox").expanduser()
DEFAULT_SLIPBOX_TBX = Path("~/code/slipbox-tinderbox/slip-box.tbx").expanduser()
DEFAULT_LIBRARY = (
    Path("~/Library/Application Support/Fichero/Slipbox.fichero").expanduser()
)

NOTE_EXTENSIONS = {
    ".md",
    ".markdown",
    ".txt",
    ".rtf",
    ".html",
    ".htm",
    ".xml",
    ".pdf",
    ".docx",
    ".doc",
    ".odt",
    ".csv",
    ".xlsx",
    ".xls",
    ".ods",
}
EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "node_modules",
}
EXCLUDED_NAMES = {".DS_Store"}


@dataclass(frozen=True)
class SlipboxImportSummary:
    """Counts returned by the slipbox importer."""

    library_path: Path
    root_document_id: str
    tinderbox_notes: int = 0
    filesystem_files: int = 0
    skipped_files: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class TinderboxNote:
    """One note parsed from a Tinderbox XML item."""

    external_id: str
    name: str
    text: str
    attributes: dict[str, str]
    prototype: str | None = None
    creator: str | None = None


def import_slipbox_via_http(
    client: ImporterHttpClient,
    *,
    library_path: Path = DEFAULT_LIBRARY,
    filesystem_root: Path = DEFAULT_SLIPBOX_FILESYSTEM,
    tinderbox_path: Path = DEFAULT_SLIPBOX_TBX,
    limit: int | None = None,
    reset: bool = False,
    auto_embed: bool = True,
) -> SlipboxImportSummary:
    library_path = library_path.expanduser().resolve()
    filesystem_root = filesystem_root.expanduser().resolve()
    tinderbox_path = tinderbox_path.expanduser().resolve()

    # ponytail: there is no remote reset endpoint yet; keep the old local-path
    # delete when possible instead of inventing cross-host reset semantics here.
    reset_local_library_if_loopback(client, library_path, reset=reset)
    client.create_library(str(library_path))

    root = ensure_remote_document(
        client,
        name="Daniel Slipbox",
        path=str(library_path),
        doc_type="folder",
        parent_id=None,
        metadata={"source_type": "slipbox_import"},
    )
    tinderbox_parent = ensure_remote_document(
        client,
        name="Tinderbox notes",
        path=str(tinderbox_path),
        doc_type="folder",
        parent_id=root["id"],
        metadata={
            "source_type": "slipbox_tinderbox",
            "source_path": str(tinderbox_path),
        },
    )
    fs_parent = ensure_remote_document(
        client,
        name="Filesystem notes",
        path=str(filesystem_root),
        doc_type="folder",
        parent_id=root["id"],
        metadata={
            "source_type": "slipbox_filesystem",
            "source_path": str(filesystem_root),
        },
    )

    errors: list[str] = []
    tinderbox_count = 0
    filesystem_count = 0
    skipped_count = 0

    if tinderbox_path.exists():
        for note in iter_tinderbox_notes(tinderbox_path):
            if limit is not None and tinderbox_count >= limit:
                break
            try:
                ensure_remote_document(
                    client,
                    name=note.name,
                    path=f"tinderbox://{note.external_id}",
                    doc_type="file",
                    file_type=str(detect_file_type(Path(f"{note.name}.md")).value),
                    parent_id=tinderbox_parent["id"],
                    page_content=note.text,
                    metadata={
                        "source_type": "slipbox_tinderbox",
                        "tinderbox_id": note.external_id,
                        "tinderbox_prototype": note.prototype,
                        "tinderbox_creator": note.creator,
                        "tinderbox_attributes": note.attributes,
                    },
                )
                tinderbox_count += 1
            except Exception as exc:  # pragma: no cover
                errors.append(f"tinderbox:{note.external_id}: {exc}")
    else:
        errors.append(f"Tinderbox file not found: {tinderbox_path}")

    if filesystem_root.exists():
        hierarchy: dict[Path, str] = {filesystem_root: fs_parent["id"]}
        for file_path in iter_slipbox_files(filesystem_root):
            if limit is not None and filesystem_count >= limit:
                break
            if not _is_importable_file(file_path):
                skipped_count += 1
                continue
            try:
                parent_id = _ensure_remote_parent_hierarchy(
                    client=client,
                    root=filesystem_root,
                    folder=file_path.parent,
                    root_parent_id=fs_parent["id"],
                    cache=hierarchy,
                )
                existing = next(
                    (
                        doc
                        for doc in client.list_documents(parent_id=parent_id)
                        if getattr(doc, "path", None) == str(file_path)
                    ),
                    None,
                )
                if existing is None:
                    client.import_file(file_path, parent_id=parent_id)
                filesystem_count += 1
            except Exception as exc:
                errors.append(f"filesystem:{file_path}: {exc}")
    else:
        errors.append(f"Filesystem slipbox root not found: {filesystem_root}")

    return SlipboxImportSummary(
        library_path=library_path,
        root_document_id=root["id"],
        tinderbox_notes=tinderbox_count,
        filesystem_files=filesystem_count,
        skipped_files=skipped_count,
        errors=errors,
    )

def iter_slipbox_files(root: Path) -> Iterable[Path]:
    """Yield non-hidden files from the filesystem slipbox tree."""

    root = root.expanduser().resolve()
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel_parts = path.relative_to(root).parts
        if any(part in EXCLUDED_DIRS or part.startswith(".") for part in rel_parts):
            continue
        if path.name in EXCLUDED_NAMES:
            continue
        yield path


def _is_importable_file(path: Path) -> bool:
    return path.suffix.lower() in NOTE_EXTENSIONS


def _ensure_remote_parent_hierarchy(
    *,
    client: ImporterHttpClient,
    root: Path,
    folder: Path,
    root_parent_id: str,
    cache: dict[Path, str],
) -> str:
    folder = folder.resolve()
    if folder in cache:
        return cache[folder]
    rel = folder.relative_to(root)
    current_path = root
    current_parent = root_parent_id
    for part in rel.parts:
        current_path = current_path / part
        if current_path not in cache:
            doc = ensure_remote_document(
                client,
                name=part,
                path=str(current_path),
                doc_type="folder",
                parent_id=current_parent,
                metadata={
                    "source_type": "slipbox_filesystem_folder",
                    "source_path": str(current_path),
                },
            )
            cache[current_path] = doc["id"]
        current_parent = cache[current_path]
    return current_parent


def iter_tinderbox_notes(tbx_path: Path) -> Iterable[TinderboxNote]:
    """Stream notes from a Tinderbox ``.tbx`` XML file."""

    for event, elem in iterparse_xml(tbx_path, events=("end",)):
        if elem.tag != "item":
            continue

        attributes: dict[str, str] = {}
        raw_text = ""
        for child in elem:
            if child.tag == "attribute":
                name = child.attrib.get("name")
                if name:
                    attributes[name] = child.text or ""
            elif child.tag in {"text", "rtf", "rtfd"}:
                raw_text = "".join(child.itertext())

        note_name = (attributes.get("Name") or elem.attrib.get("ID") or "Untitled").strip()
        plain_text = decode_tinderbox_text(raw_text)
        if note_name or plain_text.strip():
            yield TinderboxNote(
                external_id=elem.attrib.get("ID", ""),
                name=note_name or "Untitled",
                text=plain_text,
                attributes={k: v for k, v in attributes.items() if v},
                prototype=elem.attrib.get("proto"),
                creator=elem.attrib.get("Creator"),
            )
        elem.clear()


def decode_tinderbox_text(raw_text: str) -> str:
    """Decode Tinderbox's base64 RTF/RTFD payload to searchable plain text."""

    cleaned = "".join((raw_text or "").split())
    if not cleaned:
        return ""

    try:
        payload = base64.b64decode(cleaned, validate=False)
    except Exception:
        return raw_text.strip()

    rtf_start = payload.find(b"{\\rtf")
    if rtf_start >= 0:
        rtf_bytes = payload[rtf_start:]
        stripped = _strip_rtf(rtf_bytes.decode("utf-8", errors="ignore"))
        if stripped or os.environ.get("FICHERO_SLIPBOX_TEXTUTIL") != "1":
            return stripped
        converted = _textutil_rtf_to_text(rtf_bytes)
        if converted:
            return converted
        return stripped

    try:
        return payload.decode("utf-8").strip()
    except UnicodeDecodeError:
        return payload.decode("latin-1", errors="ignore").strip()


def _textutil_rtf_to_text(rtf_bytes: bytes) -> str:
    """Use macOS textutil when available; fall back silently elsewhere."""

    if not shutil.which("textutil"):
        return ""
    with tempfile.TemporaryDirectory() as tmp:
        rtf_path = Path(tmp) / "note.rtf"
        txt_path = Path(tmp) / "note.txt"
        rtf_path.write_bytes(rtf_bytes)
        result = subprocess.run(
            ["textutil", "-convert", "txt", "-output", str(txt_path), str(rtf_path)],
            capture_output=True,
            check=False,
            timeout=10,
        )
        if result.returncode != 0 or not txt_path.exists():
            return ""
        return txt_path.read_text(encoding="utf-8", errors="ignore").strip()


_RTF_HEX_RE = re.compile(r"\\'([0-9a-fA-F]{2})")
_RTF_CONTROL_RE = re.compile(r"\\[a-zA-Z]+-?\d* ?")
_RTF_ESCAPED_RE = re.compile(r"\\([{}\\])")


def _strip_rtf(rtf: str) -> str:
    """Small RTF-to-text fallback good enough for search indexing."""

    body_start = re.search(r"\\cf\d+ ?", rtf)
    if body_start:
        rtf = rtf[body_start.end() :]

    def _decode_hex(match: re.Match[str]) -> str:
        value = int(match.group(1), 16)
        if value in {0x96, 0x97}:
            return "-"
        try:
            return bytes([value]).decode("cp1252")
        except UnicodeDecodeError:
            return " "

    text = _RTF_HEX_RE.sub(_decode_hex, rtf)
    text = re.sub(r"{\\fonttbl.*?}", " ", text, flags=re.DOTALL)
    text = re.sub(r"{\\colortbl.*?}", " ", text, flags=re.DOTALL)
    text = re.sub(r"{\\\*.*?}", " ", text, flags=re.DOTALL)
    text = text.replace("\\par", "\n").replace("\\line", "\n")
    text = _RTF_ESCAPED_RE.sub(r"\1", text)
    text = _RTF_CONTROL_RE.sub(" ", text)
    text = text.replace("{", " ").replace("}", " ")
    text = unescape(text)
    lines = [" ".join(line.split()) for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()
__all__ = [name for name in dir() if not name.startswith("__")]
