"""Document export services."""

from __future__ import annotations

import re
import shutil
import zipfile
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Literal
from xml.sax.saxutils import escape

from fichero.db import Database
from fichero.models import (
    Artifact,
    DocType,
    Document,
    FileType,
    KnowledgeClaim,
    KnowledgeEntity,
)
from fichero.storage import get_display, resolve_source


IMAGE_SUFFIXES = {
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".tif",
    ".tiff",
    ".bmp",
    ".heic",
}


@dataclass
class ExportedFile:
    """A file written by an export operation."""

    path: str
    kind: str
    document_id: str | None = None


@dataclass
class MarkdownFolderExportResult:
    """Result metadata for a Markdown folder export."""

    output_path: str
    files: list[ExportedFile] = field(default_factory=list)
    assets: list[ExportedFile] = field(default_factory=list)
    document_count: int = 0


@dataclass
class WordExportResult:
    """Result metadata for a Word export."""

    output_path: str
    document_count: int
    bytes_written: int


@dataclass
class ExcelExportResult:
    """Result metadata for an Excel export."""

    output_path: str
    document_count: int
    entity_count: int
    claim_count: int
    bytes_written: int


@dataclass
class EleventySiteExportResult:
    """Result metadata for an 11ty/Netlify static-site export."""

    output_path: str
    document_count: int
    collection_count: int
    files: list[ExportedFile] = field(default_factory=list)
    assets: list[ExportedFile] = field(default_factory=list)


ExportGranularity = Literal["page", "expediente-folder", "box-collection"]


def iter_export_records(
    db: Database,
    target_id: str | None = None,
    recursive: bool = True,
    granularity: ExportGranularity = "page",
) -> Iterable[dict[str, Any]]:
    """Yield plain export records shared by static export emitters."""
    root, documents = _collect_documents(db, target_id=target_id, recursive=recursive)
    by_id = {d.id: d for d in db.all(Document)}
    root_id = root.id if root else None
    doc_ids = {doc.id for doc in documents}

    for doc in documents:
        provenance = _document_export_provenance(doc, by_id, root_id)
        scope = _scope_for_document(doc, by_id, root_id, granularity)
        yield {
            "record_type": "document",
            "granularity": granularity,
            **scope,
            **provenance,
            "id": doc.id,
            "document_id": doc.id,
            "name": doc.name,
            "doc_type": doc.doc_type.value,
            "file_type": doc.file_type.value if doc.file_type else None,
            "path": doc.path,
            "parent_id": doc.parent_id,
            "sequence": doc.sequence,
            "page_content": doc.page_content,
            "metadata": doc.metadata,
            "provenance_chain": doc.provenance_chain,
            "workflow_runs": doc.workflow_runs,
        }

    entities, claims = _knowledge_graph_rows(db, documents)
    for entity in entities:
        for scope in _knowledge_scope_records(
            entity.source_document_ids,
            by_id,
            root_id,
            granularity,
            allowed_doc_ids=doc_ids,
        ):
            yield {
                "record_type": "entity",
                "granularity": granularity,
                **scope,
                "id": entity.id,
                "entity_id": entity.id,
                "canonical_name": entity.canonical_name,
                "entity_type": entity.entity_type.value,
                "aliases": entity.aliases,
                "description": entity.description,
                "metadata": entity.metadata,
                "source_document_ids": entity.source_document_ids,
            }

    for claim in claims:
        source_ids = [
            doc_id
            for doc_id in [claim.source_document_id, *claim.source_ids]
            if isinstance(doc_id, str)
        ]
        for scope in _knowledge_scope_records(
            source_ids,
            by_id,
            root_id,
            granularity,
            allowed_doc_ids=doc_ids,
            page_label=claim.source_page_label,
            excerpt=claim.source_excerpt,
        ):
            yield {
                "record_type": "claim",
                "granularity": granularity,
                **scope,
                "id": claim.id,
                "claim_id": claim.id,
                "text": claim.text,
                "claim_type": claim.claim_type.value if claim.claim_type else None,
                "epistemic_status": (
                    claim.epistemic_status.value if claim.epistemic_status else None
                ),
                "entity_ids": claim.entity_ids,
                "metadata": claim.metadata,
                "source_document_id": claim.source_document_id,
                "source_page_label": claim.source_page_label,
                "source_excerpt": claim.source_excerpt,
            }


def export_eleventy_site(
    db: Database,
    output_path: str | Path,
    target_id: str | None = None,
    recursive: bool = True,
    overwrite: bool = False,
    package_path: str | Path | None = None,
    site_title: str | None = None,
) -> EleventySiteExportResult:
    """Export a folder (or subfolder) as a buildable 11ty/Netlify static site.

    The third export target alongside Markdown and Excel (#2535), reusing the
    same document-collection + asset-copy plumbing. Folder structure maps to
    11ty collections: each top-level folder under the export root becomes a
    collection, nested folders become subcollections, and each document is an
    item page (Markdown + YAML front matter with metadata, image copied in).

    Produces a self-contained project that builds with ``npx @11ty/eleventy``
    and deploys to Netlify (``netlify.toml`` publishes ``_site``). Assets are
    copied into the site so it is portable/publishable — a static bundle, not
    the running app (which renders via storage endpoints, not local paths).
    """
    output_dir = Path(output_path).expanduser()
    if output_dir.exists() and any(output_dir.iterdir()) and not overwrite:
        raise FileExistsError(
            f"Export folder already exists and is not empty: {output_dir}"
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    src_dir = output_dir / "src"
    src_dir.mkdir(exist_ok=True)

    root, documents = _collect_documents(db, target_id=target_id, recursive=recursive)
    package = Path(package_path).expanduser() if package_path else None
    # by_id powers the ancestor walk that reconstructs each doc's collection
    # path. ponytail: db.all() is O(library); fine for a deliberate batch
    # export, swap to a parent-chain query if it ever needs to stream.
    by_id = {d.id: d for d in db.all(Document)}
    root_id = root.id if root else None

    title = site_title or (root.name if root else "Fichero Export")
    result = EleventySiteExportResult(
        output_path=str(output_dir),
        document_count=len(documents),
        collection_count=0,
    )

    collections: set[str] = set()
    used_per_dir: dict[str, set[str]] = {}
    for doc in documents:
        rel_parts = _collection_path_for(doc, by_id, root_id)
        if rel_parts:
            collections.add(rel_parts[0])
        doc_dir = src_dir.joinpath(*rel_parts) if rel_parts else src_dir
        doc_dir.mkdir(parents=True, exist_ok=True)

        assets_dir = doc_dir / "assets"
        asset_refs: list[_AssetRef] = []
        if _is_image_document(doc):
            assets_dir.mkdir(exist_ok=True)
            asset_refs = _copy_document_assets(doc, assets_dir, package)

        used = used_per_dir.setdefault(str(doc_dir), set())
        filename = _unique_filename(_slugify(doc.name), used, ".md")
        page_path = doc_dir / filename
        page_path.write_text(
            _render_eleventy_item(db, doc, asset_refs, rel_parts),
            encoding="utf-8",
        )
        result.files.append(
            ExportedFile(path=str(page_path), kind="page", document_id=doc.id)
        )
        result.assets.extend(
            ExportedFile(path=str(a.path), kind="asset", document_id=doc.id)
            for a in asset_refs
        )

    result.collection_count = len(collections)

    # Site scaffolding — a minimal but real, buildable 11ty + Netlify project.
    (src_dir / "index.md").write_text(
        _render_eleventy_index(title, sorted(collections), documents),
        encoding="utf-8",
    )
    for name, content in _eleventy_scaffold(title).items():
        (output_dir / name).write_text(content, encoding="utf-8")
        result.files.append(ExportedFile(path=str(output_dir / name), kind="scaffold"))

    return result


def _collection_path_for(
    doc: Document,
    by_id: dict[str, Document],
    root_id: str | None,
) -> list[str]:
    """Slugged folder names from the export root down to ``doc``'s parent."""
    parts: list[str] = []
    cur = by_id.get(doc.parent_id) if doc.parent_id else None
    seen: set[str] = set()
    while cur is not None and cur.id != root_id and cur.id not in seen:
        seen.add(cur.id)
        if cur.doc_type == DocType.folder:
            parts.append(_slugify(cur.name))
        cur = by_id.get(cur.parent_id) if cur.parent_id else None
    return list(reversed(parts))


def _folder_chain_for(
    doc: Document,
    by_id: dict[str, Document],
    root_id: str | None,
) -> list[Document]:
    chain: list[Document] = []
    cur = doc if doc.doc_type == DocType.folder else by_id.get(doc.parent_id or "")
    seen: set[str] = set()
    while cur is not None and cur.id not in seen:
        seen.add(cur.id)
        if cur.doc_type == DocType.folder:
            chain.append(cur)
        if cur.id == root_id:
            break
        cur = by_id.get(cur.parent_id or "")
    chain.reverse()
    if chain and root_id and chain[0].id == root_id:
        chain = chain[1:]
    return chain


def _document_export_provenance(
    doc: Document,
    by_id: dict[str, Document],
    root_id: str | None,
) -> dict[str, Any]:
    folders = _folder_chain_for(doc, by_id, root_id)
    box = folders[0] if folders else None
    expediente = folders[-1] if folders else None
    page_label = doc.page_label or doc.metadata.get("page_label") or (
        str(doc.sequence) if doc.sequence is not None else None
    )
    return {
        "found_in_document_id": doc.id,
        "found_in_document_name": doc.name,
        "found_in_page_id": doc.id,
        "found_in_page_label": page_label,
        "found_in_expediente_id": expediente.id if expediente else None,
        "found_in_expediente_name": expediente.name if expediente else None,
        "found_in_box_collection_id": box.id if box else None,
        "found_in_box_collection_name": box.name if box else None,
    }


def _scope_for_document(
    doc: Document,
    by_id: dict[str, Document],
    root_id: str | None,
    granularity: ExportGranularity,
) -> dict[str, Any]:
    provenance = _document_export_provenance(doc, by_id, root_id)
    if granularity == "page":
        return {
            "scope_id": doc.id,
            "scope_name": doc.name,
            "scope_kind": "page",
        }
    if granularity == "expediente-folder":
        return {
            "scope_id": provenance["found_in_expediente_id"] or doc.id,
            "scope_name": provenance["found_in_expediente_name"] or doc.name,
            "scope_kind": "expediente-folder",
        }
    return {
        "scope_id": provenance["found_in_box_collection_id"] or doc.id,
        "scope_name": provenance["found_in_box_collection_name"] or doc.name,
        "scope_kind": "box-collection",
    }


def _knowledge_scope_records(
    source_document_ids: list[str],
    by_id: dict[str, Document],
    root_id: str | None,
    granularity: ExportGranularity,
    *,
    allowed_doc_ids: set[str],
    page_label: str | None = None,
    excerpt: str | None = None,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen_scope_ids: set[str] = set()
    for doc_id in source_document_ids:
        if doc_id not in allowed_doc_ids:
            continue
        doc = by_id.get(doc_id)
        if doc is None:
            continue
        provenance = _document_export_provenance(doc, by_id, root_id)
        provenance["found_in_page_label"] = (
            page_label or provenance["found_in_page_label"]
        )
        if excerpt is not None:
            provenance["found_in_excerpt"] = excerpt
        scope = _scope_for_document(doc, by_id, root_id, granularity)
        if scope["scope_id"] in seen_scope_ids:
            continue
        seen_scope_ids.add(scope["scope_id"])
        records.append({**scope, **provenance})
    return records


def _render_eleventy_item(
    db: Database,
    doc: Document,
    assets: Iterable[_AssetRef],
    collection_path: list[str],
) -> str:
    lines = [
        "---",
        f"title: {_escape_frontmatter(doc.name)}",
        f"id: {doc.id}",
        f"doc_type: {doc.doc_type.value}",
        f"file_type: {doc.file_type.value if doc.file_type else ''}",
    ]
    if collection_path:
        # 11ty groups pages by tag → the top-level folder is the collection.
        lines.append(f"tags:\n  - {_escape_frontmatter(collection_path[0])}")
        lines.append(f"collection_path: {_escape_frontmatter('/'.join(collection_path))}")
    lines.extend(["---", "", f"# {doc.name}", ""])

    for asset in assets:
        lines.extend([f"![{doc.name}]({asset.markdown_path})", ""])

    content = (doc.page_content or "").strip()
    if content:
        lines.extend([content, ""])
    artifacts = _text_artifacts(db, doc.id)
    if artifacts:
        lines.extend(["## Artifacts", ""])
        for artifact in artifacts:
            lines.extend(
                [f"### {artifact.artifact_type}", "", artifact.content.strip(), ""]
            )
    if not content and not artifacts and not list(assets):
        lines.extend(["_No text content available._", ""])

    return "\n".join(lines).rstrip() + "\n"


def _render_eleventy_index(
    title: str,
    collections: list[str],
    documents: list[Document],
) -> str:
    lines = [
        "---",
        f"title: {_escape_frontmatter(title)}",
        "---",
        "",
        f"# {title}",
        "",
        f"Exported: {datetime.now().isoformat(timespec='seconds')}",
        "",
        f"{len(documents)} item(s) across {len(collections)} collection(s).",
        "",
    ]
    if collections:
        lines.extend(["## Collections", ""])
        lines.extend(f"- {name}" for name in collections)
    return "\n".join(lines).rstrip() + "\n"


def _eleventy_scaffold(title: str) -> dict[str, str]:
    """The static-site project files that make the export buildable + deployable."""
    package_json = json.dumps(
        {
            "name": _slugify(title).lower() or "fichero-site",
            "version": "1.0.0",
            "private": True,
            "scripts": {"build": "eleventy", "serve": "eleventy --serve"},
            "devDependencies": {"@11ty/eleventy": "^3.0.0"},
        },
        indent=2,
    )
    eleventy_config = (
        "module.exports = function (eleventyConfig) {\n"
        '  eleventyConfig.addPassthroughCopy("src/**/assets");\n'
        "  return {\n"
        '    dir: { input: "src", output: "_site" },\n'
        '    markdownTemplateEngine: "njk",\n'
        "  };\n"
        "};\n"
    )
    netlify_toml = (
        "[build]\n"
        '  command = "npx @11ty/eleventy"\n'
        '  publish = "_site"\n'
    )
    readme = (
        f"# {title}\n\n"
        "Static site exported from Fichero (11ty + Netlify).\n\n"
        "## Build\n\n"
        "```sh\n"
        "npm install\n"
        "npm run build   # outputs _site/\n"
        "npm run serve   # local preview\n"
        "```\n\n"
        "Deploy `_site/` to Netlify (or run `netlify deploy`). "
        "Collections map to folders, item pages carry metadata front matter, "
        "and images are bundled under each folder's `assets/`.\n"
    )
    return {
        "package.json": package_json,
        ".eleventy.js": eleventy_config,
        "netlify.toml": netlify_toml,
        "README.md": readme,
    }


def export_markdown_folder(
    db: Database,
    output_path: str | Path,
    target_id: str | None = None,
    recursive: bool = True,
    include_assets: bool = True,
    overwrite: bool = False,
    package_path: str | Path | None = None,
) -> MarkdownFolderExportResult:
    """Export documents as a Markdown folder.

    The folder contains ``index.md``, one Markdown file per exported
    non-folder document, an ``assets/`` directory for copied image files, and a
    lightweight ``knowledge-graph.md`` placeholder. KG rendering is kept out of
    this service so the export backend stays disjoint from KG code.
    """

    output_dir = Path(output_path).expanduser()
    if output_dir.exists() and any(output_dir.iterdir()) and not overwrite:
        raise FileExistsError(
            f"Export folder already exists and is not empty: {output_dir}"
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    assets_dir = output_dir / "assets"
    if include_assets:
        assets_dir.mkdir(exist_ok=True)

    root, documents = _collect_documents(db, target_id=target_id, recursive=recursive)
    package = Path(package_path).expanduser() if package_path else None

    result = MarkdownFolderExportResult(
        output_path=str(output_dir),
        document_count=len(documents),
    )
    used_names: set[str] = set()
    index_links: list[tuple[str, str]] = []

    for doc in documents:
        filename = _unique_filename(_slugify(doc.name), used_names, ".md")
        doc_path = output_dir / filename
        asset_refs = (
            _copy_document_assets(doc, assets_dir, package) if include_assets else []
        )
        body = _render_document_markdown(db, doc, asset_refs)
        doc_path.write_text(body, encoding="utf-8")
        result.files.append(
            ExportedFile(path=str(doc_path), kind="markdown", document_id=doc.id)
        )
        result.assets.extend(
            ExportedFile(path=str(asset.path), kind="asset", document_id=doc.id)
            for asset in asset_refs
        )
        index_links.append((doc.name, filename))

    index_path = output_dir / "index.md"
    index_path.write_text(_render_index(root, index_links), encoding="utf-8")
    result.files.insert(0, ExportedFile(path=str(index_path), kind="index"))

    kg_path = output_dir / "knowledge-graph.md"
    kg_path.write_text(_render_kg_placeholder(), encoding="utf-8")
    result.files.append(ExportedFile(path=str(kg_path), kind="knowledge-graph"))

    return result


def export_word_docx(
    db: Database,
    output_path: str | Path,
    target_id: str | None = None,
    recursive: bool = True,
    overwrite: bool = False,
    package_path: str | Path | None = None,
    include_knowledge_graph: bool = True,
) -> WordExportResult:
    """Export documents as a minimal Word .docx file.

    This intentionally avoids optional dependencies. It writes a valid Office
    Open XML package with text content and, for image documents, a simple
    two-column table containing the image and its transcription/content.
    """

    output_file = Path(output_path).expanduser()
    if output_file.suffix.lower() != ".docx":
        output_file = output_file.with_suffix(".docx")
    if output_file.exists() and not overwrite:
        raise FileExistsError(f"Export file already exists: {output_file}")
    output_file.parent.mkdir(parents=True, exist_ok=True)

    root, documents = _collect_documents(db, target_id=target_id, recursive=recursive)
    package = Path(package_path).expanduser() if package_path else None

    media: list[tuple[str, Path, str]] = []
    body_parts: list[str] = [_docx_heading(root.name if root else "Library Export", 1)]

    for index, doc in enumerate(documents, start=1):
        text = _document_text(db, doc)
        image_source = _docx_image_source(doc, package)
        if image_source:
            rel_id = f"rIdImage{index}"
            media_name = f"image{index}{image_source.suffix.lower() or '.jpg'}"
            media.append((rel_id, image_source, media_name))
            body_parts.append(_docx_image_text_table(doc.name, rel_id, text))
        else:
            body_parts.append(_docx_heading(doc.name, 2))
            body_parts.extend(_docx_paragraph(part) for part in _paragraphs(text))

    if include_knowledge_graph:
        appendix = _docx_knowledge_graph_appendix(db, documents)
        if appendix:
            body_parts.extend(appendix)

    document_xml = _docx_document(body_parts)
    rels_xml = _docx_document_rels(media)
    content_types_xml = _docx_content_types(media)

    with zipfile.ZipFile(output_file, "w", compression=zipfile.ZIP_DEFLATED) as docx:
        docx.writestr(
            "mimetype",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        docx.writestr("_rels/.rels", _package_rels())
        docx.writestr("[Content_Types].xml", content_types_xml)
        docx.writestr("docProps/core.xml", _core_props())
        docx.writestr("docProps/app.xml", _app_props())
        docx.writestr("word/document.xml", document_xml)
        docx.writestr("word/_rels/document.xml.rels", rels_xml)
        docx.writestr("word/styles.xml", _docx_styles())
        for _, source, media_name in media:
            docx.write(source, f"word/media/{media_name}")

    return WordExportResult(
        output_path=str(output_file),
        document_count=len(documents),
        bytes_written=output_file.stat().st_size,
    )


def export_excel_xlsx(
    db: Database,
    output_path: str | Path,
    target_id: str | None = None,
    recursive: bool = True,
    overwrite: bool = False,
) -> ExcelExportResult:
    """Export documents, entities, and claims as an .xlsx workbook."""

    output_file = Path(output_path).expanduser()
    if output_file.suffix.lower() != ".xlsx":
        output_file = output_file.with_suffix(".xlsx")
    if output_file.exists() and not overwrite:
        raise FileExistsError(f"Export file already exists: {output_file}")
    output_file.parent.mkdir(parents=True, exist_ok=True)

    _, documents = _collect_documents(db, target_id=target_id, recursive=recursive)
    entities, claims = _knowledge_graph_rows(db, documents)

    document_rows = [
        {
            "id": doc.id,
            "name": doc.name,
            "parent_id": doc.parent_id,
            "doc_type": doc.doc_type.value,
            "file_type": doc.file_type.value if doc.file_type else "",
            "path": doc.path,
            "sequence": doc.sequence,
            "transcription": _document_text(db, doc),
            "metadata": doc.metadata,
            "created_at": doc.created_at,
            "updated_at": doc.updated_at,
        }
        for doc in documents
    ]
    entity_rows = [
        {
            "id": entity.id,
            "canonical_name": entity.canonical_name,
            "entity_type": entity.entity_type.value,
            "aliases": entity.aliases,
            "description": entity.description,
            "source_document_ids": entity.source_document_ids,
            "metadata": entity.metadata,
            "created_at": entity.created_at,
            "updated_at": entity.updated_at,
        }
        for entity in entities
    ]
    claim_rows = [
        {
            "id": claim.id,
            "text": claim.text,
            "source_document_id": claim.source_document_id,
            "source_page_label": claim.source_page_label,
            "source_excerpt": claim.source_excerpt,
            "claim_type": claim.claim_type.value if claim.claim_type else "",
            "epistemic_status": (
                claim.epistemic_status.value if claim.epistemic_status else ""
            ),
            "subject_canonical": claim.subject_canonical,
            "predicate_verb": claim.predicate_verb,
            "object_phrase": claim.object_phrase,
            "entity_ids": claim.entity_ids,
            "confidence": claim.confidence,
            "metadata": claim.metadata,
            "created_at": claim.created_at,
            "updated_at": claim.updated_at,
        }
        for claim in claims
    ]

    _write_xlsx(
        output_file,
        {
            "Documents": document_rows,
            "Entities": entity_rows,
            "Claims": claim_rows,
        },
    )

    return ExcelExportResult(
        output_path=str(output_file),
        document_count=len(document_rows),
        entity_count=len(entity_rows),
        claim_count=len(claim_rows),
        bytes_written=output_file.stat().st_size,
    )


@dataclass(frozen=True)
class _AssetRef:
    path: str
    markdown_path: str


def _collect_documents(
    db: Database,
    target_id: str | None,
    recursive: bool,
) -> tuple[Document | None, list[Document]]:
    root = db.get(Document, target_id) if target_id else None
    if target_id and root is None:
        raise ValueError(f"Document not found: {target_id}")

    if root is None:
        candidates = list(db.all(Document))
    elif root.doc_type == DocType.folder:
        candidates = (
            _descendants(db, root.id)
            if recursive
            else list(db.query(Document, parent_id=root.id))
        )
    else:
        candidates = [root]

    documents = [doc for doc in candidates if doc.doc_type != DocType.folder]
    documents.sort(
        key=lambda doc: (doc.parent_id or "", doc.sequence or 0, doc.name.lower())
    )
    return root, documents


def _descendants(db: Database, root_id: str) -> list[Document]:
    result: list[Document] = []
    queue = list(db.query(Document, parent_id=root_id))
    seen: set[str] = set()

    while queue:
        doc = queue.pop(0)
        if doc.id in seen:
            continue
        seen.add(doc.id)
        result.append(doc)
        queue.extend(db.query(Document, parent_id=doc.id))

    return result


def _render_document_markdown(
    db: Database,
    doc: Document,
    assets: Iterable[_AssetRef],
) -> str:
    lines = [
        "---",
        f"id: {doc.id}",
        f"title: {_escape_frontmatter(doc.name)}",
        f"doc_type: {doc.doc_type.value}",
        f"file_type: {doc.file_type.value if doc.file_type else ''}",
        "---",
        "",
        f"# {doc.name}",
        "",
    ]

    for asset in assets:
        lines.extend([f"![{doc.name}]({asset.markdown_path})", ""])

    content = (doc.page_content or "").strip()
    if content:
        lines.extend([content, ""])

    artifacts = _text_artifacts(db, doc.id)
    if artifacts:
        lines.extend(["## Artifacts", ""])
        for artifact in artifacts:
            lines.extend(
                [f"### {artifact.artifact_type}", "", artifact.content.strip(), ""]
            )

    if not content and not artifacts and not assets:
        lines.extend(["_No text content available._", ""])

    return "\n".join(lines).rstrip() + "\n"


def _document_text(db: Database, doc: Document) -> str:
    parts = []
    if doc.page_content and doc.page_content.strip():
        parts.append(doc.page_content.strip())
    for artifact in _text_artifacts(db, doc.id):
        parts.append(f"{artifact.artifact_type}: {artifact.content.strip()}")
    return "\n\n".join(parts).strip() or "No text content available."


def _docx_knowledge_graph_appendix(
    db: Database,
    documents: list[Document],
) -> list[str]:
    entities, claims = _knowledge_graph_rows(db, documents)
    if not claims and not entities:
        return []

    parts = [_docx_heading("Knowledge Graph Appendix", 2)]

    if entities:
        parts.append(_docx_heading("Entities", 2))
        for entity in entities:
            label = f"{entity.canonical_name} ({entity.entity_type.value})"
            if entity.description:
                label = f"{label}: {entity.description}"
            parts.append(_docx_paragraph(label))

    if claims:
        parts.append(_docx_heading("Claims", 2))
        for claim in claims:
            source = claim.source_page_label or claim.source_document_id
            label = f"{claim.text} [source: {source}]"
            parts.append(_docx_paragraph(label))
            if claim.source_excerpt:
                parts.append(_docx_paragraph(f"Excerpt: {claim.source_excerpt}"))

    return parts


def _knowledge_graph_rows(
    db: Database,
    documents: list[Document],
) -> tuple[list[KnowledgeEntity], list[KnowledgeClaim]]:
    doc_ids = {doc.id for doc in documents}
    if not doc_ids:
        return [], []

    claims = [
        claim
        for claim in db.all(KnowledgeClaim)
        if claim.source_document_id in doc_ids or doc_ids.intersection(claim.source_ids)
    ]
    claims.sort(key=lambda claim: (claim.source_document_id, claim.text.lower()))

    claim_entity_ids: set[str] = set()
    for claim in claims:
        claim_entity_ids.update(claim.entity_ids)
        for entity_id in (
            claim.subject_entity_id,
            claim.speaker_entity_id,
            claim.subject_of_inquiry_entity_id,
            claim.scribe_entity_id,
            claim.editor_entity_id,
        ):
            if entity_id:
                claim_entity_ids.add(entity_id)

    entities = [
        entity
        for entity in db.all(KnowledgeEntity)
        if entity.id in claim_entity_ids
        or doc_ids.intersection(entity.source_document_ids)
    ]
    entities.sort(key=lambda entity: entity.canonical_name.lower())
    return entities, claims


def _text_artifacts(db: Database, document_id: str) -> list[Artifact]:
    artifacts = [
        artifact
        for artifact in db.query(Artifact, document_id=document_id)
        if artifact.content and artifact.content.strip()
    ]
    artifacts.sort(key=lambda artifact: artifact.created_at)
    return artifacts


def _copy_document_assets(
    doc: Document,
    assets_dir: Path,
    package_path: Path | None,
) -> list[_AssetRef]:
    if not _is_image_document(doc):
        return []

    source = get_display(doc, package_path=package_path) or resolve_source(
        doc, library_root=package_path
    )
    if source is None or not source.exists() or not source.is_file():
        return []

    suffix = source.suffix.lower() or ".jpg"
    filename = _unique_filename(
        _slugify(doc.name), {p.name for p in assets_dir.iterdir()}, suffix
    )
    dest = assets_dir / filename
    if source.resolve() != dest.resolve():
        shutil.copy2(source, dest)
    return [_AssetRef(path=str(dest), markdown_path=f"assets/{filename}")]


def _docx_image_source(doc: Document, package_path: Path | None) -> Path | None:
    if not _is_image_document(doc):
        return None
    source = get_display(doc, package_path=package_path) or resolve_source(
        doc, library_root=package_path
    )
    if source and source.exists() and source.is_file():
        return source
    return None


def _is_image_document(doc: Document) -> bool:
    if doc.file_type == FileType.image:
        return True
    if doc.path and Path(doc.path).suffix.lower() in IMAGE_SUFFIXES:
        return True
    return False


def _render_index(root: Document | None, links: list[tuple[str, str]]) -> str:
    title = root.name if root else "Library Export"
    lines = [
        f"# {title}",
        "",
        f"Exported: {datetime.now().isoformat(timespec='seconds')}",
        "",
        "## Documents",
        "",
    ]
    if links:
        lines.extend(f"- [{name}]({filename})" for name, filename in links)
    else:
        lines.append("_No documents exported._")
    return "\n".join(lines).rstrip() + "\n"


def _render_kg_placeholder() -> str:
    return (
        "# Knowledge Graph\n\n"
        "Knowledge graph export is intentionally not rendered by this backend "
        "pass; document Markdown and assets are exported independently.\n"
    )


def _slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-._")
    return slug or "document"


def _unique_filename(stem: str, used_names: set[str], suffix: str) -> str:
    candidate = f"{stem}{suffix}"
    index = 2
    while candidate in used_names:
        candidate = f"{stem}-{index}{suffix}"
        index += 1
    used_names.add(candidate)
    return candidate


def _write_xlsx(output_file: Path, sheets: dict[str, list[dict[str, Any]]]) -> None:
    sheet_items = list(sheets.items())
    with zipfile.ZipFile(output_file, "w", compression=zipfile.ZIP_DEFLATED) as xlsx:
        xlsx.writestr("[Content_Types].xml", _xlsx_content_types(len(sheet_items)))
        xlsx.writestr("_rels/.rels", _xlsx_package_rels())
        xlsx.writestr("xl/workbook.xml", _xlsx_workbook(sheet_items))
        xlsx.writestr("xl/_rels/workbook.xml.rels", _xlsx_workbook_rels(sheet_items))
        for index, (_, rows) in enumerate(sheet_items, start=1):
            xlsx.writestr(
                f"xl/worksheets/sheet{index}.xml",
                _xlsx_sheet(rows),
            )


def _xlsx_sheet(rows: list[dict[str, Any]]) -> str:
    headers = _xlsx_headers(rows)
    values = [headers] + [
        [_xlsx_cell_value(row.get(header)) for header in headers]
        for row in rows
    ]
    row_xml = []
    for row_index, row in enumerate(values, start=1):
        cells = []
        for col_index, value in enumerate(row, start=1):
            if value == "":
                continue
            ref = f"{_xlsx_col_letter(col_index)}{row_index}"
            cells.append(
                f'<c r="{ref}" t="inlineStr"><is><t>{escape(value)}</t></is></c>'
            )
        row_xml.append(f'<row r="{row_index}">{"".join(cells)}</row>')

    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(row_xml)}</sheetData>'
        "</worksheet>"
    )


def _xlsx_headers(rows: list[dict[str, Any]]) -> list[str]:
    headers: list[str] = []
    for row in rows:
        for key in row:
            if key not in headers:
                headers.append(key)
    return headers or ["id"]


def _xlsx_cell_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    if hasattr(value, "value") and not isinstance(value, str):
        return str(value.value)
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, default=str)
    return str(value)


def _xlsx_col_letter(index: int) -> str:
    letters = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(ord("A") + remainder) + letters
    return letters


def _xlsx_content_types(sheet_count: int) -> str:
    sheets = "".join(
        f'<Override PartName="/xl/worksheets/sheet{index}.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        for index in range(1, sheet_count + 1)
    )
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  {sheets}
</Types>
"""


def _xlsx_package_rels() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>
"""


def _xlsx_workbook(sheet_items: list[tuple[str, list[dict[str, Any]]]]) -> str:
    sheets = "".join(
        f'<sheet name="{escape(name, {"\"": "&quot;"})}" sheetId="{index}" r:id="rId{index}"/>'
        for index, (name, _) in enumerate(sheet_items, start=1)
    )
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>{sheets}</sheets>
</workbook>
"""


def _xlsx_workbook_rels(sheet_items: list[tuple[str, list[dict[str, Any]]]]) -> str:
    relationships = "".join(
        f'<Relationship Id="rId{index}" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        f'Target="worksheets/sheet{index}.xml"/>'
        for index, _ in enumerate(sheet_items, start=1)
    )
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  {relationships}
</Relationships>
"""


def _escape_frontmatter(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _paragraphs(text: str) -> list[str]:
    return [part.strip() for part in text.splitlines() if part.strip()]


def _docx_document(body_parts: list[str]) -> str:
    body = "\n".join(body_parts)
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
    xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
    xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">
  <w:body>
    {body}
    <w:sectPr><w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/></w:sectPr>
  </w:body>
</w:document>
"""


def _docx_heading(text: str, level: int) -> str:
    style = "Title" if level == 1 else "Heading2"
    return f"""<w:p>
  <w:pPr><w:pStyle w:val="{style}"/></w:pPr>
  <w:r><w:t>{escape(text)}</w:t></w:r>
</w:p>"""


def _docx_paragraph(text: str) -> str:
    return f"""<w:p><w:r><w:t xml:space="preserve">{escape(text)}</w:t></w:r></w:p>"""


def _docx_image_text_table(title: str, rel_id: str, text: str) -> str:
    paragraphs = "".join(_docx_paragraph(part) for part in _paragraphs(text))
    return f"""<w:p>
  <w:pPr><w:pStyle w:val="Heading2"/></w:pPr>
  <w:r><w:t>{escape(title)}</w:t></w:r>
</w:p>
<w:tbl>
  <w:tblPr><w:tblW w:w="0" w:type="auto"/></w:tblPr>
  <w:tr>
    <w:tc><w:p><w:r>{_docx_image_drawing(rel_id)}</w:r></w:p></w:tc>
    <w:tc>{paragraphs}</w:tc>
  </w:tr>
</w:tbl>"""


def _docx_image_drawing(rel_id: str) -> str:
    # 3.2" square: 1 inch = 914400 EMU.
    cx = cy = 2926080
    return f"""<w:drawing>
  <wp:inline distT="0" distB="0" distL="0" distR="0">
    <wp:extent cx="{cx}" cy="{cy}"/>
    <wp:docPr id="1" name="Picture"/>
    <a:graphic>
      <a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">
        <pic:pic>
          <pic:nvPicPr><pic:cNvPr id="0" name="image"/><pic:cNvPicPr/></pic:nvPicPr>
          <pic:blipFill><a:blip r:embed="{rel_id}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>
          <pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm><a:prstGeom prst="rect"/></pic:spPr>
        </pic:pic>
      </a:graphicData>
    </a:graphic>
  </wp:inline>
</w:drawing>"""


def _docx_document_rels(media: list[tuple[str, Path, str]]) -> str:
    relationships = [
        '<Relationship Id="rIdStyles" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
    ]
    relationships.extend(
        f'<Relationship Id="{rel_id}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/{media_name}"/>'
        for rel_id, _, media_name in media
    )
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  {"".join(relationships)}
</Relationships>
"""


def _docx_content_types(media: list[tuple[str, Path, str]]) -> str:
    image_defaults = {
        _content_type_ext(path)
        for _, path, _ in media
        if _content_type_ext(path) not in {"jpg", "jpeg", "png"}
    }
    extras = "".join(
        f'<Default Extension="{ext}" ContentType="{_image_content_type(ext)}"/>'
        for ext in sorted(image_defaults)
    )
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Default Extension="jpg" ContentType="image/jpeg"/>
  <Default Extension="jpeg" ContentType="image/jpeg"/>
  <Default Extension="png" ContentType="image/png"/>
  {extras}
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>
"""


def _content_type_ext(path: Path) -> str:
    ext = path.suffix.lower().lstrip(".")
    return "jpg" if ext == "jpe" else ext or "jpg"


def _image_content_type(ext: str) -> str:
    if ext in {"jpg", "jpeg"}:
        return "image/jpeg"
    if ext == "png":
        return "image/png"
    if ext in {"tif", "tiff"}:
        return "image/tiff"
    if ext == "gif":
        return "image/gif"
    if ext == "webp":
        return "image/webp"
    return "application/octet-stream"


def _package_rels() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>
"""


def _docx_styles() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:style w:type="paragraph" w:styleId="Title">
    <w:name w:val="Title"/>
    <w:rPr><w:b/><w:sz w:val="40"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading2">
    <w:name w:val="heading 2"/>
    <w:rPr><w:b/><w:sz w:val="28"/></w:rPr>
  </w:style>
</w:styles>
"""


def _core_props() -> str:
    now = datetime.now().isoformat(timespec="seconds")
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
    xmlns:dc="http://purl.org/dc/elements/1.1/"
    xmlns:dcterms="http://purl.org/dc/terms/"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:creator>Fichero</dc:creator>
  <cp:lastModifiedBy>Fichero</cp:lastModifiedBy>
  <dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created>
  <dcterms:modified xsi:type="dcterms:W3CDTF">{now}</dcterms:modified>
</cp:coreProperties>
"""


def _app_props() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
    xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>Fichero</Application>
</Properties>
"""
