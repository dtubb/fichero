#!/usr/bin/env python3
"""Every `ChangeEventConsumer` must be registered with the change stream (#4954).

A store can conform to `ChangeEventConsumer`, implement `apply` and `resync` correctly,
be covered by passing tests — and never run, because nothing ever handed it to
`LibraryChangeStream.register`. That is not a subtle failure: the store simply does not
react to anything the engine emits, and every test of it still passes, because a unit
test constructs the store itself.

FOUND THE HARD WAY, 2026-09-27. `SegmentStore`'s conformance was committed with tests
and was dead code: neither it nor `SegmentService` was constructed anywhere in the app,
so `grep -rn SegmentStore fichero/fichero` outside the two model files returned two
comments. The lane that found it, found it by wiring — and wrote down why no guard
helped: "no guard asks whether a registered consumer exists for a domain the engine
emits."

It is the sixth case in two days of code that is built and has no door (#5075/#5088's
data-loss mitigation, #5110's two entity sheets, this seam's overlay function, this
store's change handling, and #4890's artifact subscriber, which the spec twice said did
not exist). A reference count cannot tell built-and-unreachable from unbuilt, and nor
can a passing test. This guard asks the one question that separates them for this
shape: is the thing plugged in?

WHAT IT CHECKS, and why that is the honest line: every type conforming to
`ChangeEventConsumer` is named in the file that performs registration. Not "is passed to
`register(` " directly — most are registered as `self.documentStore`, so the type name
appears only on the property's declaration. Naming the file is what makes the check
resolvable without a Swift type-checker, and it is sufficient: a consumer absent from
that file cannot be registered from it.

It deliberately does NOT try to prove a registration RUNS. `register` sits inside the
stream's construction closure, and whether that closure executes is a runtime question
this cannot answer. It catches the failure that actually happened — a conformer nobody
mentions where registration lives — and says so plainly rather than implying more.

Usage:
    scripts/check_change_consumers_registered.py
    scripts/check_change_consumers_registered.py --list
    scripts/check_change_consumers_registered.py --self-test
"""
from __future__ import annotations

import re
import sys

from _check_floor import require_scan_floor
from pathlib import Path
from _scan_files import scan_rglob

ROOT = Path(__file__).resolve().parent.parent
SWIFT_ROOT = ROOT / "fichero" / "fichero"
PROTOCOL = "ChangeEventConsumer"
RULE_DOC = "#4954"

#: Where registration happens. A named, committed source: if it moves, this check is
#: BLIND and says so (#4382) rather than reporting every consumer as unregistered.
REGISTRAR = SWIFT_ROOT / "Models" / "LibraryManager.swift"
#: Where the protocol and `register` live; excluded from the conformer scan so the
#: protocol's own declaration is not read as a conformance.
STREAM = SWIFT_ROOT / "Services" / "LibraryChangeStream.swift"

#: `final class X: ChangeEventConsumer`, `extension X: ChangeEventConsumer`, and the
#: multi-protocol forms (`final class X: Observable, ChangeEventConsumer`).
_CONFORMER = re.compile(
    r"\b(?:final\s+class|class|struct|actor|extension)\s+"
    r"([A-Za-z_][A-Za-z0-9_]*)\s*:[^{\n]*\b" + PROTOCOL + r"\b"
)
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)

KNOWN_UNREGISTERED: dict[str, str] = {}


def code_only(text: str) -> str:
    """Comments removed, so a conformance discussed in prose is not counted as one.

    Strings are left alone: a type name inside a string literal is not a conformance
    declaration, because the pattern requires the `class`/`extension` keyword.
    """
    text = _BLOCK_COMMENT.sub(" ", text)
    return "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("//")
    )


def conformers() -> dict[str, list[str]]:
    """Consumer type name -> the files declaring the conformance."""
    found: dict[str, list[str]] = {}
    for path in sorted(scan_rglob(SWIFT_ROOT, "*.swift")):
        if path == STREAM:
            continue
        try:
            source = code_only(path.read_text(encoding="utf-8", errors="ignore"))
        except OSError:
            continue
        for name in _CONFORMER.findall(source):
            found.setdefault(name, []).append(str(path.relative_to(SWIFT_ROOT)))
    return found


def registered_names(registrar_source: str) -> set[str]:
    """Every identifier the registrar file mentions, comments stripped.

    A consumer registered as `self.documentStore` has its TYPE named on the property
    declaration in this same file, which is why mentioning is the test rather than
    appearing inside `register(`.
    """
    return set(re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\b", code_only(registrar_source)))


def scan() -> dict[str, list[str]]:
    """Consumer -> where it is declared, for consumers the registrar never names."""
    if not REGISTRAR.exists():
        raise FileNotFoundError(REGISTRAR)
    mentioned = registered_names(REGISTRAR.read_text(encoding="utf-8", errors="ignore"))
    return {
        name: where
        for name, where in conformers().items()
        if name not in mentioned and name not in KNOWN_UNREGISTERED
    }


def _self_test() -> int:
    assert _CONFORMER.findall("final class A: ChangeEventConsumer {") == ["A"]
    assert _CONFORMER.findall("extension B: ChangeEventConsumer {") == ["B"]
    assert _CONFORMER.findall("final class C: Observable, ChangeEventConsumer {") == ["C"]
    assert _CONFORMER.findall("final class D: ChangeEventConsumerish {") == []
    # Prose about a conformance is not a conformance.
    assert _CONFORMER.findall(code_only("// final class E: ChangeEventConsumer {")) == []
    assert _CONFORMER.findall(code_only("/* extension F: ChangeEventConsumer */")) == []
    # A registrar naming the type counts however the instance is spelled.
    assert "DocumentStore" in registered_names("var documentStore: DocumentStore")
    assert "SegmentStore" in registered_names("stream.register(SegmentStore.shared(for: s))")
    assert "Ghost" not in registered_names("// Ghost was removed")
    print("check_change_consumers_registered self-test passed")
    return 0


def main() -> int:
    argv = sys.argv[1:]
    if any(a in ("-h", "--help") for a in argv):
        print(__doc__)
        return 0
    if "--self-test" in argv:
        return _self_test()

    if not REGISTRAR.exists():
        print(
            f"check_change_consumers_registered.py: BLIND -- the registrar is not on disk:\n"
            f"  REGISTRAR -> {REGISTRAR.relative_to(ROOT)}\n"
            "Registration moved; repoint the constant. Reporting every consumer as\n"
            "unregistered would be worse than saying nothing.",
            file=sys.stderr,
        )
        return 2

    all_conformers = conformers()
    require_scan_floor(len(all_conformers), 3, f"{PROTOCOL} conformers (5 on 2026-09-27)")
    missing = scan()

    print(f"change-consumer registration guardrail: {len(all_conformers)} {PROTOCOL}(s)")
    if "--list" in argv:
        mentioned = registered_names(REGISTRAR.read_text(encoding="utf-8", errors="ignore"))
        for name, where in sorted(all_conformers.items()):
            mark = "ok" if name in mentioned else "UNREGISTERED"
            print(f"  [{mark}] {name}  <-  {', '.join(where)}")
        return 0

    if missing:
        print(f"\nFAIL {len(missing)} {PROTOCOL}(s) that nothing registers. Rule: {RULE_DOC}")
        for name, where in sorted(missing.items()):
            print(f"  {name}  declared in {', '.join(where)}")
        print(
            f"\nA consumer the registrar never names cannot be registered from it, so its\n"
            f"`apply`/`resync` never run however well they are tested — a unit test builds\n"
            f"the store itself. Register it in {REGISTRAR.relative_to(ROOT)}, or add it to\n"
            "KNOWN_UNREGISTERED with the reason it is deliberately inert."
        )
        return 1

    print(f"\nPASS every {PROTOCOL} is named where registration happens.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
