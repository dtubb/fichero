"""Import IIIF Presentation 3.0 manifests and W3C AnnotationPages.

The importer is corpus-neutral. It normalizes IIIF Collection / Manifest /
Canvas records into the canonical manifest-import shape, delegates
document/image/entity creation to ``manifest_import``, then creates Fichero
annotations for W3C text anchors through the public API.
"""

from __future__ import annotations

import json
import tempfile
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fichero.importers.http_client import (
    DEFAULT_API_BASE,
    DEFAULT_TOKEN_FILE,
    HttpManifestClient,
    resolve_http_token,
)
from fichero.manifest_import import (
    CANONICAL_VERSION,
    ImportSummary,
    ManifestApiClient,
    import_manifest,
    resolve_ingest_mode,
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

_ENTITY_TYPE_MAP = {
    "people": "person",
    "person": "person",
    "persons": "person",
    "place": "location",
    "places": "location",
    "location": "location",
    "locations": "location",
    "org": "organization",
    "organization": "organization",
    "organizations": "organization",
    "date": "event",
    "dates": "event",
    "event": "event",
    "events": "event",
}


class CliIIIFClient:
    """ManifestApiClient adapter over the shared CLI transport."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def request(
        self, method: str, path: str, body: dict[str, Any] | None = None
    ) -> Any:
        return self._client.request(method, f"/api{path}", json=body)


@dataclass
class IIIFImportSummary:
    """Outcome of an IIIF import run."""

    iiif: str
    library_path: str
    manifests_seen: int = 0
    pages_seen: int = 0
    documents_created: int = 0
    documents_skipped: int = 0
    artifacts_created: int = 0
    artifacts_skipped: int = 0
    entities_created: int = 0
    entities_reused: int = 0
    annotations_created: int = 0
    annotations_skipped: int = 0
    annotation_skip_reasons: dict[str, list[str]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @classmethod
    def from_manifest_summary(
        cls,
        *,
        iiif: Path,
        manifest_summary: ImportSummary,
        manifests_seen: int,
    ) -> "IIIFImportSummary":
        return cls(
            iiif=str(iiif),
            library_path=manifest_summary.library_path,
            manifests_seen=manifests_seen,
            pages_seen=manifest_summary.pages_seen,
            documents_created=manifest_summary.documents_created,
            documents_skipped=manifest_summary.documents_skipped,
            entities_created=manifest_summary.entities_created,
            entities_reused=manifest_summary.entities_reused,
            warnings=list(manifest_summary.warnings),
        )


@dataclass
class _ParsedIIIF:
    nodes: list[dict[str, Any]]
    annotation_jobs: list[dict[str, Any]]
    manifests_seen: int
    warnings: list[str] = field(default_factory=list)


def import_iiif(
    client: ManifestApiClient,
    iiif_path: Path,
    library_path: str,
    *,
    copy_images: bool = False,
    ingest_mode: str | None = None,
) -> IIIFImportSummary:
    """Import IIIF Presentation 3.0 + W3C AnnotationPages through API routes."""

    resolve_ingest_mode(ingest_mode, copy_images)
    parsed = parse_iiif_directory(iiif_path.expanduser())
    if not parsed.nodes:
        raise ValueError(f"No IIIF manifests found under {iiif_path}")

    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".jsonl") as handle:
        for node in parsed.nodes:
            handle.write(json.dumps(node, ensure_ascii=False) + "\n")
        handle.flush()
        manifest_summary = import_manifest(
            client,
            Path(handle.name),
            library_path,
            copy_images=copy_images,
            ingest_mode=ingest_mode,
            # IIIF writes its own richer W3C transcript artifacts via
            # _import_transcript_artifacts; suppress the generic manifest
            # transcript write to avoid a duplicate per page (#1683/#1679).
            write_transcript_artifacts=False,
        )

    summary = IIIFImportSummary.from_manifest_summary(
        iiif=iiif_path,
        manifest_summary=manifest_summary,
        manifests_seen=parsed.manifests_seen,
    )
    summary.warnings.extend(parsed.warnings)
    artifacts_created, artifacts_skipped = _import_transcript_artifacts(
        client,
        parsed.nodes,
    )
    summary.artifacts_created = artifacts_created
    summary.artifacts_skipped = artifacts_skipped
    created, skipped, skip_reasons = _import_annotations(client, parsed.annotation_jobs)
    summary.annotations_created = created
    summary.annotations_skipped = skipped
    summary.annotation_skip_reasons = skip_reasons
    return summary


def import_iiif_via_http(
    *,
    iiif_path: Path,
    library_path: Path,
    api_base: str = DEFAULT_API_BASE,
    token_file: Path = DEFAULT_TOKEN_FILE,
    create_library: bool = True,
    copy_images: bool = False,
    ingest_mode: str | None = None,
    client: Any | None = None,
) -> IIIFImportSummary:
    """Convenience entry point for ``python -m fichero import-iiif``."""

    library_str = str(library_path.expanduser())
    if client is None:
        token = resolve_http_token(token_file, api_base=api_base)
        transport: ManifestApiClient = HttpManifestClient(api_base, token, library_str)
        if create_library:
            transport.request("POST", "/library", {"path": library_str})
    else:
        transport = CliIIIFClient(client)
        if create_library:
            client.request("POST", "/api/library", json={"path": library_str})
    return import_iiif(
        transport,
        iiif_path.expanduser(),
        library_str,
        copy_images=copy_images,
        ingest_mode=ingest_mode,
    )


def parse_iiif_directory(iiif_path: Path) -> _ParsedIIIF:
    """Read a IIIF file or directory into canonical manifest nodes."""

    root = iiif_path.expanduser()
    base_dir = root if root.is_dir() else root.parent
    docs = _load_json_documents(root)
    by_id = {
        str(doc.get("id") or doc.get("@id")): doc
        for _, doc in docs
        if isinstance(doc, dict) and (doc.get("id") or doc.get("@id"))
    }

    collections = [doc for _, doc in docs if _json_type(doc) == "Collection"]
    manifests = [doc for _, doc in docs if _json_type(doc) == "Manifest"]
    if collections:
        root_collection = collections[0]
    else:
        root_collection = {
            "id": f"file://{base_dir.resolve()}",
            "type": "Collection",
            "label": {"none": [base_dir.name]},
            "items": [{"id": _json_id(manifest), "type": "Manifest"} for manifest in manifests],
        }

    collection_external = _safe_external_id(_json_id(root_collection) or base_dir.name)
    nodes = [_collection_node(root_collection, collection_external, base_dir)]
    annotation_jobs: list[dict[str, Any]] = []
    seen_manifests: set[str] = set()
    seq = 0

    for manifest_ref in root_collection.get("items") or manifests:
        manifest = _resolve_ref(manifest_ref, by_id, base_dir)
        if not manifest or _json_type(manifest) != "Manifest":
            continue
        manifest_id = _json_id(manifest) or _label_text(manifest) or "manifest"
        if manifest_id in seen_manifests:
            continue
        seen_manifests.add(manifest_id)
        # A IIIF Manifest = one document. Each Canvas is a page that attaches
        # directly to the Collection folder — we do NOT emit a per-manifest
        # ``group`` folder (that produced one redundant single-page folder per
        # manifest). Manifest-level date/language fall through to the canvas.
        for canvas in manifest.get("items") or []:
            seq += 1
            canvas_node, jobs = _canvas_node(
                canvas,
                manifest=manifest,
                parent_external=collection_external,
                corpus=collection_external,
                sequence=seq,
                base_dir=base_dir,
                docs_by_id=by_id,
            )
            nodes.append(canvas_node)
            annotation_jobs.extend(jobs)

    return _ParsedIIIF(
        nodes=nodes,
        annotation_jobs=annotation_jobs,
        manifests_seen=len(seen_manifests),
    )


def _load_json_documents(root: Path) -> list[tuple[Path, dict[str, Any]]]:
    paths = (
        [root]
        if root.is_file()
        else sorted(root.rglob("*.json")) + sorted(root.rglob("*.jsonld"))
    )
    docs: list[tuple[Path, dict[str, Any]]] = []
    for path in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict):
            data.setdefault("_fichero_source_path", str(path))
            docs.append((path, data))
    return docs


def _collection_node(
    collection: dict[str, Any], external_id: str, base_dir: Path
) -> dict[str, Any]:
    metadata = _metadata_dict(collection)
    return {
        "canonical_version": CANONICAL_VERSION,
        "node_type": "group",
        "external_id": external_id,
        "parent_external_id": None,
        "corpus": external_id,
        "name": _label_text(collection) or base_dir.name,
        "page_label": None,
        "date": _nav_date(collection, metadata),
        "language": _language(collection),
        "text": None,
        "images": [],
        "entities": [],
        "claims": [],
        "metadata": {
            "source_assets": str(base_dir),
            "iiif_type": "Collection",
            "iiif_id": _json_id(collection),
            "iiif_metadata": metadata,
        },
    }


def _canvas_node(
    canvas: dict[str, Any],
    *,
    manifest: dict[str, Any],
    parent_external: str,
    corpus: str,
    sequence: int,
    base_dir: Path,
    docs_by_id: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    canvas_id = _json_id(canvas) or f"{parent_external}/canvas/{sequence}"
    external_id = _safe_external_id(canvas_id)
    metadata = _metadata_dict(canvas)
    annotation_pages = _annotation_pages(canvas, docs_by_id, base_dir)
    return (
        {
            "canonical_version": CANONICAL_VERSION,
            "node_type": "page",
            "external_id": external_id,
            "parent_external_id": parent_external,
            "corpus": corpus,
            "name": _label_text(canvas) or f"Page {sequence}",
            "sequence": sequence,
            "page_label": _label_text(canvas) or str(sequence),
            "date": _nav_date(canvas, metadata) or _nav_date(manifest, _metadata_dict(manifest)),
            "language": _language(canvas) or _language(manifest),
            "text": _canvas_text(canvas) or _text_from_pages(annotation_pages),
            "images": _canvas_images(canvas, base_dir),
            "entities": _entities_from_annotation_pages(annotation_pages, external_id),
            "claims": [],
            "metadata": {
                "iiif_type": "Canvas",
                "iiif_id": canvas_id,
                "iiif_metadata": metadata,
                "height": canvas.get("height"),
                "width": canvas.get("width"),
                "provenance": "import",
            },
        },
        _annotation_jobs_from_pages(annotation_pages, external_id),
    )


def _annotation_pages(
    canvas: dict[str, Any],
    docs_by_id: dict[str, dict[str, Any]],
    base_dir: Path,
) -> list[dict[str, Any]]:
    pages: list[dict[str, Any]] = []
    for page in canvas.get("annotations") or []:
        resolved = _resolve_ref(page, docs_by_id, base_dir)
        if resolved and _json_type(resolved) == "AnnotationPage":
            pages.append(resolved)
    return pages


def _entities_from_annotation_pages(
    pages: list[dict[str, Any]],
    canvas_external_id: str,
) -> list[dict[str, Any]]:
    entities: dict[str, dict[str, Any]] = {}
    for page in pages:
        for ann in page.get("items") or []:
            if "tagging" not in _motivations(ann):
                continue
            entity = _entity_from_annotation(ann, canvas_external_id)
            if not entity:
                continue
            key = entity["canonical_name"]
            if key in entities:
                aliases = set(entities[key].get("aliases") or []) | set(
                    entity.get("aliases") or []
                )
                entities[key]["aliases"] = sorted(aliases)
                continue
            entities[key] = entity
    return list(entities.values())


def _annotation_jobs_from_pages(
    pages: list[dict[str, Any]],
    canvas_external_id: str,
) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    for page in pages:
        page_id = _json_id(page)
        for ann in page.get("items") or []:
            selector = _selector(ann.get("target"))
            exact = _selector_exact(selector) or _body_text(ann.get("body"))
            motivations = _motivations(ann)
            entity = _entity_from_annotation(ann, canvas_external_id)
            jobs.append(
                {
                    "external_id": _json_id(ann)
                    or f"{page_id or canvas_external_id}#{len(jobs)}",
                    "canvas_external_id": canvas_external_id,
                    "kind": "highlight" if "tagging" in motivations else "note",
                    "text": exact,
                    "char_start": _selector_start(selector),
                    "char_end": _selector_end(selector),
                    "tags": sorted({"iiif", "w3c", *motivations}),
                    "entity_name": entity["canonical_name"] if entity else None,
                    "metadata": {
                        "iiif_annotation_page_id": page_id,
                        "w3c_annotation_id": _json_id(ann),
                        "w3c_motivation": sorted(motivations),
                        "w3c_selector": selector,
                        "w3c_body": ann.get("body"),
                    },
                }
            )
    return jobs


def _import_annotations(
    client: ManifestApiClient,
    jobs: list[dict[str, Any]],
) -> tuple[int, int, dict[str, list[str]]]:
    if not jobs:
        return 0, 0, {}
    docs = _list_items(client, "/documents?limit=500")
    doc_id_by_external = {
        str(doc.get("metadata", {}).get("canonical_external_id")): str(doc.get("id"))
        for doc in docs
        if doc.get("id") and doc.get("metadata", {}).get("canonical_external_id")
    }
    entities = _list_items(client, "/entities?limit=500")
    entity_id_by_name = {
        str(entity.get("canonical_name")): str(entity.get("id"))
        for entity in entities
        if entity.get("id") and entity.get("canonical_name")
    }
    existing_annotation_ids = {
        str((ann.get("metadata") or {}).get("w3c_annotation_id"))
        for ann in _list_items(client, "/annotations")
        if (ann.get("metadata") or {}).get("w3c_annotation_id")
    }
    created = 0
    skipped = 0
    skip_reasons: dict[str, list[str]] = {}

    def _record_skip(canvas_external_id: str, reason: str) -> None:
        skip_reasons.setdefault(canvas_external_id, []).append(reason)

    for job in jobs:
        if job["external_id"] in existing_annotation_ids:
            skipped += 1
            _record_skip(job["canvas_external_id"], "duplicate_annotation")
            continue
        document_id = doc_id_by_external.get(job["canvas_external_id"])
        if not document_id:
            skipped += 1
            _record_skip(job["canvas_external_id"], "missing_document")
            continue
        linked_entity_ids = []
        if job.get("entity_name") and job["entity_name"] in entity_id_by_name:
            linked_entity_ids.append(entity_id_by_name[job["entity_name"]])
        client.request(
            "POST",
            "/annotations",
            {
                "document_id": document_id,
                "kind": job["kind"],
                "char_start": job.get("char_start"),
                "char_end": job.get("char_end"),
                "text": job.get("text"),
                "tags": job.get("tags") or [],
                "linked_entity_ids": linked_entity_ids,
                "metadata": job.get("metadata") or {},
            },
        )
        created += 1
    return created, skipped, skip_reasons


def _import_transcript_artifacts(
    client: ManifestApiClient,
    nodes: list[dict[str, Any]],
) -> tuple[int, int]:
    """Create per-page transcription artifacts from imported IIIF text."""

    text_nodes = [
        node
        for node in nodes
        if node.get("node_type") == "page" and str(node.get("text") or "").strip()
    ]
    if not text_nodes:
        return 0, 0

    docs = _list_items(client, "/documents?limit=500")
    doc_id_by_external = {
        str(doc.get("metadata", {}).get("canonical_external_id")): str(doc.get("id"))
        for doc in docs
        if doc.get("id") and doc.get("metadata", {}).get("canonical_external_id")
    }

    created = 0
    skipped = 0
    for node in text_nodes:
        document_id = doc_id_by_external.get(str(node.get("external_id")))
        if not document_id:
            skipped += 1
            continue
        text = str(node.get("text") or "").strip()
        if _has_imported_transcript_artifact(client, document_id, text):
            skipped += 1
            continue
        metadata = dict(node.get("metadata") or {})
        client.request(
            "POST",
            "/artifacts/",
            {
                "document_id": document_id,
                "artifact_type": "transcription",
                "content": text,
                "data": {
                    "provenance": "import",
                    "source": "iiif_w3c",
                    "canonical_external_id": node.get("external_id"),
                    "iiif_id": metadata.get("iiif_id"),
                    "page_label": node.get("page_label"),
                    "language": node.get("language"),
                },
                "provider": "iiif-import",
                "model": "w3c-annotation",
                "step_name": "import-iiif",
                "reviewed": True,
            },
        )
        created += 1
    return created, skipped


def _has_imported_transcript_artifact(
    client: ManifestApiClient,
    document_id: str,
    content: str,
) -> bool:
    artifacts = _list_items(
        client,
        f"/artifacts/document/{document_id}?artifact_type=transcription&include_descendants=false&limit=200",
    )
    for artifact in artifacts:
        if artifact.get("content") != content:
            continue
        data = artifact.get("data") or {}
        if (
            artifact.get("provider") == "iiif-import"
            or data.get("source") == "iiif_w3c"
        ):
            return True
    return False


def _list_items(client: ManifestApiClient, path: str) -> list[dict[str, Any]]:
    response = client.request("GET", path)
    if isinstance(response, dict):
        return list(
            response.get("items")
            or response.get("entities")
            or response.get("artifacts")
            or []
        )
    if isinstance(response, list):
        return response
    return []


def _canvas_text(canvas: dict[str, Any]) -> str | None:
    for page in list(canvas.get("annotations") or []) + list(canvas.get("items") or []):
        for ann in page.get("items") or []:
            if "supplementing" in _motivations(ann):
                text = _body_text(ann.get("body"))
                if text:
                    return text
    return None


def _text_from_pages(pages: list[dict[str, Any]]) -> str | None:
    """Full transcript from the (already resolved) W3C AnnotationPages — the
    ``supplementing`` TextualBody. The converter writes it to the external
    annotation page, not inline on the Canvas, so ``_canvas_text`` misses it."""
    for page in pages:
        for ann in page.get("items") or []:
            if "supplementing" in _motivations(ann):
                text = _body_text(ann.get("body"))
                if text:
                    return text
    return None


def _canvas_images(canvas: dict[str, Any], base_dir: Path) -> list[dict[str, Any]]:
    images: list[dict[str, Any]] = []
    for page in canvas.get("items") or []:
        for ann in page.get("items") or []:
            if "painting" not in _motivations(ann):
                continue
            bodies = ann.get("body")
            for item in bodies if isinstance(bodies, list) else [bodies]:
                if not isinstance(item, dict):
                    continue
                image_id = _json_id(item)
                source_path = item.get("source_path") or item.get("path") or image_id
                images.append(
                    {
                        "role": item.get("role") or "enhanced",
                        "path": image_id,
                        "source_path": _local_path(source_path, base_dir),
                        "is_representative": True,
                        "metadata": {
                            "iiif_body": item,
                            "format": item.get("format"),
                            "height": item.get("height"),
                            "width": item.get("width"),
                        },
                    }
                )
    return images


def _entity_from_annotation(
    ann: dict[str, Any],
    canvas_external_id: str,
) -> dict[str, Any] | None:
    body = ann.get("body")
    bodies = body if isinstance(body, list) else [body]
    for item in bodies:
        if not isinstance(item, dict):
            continue
        # The converter wraps each entity body as a W3C SpecificResource whose
        # ``source`` (a TextualBody) carries the real name (``value``) + type
        # (``dc:type``). Descend into it so we get "San Pablo"/"Location", not
        # the slugified id ("san-pablo") or a quote fragment.
        value_body = item
        src = item.get("source")
        if isinstance(src, dict):
            value_body = src
        text = _body_text(value_body) or _body_text(item)
        entity_id = _json_id(value_body) or _json_id(item)
        if not text:
            # Without a real name this isn't an entity (e.g. a plain text-quote
            # highlight) — skip rather than inventing a slug entity.
            continue
        canonical_name = text
        selector = _selector(ann.get("target"))
        return {
            "external_id": entity_id or _json_id(ann) or canonical_name,
            "canonical_name": canonical_name,
            "entity_type": _entity_type(value_body),
            "aliases": [text] if text and text != canonical_name else [],
            "language": _language(item),
            "metadata": {
                "source": "iiif-w3c",
                "w3c_annotation_id": _json_id(ann),
                "w3c_entity_body_id": entity_id,
                "w3c_selector": selector,
                "canvas_external_id": canvas_external_id,
            },
        }
    return None


def _entity_type(body: dict[str, Any]) -> str:
    raw = (
        body.get("dc:type")
        or body.get("entity_type")
        or body.get("classification")
        or body.get("category")
        or "other"
    )
    if isinstance(raw, list):
        raw = raw[0] if raw else "other"
    normalized = str(raw).strip().lower()
    mapped = _ENTITY_TYPE_MAP.get(normalized, normalized)
    return mapped if mapped in _VALID_ENTITY_TYPES else "other"


def _resolve_ref(
    ref: dict[str, Any],
    by_id: dict[str, dict[str, Any]],
    base_dir: Path,
) -> dict[str, Any] | None:
    if not isinstance(ref, dict):
        return None
    if ref.get("items"):
        return ref
    ref_id = _json_id(ref)
    if ref_id in by_id:
        return by_id[ref_id]
    if ref_id:
        parsed = urllib.parse.urlparse(ref_id)
        path = Path(urllib.parse.unquote(parsed.path if parsed.scheme == "file" else ref_id))
        if not path.is_absolute():
            path = base_dir / path
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return None
            if isinstance(data, dict):
                return data
    return ref


def _json_type(obj: dict[str, Any]) -> str | None:
    value = obj.get("type") or obj.get("@type")
    if isinstance(value, list):
        value = value[0] if value else None
    if not value:
        return None
    return str(value).rsplit("/", 1)[-1]


def _json_id(obj: dict[str, Any] | None) -> str | None:
    if not isinstance(obj, dict):
        return None
    value = obj.get("id") or obj.get("@id")
    return str(value) if value else None


def _label_text(obj: dict[str, Any]) -> str | None:
    label = obj.get("label")
    if isinstance(label, str):
        return label
    if isinstance(label, dict):
        for key in ("en", "none", "@none"):
            value = label.get(key)
            if isinstance(value, list) and value:
                return str(value[0])
            if isinstance(value, str):
                return value
        for value in label.values():
            if isinstance(value, list) and value:
                return str(value[0])
            if isinstance(value, str):
                return value
    return None


def _metadata_dict(obj: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for row in obj.get("metadata") or []:
        if not isinstance(row, dict):
            continue
        label = _label_text({"label": row.get("label")})
        value = _label_text({"label": row.get("value")}) or row.get("value")
        if label:
            result[str(label)] = value
    return result


def _nav_date(obj: dict[str, Any], metadata: dict[str, Any]) -> str | None:
    value = obj.get("navDate") or obj.get("nav_date") or metadata.get("date") or metadata.get("Date")
    return str(value) if value else None


def _language(obj: dict[str, Any]) -> str | None:
    value = obj.get("language")
    if isinstance(value, list):
        return str(value[0]) if value else None
    return str(value) if value else None


def _body_text(body: Any) -> str | None:
    if isinstance(body, str):
        return body
    if isinstance(body, list):
        parts = [_body_text(item) for item in body]
        return "\n".join(part for part in parts if part) or None
    if not isinstance(body, dict):
        return None
    for key in ("value", "text", "label", "exact", "name"):
        value = body.get(key)
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            return _label_text({"label": value})
    return None


def _motivations(ann: dict[str, Any]) -> set[str]:
    value = ann.get("motivation") or ann.get("motivatedBy") or []
    if isinstance(value, str):
        return {value}
    if isinstance(value, list):
        return {str(item) for item in value}
    return set()


def _selector(target: Any) -> dict[str, Any] | None:
    if isinstance(target, list):
        for item in target:
            selector = _selector(item)
            if selector:
                return selector
    if not isinstance(target, dict):
        return None
    selector = target.get("selector")
    if isinstance(selector, list):
        for item in selector:
            if isinstance(item, dict) and _json_type(item) in {
                "TextPositionSelector",
                "TextQuoteSelector",
            }:
                return item
        return selector[0] if selector else None
    return selector if isinstance(selector, dict) else None


def _selector_start(selector: dict[str, Any] | None) -> int | None:
    if not selector:
        return None
    value = selector.get("start")
    return int(value) if isinstance(value, int | str) and str(value).isdigit() else None


def _selector_end(selector: dict[str, Any] | None) -> int | None:
    if not selector:
        return None
    value = selector.get("end")
    return int(value) if isinstance(value, int | str) and str(value).isdigit() else None


def _selector_exact(selector: dict[str, Any] | None) -> str | None:
    if not selector:
        return None
    value = selector.get("exact")
    return str(value) if value else None


def _local_path(value: str | None, base_dir: Path) -> str | None:
    if not value:
        return None
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme == "file":
        return urllib.parse.unquote(parsed.path)
    if parsed.scheme in {"http", "https"}:
        return value
    path = Path(urllib.parse.unquote(value))
    if not path.is_absolute():
        path = base_dir / path
    return str(path)


def _safe_external_id(value: str) -> str:
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme == "file":
        value = urllib.parse.unquote(parsed.path)
    return (
        value.strip()
        .replace("://", "__")
        .replace("/", "__")
        .replace("#", "__")
        .replace("?", "__")
        .strip("_")
    )

__all__ = [name for name in dir() if not name.startswith("__")]

__all__ = [
    'Any',
    'CANONICAL_VERSION',
    'DEFAULT_API_BASE',
    'DEFAULT_TOKEN_FILE',
    'HttpManifestClient',
    'IIIFImportSummary',
    'ImportSummary',
    'ManifestApiClient',
    'Path',
    '_ENTITY_TYPE_MAP',
    '_ParsedIIIF',
    '_VALID_ENTITY_TYPES',
    '_annotation_jobs_from_pages',
    '_annotation_pages',
    '_body_text',
    '_canvas_images',
    '_canvas_node',
    '_canvas_text',
    '_collection_node',
    '_entities_from_annotation_pages',
    '_entity_from_annotation',
    '_entity_type',
    '_has_imported_transcript_artifact',
    '_import_annotations',
    '_import_transcript_artifacts',
    '_json_id',
    '_json_type',
    '_label_text',
    '_language',
    '_list_items',
    '_load_json_documents',
    '_local_path',
    '_metadata_dict',
    '_motivations',
    '_nav_date',
    '_resolve_ref',
    '_safe_external_id',
    '_selector',
    '_selector_end',
    '_selector_exact',
    '_selector_start',
    '_text_from_pages',
    'annotations',
    'dataclass',
    'field',
    'import_iiif',
    'import_iiif_via_http',
    'import_manifest',
    'json',
    'parse_iiif_directory',
    'resolve_ingest_mode',
    'tempfile',
    'urllib',
]
