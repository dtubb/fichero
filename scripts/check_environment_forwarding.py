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
SHAPE instead — but only at a boundary that is REAL.

The first version assumed every unforwarded type was a hazard. Measuring proved
that wrong: 14 types were unforwarded and read by 39 in-tree views, and NONE of
them ever crashed. Environment values inherit down the view tree. The one type
that did crash, ActivityStore, is read by two TOOLBAR items — and toolbar content
is laid out by the window, not by this tree, so it does not inherit. A Scene
likewise never inherits from another Scene (#3350).

So the property here is narrow and true: a type LibraryWorkspaceRoot injects,
that a mirror host does not forward, AND that is read non-optionally from OUTSIDE
the view tree. In-tree readers are not gaps and are not reported.

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

# Self-test seam (2026-08-09): the self-test used to WRITE mutations into the
# real source files and restore them in a `finally` — unsafe under a
# concurrent writer (another agent's edit could be clobbered by the restore)
# and not crash-safe (finally does not survive SIGKILL). All reads go through
# `_read`, which consults this in-memory override map first; the self-test
# synthesizes its regressions HERE and never touches disk.
_TEXT_OVERRIDES: dict[Path, str] = {}


def _read(path: Path) -> str:
    if path in _TEXT_OVERRIDES:
        return _TEXT_OVERRIDES[path]
    return path.read_text(encoding="utf-8", errors="replace")

# The shared re-injection helper, and the hosts that exist ONLY to carry the
# library environment across a hosting boundary. See `boundary_gaps`.
SHARED_HELPER = APP / "Views" / "Shell" / "LibraryServiceEnvironment.swift"
BOUNDARY_HOSTS = [
    SHARED_HELPER,
    APP / "Views" / "Inspector" / "FocusedDocument.swift",
]
HELPER_CALL = ".libraryServiceEnvironment("

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


def is_hosted_outside_the_view_tree(path: Path, text: str) -> bool:
    """Whether this view is laid out by something OTHER than the content tree.

    Toolbar content is laid out by the WINDOW, and a Scene never inherits from
    another Scene. Those are the only two boundaries an environment value must
    be carried across by hand (#4455); everything inside the tree inherits.
    """
    return (
        "ToolbarItem" in path.name
        or path.name.endswith("Window.swift")
        or re.search(r":\s*ToolbarContent\b", text) is not None
    )


def non_optional_env_reads() -> dict[str, set[str]]:
    """Type -> files that read it NON-optionally FROM OUTSIDE the view tree.

    Two filters, and the second is the whole point of this check (#4455):

    * an optional read (`var x: Foo?`) cannot trap, so it is not a hazard;
    * an IN-TREE read inherits, so it is not a hazard either. The first version
      of this script counted those, and reported 39 in-tree readers across 14
      types as gaps. Every one was a non-problem. A guardrail that fires on a
      non-problem costs time forever and trains people to add ceremony, which is
      how the forwarding list it guards reached ~43 entries.

    Measured basis: those 39 in-tree readers never crashed while unforwarded.
    The one type that DID crash, ActivityStore (#4448), is read by two toolbar
    items. 39 in-tree fine, 2 toolbar trapping — the boundary is the host, not
    the forwarding chain.
    """
    found: dict[str, set[str]] = {}
    for path in APP.rglob("*.swift"):
        text = _read(path)
        if not is_hosted_outside_the_view_tree(path, text):
            continue
        for type_name, _var, optional in ENV_READ_RE.findall(text):
            if optional == "?":
                continue
            found.setdefault(type_name, set()).add(str(path.relative_to(REPO)))
    return found


def injected_types(path: Path, prop_types: dict[str, str]) -> set[str]:
    """Types a host injects, resolving `library.x` and bare locals to type names."""
    text = _read(path)
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


def injected_library_types(path: Path, prop_types: dict[str, str]) -> set[str]:
    """Only the LIBRARY-scoped types a file injects — `.environment(library.x)`.

    Deliberately narrower than `injected_types`: a boundary host also forwards
    window/app objects (`windowState`, `kgFocusState`), and those are not part
    of the per-library contract being compared.
    """
    text = _read(path)
    types: set[str] = set()
    for expr in INJECT_RE.findall(text):
        if "." not in expr:
            continue
        if resolved := prop_types.get(expr.split(".")[-1]):
            types.add(resolved)
    return types


def boundary_gaps(canonical: set[str], prop_types: dict[str, str]) -> list[str]:
    """Types a cross-boundary re-injection host fails to carry — ALL of them.

    Why this rule is absolute where the MIRROR_HOSTS rule is narrowed:

    `DocumentTabView` sits INSIDE the library tree, so a value it omits is
    still inherited by everything below it; only an out-of-tree reader (a
    toolbar item, another Scene) can trap, and narrowing to those avoids
    reporting 39 non-problems.

    A BOUNDARY host has no such inheritance to fall back on and — critically —
    no bounded subtree to reason about. `.inspector` content is hosted outside
    the tab tree and `inspectorContainerView` mounts the WHOLE detail view
    there, so "which types can this host's subtree read" is "all of them". Any
    omission is a live `No Observable object of type X found` waiting for the
    user to open the right pane.

    That is not theoretical. On 2026-08-08 this script printed "no new
    environment-forwarding gaps" through three consecutive crashes of exactly
    this kind, because the only host it looked at was DocumentTabView. The
    docked-inspector boundary re-injected NOTHING and was not on the list; the
    detached one hand-copied 33 of 37. A sweep that cannot look at the failing
    boundary is not a guardrail.

    A host satisfies the rule either by calling the shared helper or, for the
    helper itself, by listing the canonical set in full.
    """
    gaps: list[str] = []
    for host in BOUNDARY_HOSTS:
        text = _read(host)
        if host != SHARED_HELPER and HELPER_CALL in text:
            continue  # delegates to the one list — that IS the fix
        for type_name in sorted(canonical - injected_library_types(host, prop_types)):
            gaps.append(f"{host.name}:{type_name}")
    return gaps


def read_baseline() -> set[str]:
    if not BASELINE.exists():
        return set()
    return {
        line.strip()
        for line in BASELINE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }


def main() -> int:
    for required in (LIBRARY_MANAGER, CANONICAL_HOST, *MIRROR_HOSTS, *BOUNDARY_HOSTS):
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
                continue  # in-tree or optional: it inherits and cannot trap
            key = f"{host.name}:{type_name}"
            all_gaps.append(key)
            if key not in baseline:
                new_gaps.append(f"{key} (read non-optionally in "
                                f"{len(reads[type_name])} view(s))")

    library_canonical = injected_library_types(CANONICAL_HOST, prop_types)
    missing_at_boundary = boundary_gaps(library_canonical, prop_types)

    print(f"Environment-forwarding guardrail: {len(canonical)} canonical "
          f"per-library injections in {CANONICAL_HOST.name}")
    print(f"  {len(all_gaps)} forwarding gap(s); {len(baseline)} known (#4455).")
    print(f"  {len(BOUNDARY_HOSTS)} cross-boundary host(s) checked against the "
          f"{len(library_canonical)} library-scoped types; "
          f"{len(missing_at_boundary)} missing.")

    if missing_at_boundary:
        print("\nA cross-boundary re-injection host is INCOMPLETE. `.inspector`\n"
              "content and detached Scenes inherit nothing, and the docked\n"
              "inspector hosts the whole detail view — every omission below is a\n"
              'live "No Observable object of type X found" (the 2026-08-08\n'
              "crash loop). Forward it, or call libraryServiceEnvironment(_:):\n",
              file=sys.stderr)
        for gap in missing_at_boundary:
            print(f"  {gap}", file=sys.stderr)
        return 1

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

    IN-MEMORY (2026-08-09 rewrite): every synthesized regression lives in
    `_TEXT_OVERRIDES`; nothing is written to disk, so an interrupted or
    concurrent run cannot clobber real source — the old form wrote mutations
    into the actual files and restored in a `finally`, which is neither
    crash-safe nor safe under a concurrent writer. The three cases are
    reverts of real fixes, not invented shapes.
    """
    host = MIRROR_HOSTS[0]
    detached = BOUNDARY_HOSTS[1]
    failures: list[str] = []

    def expect(label: str, want: int) -> None:
        got = main()
        print(f"  [{'ok' if got == want else 'FAIL'}] {label}: rc={got} (want {want})")
        if got != want:
            failures.append(label)

    try:
        expect("tree as it stands is clean", 0)

        host_original = _read(host)
        dropped = host_original.replace("                .environment(library.activityStore)\n", "")
        if dropped == host_original:
            failures.append("could not simulate the #4448 regression — the forward moved")
        else:
            _TEXT_OVERRIDES[host] = dropped
            expect("reverting the #4448 ActivityStore forward is caught", 1)
            _TEXT_OVERRIDES.clear()

        helper_original = _read(SHARED_HELPER)
        thinned = helper_original.replace(
            "            .environment(library.activityStore)\n", "")
        if thinned == helper_original:
            failures.append("could not thin the shared helper — the list moved")
        else:
            _TEXT_OVERRIDES[SHARED_HELPER] = thinned
            expect("a service dropped from the shared helper is caught", 1)
            _TEXT_OVERRIDES.clear()

        detached_original = _read(detached)
        hand_rolled = detached_original.replace(
            "            .libraryServiceEnvironment(library)\n",
            "            .environment(library.documentStore)\n")
        if hand_rolled == detached_original:
            failures.append("could not un-delegate the detached inspector — the call moved")
        else:
            _TEXT_OVERRIDES[detached] = hand_rolled
            expect("a boundary host reverting to a hand-picked list is caught", 1)
            _TEXT_OVERRIDES.clear()

        expect("overrides cleared, tree clean again", 0)
    finally:
        _TEXT_OVERRIDES.clear()


    if failures:
        print("\nself-test FAILED:", "; ".join(failures), file=sys.stderr)
        return 1
    print("\nself-test passed: the guardrail fires on a real regression.")
    return 0


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(self_test())
    sys.exit(main())
