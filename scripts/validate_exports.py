#!/usr/bin/env python3
"""Does OUR export of every file in a directory validate against the latest schema?

    PYTHONPATH=fichero-server/src .venv/bin/python scripts/validate_exports.py <dir> [-r] [--inputs]

THE POINT IS OUR EXPORT (ruled 2026-09-27). Every file here is an INPUT, in any version
of its format: PAGE 2013, ALTO 2 or 4.3, files that are invalid by their own schema.
Reading them is how material gets in. The default mode reads each one, writes it back
out through our writer for its format, and validates OUR output against the latest
schema that writer targets. It exits 1 only when one of OUR exports is invalid, or when
a file we recognise could not be read or written (that is ours too: reading every
input is the job). It also exits 1 when nothing was exported at all, because an empty
directory, or one full of files nothing claims, is not a pass. That is the
absence-read-as-success trap.

Each input's OWN validity is reported alongside, as information, never as a failure:

* `valid`         -- checked against its own schema and fine.
* `INVALID`       -- checked against its own schema, with the messages.
* `other version` -- a version we vendor no schema for (ALTO 2.x: its schema states no
                     licence). Neither valid nor invalid.
* `no schema`     -- the format has none by nature (hOCR, YOLO).
* `unrecognised`  -- no registered format claims the bytes.

`--inputs` checks the inputs only (the earlier behaviour): useful for looking at other
tools' files, and it exits 1 on an invalid input.
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
#: Transkribus writes PAGE 2013; Kraken writes ALTO 4.3; 4.4 is current. ALTO 2.x is NOT here:
#: its schema states no licence (schemas/PROVENANCE.md).
OTHER_VERSION_SCHEMAS = {
    "alto-4-2.xsd": "alto-4-2.xsd",
    "http://schema.primaresearch.org/PAGE/gts/pagecontent/2013-07-15": "pagecontent-2013-07-15.xsd",
    "alto-4-3.xsd": "alto-4-3.xsd",
    "alto-4-4.xsd": "alto-4-4.xsd",
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
    if spec.schema is None and spec.check is None:
        return "no schema", spec.name, []
    if spec.schema is None:  # a checker written from the format's normative text
        problems = validate(spec, data)
        return ("INVALID" if problems else "valid"), spec.name, problems
    version = other_version(spec, data)
    if version is not None:
        schema = OTHER_VERSION_SCHEMAS.get(version)
        if schema is None:
            return "other version", spec.name, [f"declares {version}; no schema for it is vendored"]
        problems = validate_xml(data, SCHEMA_DIR / schema)
        return ("INVALID" if problems else "valid"), f"{spec.name} ({schema})", problems
    problems = validate(spec, data)
    return ("INVALID" if problems else "valid"), spec.name, problems


def export_check(filename: str, data: bytes) -> tuple[str, str | None, list[str]]:
    """(outcome, format, problems) for OUR export of this input.

    `exported`: our writer's output passed the latest schema (the harness validates every
    write). `EXPORT INVALID`: it did not. `UNREADABLE` / `UNWRITABLE`: we recognise the
    format and failed it -- ours as well. `not exported`: no format claims it, or the format
    goes one way only.
    """
    from fichero_server.formats import InvalidExport, read_page, write_page

    spec = format_for(filename, data)
    if spec is None or not (spec.reads and spec.writes):
        return "not exported", spec.name if spec else None, []
    try:
        page = read_page(spec.name, data)
    except Exception as exc:  # noqa: BLE001 -- reported by name, and counted as a failure
        return "UNREADABLE", spec.name, [f"{type(exc).__name__}: {exc}"]
    try:
        write_page(spec.name, page)
    except InvalidExport as exc:
        return "EXPORT INVALID", spec.name, list(exc.problems)
    except Exception as exc:  # noqa: BLE001 -- reported by name, and counted as a failure
        return "UNWRITABLE", spec.name, [f"{type(exc).__name__}: {exc}"]
    return "exported", spec.name, []


OUR_FAILURES = ("EXPORT INVALID", "UNREADABLE", "UNWRITABLE")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("directory", type=Path)
    parser.add_argument("--recursive", "-r", action="store_true")
    parser.add_argument("--inputs", action="store_true", help="check the inputs only")
    args = parser.parse_args(argv)

    if not args.directory.is_dir():
        print(f"not a directory: {args.directory}", file=sys.stderr)
        return 2
    walk = args.directory.rglob("*") if args.recursive else args.directory.iterdir()
    files = sorted(p for p in walk if p.is_file() and not p.name.startswith("."))
    return _inputs(files, args.directory) if args.inputs else _exports(files, args.directory)


def _print(outcome: str, name: str | None, path: Path, root: Path, problems: list[str]) -> None:
    print(f"{outcome:<15} {name or '-':<30} {path.relative_to(root)}")
    for problem in problems[:20]:
        print(f"    {problem}")
    if len(problems) > 20:
        print(f"    ... and {len(problems) - 20} more")


def _exports(files: list[Path], root: Path) -> int:
    ours: dict[str, int] = {}
    theirs: dict[str, int] = {}
    for path in files:
        data = path.read_bytes()
        outcome, name, problems = export_check(path.name, data)
        ours[outcome] = ours.get(outcome, 0) + 1
        input_outcome = check_bytes(path.name, data)[0]
        theirs[input_outcome] = theirs.get(input_outcome, 0) + 1
        _print(outcome, name, path, root, problems)
        print(f"    (the input itself: {input_outcome})")

    summary = ", ".join(f"{ours.get(k, 0)} {k}" for k in ("exported", *OUR_FAILURES, "not exported"))
    info = ", ".join(f"{theirs.get(k, 0)} {k}" for k in ("valid", "INVALID", "other version", "no schema", "unrecognised"))
    print(f"\n{len(files)} files. Our exports: {summary}.")
    print(f"The inputs as they arrived (information, not a failure): {info}.")
    if any(ours.get(k) for k in OUR_FAILURES):
        return 1
    if not ours.get("exported"):
        print("nothing was exported -- this is not a pass", file=sys.stderr)
        return 1
    return 0


def _inputs(files: list[Path], root: Path) -> int:
    counts: dict[str, int] = {}
    for path in files:
        outcome, name, problems = check(path)
        counts[outcome] = counts.get(outcome, 0) + 1
        _print(outcome, name, path, root, problems)

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
