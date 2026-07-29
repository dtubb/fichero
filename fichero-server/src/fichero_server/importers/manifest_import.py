"""Import a canonical corpus manifest into a Fichero library via the API.

This is the engine-side backing for the ``fichero import-manifest`` CLI
command. It reads a ``fichero-corpus-import-v1`` manifest (a general
interchange format produced by corpus-specific converters — *not*
Marshall-specific) and creates the corresponding folders, documents, image
renditions, entities, and claims **through the same FastAPI routes the
SwiftUI app uses** (``POST /api/documents``, ``/api/entities``,
``/api/claims``). It never writes ``db.save`` / SQL directly.

Design notes
------------
* **Transport-agnostic.** All HTTP goes through a tiny ``ManifestApiClient``
  protocol (``request(method, path, body) -> Any``). The default
  implementation reuses the shared ``FicheroClient`` transport with the
  Bearer key from ``~/Library/Application Support/Fichero/.api-key`` and the
  ``X-Fichero-Library-Path`` header. Tests inject a FastAPI ``TestClient``
  adapter so the importer can be exercised end-to-end against the real routes
  with no live server.
* **Images are referenced, never copied.** Each document's ``path`` points at
  the rendition's existing ``source_path`` on disk; the full ``images[]`` list
  (with every role + source path) is preserved under document metadata.
* **Idempotent.** Re-running against the same library skips documents whose
  ``canonical_external_id`` already exists, reuses entities by canonical name,
  and skips claims already recorded (matched by ``canonical_claim_external_id``
  in claim metadata). Safe to re-run after a partial import.
* **Validated.** The manifest's ``canonical_version`` must match; nodes must
  appear parent-before-child; a missing parent is a hard error.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fichero_server.importers.http_client import (
    DEFAULT_API_BASE,
    DEFAULT_TOKEN_FILE,
    HttpManifestClient,
    ManifestApiClient,
    resolve_http_token,
)
logger = logging.getLogger(__name__)

CANONICAL_VERSION = "fichero-corpus-import-v1"

# How a page's source image is brought into the library.
#   link  — reference the file in place (bytes stay where they are); the local
#           preview cache is still warmed so the app never reaches over the
#           network to render a thumbnail/display.
#   copy  — copy the bytes into {library}/files/ (the app renders locally).
#   move  — copy the bytes in, then delete the SOURCE *only when it is safe*
#           (a normal local disk). NEVER delete off a network/removable volume
#           (e.g. under /Volumes/): we fall back to copy-and-keep and warn.
INGEST_MODES = ("link", "copy", "move")
DEFAULT_INGEST_MODE = "link"
# Preferred display rendition for a document's primary ``path`` reference.
IMAGE_ROLE_PREFERENCE = (
    "enhanced",
    "background_removed",
    "rotated",
    "crop",
    "original",
)

_VALID_ENTITY_TYPES = {
    "person",
    "location",
    "organization",
    "event",
    "concept",
    "citation",
    "other",
}
# A manifest "group" is a *container* node (e.g. a diary holding its pages). We
# import it as a navigable **folder** so its child pages render in the app's
# document grid; importing it as doc_type "group" made the grid draw it as an
# empty leaf ("Empty Folder") and hid the children. The container carries no
# image bytes, so nothing downstream depends on it being doc_type "group" for
# these corpus imports — only `_NODE_TYPE_TO_DOC_TYPE` ever produced that value.
_NODE_TYPE_TO_DOC_TYPE = {"folder": "folder", "group": "folder", "page": "page"}


class CliManifestClient:
    """ManifestApiClient adapter over the shared CLI transport."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def request(
        self, method: str, path: str, body: dict[str, Any] | None = None
    ) -> Any:
        return self._client.request(method, f"/api{path}", json=body)


def resolve_ingest_mode(ingest_mode: str | None, copy_images: bool) -> str:
    """Resolve the effective ingest mode from the new flag + legacy alias.

    ``ingest_mode`` (``link``/``copy``/``move``) wins when given. The legacy
    ``copy_images`` boolean maps to ``copy`` for back-compat. Default ``link``.
    """
    if ingest_mode is not None:
        mode = str(ingest_mode).strip().lower()
        if mode not in INGEST_MODES:
            raise ValueError(
                f"Unknown ingest mode {ingest_mode!r}; "
                f"expected one of {INGEST_MODES}"
            )
        return mode
    return "copy" if copy_images else DEFAULT_INGEST_MODE


def _is_safe_to_delete_source(source: Path) -> bool:
    """Conservatively decide whether ``source`` may be deleted after a move.

    Deleting off a network or removable volume is dangerous and forbidden, so
    we only return True for paths that clearly live on the local boot volume:
    under ``$HOME`` (and NOT under ``/Volumes``). Anything mounted under
    ``/Volumes/`` (external disks, SMB/AFP/NFS network shares) is treated as
    unsafe. When in any doubt, return False (caller falls back to copy-and-keep).
    """
    try:
        resolved = Path(source).expanduser().resolve()
    except (OSError, RuntimeError, ValueError):
        return False
    parts = resolved.parts
    # Anything mounted under /Volumes is external/network — never delete.
    if len(parts) >= 2 and parts[1] == "Volumes":
        return False
    try:
        home = Path(os.path.expanduser("~")).resolve()
    except (OSError, RuntimeError, ValueError):
        return False
    try:
        resolved.relative_to(home)
    except ValueError:
        # Not under $HOME — too risky to delete automatically.
        return False
    return True


@dataclass
class ImportSummary:
    """Outcome of an import run."""

    manifest: str
    library_path: str
    nodes_seen: int = 0
    pages_seen: int = 0
    documents_created: int = 0
    documents_skipped: int = 0
    entities_created: int = 0
    entities_reused: int = 0
    artifacts_created: int = 0
    artifacts_skipped: int = 0
    claims_created: int = 0
    claims_skipped: int = 0
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "manifest": self.manifest,
            "library_path": self.library_path,
            "nodes_seen": self.nodes_seen,
            "pages_seen": self.pages_seen,
            "documents_created": self.documents_created,
            "documents_skipped": self.documents_skipped,
            "entities_created": self.entities_created,
            "entities_reused": self.entities_reused,
            "artifacts_created": self.artifacts_created,
            "artifacts_skipped": self.artifacts_skipped,
            "claims_created": self.claims_created,
            "claims_skipped": self.claims_skipped,
            "warnings": self.warnings,
        }


# ---------------------------------------------------------------------------
# Manifest reading + validation
# ---------------------------------------------------------------------------


def read_manifest(path: Path) -> list[dict[str, Any]]:
    """Read a JSONL manifest into a list of node dicts."""
    nodes: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                nodes.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid JSONL at {path}:{line_no}: {exc}"
                ) from exc
    return nodes


def validate_nodes(nodes: list[dict[str, Any]]) -> None:
    """Validate canonical version, required fields, and parent ordering."""
    if not nodes:
        raise ValueError("Manifest is empty")
    seen: set[str] = set()
    for index, node in enumerate(nodes):
        version = node.get("canonical_version")
        if version != CANONICAL_VERSION:
            raise ValueError(
                f"Node {index} has canonical_version={version!r}, "
                f"expected {CANONICAL_VERSION!r}"
            )
        external_id = node.get("external_id")
        if not external_id:
            raise ValueError(f"Node {index} is missing external_id")
        node_type = node.get("node_type")
        if node_type not in _NODE_TYPE_TO_DOC_TYPE:
            raise ValueError(
                f"Node {external_id} has unknown node_type={node_type!r}"
            )
        parent = node.get("parent_external_id")
        if parent and parent not in seen:
            raise ValueError(
                f"Node {external_id} references parent {parent!r} that does "
                "not appear before it (manifest must be parent-before-child)"
            )
        seen.add(external_id)


# ---------------------------------------------------------------------------
# Payload builders
# ---------------------------------------------------------------------------


def preferred_image(node: dict[str, Any]) -> dict[str, Any] | None:
    images = node.get("images") or []
    for role in IMAGE_ROLE_PREFERENCE:
        for image in images:
            if image.get("role") == role:
                return image
    return images[0] if images else None


def _canonical_metadata(node: dict[str, Any]) -> dict[str, Any]:
    """Build the canonical metadata block shared by reference and copy modes."""
    image = preferred_image(node)
    # Start from the node's full per-file metadata dict, then layer the
    # canonical fields on top so every document carries BOTH the raw manifest
    # metadata AND the canonical fields (date/page_label/sequence/language/
    # node_type/corpus/external ids/image roles).
    metadata = dict(node.get("metadata") or {})
    metadata.update(
        {
            "canonical_version": node.get("canonical_version"),
            "canonical_external_id": node.get("external_id"),
            "canonical_parent_external_id": node.get("parent_external_id"),
            "canonical_node_type": node.get("node_type"),
            "corpus": node.get("corpus"),
            "page_label": node.get("page_label"),
            "date": node.get("date"),
            "sequence": node.get("sequence"),
            "language": node.get("language"),
            "images": node.get("images") or [],
            "preferred_image_role": image.get("role") if image else None,
        }
    )
    return metadata


def document_payload(
    node: dict[str, Any], parent_id: str | None
) -> dict[str, Any]:
    """Build a ``POST /api/documents`` body for a manifest node.

    Images are *referenced*: ``path`` points at the chosen rendition's
    existing ``source_path`` on disk. The full ``images[]`` list (every role +
    source path) is preserved under metadata so renditions survive the round
    trip without any file being copied.
    """
    image = preferred_image(node)
    metadata = _canonical_metadata(node)
    image_path = image.get("source_path") if image else None
    if image_path and Path(str(image_path)).expanduser().is_absolute():
        image_path = None
    payload: dict[str, Any] = {
        "name": node.get("name") or node.get("external_id"),
        "parent_id": parent_id,
        "doc_type": _NODE_TYPE_TO_DOC_TYPE[node["node_type"]],
        "path": image_path,
        "page_content": node.get("text"),
        "metadata": metadata,
    }
    if node.get("node_type") == "page" and image is not None:
        payload["file_type"] = "image"
    return payload


def entity_payload(
    entity: dict[str, Any],
    node: dict[str, Any],
    source_document_id: str | None = None,
) -> dict[str, Any]:
    entity_type = entity.get("entity_type") or "other"
    if entity_type not in _VALID_ENTITY_TYPES:
        entity_type = "other"
    metadata = dict(entity.get("metadata") or {})
    if entity.get("external_id"):
        metadata.setdefault("canonical_entity_external_id", entity["external_id"])
    source_document_ids = list(entity.get("source_document_ids") or [])
    if source_document_id:
        source_document_ids.append(source_document_id)
    return {
        "id": entity.get("id"),
        "canonical_name": entity["canonical_name"],
        "entity_type": entity_type,
        "aliases": entity.get("aliases") or [],
        "description": entity.get("description"),
        "language": entity.get("language") or node.get("language"),
        "metadata": metadata,
        "source_document_ids": sorted(set(source_document_ids)),
    }


def _entity_artifact_type(entity_type: str) -> str | None:
    match entity_type:
        case "person":
            return "people"
        case "location":
            return "places"
        case "organization":
            return "organizations"
        case "event":
            return "events"
        case "concept":
            return "keywords"
        case _:
            return None


def _entity_artifact_item(entity: dict[str, Any]) -> dict[str, Any]:
    item: dict[str, Any] = {
        "name": entity.get("canonical_name"),
        "entity_type": entity.get("entity_type") or "other",
        "aliases": entity.get("aliases") or [],
        "description": entity.get("description"),
        "language": entity.get("language"),
        "external_id": entity.get("external_id"),
        "metadata": entity.get("metadata") or {},
    }
    return {k: v for k, v in item.items() if v not in (None, "", [])}


def _entity_artifact_content(artifact_type: str, items: list[dict[str, Any]]) -> str:
    title = artifact_type.replace("_", " ").replace("-", " ").title()
    lines = [f"## {title}"]
    for item in items:
        name = item.get("name")
        if name:
            lines.append(f"- {name}")
    return "\n".join(lines)


def _import_receipt_content(node: dict[str, Any]) -> str:
    name = node.get("name") or node.get("external_id") or "page"
    page_label = node.get("page_label")
    if page_label:
        return f"Imported {name} (page {page_label}) from manifest."
    return f"Imported {name} from manifest."


def _import_receipt_data(node: dict[str, Any]) -> dict[str, Any]:
    images = node.get("images") or []
    return {
        "source": "manifest-import",
        "external_id": node.get("external_id"),
        "page_label": node.get("page_label"),
        "canonical_version": node.get("canonical_version"),
        "image_roles": [img.get("role") for img in images if img.get("role")],
        "image_count": len(images),
    }


def claim_payload(
    claim: dict[str, Any],
    node: dict[str, Any],
    source_document_id: str | None,
    entity_ids: list[str],
) -> dict[str, Any]:
    metadata = dict(claim.get("metadata") or {})
    if claim.get("external_id"):
        metadata["canonical_claim_external_id"] = claim["external_id"]
    payload: dict[str, Any] = {
        "text": claim["text"],
        "source_document_id": source_document_id,
        "source_page_label": node.get("page_label"),
        "source_excerpt": claim.get("source_excerpt"),
        "source_ref": claim.get("source_ref") or node.get("external_id"),
        "entity_ids": entity_ids,
        "confidence": claim.get("confidence", 0.5),
        "language": claim.get("language") or node.get("language"),
        "metadata": metadata,
        "created_by": "manifest-importer",
        "claim_type": claim.get("claim_type"),
        "subject_canonical": claim.get("subject_canonical"),
        "predicate_verb": claim.get("predicate_verb"),
        "object_phrase": claim.get("object_phrase"),
        "claim_recorded_at": claim.get("claim_recorded_at") or node.get("date"),
    }
    return {k: v for k, v in payload.items() if v is not None}


# ---------------------------------------------------------------------------
# API helpers (idempotency lookups)
# ---------------------------------------------------------------------------


def _list_documents(client: ManifestApiClient) -> list[dict[str, Any]]:
    response = client.request("GET", "/documents?limit=500")
    if isinstance(response, dict):
        return list(response.get("items") or [])
    if isinstance(response, list):
        return response
    return []


def _list_entities(client: ManifestApiClient) -> list[dict[str, Any]]:
    response = client.request("GET", "/entities?limit=500")
    if isinstance(response, dict):
        return list(response.get("items") or response.get("entities") or [])
    if isinstance(response, list):
        return response
    return []


def _list_claim_external_ids(client: ManifestApiClient) -> set[str]:
    response = client.request("GET", "/claims?limit=500")
    items: list[dict[str, Any]] = []
    if isinstance(response, dict):
        items = list(response.get("items") or [])
    elif isinstance(response, list):
        items = response
    existing: set[str] = set()
    for claim in items:
        meta = claim.get("metadata") or {}
        ext = meta.get("canonical_claim_external_id")
        if ext:
            existing.add(str(ext))
    return existing


def _list_artifact_keys(client: ManifestApiClient) -> set[tuple[str, str]]:
    response = client.request("GET", "/artifacts/?limit=500")
    items: list[dict[str, Any]] = []
    if isinstance(response, dict):
        items = list(response.get("items") or [])
    elif isinstance(response, list):
        items = response
    keys: set[tuple[str, str]] = set()
    for artifact in items:
        doc_id = artifact.get("document_id")
        artifact_type = artifact.get("artifact_type")
        if doc_id and artifact_type:
            keys.add((str(doc_id), str(artifact_type)))
    return keys


def _existing_doc_id_by_external(
    docs: list[dict[str, Any]],
) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for doc in docs:
        meta = doc.get("metadata") or {}
        external = meta.get("canonical_external_id")
        if external and doc.get("id"):
            mapping[str(external)] = str(doc["id"])
    return mapping


def _existing_doc_by_external(
    docs: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    mapping: dict[str, dict[str, Any]] = {}
    for doc in docs:
        meta = doc.get("metadata") or {}
        external = meta.get("canonical_external_id")
        if external:
            mapping[str(external)] = doc
    return mapping


# ---------------------------------------------------------------------------
# Import driver
# ---------------------------------------------------------------------------


def _rewrite_images_to_local(
    metadata: dict[str, Any], original_source: str, local_path: str
) -> None:
    """Point every active image path at the local in-library file (copy/move).

    After the bytes are copied into the library, NOTHING the app loads should
    reference the original (possibly network) ``source_path``. We rewrite each
    ``images[]`` entry whose ``source_path`` matched the rendition we copied to
    the local path, preserving the original under ``original_source_path`` for
    provenance. ``source_path`` (top-level fallback) is rewritten too.
    """
    for image in metadata.get("images") or []:
        if not isinstance(image, dict):
            continue
        if image.get("source_path") == original_source:
            image["original_source_path"] = original_source
            image["source_path"] = local_path
    if metadata.get("source_path") == original_source:
        metadata["original_source_path"] = original_source
        metadata["source_path"] = local_path


def _warm_preview_cache(
    client: ManifestApiClient, doc_id: str, summary: "ImportSummary"
) -> None:
    """Force the engine to render + cache a LOCAL thumbnail and display image.

    GETting the storage endpoints triggers ``ensure_thumbnail`` /
    ``ensure_display``, which render from the document's source and write JPEGs
    into ``{library}/storage/thumbnails/`` — local files. This is what stops the
    app's viewer from spinning on a referenced (network) import: even in LINK
    mode the real bytes stay remote but the preview the app shows is local and
    fast. Failures are non-fatal (warn and continue).
    """
    for kind in ("thumbnail", "display"):
        try:
            client.request("GET", f"/storage/{kind}/{doc_id}")
        except Exception as exc:  # noqa: BLE001 - preview is best-effort
            summary.warnings.append(
                f"Could not warm {kind} preview for {doc_id}: {exc}"
            )


def _ingest_page_image(
    client: ManifestApiClient,
    node: dict[str, Any],
    parent_id: str | None,
    ingest_mode: str,
    summary: "ImportSummary",
) -> str:
    """Bring a page's preferred image into the library under ``ingest_mode``.

    * ``link`` — reference the source path in place (no byte copy); the local
      preview cache is still warmed so the app never loads over the network.
    * ``copy`` — copy the bytes into ``{library}/files/`` via the engine's
      native ingest path; the active image path is rewritten to the local file.
    * ``move`` — copy the bytes in, then delete the SOURCE only when it is safe
      to do so (local boot volume). Network/removable sources (``/Volumes/...``)
      are NEVER deleted: we fall back to copy-and-keep and warn.

    ``extract_text=False`` is critical in every copying mode: the manifest
    already carries the clean transcript, so ingest must NOT run Apple Vision
    OCR that would compete with it. Returns the created document id.
    """
    image = preferred_image(node)
    source_path = image.get("source_path") if image else None
    if not source_path:
        # No image — plain reference document, but still try to warm a preview.
        created = client.request(
            "POST", "/documents", document_payload(node, parent_id)
        )
        doc_id = str(created["id"])
        _warm_preview_cache(client, doc_id, summary)
        return doc_id

    # LINK: reference the source in place; just warm the local preview cache.
    if ingest_mode == "link":
        created = client.request(
            "POST", "/documents", document_payload(node, parent_id)
        )
        doc_id = str(created["id"])
        _warm_preview_cache(client, doc_id, summary)
        return doc_id

    # COPY / MOVE: copy bytes into the library via the native ingest path.
    ingested = client.request(
        "POST",
        "/ingest/file",
        {
            "path": source_path,
            "parent_id": parent_id,
            "copy_mode": True,
            # Do NOT extract text on ingest — page_content comes from the
            # manifest transcript (provenance import, not Apple Vision OCR).
            "extract_text": False,
            "auto_embed": False,
        },
    )
    doc_id = str(ingested["id"])
    local_path = ingested.get("path") if isinstance(ingested, dict) else None

    metadata = _canonical_metadata(node)
    metadata["provenance"] = "import"
    metadata["ingest_mode"] = ingest_mode
    # Rewrite the active image path to the local in-library file so the app
    # never reaches over the network for this rendition.
    if local_path:
        _rewrite_images_to_local(metadata, str(source_path), str(local_path))

    update_body: dict[str, Any] = {
        "name": node.get("name") or node.get("external_id"),
        "doc_type": _NODE_TYPE_TO_DOC_TYPE[node["node_type"]],
        "page_content": node.get("text"),
        "metadata": metadata,
    }
    client.request("PUT", f"/documents/{doc_id}", update_body)

    # MOVE: delete the source only when it is safe (never off a network/
    # removable volume). The engine's own ingest MOVE would delete blindly, so
    # we deliberately ingest with copy_mode and handle deletion here.
    if ingest_mode == "move":
        if _is_safe_to_delete_source(Path(str(source_path))):
            try:
                Path(str(source_path)).expanduser().resolve().unlink()
            except OSError as exc:
                summary.warnings.append(
                    f"Move requested but could not delete source {source_path}: "
                    f"{exc} (bytes are safely copied into the library)"
                )
        else:
            summary.warnings.append(
                f"Move requested but source {source_path} is on a network/"
                "removable volume — refusing to delete (copied into library, "
                "original left in place)."
            )

    # Warm the local preview cache (bytes are local now, but force it so the
    # app has a ready thumbnail/display without a first-render stall).
    _warm_preview_cache(client, doc_id, summary)
    return doc_id


def import_manifest(
    client: ManifestApiClient,
    manifest_path: Path,
    library_path: str,
    *,
    copy_images: bool = False,
    ingest_mode: str | None = None,
    write_transcript_artifacts: bool = True,
) -> ImportSummary:
    """Import a canonical manifest into a library through the API client.

    ``ingest_mode`` controls how each page's image is brought into the library:

    * ``link`` (default) — reference the source path in place; the local
      preview cache is still warmed so the app renders locally (no network spin).
    * ``copy`` — copy the bytes into the library; the active image path is
      rewritten to the local file.
    * ``move`` — copy the bytes in, then delete the source *only when safe*
      (local boot volume). Network/removable sources are never deleted.

    ``copy_images`` is the legacy alias: True ⇒ ``copy``. ``ingest_mode`` wins
    when both are supplied.
    """
    mode = resolve_ingest_mode(ingest_mode, copy_images)
    nodes = read_manifest(manifest_path)
    validate_nodes(nodes)

    summary = ImportSummary(
        manifest=str(manifest_path),
        library_path=library_path,
        nodes_seen=len(nodes),
        pages_seen=sum(1 for n in nodes if n.get("node_type") == "page"),
    )

    # --- documents (folders/groups/pages), parent-before-child ---
    existing_docs = _list_documents(client)
    doc_id_by_external = _existing_doc_id_by_external(existing_docs)
    existing_doc_by_external = _existing_doc_by_external(existing_docs)

    for node in nodes:
        external_id = node["external_id"]
        if external_id in doc_id_by_external:
            summary.documents_skipped += 1
            continue
        parent_external = node.get("parent_external_id")
        parent_id = doc_id_by_external.get(parent_external) if parent_external else None
        if parent_external and not parent_id:
            raise RuntimeError(
                f"Missing parent for {external_id}: {parent_external}"
            )
        if node.get("node_type") == "page" and preferred_image(node):
            # Pages with an image always go through the mode-aware path (link
            # references + warms a local preview; copy/move bring bytes local).
            new_id = _ingest_page_image(client, node, parent_id, mode, summary)
        else:
            created = client.request(
                "POST", "/documents", document_payload(node, parent_id)
            )
            new_id = str(created["id"])
        doc_id_by_external[external_id] = new_id
        summary.documents_created += 1

    # --- entities (deduped by canonical name across the whole manifest) ---
    entity_id_by_key: dict[str, str] = {}
    existing_entity_by_name: dict[str, dict[str, Any]] = {}
    for existing in _list_entities(client):
        name = existing.get("canonical_name")
        if name and existing.get("id"):
            entity_id_by_key[str(name)] = str(existing["id"])
            existing_entity_by_name[str(name)] = existing

    for node in nodes:
        source_document_id = doc_id_by_external.get(node["external_id"])
        existing_doc = existing_doc_by_external.get(node["external_id"]) or {}
        if existing_doc.get("exclude_from_processing") is True:
            logger.info(
                "Skipping manifest processing for excluded document %s (%s)",
                source_document_id,
                node["external_id"],
            )
            continue
        for entity in node.get("entities") or []:
            name = entity.get("canonical_name")
            if not name:
                continue
            ext = entity.get("external_id")
            if name in entity_id_by_key:
                # Reuse — register the external_id alias for claim refs.
                if ext:
                    entity_id_by_key[ext] = entity_id_by_key[name]
                if source_document_id:
                    existing = existing_entity_by_name.get(name, {})
                    existing_sources = set(existing.get("source_document_ids") or [])
                    if source_document_id not in existing_sources:
                        merged = dict(entity)
                        merged["id"] = entity_id_by_key[name]
                        merged["source_document_ids"] = sorted(
                            existing_sources | {source_document_id}
                        )
                        updated = client.request(
                            "POST",
                            "/entities",
                            entity_payload(merged, node, source_document_id),
                        )
                        if isinstance(updated, dict):
                            existing_entity_by_name[name] = updated
                summary.entities_reused += 1
                continue
            created = client.request(
                "POST",
                "/entities",
                entity_payload(entity, node, source_document_id),
            )
            new_id = str(created["id"])
            entity_id_by_key[name] = new_id
            if isinstance(created, dict):
                existing_entity_by_name[name] = created
            if ext:
                entity_id_by_key[ext] = new_id
            summary.entities_created += 1

    # --- artifacts (page-level processing outputs: transcript + entity lists) ---
    existing_artifact_keys = _list_artifact_keys(client)
    for node in nodes:
        doc_id = doc_id_by_external.get(node["external_id"])
        if not doc_id:
            continue
        existing_doc = existing_doc_by_external.get(node["external_id"]) or {}
        if existing_doc.get("exclude_from_processing") is True:
            logger.info(
                "Skipping manifest artifacts for excluded document %s (%s)",
                doc_id,
                node["external_id"],
            )
            continue

        if node.get("node_type") == "page":
            key = (doc_id, "import_receipt")
            if key in existing_artifact_keys:
                summary.artifacts_skipped += 1
            else:
                client.request(
                    "POST",
                    "/artifacts/",
                    {
                        "document_id": doc_id,
                        "artifact_type": "import_receipt",
                        "content": _import_receipt_content(node),
                        "data": _import_receipt_data(node),
                        "provider": "manifest-importer",
                        "model": CANONICAL_VERSION,
                        "step_name": "import_manifest",
                        "confidence": 1.0,
                    },
                )
                existing_artifact_keys.add(key)
                summary.artifacts_created += 1

        text = (node.get("text") or "").strip()
        if text and write_transcript_artifacts:
            key = (doc_id, "transcription")
            if key in existing_artifact_keys:
                summary.artifacts_skipped += 1
            else:
                client.request(
                    "POST",
                    "/artifacts/",
                    {
                        "document_id": doc_id,
                        "artifact_type": "transcription",
                        "content": text,
                        "data": {
                            "source": "manifest-import",
                            "page_label": node.get("page_label"),
                            "external_id": node.get("external_id"),
                        },
                        "provider": "manifest-importer",
                        "model": CANONICAL_VERSION,
                        "step_name": "import_manifest",
                        "confidence": 1.0,
                    },
                )
                existing_artifact_keys.add(key)
                summary.artifacts_created += 1

        grouped_entities: dict[str, list[dict[str, Any]]] = {}
        for entity in node.get("entities") or []:
            entity_type = entity.get("entity_type") or "other"
            artifact_type = _entity_artifact_type(entity_type)
            if not artifact_type:
                continue
            grouped_entities.setdefault(artifact_type, []).append(
                _entity_artifact_item(entity)
            )
        for artifact_type, items in grouped_entities.items():
            if not items:
                continue
            key = (doc_id, artifact_type)
            if key in existing_artifact_keys:
                summary.artifacts_skipped += 1
                continue
            client.request(
                "POST",
                "/artifacts/",
                {
                    "document_id": doc_id,
                    "artifact_type": artifact_type,
                    "content": _entity_artifact_content(artifact_type, items),
                    "data": {
                        "items": items,
                        "source": "manifest-import",
                        "page_label": node.get("page_label"),
                        "external_id": node.get("external_id"),
                    },
                    "provider": "manifest-importer",
                    "model": CANONICAL_VERSION,
                    "step_name": "import_manifest",
                    "confidence": 1.0,
                },
            )
            existing_artifact_keys.add(key)
            summary.artifacts_created += 1

    # --- claims ---
    existing_claim_externals = _list_claim_external_ids(client)
    for node in nodes:
        source_document_id = doc_id_by_external.get(node["external_id"])
        existing_doc = existing_doc_by_external.get(node["external_id"]) or {}
        if existing_doc.get("exclude_from_processing") is True:
            logger.info(
                "Skipping manifest claims for excluded document %s (%s)",
                source_document_id,
                node["external_id"],
            )
            continue
        for claim in node.get("claims") or []:
            ext = claim.get("external_id")
            if ext and ext in existing_claim_externals:
                summary.claims_skipped += 1
                continue
            refs = claim.get("entity_refs") or []
            entity_ids = [
                entity_id_by_key[ref] for ref in refs if ref in entity_id_by_key
            ]
            missing = [ref for ref in refs if ref not in entity_id_by_key]
            if missing:
                summary.warnings.append(
                    f"Claim {ext or claim.get('text', '')[:40]!r} references "
                    f"unknown entities: {missing}"
                )
            client.request(
                "POST",
                "/claims",
                claim_payload(claim, node, source_document_id, entity_ids),
            )
            if ext:
                existing_claim_externals.add(ext)
            summary.claims_created += 1

    return summary


def import_manifest_via_http(
    *,
    manifest_path: Path,
    library_path: Path,
    api_base: str = DEFAULT_API_BASE,
    token_file: Path = DEFAULT_TOKEN_FILE,
    create_library: bool = True,
    copy_images: bool = False,
    ingest_mode: str | None = None,
    client: Any | None = None,
) -> ImportSummary:
    """Convenience entry point: import a manifest into a live engine over HTTP.

    Reads the Bearer key from ``token_file`` and (optionally) creates the
    target ``.fichero`` library first via ``POST /api/library`` so a single
    command can bootstrap and populate a fresh library.

    ``ingest_mode`` (``link``/``copy``/``move``) controls how page images are
    brought into the library; a local preview is always cached. ``copy_images``
    is the legacy alias for ``copy``.
    """
    library_str = str(library_path.expanduser())
    if client is None:
        token = resolve_http_token(token_file, api_base=api_base)
        transport: ManifestApiClient = HttpManifestClient(api_base, token, library_str)
        if create_library:
            transport.request("POST", "/library", {"path": library_str})
    else:
        transport = CliManifestClient(client)
        if create_library:
            client.request("POST", "/api/library", json={"path": library_str})
    return import_manifest(
        transport,
        manifest_path.expanduser(),
        library_str,
        copy_images=copy_images,
        ingest_mode=ingest_mode,
    )

__all__ = [name for name in dir() if not name.startswith("__")]
