#!/usr/bin/env python3
"""Validate every interchange file in a directory against its format's own schema.

    PYTHONPATH=fichero-server/src .venv/bin/python scripts/validate_exports.py <dir> [--recursive]

For a researcher who exported a library and wants to know it will open elsewhere,
and for us after changing a writer. Each file is identified by its BYTES (PAGE XML,
ALTO and TEI are all `.xml`), then checked with the same `validate()` the export
path runs, offline, against the vendored schemas.

Five outcomes per file, never collapsed into two:

* `valid`         -- the schema was consulted and found nothing.
* `INVALID`       -- the schema's own messages follow.
* `other version` -- the file is a version of the format we vendor no schema for
                     (ALTO 2.0, say). A version we DO vendor (PAGE 2013, ALTO 4.3)
                     is validated against its own schema instead. NOT invalid and NOT valid:
                     validating a 2013 PAGE file against the 2019 schema reports
                     every element as wrong, and that is a statement about us.
* `no schema`     -- the format has none by nature (hOCR is HTML, YOLO is lines of
                     numbers). NOT reported as valid: nothing was checked.
* `unrecognised`  -- no registered format claims the bytes.

Exit status is 1 if anything is INVALID, and also if NOTHING was validated: a
directory of the wrong files, or an empty one, is not a passing export. That is
the absence-read-as-success trap, and a script whose only job is to say "these are
fine" is where it does the most harm.
"""

from __future__ import annotations

import argparse
import re
import sys
from functools import lru_cache
from pathlib import Path

from fichero_server.formats import FormatSpec, format_for, validate
from fichero_server.formats.harness import SCHEMA_DIR
from fichero_server.formats.validation import parse, validate_xml

XSI = "{http://www.w3.org/2001/XMLSchema-instance}schemaLocation"
#: `alto-4-3.xsd`: a family and a version in the file name. ALTO keeps ONE namespace
#: for every 4.x, so the namespace cannot tell 4.2 from 4.3 and the declared file can.
#: Other versions we DO vendor a schema for, by what `other_version` returns. Exports
#: are written in the newest; these are for reading what other tools wrote.
#: Transkribus writes PAGE 2013; Kraken writes ALTO 4.3.
OTHER_VERSION_SCHEMAS = {
    "http://schema.primaresearch.org/PAGE/gts/pagecontent/2013-07-15": "pagecontent-2013-07-15.xsd",
    "alto-4-3.xsd": "alto-4-3.xsd",
}
VERSIONED_XSD = re.compile(r"^(?P<family>.+?)-(?P<version>\d+(?:-\d+)*)\.xsd$")


@lru_cache(maxsize=None)
def _target_namespace(schema: Path) -> str | None:
    return parse(schema.read_bytes()).get("targetNamespace")


def other_version(spec: FormatSpec, data: bytes) -> str | None:
    """What other version of the format these bytes declare, or None.

    Two signals, because formats version differently: PAGE changes NAMESPACE per
    release (2013-07-15, 2019-07-15), ALTO keeps `ns-v4#` for all of 4.x and says
    which in the schema FILE it declares. A file declaring nothing is validated --
    our own writers declare nothing, and they are what this checks first.
    """
    path = spec.schema_path()
    try:
        root = parse(data)
    except Exception:  # not well-formed: let validate() say so, in its own words
        return None
    namespace = root.tag[1:].split("}")[0] if root.tag.startswith("{") else ""
    if namespace != (_target_namespace(path) or ""):
        return namespace or "no namespace"
    pairs = (root.get(XSI) or "").split()
    declared = dict(zip(pairs[::2], pairs[1::2])).get(namespace, "")
    theirs = VERSIONED_XSD.match(declared.rsplit("/", 1)[-1])
    ours = VERSIONED_XSD.match(path.name)
    # ponytail: file-name versions only; a format that versions some third way needs its own signal here
    if theirs and ours and theirs["family"] == ours["family"] and theirs["version"] != ours["version"]:
        return declared.rsplit("/", 1)[-1]
    return None


def check(path: Path) -> tuple[str, str | None, list[str]]:
    """(outcome, format name or None, problems) for one file."""
    return check_bytes(path.name, path.read_bytes())


def check_bytes(filename: str, data: bytes) -> tuple[str, str | None, list[str]]:
    spec = format_for(filename, data)
    if spec is None:
        return "unrecognised", None, []
    if spec.schema is None:
        return "no schema", spec.name, []
    version = other_version(spec, data)
    if version is not None:
        schema = OTHER_VERSION_SCHEMAS.get(version)
        if schema is None:
            return "other version", spec.name, [f"declares {version}; no schema for it is vendored"]
        problems = validate_xml(data, SCHEMA_DIR / schema)
        return ("INVALID" if problems else "valid"), f"{spec.name} ({schema})", problems
    problems = validate(spec, data)
    return ("INVALID" if problems else "valid"), spec.name, problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("directory", type=Path)
    parser.add_argument("--recursive", "-r", action="store_true")
    args = parser.parse_args(argv)

    if not args.directory.is_dir():
        print(f"not a directory: {args.directory}", file=sys.stderr)
        return 2
    walk = args.directory.rglob("*") if args.recursive else args.directory.iterdir()
    files = sorted(p for p in walk if p.is_file() and not p.name.startswith("."))

    counts: dict[str, int] = {}
    for path in files:
        outcome, name, problems = check(path)
        counts[outcome] = counts.get(outcome, 0) + 1
        label = f"{outcome:<13} {name or '-':<30} {path.relative_to(args.directory)}"
        print(label)
        for problem in problems[:20]:
            print(f"    {problem}")
        if len(problems) > 20:
            print(f"    ... and {len(problems) - 20} more")

    summary = ", ".join(f"{counts.get(k, 0)} {k}" for k in ("valid", "INVALID", "other version", "no schema", "unrecognised"))
    print(f"\n{len(files)} files: {summary}")
    if counts.get("INVALID"):
        return 1
    if not counts.get("valid"):
        print("nothing was validated -- this is not a pass", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
