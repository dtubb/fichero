#!/usr/bin/env python3
"""Build the full User Guide .docx: manuscript chapters + capability reference.

Daniel's rulings (2026-08-29): the generated reference IS an appendix inside
the printed book, prompts in small type, wording stays honest
("Human-verified: not yet"). The manuscript master in Drive is never touched;
this writes a separate built artifact beside it.

Order (deterministic, mirrors the site):
  docs/user/guide/NN-*.md            (the human-edited chapters)
  Appendix part page (generated)
  docs/user/reference/index.md
  docs/user/reference/workflows/index.md + workflows/*.md
  docs/user/reference/tools/index.md + tools/*.md

Usage:
  python3 scripts/build_manual_appendix.py             # writes the Drive docx
  python3 scripts/build_manual_appendix.py --out X.docx
"""

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DRIVE = Path.home() / "My Drive/Tubb Lab/Apps/Fichero"
PANDOC = shutil.which("pandoc") or "/opt/homebrew/bin/pandoc"
GUIDE = REPO / "docs/user/guide"
REFERENCE = REPO / "docs/user/reference"
CODE_PT_HALF = "16"  # 8pt — the small-type ruling for prompts


def make_reference_doc(scratch: Path) -> Path:
    """Pandoc's default reference.docx with SourceCode/VerbatimChar shrunk."""
    ref = scratch / "reference.docx"
    ref.write_bytes(subprocess.run(
        [PANDOC, "--print-default-data-file", "reference.docx"],
        check=True, capture_output=True,
    ).stdout)
    patched = scratch / "reference-small-code.docx"
    with zipfile.ZipFile(ref) as zin, zipfile.ZipFile(patched, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "word/styles.xml":
                data = shrink_code_styles(data.decode("utf-8")).encode("utf-8")
            zout.writestr(item, data)
    return patched


def shrink_code_styles(xml: str) -> str:
    """Force a small w:sz on the code styles, adding rPr/sz if absent."""
    sz = f'<w:sz w:val="{CODE_PT_HALF}"/><w:szCs w:val="{CODE_PT_HALF}"/>'
    for style_id in ("SourceCode", "VerbatimChar"):
        m = re.search(rf'<w:style [^>]*w:styleId="{style_id}".*?</w:style>', xml, re.S)
        if not m:
            continue
        original = m.group(0)
        new = re.sub(r'<w:sz(?:Cs)?\b[^>]*/>', "", original)  # drop any existing sizes
        if "<w:rPr>" in new:
            new = new.replace("<w:rPr>", f"<w:rPr>{sz}", 1)
        else:
            new = new.replace("</w:style>", f"<w:rPr>{sz}</w:rPr></w:style>", 1)
        xml = xml.replace(original, new)
    return xml


def collect_inputs(scratch: Path) -> list[Path]:
    chapters = sorted(GUIDE.glob("[0-9][0-9]-*.md"))
    if not chapters:
        sys.exit(f"error: no chapters in {GUIDE} — run sync_manuscript.py user first")
    for req in (REFERENCE / "index.md", REFERENCE / "workflows/index.md", REFERENCE / "tools/index.md"):
        if not req.exists():
            sys.exit(f"error: {req} missing — run generate_capability_reference.py first")
    part = scratch / "zz-appendix-part.md"
    part.write_text(
        "# Appendix: Every Workflow and Tool\n\n"
        "The pages that follow are generated directly from the application, so "
        "the manual and the software cannot disagree about what a step does or "
        "what it asks a model. Prompts are printed in full, in small type, so "
        "you can reason about them.\n",
        encoding="utf-8",
    )
    return (
        chapters
        + [part, REFERENCE / "index.md", REFERENCE / "workflows/index.md"]
        + sorted(p for p in (REFERENCE / "workflows").glob("*.md") if p.name != "index.md")
        + [REFERENCE / "tools/index.md"]
        + sorted(p for p in (REFERENCE / "tools").glob("*.md") if p.name != "index.md")
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=DRIVE / "Fichero User Guide with Reference.docx")
    args = ap.parse_args()

    scratch = Path(tempfile.mkdtemp(prefix="manual-appendix-"))
    inputs = collect_inputs(scratch)
    ref_doc = make_reference_doc(scratch)

    # Demote reference pages so their H1s sit under the Appendix part heading.
    demoted = []
    for p in inputs:
        if REFERENCE in p.parents:
            d = scratch / f"ref-{len(demoted):03d}-{p.name}"
            d.write_text(re.sub(r"^(#+) ", r"#\1 ", p.read_text(encoding="utf-8"), flags=re.M), encoding="utf-8")
            demoted.append(d)
        else:
            demoted.append(p)

    cmd = [
        PANDOC, *map(str, demoted),
        "-f", "gfm", "-o", str(args.out),
        "--reference-doc", str(ref_doc),
        "--toc", "--toc-depth=2",
        "--resource-path", f"{REPO}/docs/user/guide:{REPO}/docs/user/reference/workflows:{REPO}/docs/user/reference/tools:{REPO}/docs/user/reference",
        "--metadata", "title=Fichero User Guide",
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr, file=sys.stderr)
        return 1
    n_ref = sum(1 for p in inputs if REFERENCE in p.parents)
    print(f"wrote {args.out}  ({len(inputs) - n_ref - 1} chapters + {n_ref} reference pages)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
