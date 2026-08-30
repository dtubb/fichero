#!/usr/bin/env python3
"""RETIRED as the authoring path (Daniel, 2026-08-30): the markdown pages in
docs/<guide>/guide/ are the MASTERS now, edited in Scrivener (folder sync) or
directly — see docs/contributor/writing-the-guides.md. Keep this script only
for one-off recovery of prose that exists solely in a .docx.

Sync a guide manuscript (Daniel's edited .docx) back into docs/ pages.

The manuscripts in ~/My Drive/Tubb Lab/Apps/Fichero/ are the human-edited
masters (see AGENTS.md "Manuscript model"). This script does the derived
half mechanically:

  1. pandoc the .docx back to markdown
  2. refresh the .md master beside the .docx
  3. split on H2 chapter headings into per-chapter pages under
     docs/<guide>/guide/NN-<slug>.md
  4. print the mkdocs `nav:` block for the chapters

It does NOT edit mkdocs.yml or delete the old hand-written pages — paste
the printed nav and retire superseded pages deliberately, then run
scripts/check_docs_publication.py and `mkdocs build --strict`.

Usage:
  python3 scripts/sync_manuscript.py user               # sync the User Guide
  python3 scripts/sync_manuscript.py contributor        # sync the Contributor Guide
  python3 scripts/sync_manuscript.py user --dry-run     # show the split, write nothing
"""

import argparse
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

DRIVE = Path.home() / "My Drive/Tubb Lab/Apps/Fichero"
REPO = Path(__file__).resolve().parent.parent
PANDOC = shutil.which("pandoc") or "/opt/homebrew/bin/pandoc"

GUIDES = {
    "user": {
        "docx": DRIVE / "Fichero User Guide.docx",
        "pages_dir": REPO / "docs/user/guide",
        "assets_dir": REPO / "docs/assets/users",
    },
    "contributor": {
        "docx": DRIVE / "Fichero Contributor Guide.docx",
        "pages_dir": REPO / "docs/contributor/guide",
        "assets_dir": REPO / "docs/assets/contributor",
    },
}


BADGE = "> \U0001F916 *AI Drafted (Not reviewed)*"


def slugify(title: str) -> str:
    t = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    t = re.sub(r"^(chapter\s+)?\d+[.:]?\s*", "", t, flags=re.I)  # drop "Chapter 3." / "3. "
    t = re.sub(r"[^a-zA-Z0-9]+", "-", t).strip("-").lower()
    return t[:60].strip("-") or "untitled"


def strip_marks(text: str) -> str:
    """Remove Word-highlight spans (Daniel's yellow = not-yet-edited marker)."""
    return re.sub(r'</?span[^>]*>', "", text)


def place_images(md: str, scratch: Path, assets_dir: Path, *, dry_run: bool) -> str:
    """Name extracted images from alt text or a following "Figure …" caption
    line, copy them into assets_dir, and rewrite refs page-relative
    (pages live two levels below docs/)."""
    rel_prefix = f"../../assets/{assets_dir.name}"
    lines = md.split("\n")
    seq = 0
    # Sized images come out of pandoc as raw HTML <img>; plain ones as ![alt](path).
    img_res = [
        re.compile(r"!\[(?P<alt>[^\]]*)\]\((?P<src>[^)\s]+)[^)]*\)"),
        re.compile(r'<img src="(?P<src>[^"]+)"[^>]*?(?:alt="(?P<alt>[^"]*)")?\s*/?>'),
    ]
    for i, line in enumerate(lines):
        for m in [m for rx in img_res for m in rx.finditer(line)]:
            src = Path(m.group("src"))
            if not src.is_absolute() or not src.exists():
                continue
            seq += 1
            name = (m.group("alt") or "").strip()
            if not name:  # look ahead for a caption line: "Figure 3: The library window"
                for nxt in lines[i + 1 : i + 3]:
                    if re.match(r"\s*[*_]?Figure\b", nxt, re.I):
                        name = re.sub(r"^[*_\s]*Figure\s*[\d.]*[:.]?\s*", "", nxt, flags=re.I).strip("*_ .")
                        break
            fname = f"{seq:02d}-{slugify(name) if name else src.stem}{src.suffix.lower()}"
            if not dry_run:
                assets_dir.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src, assets_dir / fname)
            line = line.replace(m.group("src"), f"{rel_prefix}/{fname}")
            print(f"  image: {fname}" + ("" if name else "  (no alt/caption — consider adding one)"))
        lines[i] = line
    return "\n".join(lines)


def fill_screenshot_placeholders(md: str, assets_dir: Path) -> str:
    """[SCREENSHOT: name — description] placeholders typed in the manuscript.
    If assets_dir/<slug(name)>.png exists, the placeholder becomes the image
    (description as caption). Otherwise it stays as a visible TODO on the page
    and is printed as the shot list for whoever drives the app."""
    rel_prefix = f"../../assets/{assets_dir.name}"
    todo = []

    def sub(m):
        raw = m.group(1)
        name, _, desc = [s.strip() for s in raw.partition("—" if "—" in raw else "-")]
        slug = slugify(name)
        for ext in (".png", ".jpg", ".jpeg"):
            if (assets_dir / f"{slug}{ext}").exists():
                cap = f"\n*{desc}*" if desc else ""
                return f"![{desc or name}]({rel_prefix}/{slug}{ext}){cap}"
        todo.append(f"{slug}.png — {desc or name}")
        return f"> 📷 *Screenshot to come: {desc or name}*"

    md = re.sub(r"\\?\[SCREENSHOT:?\s*([^\]]+?)\\?\]", sub, md, flags=re.I)
    if todo:
        print(f"\nshot list ({len(todo)} needed in {assets_dir}):")
        for s in todo:
            print(f"  {s}")
    return md


def split_chapters(md: str) -> list[tuple[str, str]]:
    """Return [(title, body)] split on H2 headings; body includes the heading."""
    parts = re.split(r"^## (.+)$", md, flags=re.M)
    chapters = []
    for i in range(1, len(parts) - 1, 2):
        title = parts[i].strip()
        body = f"# {title}\n{parts[i + 1].rstrip()}\n"
        chapters.append((title, body))
    return chapters


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("guide", choices=GUIDES)
    ap.add_argument("--dry-run", action="store_true", help="print the split; write nothing")
    args = ap.parse_args()

    g = GUIDES[args.guide]
    docx = g["docx"]
    if not docx.exists():
        sys.exit(f"error: {docx} not found")

    # Extract embedded images to a scratch dir, then name and place them.
    import tempfile
    scratch = Path(tempfile.mkdtemp(prefix="manuscript-media-"))
    md = subprocess.run(
        [PANDOC, str(docx), "-t", "gfm", "--wrap=none", f"--extract-media={scratch}"],
        check=True, capture_output=True, text=True,
    ).stdout
    md = place_images(md, scratch, g["assets_dir"], dry_run=args.dry_run)
    md = fill_screenshot_placeholders(md, g["assets_dir"])
    # Part markers ("# Part I — …") are structure inside the manuscript, not pages.
    md = re.sub(r"^# Part [^\n]+\n", "", md, flags=re.M)

    chapters = split_chapters(md)
    if not chapters:
        sys.exit("error: no '## ' chapter headings found — check the docx heading levels")

    # Word-highlight convention: a chapter whose TITLE is highlighted has not
    # been human-edited yet -> its page carries the AI-draft badge. Strip the
    # highlight markup itself everywhere; skip any Word-side table of contents.
    processed = []
    for title, body in chapters:
        unreviewed = 'class="mark"' in title
        title = strip_marks(title).strip()
        if slugify(title) in ("table-of-contents", "contents"):
            continue
        body = strip_marks(body)
        body = re.sub(r"^# .+$", f"# {title}", body, count=1, flags=re.M)
        if unreviewed:
            body = body.replace(f"# {title}\n", f"# {title}\n\n{BADGE}\n", 1)
        processed.append((title, body))
    chapters = processed

    pages_dir = g["pages_dir"]
    nav_lines = []
    print(f"{docx.name}: {len(chapters)} chapters")
    for n, (title, body) in enumerate(chapters, 1):
        rel = f"{pages_dir.relative_to(REPO / 'docs')}/{n:02d}-{slugify(title)}.md"
        label = re.sub(r"^(?:Chapter )?[0-9]+[.:] *", "", title)
        if ":" in label or label.startswith(("'", '"')):
            label = '"' + label.replace('"', "'") + '"'
        nav_lines.append(f"      - {label}: {rel}")
        print(f"  {rel}  ({len(body.split())} words)")
        if not args.dry_run:
            page = REPO / "docs" / rel
            page.parent.mkdir(parents=True, exist_ok=True)
            page.write_text(body, encoding="utf-8")

    if not args.dry_run:
        written = {f"{n:02d}-{slugify(title)}.md" for n, (title, _) in enumerate(chapters, 1)}
        for stale in pages_dir.glob("[0-9][0-9]-*.md"):
            if stale.name not in written:
                stale.unlink()
                print(f"  pruned stale page: {stale.name}")

    if not args.dry_run:
        # Refresh the .md master beside the .docx so the pair never drifts.
        (docx.with_suffix(".md")).write_text(md, encoding="utf-8")
        print(f"refreshed master: {docx.with_suffix('.md').name}")

    if args.dry_run:
        print("\nmkdocs nav block for these chapters:\n")
        print("\n".join(nav_lines))
        return 0

    # Update the generated nav block in mkdocs.yml (between BEGIN/END markers).
    marker = f"{args.guide}-guide chapters"
    yml = REPO / "mkdocs.yml"
    yt = yml.read_text()
    begin, end = f"# BEGIN {marker}", f"# END {marker}"
    if begin in yt and end in yt:
        head, _, rest = yt.partition(begin)
        mid, _, tail = rest.partition(end)
        first_line = mid.split("\n")[0]  # keep the marker's own comment text
        yt = head + begin + first_line + "\n" + "\n".join(nav_lines) + "\n      " + end + tail
        yml.write_text(yt)
        print("mkdocs.yml nav updated")
    else:
        print(f"NOTE: no '{begin}' markers in mkdocs.yml — paste this nav manually:")
        print("\n".join(nav_lines))

    # Site gates: publication guard + strict build.
    ok = True
    for cmd in ([sys.executable, "scripts/check_docs_publication.py"],
                [shutil.which("mkdocs") or "mkdocs", "build", "--strict"]):
        r = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)
        line = (r.stdout + r.stderr).strip().splitlines()
        print(f"{cmd[-2] if cmd[-1]=='--strict' else Path(str(cmd[-1])).name}: {'OK' if r.returncode == 0 else 'FAILED'}"
              + (f" — {line[-1]}" if line else ""))
        ok = ok and r.returncode == 0
    if not ok:
        print("site gates FAILED — fix before deploying")
        return 1
    print("site updated and gated; deploy with scripts/deploy-site.sh when ready")
    return 0


if __name__ == "__main__":
    sys.exit(main())
