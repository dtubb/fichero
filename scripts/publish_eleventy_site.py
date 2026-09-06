#!/usr/bin/env python3
"""Publish a Fichero library (or a folder within it) as a themed, buildable
11ty static site — SCOOP step 10, "Publish a catalogue".

This is a thin, generic wrapper around the engine's existing, sanctioned 11ty
exporter (``fichero_server.export_service.export_eleventy_site``). It:

  1. copies the library's DuckDB to a temp file and opens *that* (lock-safe: the
     running app may hold the real library read-write), so this is a pure,
     offline read that never touches the live library;
  2. runs ``export_eleventy_site`` to produce the data-driven site (pages per
     document with image + transcript, entity/claim pages, scope indexes,
     collections, search index) — the engine code is left untouched;
  3. post-processes the output: rewrites document-image links to site-absolute
     URLs (the raw export links break under 11ty pretty-URLs), trims redundant
     headings/import receipts, assigns layouts, and builds a catalogue of
     expedientes for the home cards;
  4. overlays the ``archivos_nuestros``-style theme (Nunjucks ``_includes`` +
     one lean CSS + Pagefind search) and rewrites the scaffold so the site
     builds with ``npx @11ty/eleventy`` and deploys to Netlify.

Everything is driven by config (CLI flags or a JSON file) so any library/folder
can produce a site.

Usage
-----
    python scripts/publish_eleventy_site.py \
        --library "~/Fichero/Istmina Demo.fichero" \
        --out ~/Desktop/istmina-site \
        --title "Istmina Demo" \
        --subtitle "Archivo minero del Chocó" --overwrite

    cd ~/Desktop/istmina-site && npm install && npx @11ty/eleventy --serve
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

# Make the engine package importable when run from the repo root.
_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "fichero-server" / "src"))

from fichero_server.db import Database  # noqa: E402
from fichero_server.export_service import export_eleventy_site  # noqa: E402

THEME_DIR = Path(__file__).resolve().parent / "eleventy_theme"


# --------------------------------------------------------------------------- #
# Front matter helpers
# --------------------------------------------------------------------------- #
_FM_RE = re.compile(r"^---\n(.*?)\n---\n?(.*)$", re.DOTALL)


def split_front_matter(text: str) -> tuple[str, str]:
    """Return (raw_front_matter, body). Empty front matter if none present."""
    m = _FM_RE.match(text)
    if not m:
        return "", text
    return m.group(1), m.group(2)


def fm_get(raw_fm: str, key: str) -> str | None:
    """Read a scalar key from a raw YAML front-matter block (quotes stripped)."""
    m = re.search(rf"^{re.escape(key)}:\s*(.+)$", raw_fm, re.MULTILINE)
    if not m:
        return None
    return m.group(1).strip().strip('"').strip("'")


def yaml_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def prettify_slug(slug: str) -> str:
    return re.sub(r"[-_]+", " ", slug).strip().strip(" ").title()


# --------------------------------------------------------------------------- #
# Post-processing the raw export
# --------------------------------------------------------------------------- #
def process_document_pages(src_dir: Path, base: str = "") -> dict[str, dict]:
    """Fix image links + layouts on every document page; return expediente map.

    Returns {expediente_slug: {title, box, count, thumbnail, url}} for the home
    catalogue cards. ``base`` is an optional deploy path prefix (e.g. "/repo"
    for a GitHub Pages project site); "" for a root deploy (Netlify).
    """
    expedientes: dict[str, dict] = {}
    # Human titles for expedientes (from the exporter's scope-index pages).
    exp_titles = _scope_titles(src_dir / "expedientes")

    for md in sorted(src_dir.rglob("*.md")):
        rel = md.relative_to(src_dir)
        if rel.parts[0] in {"entities", "claims", "expedientes", "box-collections"}:
            continue
        if md.name in {"index.md", "search.md"}:
            continue
        raw_fm, body = split_front_matter(md.read_text(encoding="utf-8"))
        if fm_get(raw_fm, "doc_type") != "page":
            continue

        coll_path = fm_get(raw_fm, "collection_path") or ""
        title = fm_get(raw_fm, "title") or md.stem
        file_type = fm_get(raw_fm, "file_type") or ""

        # 1) Rewrite relative image links to site-absolute (pretty-URL safe).
        if coll_path:
            body = re.sub(
                r"\]\(assets/",
                f"]({base}/{coll_path}/assets/",
                body,
            )
        # 2) First image → thumbnail.
        img_match = re.search(r"!\[[^\]]*\]\((/[^)]+)\)", body)
        thumbnail = img_match.group(1) if img_match else None
        # 3) Extract the transcript (drop image + heading + import receipts) and
        #    render it TIGHT — collapse blank lines so it isn't double-spaced.
        transcript_html = _tidy_transcript(body)

        parts = [p for p in coll_path.split("/") if p]
        box_slug = parts[0] if parts else ""
        exp_slug = parts[-1] if parts else ""
        page_label = None
        lm = re.search(r"[-_](\d+)$", title)
        if lm:
            page_label = str(int(lm.group(1)))

        exp_url = f"{base}/expedientes/{exp_slug}/" if exp_slug else f"{base}/"
        doc_url = base + "/" + rel.with_suffix("").as_posix() + "/"
        new_fm = "\n".join(
            line
            for line in [
                f"title: {yaml_quote(title)}",
                "layout: page.njk",
                "doc_type: page",
                f"file_type: {yaml_quote(file_type)}" if file_type else None,
                f"box: {yaml_quote(prettify_slug(box_slug))}" if box_slug else None,
                (
                    f"expediente: {yaml_quote(exp_titles.get(exp_slug, prettify_slug(exp_slug)))}"
                    if exp_slug
                    else None
                ),
                f"expediente_url: {yaml_quote(exp_url)}" if exp_slug else None,
                f"page_label: {yaml_quote(page_label)}" if page_label else None,
                f"image: {yaml_quote(thumbnail)}" if thumbnail else None,
                f"thumbnail: {yaml_quote(thumbnail)}" if thumbnail else None,
            ]
            if line is not None
        )
        md.write_text(f"---\n{new_fm}\n---\n{transcript_html}", encoding="utf-8")

        # Accumulate expediente catalogue entry.
        if exp_slug:
            entry = expedientes.setdefault(
                exp_slug,
                {
                    "slug": exp_slug,
                    "title": exp_titles.get(exp_slug, prettify_slug(exp_slug)),
                    "box": prettify_slug(box_slug) if box_slug != exp_slug else "",
                    "box_slug": box_slug,
                    "count": 0,
                    "thumbnail": None,
                    "url": exp_url,
                    "pages": [],
                },
            )
            entry["count"] += 1
            if entry["thumbnail"] is None and thumbnail:
                entry["thumbnail"] = thumbnail
            entry["pages"].append(
                {
                    "title": f"Página {page_label}" if page_label else title,
                    "url": doc_url,
                    "thumbnail": thumbnail,
                }
            )

    return expedientes


def _tidy_transcript(body: str) -> str:
    """Return the transcript as tight HTML (no double-spaced blank lines).

    Drops the leading markdown image + H1 heading and the import-receipt
    artifacts, keeps the transcription text, and renders consecutive lines
    together (single <br>) with paragraph breaks only where the source had a
    real gap collapsed to one.
    """
    from html import escape

    # Drop everything from the Artifacts section onward, minus the transcription.
    parts = re.split(r"\n##\s+Artifacts\s*\n", body, maxsplit=1)
    main = parts[0]
    transcription = ""
    if len(parts) > 1:
        tm = re.search(r"###\s+transcription\s*\n(.*?)(?:\n###\s+|\Z)", parts[1], re.DOTALL)
        if tm:
            transcription = tm.group(1)

    # Remove markdown images and the redundant leading H1.
    main = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", main)
    main = re.sub(r"^\s*#\s+.*$", "", main, count=1, flags=re.MULTILINE)

    text = main.strip() or transcription.strip()
    if not text:
        return '<p class="muted">Sin transcripción disponible.</p>\n'

    # The source puts a blank line between every line, which renders
    # double-spaced. Collapse blank runs so lines sit tight, then join the
    # remaining non-empty lines with <br> inside a single paragraph.
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return '<p class="muted">Sin transcripción disponible.</p>\n'
    return "<p>" + "<br>\n".join(escape(ln) for ln in lines) + "</p>\n"


def _scope_titles(scope_dir: Path) -> dict[str, str]:
    titles: dict[str, str] = {}
    if not scope_dir.is_dir():
        return titles
    for md in scope_dir.glob("*.md"):
        raw_fm, _ = split_front_matter(md.read_text(encoding="utf-8"))
        titles[md.stem] = fm_get(raw_fm, "title") or prettify_slug(md.stem)
    return titles


# --------------------------------------------------------------------------- #
# Theme overlay
# --------------------------------------------------------------------------- #
def overlay_theme(output_dir: Path, src_dir: Path, cfg: dict, catalogue: dict) -> None:
    # 1) Copy theme _includes + assets into src/.
    includes_dst = src_dir / "_includes"
    includes_dst.mkdir(exist_ok=True)
    for njk in (THEME_DIR / "_includes").glob("*.njk"):
        shutil.copy2(njk, includes_dst / njk.name)
    assets_dst = src_dir / "assets"
    assets_dst.mkdir(exist_ok=True)
    for asset in (THEME_DIR / "assets").iterdir():
        dest = assets_dst / asset.name
        if asset.is_dir():
            shutil.copytree(asset, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(asset, dest)

    # 2) Global data: site config + catalogue.
    data_dir = src_dir / "_data"
    data_dir.mkdir(exist_ok=True)
    expedientes = sorted(catalogue.values(), key=lambda e: e["title"])
    site = {
        "title": cfg["title"],
        "subtitle": cfg.get("subtitle", ""),
        "lang": cfg.get("lang", "es"),
        "base": cfg.get("base", ""),
        "include_entities": cfg.get("include_entities", True),
        "include_claims": cfg.get("include_claims", True),
        "include_search": cfg.get("include_search", True),
        "doc_count": cfg["doc_count"],
        "expediente_count": len(expedientes),
        "entity_count": cfg["entity_count"],
        "claim_count": cfg["claim_count"],
    }
    (data_dir / "site.json").write_text(json.dumps(site, ensure_ascii=False, indent=2), "utf-8")
    (data_dir / "catalogue.json").write_text(
        json.dumps({"expedientes": expedientes}, ensure_ascii=False, indent=2), "utf-8"
    )

    # 3) Default layout for every page (doc pages / index / search override it).
    (src_dir / "src.11tydata.js").write_text(
        "module.exports = {\n"
        "  eleventyComputed: {\n"
        '    layout: (data) => data.layout || "content.njk",\n'
        "  },\n"
        "};\n",
        "utf-8",
    )

    # 4) Home page (cards) + Pagefind search page.
    (src_dir / "index.md").write_text(
        "---\nlayout: home.njk\n---\n", "utf-8"
    )
    if site["include_search"]:
        (src_dir / "search.md").write_text(_search_page(site["base"]), "utf-8")
    elif (src_dir / "search.md").exists():
        (src_dir / "search.md").unlink()

    # 5) Folder pages as thumbnail grids (the app's "thumbnail browser" feel):
    #    each expediente → a grid of its page thumbnails; each box → a grid of
    #    expediente cards. Replaces the raw exporter's plain link lists.
    _write_folder_grids(src_dir, expedientes, site["base"])

    # 6) Entities index (the exporter emits entity pages but no index page).
    if cfg.get("include_entities"):
        _write_entities_index(src_dir)

    # 6) Rewrite the scaffold so it builds themed + with Pagefind.
    _write_scaffold(output_dir, cfg["title"], site["include_search"])


def _render_card_grid(items: list[dict]) -> str:
    """Bootstrap thumbnail-card grid matching the archivos_nuestros post-item look."""
    from html import escape

    cards = []
    for it in items:
        thumb = it.get("thumbnail")
        title = escape(it["title"])
        img = (
            f'<img src="{thumb}" class="img-fluid" alt="{title}" loading="lazy">'
            if thumb
            else ""
        )
        badge = f'<span class="post-date">{it["count"]} pág.</span>' if it.get("count") else ""
        sub = (
            f'<div class="meta d-flex align-items-center"><i class="bi bi-folder2"></i> '
            f'<span class="ps-2">{escape(it["subtitle"])}</span></div>'
            if it.get("subtitle")
            else ""
        )
        cards.append(
            '<div class="col-xl-3 col-lg-4 col-md-6">'
            '<div class="post-item position-relative h-100">'
            f'<div class="post-img position-relative overflow-hidden">{img}{badge}</div>'
            '<div class="post-content d-flex flex-column">'
            f'<h3 class="post-title">{title}</h3>{sub}<hr>'
            f'<a href="{it["url"]}" class="readmore stretched-link"><span>Ver</span> '
            '<i class="bi bi-arrow-right"></i></a>'
            "</div></div></div>"
        )
    return '<div class="row gy-4">\n' + "\n".join(cards) + "\n</div>\n"


def _write_folder_grids(src_dir: Path, expedientes: list[dict], base: str = "") -> None:
    """Overwrite expediente + box-collection index pages with thumbnail grids."""
    exp_dir = src_dir / "expedientes"
    for exp in expedientes:
        target = exp_dir / f"{exp['slug']}.md"
        if not target.exists():
            continue
        from html import escape as _esc

        # Order pages numerically (Página 1, 2, … 10), not lexically.
        def _page_num(p: dict) -> tuple[int, str]:
            m = re.search(r"(\d+)", p.get("title", ""))
            return (int(m.group(1)) if m else 10**9, p.get("title", ""))

        pages = sorted(exp.get("pages", []), key=_page_num)
        grid = _render_card_grid(pages)
        target.write_text(
            "---\n"
            f"title: {yaml_quote(exp['title'])}\n"
            "layout: base.njk\n"
            "---\n\n"
            '<section class="recent-posts section folder-page">\n'
            '  <div class="container">\n'
            f'    <nav class="doc-crumbs mb-2"><a href="{base}/">Inicio</a> '
            f'<i class="bi bi-chevron-right"></i> <a href="{base}/expedientes/">Expedientes</a></nav>\n'
            f'    <div class="section-title"><h2>{_esc(exp["title"])}</h2></div>\n'
            f'    <p class="muted">{exp["count"]} páginas</p>\n'
            f"    {grid}\n"
            "  </div>\n"
            "</section>\n",
            "utf-8",
        )

    # Box-collection pages: grid of expediente cards.
    box_dir = src_dir / "box-collections"
    if not box_dir.is_dir():
        return
    boxes: dict[str, list[dict]] = {}
    for exp in expedientes:
        boxes.setdefault(exp.get("box_slug", ""), []).append(exp)
    box_titles = _scope_titles(box_dir)
    for box_slug, exps in boxes.items():
        target = box_dir / f"{box_slug}.md"
        if not target.exists():
            continue
        items = [
            {
                "url": e["url"],
                "thumbnail": e.get("thumbnail"),
                "title": e["title"],
                "count": e["count"],
            }
            for e in sorted(exps, key=lambda e: e["title"])
        ]
        from html import escape as _esc

        title = box_titles.get(box_slug, prettify_slug(box_slug))
        target.write_text(
            "---\n"
            f"title: {yaml_quote(title)}\n"
            "layout: base.njk\n"
            "---\n\n"
            '<section class="recent-posts section folder-page">\n'
            '  <div class="container">\n'
            f'    <nav class="doc-crumbs mb-2"><a href="{base}/">Inicio</a></nav>\n'
            f'    <div class="section-title"><h2>{_esc(title)}</h2></div>\n'
            f"    {_render_card_grid(items)}\n"
            "  </div>\n"
            "</section>\n",
            "utf-8",
        )


def _write_entities_index(src_dir: Path) -> None:
    ent_dir = src_dir / "entities"
    if not ent_dir.is_dir():
        return
    titles = _scope_titles(ent_dir)  # {slug: title}, excludes nothing
    items = sorted(
        ((slug, title) for slug, title in titles.items() if slug != "index"),
        key=lambda st: st[1].lower(),
    )
    lines = [
        "---",
        'title: "Entidades"',
        "layout: content.njk",
        "---",
        "",
        '<div class="section-title"><h2>Entidades</h2></div>',
        "",
    ]
    lines += [f"- [{title}]({slug}/)" for slug, title in items]
    lines.append("")
    (ent_dir / "index.md").write_text("\n".join(lines), "utf-8")


def _search_page(base: str = "") -> str:
    return (
        "---\n"
        'title: "Buscar"\n'
        "layout: base.njk\n"
        "---\n\n"
        '<div class="section-title"><h2>Buscar en el catálogo</h2></div>\n'
        '<div id="search"></div>\n'
    )


def _write_scaffold(output_dir: Path, title: str, include_search: bool) -> None:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "fichero-site"
    dev_deps = {"@11ty/eleventy": "^3.0.0"}
    if include_search:
        dev_deps["pagefind"] = "^1.1.0"
    package_json = {
        "name": slug,
        "version": "1.0.0",
        "private": True,
        "scripts": {"build": "eleventy", "serve": "eleventy --serve"},
        "devDependencies": dev_deps,
    }
    (output_dir / "package.json").write_text(
        json.dumps(package_json, indent=2), "utf-8"
    )

    pagefind_hook = (
        "  eleventyConfig.on('eleventy.after', () => {\n"
        "    execSync('npx pagefind --site _site', { stdio: 'inherit' });\n"
        "  });\n"
        if include_search
        else ""
    )
    eleventy_config = (
        "const { execSync } = require('child_process');\n\n"
        "module.exports = function (eleventyConfig) {\n"
        '  eleventyConfig.addPassthroughCopy("src/assets");\n'
        '  eleventyConfig.addPassthroughCopy("src/**/assets");\n'
        f"{pagefind_hook}"
        "  return {\n"
        '    dir: { input: "src", output: "_site", includes: "_includes", data: "_data" },\n'
        '    markdownTemplateEngine: "njk",\n'
        '    htmlTemplateEngine: "njk",\n'
        "  };\n"
        "};\n"
    )
    (output_dir / ".eleventy.js").write_text(eleventy_config, "utf-8")

    (output_dir / "netlify.toml").write_text(
        "[build]\n"
        '  command = "npm install && npx @11ty/eleventy"\n'
        '  publish = "_site"\n\n'
        "[build.environment]\n"
        '  NODE_VERSION = "20"\n',
        "utf-8",
    )
    (output_dir / "README.md").write_text(
        f"# {title}\n\n"
        "Static catalogue published from a Fichero library (11ty + Pagefind + Netlify).\n\n"
        "## Run locally\n\n"
        "```sh\n"
        "npm install\n"
        "npx @11ty/eleventy --serve   # http://localhost:8080\n"
        "```\n\n"
        "## Build\n\n"
        "```sh\n"
        "npm install && npx @11ty/eleventy   # → _site/\n"
        "```\n\n"
        "## Deploy (self-contained, no local paths)\n\n"
        "- **Netlify:** drag the built `_site/` folder onto app.netlify.com/drop, "
        "or connect the repo (build `npx @11ty/eleventy`, publish `_site`). Works as-is.\n"
        "- **GitHub Pages (user/org site or a custom domain at the root):** publish "
        "`_site/` as-is.\n"
        "- **GitHub Pages project site** served under `/<repo>/`: regenerate with "
        "`--base-url /<repo>` so every asset/link is prefixed for that sub-path.\n\n"
        "Regenerate with `scripts/publish_eleventy_site.py` in the Fichero repo.\n",
        "utf-8",
    )
    # Drop the .nojekyll for GitHub Pages friendliness too.
    (output_dir / ".gitignore").write_text("node_modules/\n_site/\n.pagefind/\n", "utf-8")


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def resolve_duckdb(library: Path) -> Path:
    """Accept a .fichero bundle dir or a direct .duckdb path."""
    library = library.expanduser()
    if library.is_dir():
        db = library / "fichero.duckdb"
        if not db.exists():
            raise SystemExit(f"No fichero.duckdb inside {library}")
        return db
    if library.suffix == ".duckdb" and library.exists():
        return library
    raise SystemExit(f"Library not found: {library}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--library", help="Path to a .fichero bundle (or a .duckdb file)")
    ap.add_argument("--out", help="Output directory for the site project")
    ap.add_argument("--folder", default=None, help="Folder/document id to publish (default: whole library)")
    ap.add_argument("--title", default=None, help="Site title")
    ap.add_argument("--subtitle", default="", help="Site subtitle / tagline")
    ap.add_argument("--lang", default="es", help="Site language code (default: es)")
    ap.add_argument("--config", default=None, help="JSON config file (overridden by flags)")
    ap.add_argument("--base-url", default=None, help="Deploy path prefix for a sub-path host, e.g. '/my-repo' for GitHub Pages project sites. Default '' (root — Netlify/*.github.io). Leave empty for local serve.")
    ap.add_argument("--overwrite", action="store_true", help="Write into a non-empty output dir")
    ap.add_argument("--no-entities", action="store_true")
    ap.add_argument("--no-claims", action="store_true")
    ap.add_argument("--no-search", action="store_true")
    args = ap.parse_args()

    cfg: dict = {}
    if args.config:
        cfg.update(json.loads(Path(args.config).expanduser().read_text("utf-8")))
    if args.library:
        cfg["library"] = args.library
    if args.out:
        cfg["out"] = args.out
    if args.folder is not None:
        cfg["folder"] = args.folder
    if args.title is not None:
        cfg["title"] = args.title
    if args.subtitle:
        cfg["subtitle"] = args.subtitle
    cfg.setdefault("lang", args.lang)
    if args.no_entities:
        cfg["include_entities"] = False
    if args.no_claims:
        cfg["include_claims"] = False
    if args.no_search:
        cfg["include_search"] = False
    cfg.setdefault("include_entities", True)
    cfg.setdefault("include_claims", True)
    cfg.setdefault("include_search", True)
    if args.base_url is not None:
        cfg["base_url"] = args.base_url
    # Normalize base: "" (root) or "/prefix" with no trailing slash.
    base = (cfg.get("base_url") or "").strip().rstrip("/")
    if base and not base.startswith("/"):
        base = "/" + base
    cfg["base"] = base

    if not cfg.get("library") or not cfg.get("out"):
        raise SystemExit("--library and --out are required (or provide them in --config)")

    library = Path(cfg["library"]).expanduser()
    duckdb_path = resolve_duckdb(library)
    package_path = library if library.is_dir() else duckdb_path.parent
    output_dir = Path(cfg["out"]).expanduser()
    title = cfg.get("title") or (library.stem if library.is_dir() else "Fichero Catalogue")
    cfg["title"] = title

    print(f"[publish] library : {library}")
    print(f"[publish] output  : {output_dir}")
    print(f"[publish] title   : {title}")

    # Clean the output dir on --overwrite so stale pages/assets don't linger.
    if args.overwrite and output_dir.exists():
        if output_dir in (Path.home(), Path("/")) or output_dir == Path(output_dir.anchor):
            raise SystemExit(f"Refusing to clear unsafe output path: {output_dir}")
        shutil.rmtree(output_dir)

    # 1) Lock-safe: work on a throwaway copy of the DuckDB.
    with tempfile.TemporaryDirectory(prefix="fichero-export-") as tmp:
        tmp_db = Path(tmp) / "library.duckdb"
        shutil.copy2(duckdb_path, tmp_db)
        db = Database(tmp_db)
        try:
            result = export_eleventy_site(
                db=db,
                output_path=output_dir,
                target_id=cfg.get("folder"),
                recursive=True,
                overwrite=args.overwrite,
                package_path=str(package_path),
                site_title=title,
            )
        finally:
            db.close()

    src_dir = output_dir / "src"
    # Count entities/claims from the emitted pages.
    entity_count = len(list((src_dir / "entities").glob("*.md"))) if (src_dir / "entities").is_dir() else 0
    claim_files = list((src_dir / "claims").glob("*.md")) if (src_dir / "claims").is_dir() else []
    claim_count = result_claim_count(output_dir)
    cfg["doc_count"] = result.document_count
    cfg["entity_count"] = entity_count
    cfg["claim_count"] = claim_count

    print(f"[publish] exported {result.document_count} document pages, "
          f"{result.collection_count} collection(s), {entity_count} entities.")

    # 2) Post-process + 3) theme overlay.
    catalogue = process_document_pages(src_dir, cfg["base"])
    if not cfg.get("include_entities") and (src_dir / "entities").is_dir():
        shutil.rmtree(src_dir / "entities")
    if not cfg.get("include_claims") and (src_dir / "claims").is_dir():
        shutil.rmtree(src_dir / "claims")
    overlay_theme(output_dir, src_dir, cfg, catalogue)

    print(f"[publish] {len(catalogue)} expedientes catalogued.")
    print("\nDone. To preview locally:")
    print(f"  cd {output_dir}")
    print("  npm install")
    print("  npx @11ty/eleventy --serve   # http://localhost:8080\n")
    return 0


def result_claim_count(output_dir: Path) -> int:
    """Claims live in a single claims/index.md listing; count its list items."""
    claim_index = output_dir / "src" / "claims" / "index.md"
    if not claim_index.exists():
        return 0
    _, body = split_front_matter(claim_index.read_text("utf-8"))
    return len(re.findall(r"^\s*-\s+", body, re.MULTILINE))


if __name__ == "__main__":
    raise SystemExit(main())
