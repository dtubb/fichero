"""file(1) output piped into a text filter must run under LC_ALL=C (#4488-class).

``file`` echoes bytes from the paths and contents it inspects; the embedded
engine ships names that are not valid UTF-8; under a UTF-8 locale, awk/grep/
cut/sed/tr ABORT on those bytes ("Illegal byte sequence") — and in a release
script that abort takes the release with it. It killed three release runs on
2026-08-02, twice because the sweep that "fixed the class" stopped at the
first sites it recognised: four file(1)->awk pipes existed, two were fixed,
and the third killed TestFlight.

This check IS the re-enumeration that was skipped. Enumerate-then-assert:
every ``file``-producing pipeline segment feeding awk/grep/cut/sed/tr under
scripts/ (and fichero-server/scripts/) must carry ``LC_ALL=C`` on the line.
Not narrowed to awk: cut and tr fail on the same bytes — the diagnosis took
an hour precisely because the diagnostic pipeline itself choked and printed
a complaint about itself instead of the error underneath.

Exit codes: 0 all pipes safe · 1 violations (listed) · 2 BLIND (roots
missing, or zero file(1) pipes found — the idiom moved, never "all safe").
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from _check_floor import require_scan_floor

ROOT = Path(__file__).resolve().parent.parent
SCAN_ROOTS = (ROOT / "scripts", ROOT / "fichero-server" / "scripts")
# `scripts/gate` is bash without the .sh extension; include it explicitly.
EXTRA_FILES = (ROOT / "scripts" / "gate",)

# A pipeline segment that runs file(1): `file ...`, `-exec file {} +`,
# `xargs file`. Word-bounded so "profile"/"filename" never match.
_FILE_CMD = re.compile(r"(?:^|[|;&(`]|\bexec\s|\bxargs\s+)\s*file\b")
_TEXT_FILTER_PIPE = re.compile(r"\|\s*(?:LC_ALL=C\s+)?(awk|grep|cut|sed|tr)\b")


def _logical_lines(text: str):
    """Join backslash-continued lines so a wrapped pipeline is one unit."""
    joined: list[tuple[int, str]] = []
    buffer = ""
    start = 0
    for i, raw in enumerate(text.splitlines(), 1):
        if not buffer:
            start = i
        if raw.rstrip().endswith("\\"):
            buffer += raw.rstrip()[:-1] + " "
            continue
        joined.append((start, buffer + raw))
        buffer = ""
    if buffer:
        joined.append((start, buffer))
    return joined


def scan() -> tuple[list[str], int]:
    """(violations, file_pipe_sites_examined)."""
    violations: list[str] = []
    sites = 0
    shell_files: list[Path] = []
    for root in SCAN_ROOTS:
        if root.is_dir():
            shell_files.extend(sorted(root.rglob("*.sh")))
    shell_files.extend(p for p in EXTRA_FILES if p.is_file())

    for path in shell_files:
        try:
            text = path.read_text(errors="ignore")
        except OSError:
            continue
        for lineno, line in _logical_lines(text):
            code = line.split("#", 1)[0]
            if "file" not in code or "|" not in code:
                continue
            if not _FILE_CMD.search(code):
                continue
            if not _TEXT_FILTER_PIPE.search(code):
                continue
            sites += 1
            if "LC_ALL=C" not in code:
                rel = path.relative_to(ROOT).as_posix()
                violations.append(
                    f"{rel}:{lineno}: file(1) piped into a text filter "
                    f"without LC_ALL=C — non-UTF-8 bytes will ABORT it"
                )
    return violations, sites


def _self_test() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        bad = Path(tmp) / "bad.sh"
        bad.write_text(
            'find "$APP" -type f -exec file {} + | awk -F: \'/Mach-O/ {print $1}\'\n'
        )
        good = Path(tmp) / "good.sh"
        good.write_text(
            'find "$APP" -type f -exec file {} + | LC_ALL=C awk -F: \'/Mach-O/ {print $1}\'\n'
        )
        caught: list[str] = []
        for p in (bad, good):
            for lineno, line in _logical_lines(p.read_text()):
                code = line.split("#", 1)[0]
                if (
                    _FILE_CMD.search(code)
                    and _TEXT_FILTER_PIPE.search(code)
                    and "LC_ALL=C" not in code
                ):
                    caught.append(p.name)
        assert caught == ["bad.sh"], (
            f"self-test: expected exactly bad.sh caught, got {caught} — "
            "the detector cannot be trusted"
        )


def main() -> int:
    argv = sys.argv[1:]
    if any(a in ("-h", "--help") for a in argv):
        print(__doc__)
        return 0

    _self_test()
    if "--self-test" in argv:
        print("check_locale_safe_binary_pipes self-test: OK")
        return 0

    missing = [str(r) for r in SCAN_ROOTS if not r.is_dir()]
    if missing:
        print(
            f"BLIND: scan root(s) missing: {', '.join(missing)} (#4382)",
            file=sys.stderr,
        )
        return 2

    violations, sites = scan()
    # #4487 scan floor on the pipe-site population: zero file(1) pipes found
    # means the idiom moved (or the detector died), never "all safe".
    # 1 site on this branch on 2026-08-02; ~5 expected after the release-lane
    # merge lands its four.
    require_scan_floor(sites, 1, "file(1)->text-filter pipe sites (1+ on 2026-08-02)")

    print(f"Locale-safe binary pipes: {sites} file(1) pipe site(s) scanned.")
    if violations:
        print(f"\n  ✗ {len(violations)} pipe(s) without LC_ALL=C:")
        for v in violations:
            print(f"      {v}")
        print(
            "\nFix: prefix the text filter with LC_ALL=C (e.g. "
            "`file ... | LC_ALL=C awk ...`). file(1) emits raw bytes; a UTF-8 "
            "locale makes awk/grep/cut/sed/tr abort on them, and in a release "
            "script that abort takes the release with it."
        )
        return 1
    print("  ✓ every file(1) pipe runs its filter under LC_ALL=C.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
