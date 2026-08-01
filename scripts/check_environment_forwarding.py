#!/usr/bin/env python3
"""Guardrail: the explicit environment hosts must not drift from the canonical
per-library injection list (#4448, #4455).

Why this exists
---------------
`DocumentTabView` builds `ContentView()` and re-forwards library-scoped
`@Observable` values to it BY HAND. When a value a descendant reads
non-optionally is missing from that list, SwiftUI does not warn, does not
degrade, and does not fail to build — it traps at runtime with

    No Observable object of type X found

from `EnvironmentValues.subscript.getter`. That crash has now shipped four
times, each time fixed by appending one more line to the list:

    #1561  WorkflowExecutionObserver
    #3298  KGQueryStore
    #3350  ArtifactService
    #4448  ActivityStore, WorkflowExecutionStore

A test that names the type which broke cannot catch the fifth. This checks the
SHAPE instead: `LibraryWorkspaceRoot` is the canonical, complete per-library
list, and anything it injects that a mirror host does not forward — while some
view reads it non-optionally — is a crash waiting for the right click.

Today's divergence is real and large, so it is recorded as a baseline in
`scripts/known_environment_forwarding_gaps.txt` (tracked by #4455). This script
fails on anything NEW. It is a ratchet, not a clean bill of health: the baseline
is debt, and shrinking it is the point.

Exit codes: 0 = no new gaps, 1 = a new gap, 2 = the file shapes moved.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
APP = REPO / "fichero" / "fichero"

LIBRARY_MANAGER = APP / "Models" / "LibraryManager.swift"
CANONICAL_HOST = APP / "Views" / "Library" / "Workspace" / "LibraryWorkspaceRoot.swift"
MIRROR_HOSTS = [APP / "Views" / "Shell" / "DocumentTabView.swift"]
BASELINE = REPO / "scripts" / "known_environment_forwarding_gaps.txt"

# `.environment(library.foo)` / `.environment(appState.foo)` / `.environment(foo)`
INJECT_RE = re.compile(r"\.environment\(\s*([A-Za-z_][A-Za-z0-9_.]*)\s*\)")
# `@Environment(Type.self) [private] var name[: Type[?]]`
ENV_READ_RE = re.compile(
    r"@Environment\(\s*([A-Za-z_][A-Za-z0-9_]*)\.self\s*\)\s*"
    r"(?:private\s+|public\s+|internal\s+)?var\s+([A-Za-z_][A-Za-z0-9_]*)"
    r"(?:\s*:\s*[A-Za-z_][A-Za-z0-9_]*(\?)?)?"
)
# `[@ObservationIgnored] [private(set)] [lazy] var|let name: Type`.
# `let` matters: most of LibraryReference's services are `let`, and requiring
# `var` silently resolved only half the list — which the sanity check below
# caught as parser blindness rather than letting it pass as "no gaps".
PROPERTY_RE = re.compile(
    r"^\s*(?:@ObservationIgnored\s+)?(?:private\(set\)\s+)?(?:lazy\s+)?(?:var|let)\s+"
    r"([A-Za-z_][A-Za-z0-9_]*)\s*:\s*([A-Za-z_][A-Za-z0-9_]*)",
    re.MULTILINE,
)


def library_property_types() -> dict[str, str]:
    """`LibraryReference.documentStore` -> `DocumentStore`."""
    return dict(PROPERTY_RE.findall(LIBRARY_MANAGER.read_text(encoding="utf-8")))


def non_optional_env_reads() -> dict[str, set[str]]:
    """Type -> files that read it as a NON-optional @Environment value.

    An optional read (`var x: Foo?`) cannot trap, so it is not a hazard.
    """
    found: dict[str, set[str]] = {}
    for path in APP.rglob("*.swift"):
        text = path.read_text(encoding="utf-8", errors="replace")
        for type_name, _var, optional in ENV_READ_RE.findall(text):
            if optional == "?":
                continue
            found.setdefault(type_name, set()).add(str(path.relative_to(REPO)))
    return found


def injected_types(path: Path, prop_types: dict[str, str]) -> set[str]:
    """Types a host injects, resolving `library.x` and bare locals to type names."""
    text = path.read_text(encoding="utf-8", errors="replace")
    # A host's own `@Environment(T.self) var name` gives `name` -> `T`, and its
    # own stored `let windowState: WindowState` gives the rest — a host forwards
    # both things it received and things it holds.
    local = {var: type_name for type_name, var, _ in ENV_READ_RE.findall(text)}
    local.update(dict(PROPERTY_RE.findall(text)))
    types: set[str] = set()
    for expr in INJECT_RE.findall(text):
        leaf = expr.split(".")[-1]
        if resolved := (prop_types.get(leaf) or local.get(leaf)):
            types.add(resolved)
        elif leaf[:1].isupper():
            types.add(leaf)  # `.environment(FeatureManager.shared)` style
    return types


def read_baseline() -> set[str]:
    if not BASELINE.exists():
        return set()
    return {
        line.strip()
        for line in BASELINE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }


def main() -> int:
    for required in (LIBRARY_MANAGER, CANONICAL_HOST, *MIRROR_HOSTS):
        if not required.exists():
            print(f"environment-forwarding guardrail: {required} is missing — "
                  "the composition roots moved; update this check.", file=sys.stderr)
            return 2

    prop_types = library_property_types()
    canonical = injected_types(CANONICAL_HOST, prop_types)
    if len(canonical) < 20:
        print("environment-forwarding guardrail: only "
              f"{len(canonical)} injections parsed from {CANONICAL_HOST.name}; "
              "the parser has gone blind rather than the list having shrunk.",
              file=sys.stderr)
        return 2

    reads = non_optional_env_reads()
    baseline = read_baseline()
    new_gaps: list[str] = []
    all_gaps: list[str] = []

    for host in MIRROR_HOSTS:
        forwarded = injected_types(host, prop_types)
        for type_name in sorted(canonical - forwarded):
            if type_name not in reads:
                continue  # nothing reads it non-optionally; it cannot trap
            key = f"{host.name}:{type_name}"
            all_gaps.append(key)
            if key not in baseline:
                new_gaps.append(f"{key} (read non-optionally in "
                                f"{len(reads[type_name])} view(s))")

    print(f"Environment-forwarding guardrail: {len(canonical)} canonical "
          f"per-library injections in {CANONICAL_HOST.name}")
    print(f"  {len(all_gaps)} forwarding gap(s); {len(baseline)} known (#4455).")

    if new_gaps:
        print("\nNEW environment-forwarding gap(s) — these trap at runtime with\n"
              '"No Observable object of type X found", the #4448 crash:\n',
              file=sys.stderr)
        for gap in new_gaps:
            print(f"  {gap}", file=sys.stderr)
        print("\nForward it from the host, or make every reader declare it "
              "optional. If it is genuinely unreachable there, add it to\n"
              f"{BASELINE.relative_to(REPO)} WITH a reason.", file=sys.stderr)
        return 1

    stale = sorted(baseline - set(all_gaps))
    if stale:
        print("\n✓ These baseline entries are now FIXED — delete them from "
              f"{BASELINE.relative_to(REPO)} so the ratchet tightens:")
        for entry in stale:
            print(f"  {entry}")

    print("\nOK: no new environment-forwarding gaps.")
    return 0


def self_test() -> int:
    """Prove the guardrail FIRES, not merely that it passes.

    A check that only ever returns 0 is indistinguishable from a check that
    inspects nothing — this repo has shipped that mistake more than once. So the
    proof is runnable rather than a claim in a commit message:

      1. the tree as it stands is clean;
      2. reverting #4448's own fix (dropping the `library.activityStore`
         forward) makes it fail, naming ActivityStore;
      3. deleting a baseline line makes it fail, so the ratchet is load-bearing
         and cannot be quietly widened;
      4. everything is restored afterwards.

    Every mutation is written to a temp copy and restored in a `finally`, so an
    interrupted self-test cannot leave edited source behind.
    """
    host = MIRROR_HOSTS[0]
    host_original = host.read_text(encoding="utf-8")
    baseline_original = BASELINE.read_text(encoding="utf-8") if BASELINE.exists() else ""
    failures: list[str] = []

    def expect(label: str, want: int) -> None:
        got = main()
        print(f"  [{'ok' if got == want else 'FAIL'}] {label}: rc={got} (want {want})")
        if got != want:
            failures.append(label)

    try:
        expect("tree as it stands is clean", 0)

        dropped = host_original.replace("                .environment(library.activityStore)\n", "")
        if dropped == host_original:
            failures.append("could not simulate the #4448 regression — the forward moved")
        else:
            host.write_text(dropped, encoding="utf-8")
            expect("reverting the #4448 ActivityStore forward is caught", 1)
            host.write_text(host_original, encoding="utf-8")

        trimmed = "\n".join(
            line for line in baseline_original.splitlines() if "NoteStore" not in line
        )
        BASELINE.write_text(trimmed + "\n", encoding="utf-8")
        expect("removing a baseline entry is caught (ratchet holds)", 1)
        BASELINE.write_text(baseline_original, encoding="utf-8")

        expect("everything restored", 0)
    finally:
        host.write_text(host_original, encoding="utf-8")
        BASELINE.write_text(baseline_original, encoding="utf-8")

    if failures:
        print("\nself-test FAILED:", "; ".join(failures), file=sys.stderr)
        return 1
    print("\nself-test passed: the guardrail fires on a real regression.")
    return 0


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(self_test())
    sys.exit(main())
