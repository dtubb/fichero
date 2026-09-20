#!/usr/bin/env python3
"""Fail when something reads `Artifact.ocr_geometry` directly (#4924).

THE DEFECT THIS EXISTS FOR
--------------------------
From a person's first edit, a page's boxes stop living in
`Artifact.ocr_geometry`. The block is KEPT -- it is the record of what the
machine produced, and still the home of each box's words -- but it is frozen
at the state BEFORE that edit, for good. The live answer comes from the
segment rows, through
`api/routes/document/segment_conversion.py::live_geometry`.

So `artifact.ocr_geometry` is now a trap with no tripwire. A reader that
takes it gets a page as it looked before its owner curated it: correct-
looking boxes, in the right shape, in the right frame, simply not where the
historian put them. Nothing raises. Nothing logs. The recon for #4924 found
SIX such readers in code that was already written and passing -- among them
`GET /api/artifacts/{id}/region`, which is the single seam where a claim, a
highlight or a search hit becomes a place on the page. A claim's highlight
pointing at where a box used to be is exactly the class of silent wrongness
this project cannot ship.

The type system cannot help: the field is a plain `OCRGeometryResult | None`
and the stale read is the same type as the live one. So the check lives here.

WHAT IT SEES AND DOES NOT SEE (read before trusting a green run)
---------------------------------------------------------------
Pure AST, no regex: every `<expr>.ocr_geometry` attribute access in the
server, CLI and MCP source trees, minus the permitted files below and minus
WRITES (`x.ocr_geometry = ...` and `ocr_geometry=` keyword arguments, which
are how an artifact is built in the first place and are not this defect).

It CANNOT see a dynamic read -- `getattr(artifact, field)`,
`artifact.model_dump()["ocr_geometry"]`, a dict built from a row. Those are
counted and reported, never silently dropped: a green run means "no direct
attribute read outside the permitted files", NOT "everything reads live".

Tests are not scanned. A test may legitimately assert on the STORED block --
indeed `source.store.conversion-changes-nothing-seen` must -- and forcing
them through `live_geometry` would make the tests agree with the code by
construction, which is the opposite of a test.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

SCANNED_ROOTS = (
    "fichero-server/src/fichero_server",
    "fichero-cli/src/fichero_cli",
    "fichero-mcp/src/fichero_mcp",
)

#: A single line may be allowed instead of a whole file, by ending it with
#: this pragma and a reason. PREFER THE PRAGMA: permitting a 1,300-line
#: module wholesale also blesses the next raw read somebody adds to it, and
#: the reason then lives at the read rather than in this script.
PRAGMA = "# raw-geometry-ok:"

#: The ONLY files allowed to read the stored block directly. Both want the
#: MACHINE'S ORIGINAL rather than the person's current page, and say so in
#: their own comments. Adding a file here is a decision to serve possibly
#: stale geometry: say why, in the file, next to the read.
PERMITTED = {
    # `live_geometry` itself: it decides WHICH store to read, and rebuilds
    # the person's page FROM the original.
    "fichero-server/src/fichero_server/api/routes/document/segment_conversion.py",
    # The read seam and the conversion: `segments_from_result` turns the
    # machine's own block into the rows, and the seam serves the block for
    # artifacts nobody has edited yet.
    "fichero-server/src/fichero_server/api/routes/document/segments.py",
}

ATTR = "ocr_geometry"


class Reads(ast.NodeVisitor):
    def __init__(self) -> None:
        self.reads: list[tuple[int, str]] = []
        self.dynamic: list[tuple[int, str]] = []

    def visit_Attribute(self, node: ast.Attribute) -> None:
        # A write (`x.ocr_geometry = ...`) parses as an Attribute with
        # Store context; only Load context is a read.
        if node.attr == ATTR and isinstance(node.ctx, ast.Load):
            self.reads.append((node.lineno, ast.unparse(node)))
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name) and node.func.id == "getattr":
            if len(node.args) >= 2 and not (
                isinstance(node.args[1], ast.Constant) and node.args[1].value != ATTR
            ):
                self.dynamic.append((node.lineno, ast.unparse(node)[:90]))
        self.generic_visit(node)


def main() -> int:
    offenders: list[str] = []
    allowed_lines: list[str] = []
    dynamic: list[str] = []
    scanned = 0

    for root in SCANNED_ROOTS:
        base = REPO / root
        if not base.exists():
            print(f"FAIL: scanned root missing, the check would pass vacuously: {root}")
            return 1
        for path in sorted(base.rglob("*.py")):
            rel = path.relative_to(REPO).as_posix()
            scanned += 1
            try:
                text = path.read_text(encoding="utf-8")
                lines = text.splitlines()
                tree = ast.parse(text)
            except SyntaxError as exc:
                print(f"FAIL: cannot parse {rel}: {exc}")
                return 1
            visitor = Reads()
            visitor.visit(tree)
            for lineno, src in visitor.dynamic:
                dynamic.append(f"  {rel}:{lineno}  {src}")
            if rel in PERMITTED:
                continue
            for lineno, src in visitor.reads:
                line = lines[lineno - 1] if 0 < lineno <= len(lines) else ""
                if PRAGMA in line:
                    reason = line.split(PRAGMA, 1)[1].strip()
                    if not reason:
                        print(
                            f"FAIL: {rel}:{lineno} uses {PRAGMA} with no reason. "
                            "The reason IS the allowance."
                        )
                        return 1
                    allowed_lines.append(f"  {rel}:{lineno}  {reason}")
                    continue
                offenders.append(f"  {rel}:{lineno}  {src}")

    print(f"scanned {scanned} files in {len(SCANNED_ROOTS)} roots")
    if dynamic:
        print(
            f"\nNOTE: {len(dynamic)} dynamic attribute access(es) this check cannot "
            "resolve. A green run does not cover these:"
        )
        for line in dynamic:
            print(line)

    if allowed_lines:
        print(f"\n{len(allowed_lines)} read(s) allowed line by line:")
        for line in allowed_lines:
            print(line)

    if not offenders:
        print(
            f"\nOK: no direct `.{ATTR}` read outside the "
            f"{len(PERMITTED)} permitted file(s) and "
            f"{len(allowed_lines)} allowed line(s)."
        )
        return 0

    print(
        f"\nFAIL: {len(offenders)} direct read(s) of the STORED geometry block "
        "outside the permitted files:\n"
    )
    for line in offenders:
        print(line)
    print(
        "\nOn a converted page that block is frozen at the state BEFORE its "
        "owner's first\nedit. Call "
        "`api/routes/document/segment_conversion.py::live_geometry(db, artifact)`\n"
        "instead -- it returns the block for an unconverted artifact and the "
        "live rows for a\nconverted one. If this reader genuinely wants the "
        "MACHINE'S ORIGINAL, add its file\nto PERMITTED in this script AND say "
        "why in a comment beside the read (#4924)."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
