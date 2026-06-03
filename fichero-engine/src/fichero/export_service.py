"""Document export services."""

from __future__ import annotations

import json
import re
import shutil
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable
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
class JsonExportResult:
    """Result metadata for a structured JSON export."""

    output_path: str
    document_count: int
    artifact_count: int
    entity_count: int
    claim_count: int
    bytes_written: int


@dataclass
class HtmlWebsiteExportResult:
    """Result metadata for a static HTML website export."""

    output_path: str
    files: list[ExportedFile] = field(default_factory=list)
    assets: list[ExportedFile] = field(default_factory=list)
    document_count: int = 0


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


def export_json_file(
    db: Database,
    output_path: str | Path,
    target_id: str | None = None,
    recursive: bool = True,
    overwrite: bool = False,
) -> JsonExportResult:
    """Export documents, artifacts, and scoped KG data as a JSON file."""

    output_file = Path(output_path).expanduser()
    if output_file.suffix.lower() != ".json":
        output_file = output_file.with_suffix(".json")
    if output_file.exists() and not overwrite:
        raise FileExistsError(f"Export file already exists: {output_file}")
    output_file.parent.mkdir(parents=True, exist_ok=True)

    root, documents = _collect_documents(db, target_id=target_id, recursive=recursive)
    document_ids = {doc.id for doc in documents}
    artifacts = _collect_artifacts(db, document_ids)
    claims = _collect_claims(db, document_ids)
    entities = _collect_entities(db, document_ids, claims)

    payload = {
        "doc": _dump_model(root or documents[0]) if root or documents else None,
        "documents": [_dump_model(doc) for doc in documents],
        "transcription": _combined_transcription(db, documents),
        "artifacts": [_dump_model(artifact) for artifact in artifacts],
        "kg": {
            "entities": [_dump_model(entity) for entity in entities],
            "claims": [_dump_model(claim) for claim in claims],
        },
        "exported_at": datetime.now().isoformat(timespec="seconds"),
    }
    output_file.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    return JsonExportResult(
        output_path=str(output_file),
        document_count=len(documents),
        artifact_count=len(artifacts),
        entity_count=len(entities),
        claim_count=len(claims),
        bytes_written=output_file.stat().st_size,
    )


def export_html_site(
    db: Database,
    output_path: str | Path,
    target_id: str | None = None,
    recursive: bool = True,
    include_assets: bool = True,
    overwrite: bool = False,
    package_path: str | Path | None = None,
) -> HtmlWebsiteExportResult:
    """Export a library, folder, or document as a static HTML website."""

    output_dir = Path(output_path).expanduser()
    if output_dir.exists() and any(output_dir.iterdir()) and not overwrite:
        raise FileExistsError(
            f"Export folder already exists and is not empty: {output_dir}"
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    docs_dir = output_dir / "docs"
    assets_dir = output_dir / "assets"
    js_dir = output_dir / "js"
    docs_dir.mkdir(exist_ok=True)
    if include_assets:
        assets_dir.mkdir(exist_ok=True)
    js_dir.mkdir(exist_ok=True)

    root, documents = _collect_documents(db, target_id=target_id, recursive=recursive)
    document_ids = {doc.id for doc in documents}
    claims = _collect_claims(db, document_ids)
    entities = _collect_entities(db, document_ids, claims)
    package = Path(package_path).expanduser() if package_path else None

    result = HtmlWebsiteExportResult(
        output_path=str(output_dir),
        document_count=len(documents),
    )
    used_slugs: set[str] = set()
    pages: list[tuple[Document, str, str]] = []
    search_items: list[dict[str, str]] = []

    for doc in documents:
        slug = _unique_slug(_slugify(doc.name).lower(), used_slugs)
        relative_url = f"docs/{slug}/index.html"
        page_dir = docs_dir / slug
        page_dir.mkdir(parents=True, exist_ok=True)
        asset_refs = (
            _copy_document_assets(doc, assets_dir, package) if include_assets else []
        )
        page_html = _render_html_document_page(
            db=db,
            doc=doc,
            assets=asset_refs,
            entities=_entities_for_document(doc.id, entities, claims),
            claims=_claims_for_document(doc.id, claims),
        )
        page_path = page_dir / "index.html"
        page_path.write_text(page_html, encoding="utf-8")
        result.files.append(
            ExportedFile(path=str(page_path), kind="html", document_id=doc.id)
        )
        result.assets.extend(
            ExportedFile(path=str(asset.path), kind="asset", document_id=doc.id)
            for asset in asset_refs
        )
        pages.append((doc, slug, relative_url))
        search_items.append(
            {
                "title": doc.name,
                "url": relative_url,
                "text": _document_text(db, doc),
            }
        )

    search_path = js_dir / "search.js"
    search_path.write_text(_render_search_js(search_items), encoding="utf-8")
    result.files.append(ExportedFile(path=str(search_path), kind="search-index"))

    index_path = output_dir / "index.html"
    index_path.write_text(
        _render_html_index(root=root, pages=pages),
        encoding="utf-8",
    )
    result.files.insert(0, ExportedFile(path=str(index_path), kind="index"))

    return result


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


def _collect_artifacts(db: Database, document_ids: set[str]) -> list[Artifact]:
    artifacts = [
        artifact
        for artifact in db.all(Artifact)
        if artifact.document_id in document_ids
        or artifact.source_document_id in document_ids
    ]
    artifacts.sort(key=lambda artifact: (artifact.document_id, artifact.created_at))
    return artifacts


def _collect_claims(
    db: Database,
    document_ids: set[str],
) -> list[KnowledgeClaim]:
    claims = [
        claim
        for claim in db.all(KnowledgeClaim)
        if claim.source_document_id in document_ids
        or bool(set(claim.source_ids or []) & document_ids)
    ]
    claims.sort(key=lambda claim: (claim.source_document_id, claim.created_at, claim.id))
    return claims


def _collect_entities(
    db: Database,
    document_ids: set[str],
    claims: list[KnowledgeClaim],
) -> list[KnowledgeEntity]:
    claim_entity_ids = {
        entity_id
        for claim in claims
        for entity_id in [
            *claim.entity_ids,
            claim.subject_entity_id,
            claim.speaker_entity_id,
            claim.subject_of_inquiry_entity_id,
            claim.scribe_entity_id,
            claim.editor_entity_id,
        ]
        if entity_id
    }
    entities = [
        entity
        for entity in db.all(KnowledgeEntity)
        if entity.id in claim_entity_ids
        or bool(set(entity.source_document_ids or []) & document_ids)
    ]
    entities.sort(key=lambda entity: (entity.canonical_name.lower(), entity.id))
    return entities


def _combined_transcription(db: Database, documents: list[Document]) -> str:
    return "\n\n".join(_document_text(db, doc) for doc in documents).strip()


def _dump_model(model: Any) -> dict[str, Any]:
    return model.model_dump(mode="json")


def _claims_for_document(
    document_id: str,
    claims: list[KnowledgeClaim],
) -> list[KnowledgeClaim]:
    return [
        claim
        for claim in claims
        if claim.source_document_id == document_id
        or document_id in (claim.source_ids or [])
    ]


def _entities_for_document(
    document_id: str,
    entities: list[KnowledgeEntity],
    claims: list[KnowledgeClaim],
) -> list[KnowledgeEntity]:
    doc_claims = _claims_for_document(document_id, claims)
    claim_entity_ids = {
        entity_id
        for claim in doc_claims
        for entity_id in [
            *claim.entity_ids,
            claim.subject_entity_id,
            claim.speaker_entity_id,
            claim.subject_of_inquiry_entity_id,
            claim.scribe_entity_id,
            claim.editor_entity_id,
        ]
        if entity_id
    }
    return [
        entity
        for entity in entities
        if entity.id in claim_entity_ids
        or document_id in (entity.source_document_ids or [])
    ]


def _render_html_index(
    root: Document | None,
    pages: list[tuple[Document, str, str]],
) -> str:
    title = root.name if root else "Library Export"
    links = "\n".join(
        (
            f'<li><a href="{_html_attr(url)}">{_html(doc.name)}</a></li>'
            for doc, _, url in pages
        )
    )
    if not links:
        links = "<li>No documents exported.</li>"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_html(title)}</title>
  <style>{_html_css()}</style>
</head>
<body>
  <main>
    <header>
      <p class="eyebrow">Fichero static export</p>
      <h1>{_html(title)}</h1>
      <p>{len(pages)} documents exported.</p>
    </header>
    <section>
      <h2>Search</h2>
      <input id="search" type="search" placeholder="Search documents" autocomplete="off">
      <ul id="search-results"></ul>
    </section>
    <section>
      <h2>Documents</h2>
      <ul class="doc-list">
        {links}
      </ul>
    </section>
  </main>
  <script src="js/search.js"></script>
</body>
</html>
"""


def _render_html_document_page(
    db: Database,
    doc: Document,
    assets: Iterable[_AssetRef],
    entities: list[KnowledgeEntity],
    claims: list[KnowledgeClaim],
) -> str:
    text = _document_text(db, doc)
    gallery = _render_html_gallery(doc, assets)
    entity_list = _render_html_entities(entities)
    claim_list = _render_html_claims(claims)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_html(doc.name)}</title>
  <style>{_html_css()}</style>
</head>
<body>
  <main>
    <nav><a href="../../index.html">Index</a></nav>
    <article>
      <header>
        <p class="eyebrow">{_html(doc.doc_type.value)}</p>
        <h1>{_html(doc.name)}</h1>
      </header>
      {gallery}
      <section>
        <h2>Transcription</h2>
        {_html_paragraphs(text)}
      </section>
      <section>
        <h2>Knowledge Graph Entities</h2>
        {entity_list}
      </section>
      <section>
        <h2>Claims</h2>
        {claim_list}
      </section>
    </article>
  </main>
</body>
</html>
"""


def _render_html_gallery(doc: Document, assets: Iterable[_AssetRef]) -> str:
    images = "\n".join(
        (
            '<figure>'
            f'<img src="../../assets/{_html_attr(Path(asset.path).name)}" '
            f'alt="{_html_attr(doc.name)}">'
            f"<figcaption>{_html(doc.name)}</figcaption>"
            "</figure>"
            for asset in assets
        )
    )
    if not images:
        return ""
    return f"<section><h2>Images</h2><div class=\"gallery\">{images}</div></section>"


def _render_html_entities(entities: list[KnowledgeEntity]) -> str:
    if not entities:
        return "<p>No linked entities.</p>"
    items = "\n".join(
        (
            f'<li id="entity-{_html_attr(entity.id)}">'
            f"<strong>{_html(entity.canonical_name)}</strong>"
            f" <span>{_html(entity.entity_type.value)}</span>"
            "</li>"
            for entity in entities
        )
    )
    return f"<ul>{items}</ul>"


def _render_html_claims(claims: list[KnowledgeClaim]) -> str:
    if not claims:
        return "<p>No linked claims.</p>"
    items = "\n".join(
        (
            f'<li id="claim-{_html_attr(claim.id)}">'
            f"{_html(claim.text)}"
            f" <span>{claim.confidence:.2f}</span>"
            "</li>"
            for claim in claims
        )
    )
    return f"<ul>{items}</ul>"


def _render_search_js(items: list[dict[str, str]]) -> str:
    payload = json.dumps(items, ensure_ascii=False, sort_keys=True)
    return f"""const FICHERO_SEARCH_INDEX = {payload};

const input = document.getElementById("search");
const results = document.getElementById("search-results");

function renderSearch(query) {{
  if (!results) return;
  const terms = query.trim().toLowerCase().split(/\\s+/).filter(Boolean);
  const matches = FICHERO_SEARCH_INDEX.filter((item) => {{
    const haystack = `${{item.title}} ${{item.text}}`.toLowerCase();
    return terms.length === 0 || terms.every((term) => haystack.includes(term));
  }}).slice(0, 50);
  results.innerHTML = matches.map((item) =>
    `<li><a href="${{item.url}}">${{item.title}}</a></li>`
  ).join("");
}}

if (input) {{
  input.addEventListener("input", () => renderSearch(input.value));
  renderSearch("");
}}
"""


def _html_css() -> str:
    return """
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;margin:0;background:#f8f8f6;color:#202020;line-height:1.55}
main{max-width:960px;margin:0 auto;padding:32px 20px}
header{border-bottom:1px solid #d8d5cf;margin-bottom:24px}
h1{font-size:32px;line-height:1.2;margin:4px 0 16px}
h2{font-size:20px;margin-top:28px}
a{color:#075a8f}
input[type=search]{box-sizing:border-box;width:100%;max-width:560px;padding:10px 12px;border:1px solid #aaa;border-radius:6px;font:inherit;background:white}
.eyebrow{color:#666;text-transform:uppercase;font-size:12px;letter-spacing:.08em}
.doc-list li,#search-results li{margin:8px 0}
.gallery{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px}
figure{margin:0}
img{max-width:100%;height:auto;border:1px solid #d8d5cf;background:white}
figcaption,span{color:#666;font-size:13px}
pre{white-space:pre-wrap;background:white;border:1px solid #d8d5cf;padding:16px;overflow:auto}
"""


def _html_paragraphs(text: str) -> str:
    if not text.strip():
        return "<p>No text content available.</p>"
    return f"<pre>{_html(text)}</pre>"


def _html(value: object) -> str:
    return escape(str(value))


def _html_attr(value: object) -> str:
    return escape(str(value), {'"': "&quot;"})


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

    source = get_display(doc, package_path=package_path) or resolve_source(doc)
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
    source = get_display(doc, package_path=package_path) or resolve_source(doc)
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


def _unique_slug(stem: str, used_slugs: set[str]) -> str:
    candidate = stem or "document"
    index = 2
    while candidate in used_slugs:
        candidate = f"{stem}-{index}"
        index += 1
    used_slugs.add(candidate)
    return candidate


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
