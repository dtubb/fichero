"""Link-only cloud importers (Dropbox/Box) into the Fichero library model."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fichero.importers.http_client import (
    ImporterHttpClient,
    ensure_remote_document,
    reset_local_library_if_loopback,
)
from fichero.ingest import detect_file_type


@dataclass(frozen=True)
class CloudLinkImportSummary:
    provider: str
    library_path: Path
    root_document_id: str
    imported_links: int = 0
    skipped_rows: int = 0
    errors: list[str] = field(default_factory=list)


def import_dropbox_links_via_http(
    client: ImporterHttpClient,
    *,
    library_path: Path,
    manifest_path: Path,
    reset: bool = False,
) -> CloudLinkImportSummary:
    return _import_cloud_links_via_http(
        client,
        provider="dropbox",
        provider_domain="dropbox.com",
        library_path=library_path,
        manifest_path=manifest_path,
        root_name="Dropbox Linked Sources",
        reset=reset,
    )


def import_box_links_via_http(
    client: ImporterHttpClient,
    *,
    library_path: Path,
    manifest_path: Path,
    reset: bool = False,
) -> CloudLinkImportSummary:
    return _import_cloud_links_via_http(
        client,
        provider="box",
        provider_domain="box.com",
        library_path=library_path,
        manifest_path=manifest_path,
        root_name="Box Linked Sources",
        reset=reset,
    )


def _import_cloud_links_via_http(
    client: ImporterHttpClient,
    *,
    provider: str,
    provider_domain: str,
    library_path: Path,
    manifest_path: Path,
    root_name: str,
    reset: bool = False,
) -> CloudLinkImportSummary:
    library_path = library_path.expanduser().resolve()
    manifest_path = manifest_path.expanduser().resolve()

    # ponytail: only local loopback engines may delete local libraries.
    reset_local_library_if_loopback(client, library_path, reset=reset)
    client.create_library(str(library_path))

    root = ensure_remote_document(
        client,
        name=root_name,
        path=str(manifest_path),
        doc_type="folder",
        parent_id=None,
        metadata={"source_type": f"{provider}_link_import"},
    )

    imported = 0
    skipped = 0
    errors: list[str] = []

    try:
        rows = _load_manifest_rows(manifest_path)
    except Exception as exc:
        return CloudLinkImportSummary(
            provider=provider,
            library_path=library_path,
            root_document_id=root["id"],
            imported_links=0,
            skipped_rows=0,
            errors=[f"manifest:{manifest_path}: {exc}"],
        )

    for idx, row in enumerate(rows, start=1):
        url = _coalesce(row, "url", "link", "shared_link", "web_url")
        if not url or provider_domain not in urlparse(url).netloc.lower():
            skipped += 1
            continue
        try:
            name = _coalesce(row, "name", "filename", "title") or f"{provider}-link-{idx}"
            external_id = _coalesce(row, "external_id", "id", "file_id")
            display_path = _coalesce(row, "path_display", "path", "full_path")
            file_type = detect_file_type(Path(urlparse(url).path or name))
            ensure_remote_document(
                client,
                name=name,
                path=url,
                doc_type="file",
                file_type=file_type,
                parent_id=root["id"],
                metadata={
                    "source_type": f"{provider}_link",
                    "provider": provider,
                    "provider_external_id": external_id,
                    "provider_path_display": display_path,
                    "provider_manifest_row": idx,
                    "link_only": True,
                    "remote_reference": True,
                    "manifest_row": row,
                },
            )
            imported += 1
        except Exception as exc:  # pragma: no cover
            errors.append(f"row:{idx}: {exc}")

    return CloudLinkImportSummary(
        provider=provider,
        library_path=library_path,
        root_document_id=root["id"],
        imported_links=imported,
        skipped_rows=skipped,
        errors=errors,
    )


def _load_manifest_rows(path: Path) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".json":
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            return [dict(item) for item in raw if isinstance(item, dict)]
        if isinstance(raw, dict) and isinstance(raw.get("items"), list):
            return [dict(item) for item in raw["items"] if isinstance(item, dict)]
        raise ValueError("JSON manifest must be a list[object] or {'items':[...]} shape")
    if suffix == ".csv":
        with path.open("r", encoding="utf-8", newline="") as fh:
            return [dict(row) for row in csv.DictReader(fh)]
    raise ValueError("Manifest must be .json or .csv")


def _coalesce(row: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = row.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None

__all__ = [name for name in dir() if not name.startswith("__")]
