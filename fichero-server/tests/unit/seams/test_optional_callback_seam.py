"""Seam category 5 — optional callbacks that silently remove affordances (#4420).

The archetype is #4393. ``EntityKindRow`` declares
``var onNavigateToSource: ((String) -> Void)?`` and its claim block renders
the source button only inside a conditional binding
(``EntityKindRow+ClaimBlock.swift:228``: ``let navigate = onNavigateToSource,``).
The property is optional and defaults to nil, so a host that constructs the
row without passing it makes the arrow, the hover preview, the page and the
excerpt disappear — and **a claim with a source becomes indistinguishable
from a claim with none**. Nothing warns; the control is simply not there.

The general rule #4420 states: **a missing dependency must be loud, not
invisible.** A required capability expressed as an optional with a nil
default has no failure mode — only a quieter UI.

THE RULE HERE, mechanically:

    an optional closure property that GATES A VISIBLE CONTROL
    must be supplied at every construction site of its owning View.

"Gates a visible control" is approximated by the closure appearing in a
conditional binding or nil-check (``if let onX``, ``let y = onX,``,
``onX != nil``). That is the pattern that makes a control vanish rather than
merely no-op — an unconditional ``onX?()`` call site is a disabled action,
which is a different and much milder thing, and is deliberately not flagged.

Swift has no AST module here, so this is regex over source. Three
false-positive classes were found by hand-checking the first pass and are
excluded, each because a real example was read:

* **comments and string literals** — ``// MARK: - ReferenceRowView (#3258)``
  was matched as a construction of ``ReferenceRowView``;
* **the declaration itself** — ``struct Foo: View`` is not a call to ``Foo``;
* **``#Preview`` blocks** — all three ``ChatInspector`` hits were previews,
  which legitimately omit optional callbacks because nothing is wired up in
  a canvas preview.

Findings are reported, not fixed (#4420).
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[4] / "fichero" / "fichero"

_LINE_COMMENT = re.compile(r"//.*$", re.M)
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_STRING = re.compile(r'"(?:[^"\\]|\\.)*"')
_PREVIEW = re.compile(r"#Preview[^{]*\{", re.M)

_OPTIONAL_CLOSURE_PROP = re.compile(
    r"^\s*var\s+(on[A-Z]\w*)\s*:\s*\(\([^)]*\)\s*->\s*[^)]*\)\?", re.M
)
_VIEW_STRUCT = re.compile(r"struct\s+(\w+)\s*:\s*View")

# Construction sites that may omit a gating callback, with a reason each.
# Empty: every site the sweep flags today was hand-checked and is a real
# finding, reported on #4393.
ALLOWED_OMISSIONS: dict[str, str] = {}


def _strip_noise(text: str) -> str:
    """Remove comments and string literals, then blank out #Preview bodies."""
    text = _BLOCK_COMMENT.sub("", text)
    text = _LINE_COMMENT.sub("", text)
    text = _STRING.sub('""', text)

    out = text
    while True:
        match = _PREVIEW.search(out)
        if match is None:
            return out
        depth, end = 1, len(out)
        for index in range(match.end(), len(out)):
            if out[index] == "{":
                depth += 1
            elif out[index] == "}":
                depth -= 1
                if depth == 0:
                    end = index + 1
                    break
        # Preserve line count so reported line numbers stay accurate.
        body = out[match.start() : end]
        out = out[: match.start()] + "\n" * body.count("\n") + out[end:]


def _sources() -> dict[Path, str]:
    return {
        path: _strip_noise(path.read_text(errors="ignore"))
        for path in sorted(APP_ROOT.rglob("*.swift"))
    }


def _gating_properties(sources: dict[Path, str]) -> set[tuple[str, str]]:
    """(View type, closure property) pairs whose nil-ness removes a control."""
    declared: dict[str, set[str]] = defaultdict(set)
    for text in sources.values():
        owners = _VIEW_STRUCT.findall(text)
        if not owners:
            continue
        for match in _OPTIONAL_CLOSURE_PROP.finditer(text):
            declared[owners[0]].add(match.group(1))

    gating: set[tuple[str, str]] = set()
    for view_type, props in declared.items():
        for prop in props:
            pattern = re.compile(
                rf"(if\s+let\s+{prop}\b)|(let\s+\w+\s*=\s*{prop}\s*,)|({prop}\s*!=\s*nil)"
            )
            if any(
                pattern.search(text) for text in sources.values() if view_type in text
            ):
                gating.add((view_type, prop))
    return gating


def _call_body(text: str, start: int) -> str:
    segment = text[start : start + 1500]
    depth = 1
    for index, char in enumerate(segment):
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return segment[:index]
    return segment


def _unsupplied_sites() -> dict[str, list[str]]:
    """'Type.prop' -> ['relative/File.swift:line', …] omitting the callback."""
    sources = _sources()
    findings: dict[str, list[str]] = defaultdict(list)

    for view_type, prop in sorted(_gating_properties(sources)):
        key = f"{view_type}.{prop}"
        # Not a declaration (`struct Foo`), not a member access (`.Foo(`).
        call = re.compile(rf"(?<!struct )(?<!\.)\b{view_type}\(")
        for path, text in sources.items():
            for match in call.finditer(text):
                if prop in _call_body(text, match.end()):
                    continue
                line = text[: match.start()].count("\n") + 1
                site = f"{path.relative_to(APP_ROOT)}:{line}"
                if f"{key}@{site}" in ALLOWED_OMISSIONS:
                    continue
                findings[key].append(site)
    return {k: v for k, v in findings.items() if v}


def test_the_sweep_has_something_to_scan():
    """Guard the guard (#4382)."""
    assert APP_ROOT.is_dir(), f"Swift sources not found at {APP_ROOT}"
    sources = _sources()
    assert len(sources) >= 500, (
        f"only {len(sources)} Swift files found under {APP_ROOT} — the sweep "
        "would pass vacuously"
    )
    gating = _gating_properties(sources)
    assert len(gating) >= 10, (
        f"only {len(gating)} control-gating optional closures detected — the "
        "regexes have stopped matching the declaration or binding pattern"
    )


def test_preview_blocks_are_excluded():
    """The exclusion must actually work, or it silently hides real findings.

    Proven by mutation rather than asserted: ChatInspector constructs itself
    three times, all inside #Preview blocks. If the stripper regressed, this
    type would reappear in the findings.
    """
    sources = _sources()
    chat = next(
        (t for p, t in sources.items() if p.name == "ChatInspector.swift"), None
    )
    assert chat is not None, "ChatInspector.swift not found — update this test"
    assert "#Preview" not in chat, "#Preview bodies were not stripped"
    assert "struct ChatInspector" in chat, (
        "the stripper removed real code, not just preview bodies"
    )


def test_every_control_gating_callback_is_supplied_by_every_host():
    """An unsupplied gating callback removes a control with no warning."""
    findings = _unsupplied_sites()
    rendered = "\n  ".join(
        f"{key} — omitted at {', '.join(sites[:3])}"
        + (f" (+{len(sites) - 3} more)" if len(sites) > 3 else "")
        for key, sites in sorted(findings.items())
    )
    assert findings == {}, (
        f"{len(findings)} optional closure(s) that gate a visible control are "
        "not supplied by every host. Where a host omits one, the control is "
        "simply absent — indistinguishable from data that has nothing to show "
        "(#4393):\n  " + rendered
    )


def test_claim_source_navigation_is_supplied_everywhere():
    """#4393 itself, addressable on its own.

    A claim rendered without onNavigateToSource shows no source affordance,
    so a claim that HAS a source looks exactly like one that does not — the
    specific confusion this issue was filed for.
    """
    findings = _unsupplied_sites()
    offenders = {
        key: sites
        for key, sites in findings.items()
        if key.endswith(".onNavigateToSource")
    }
    assert offenders == {}, (
        "these hosts render claims without source navigation, making a claim "
        f"with a source indistinguishable from one without (#4393): {offenders}"
    )


def test_allowlist_has_no_stale_entries():
    """Bidirectional hygiene: an excused site that now supplies it must fail."""
    sources = _sources()
    gating = {f"{t}.{p}" for t, p in _gating_properties(sources)}
    stale: list[str] = []
    for entry in ALLOWED_OMISSIONS:
        key, _, site = entry.partition("@")
        if key not in gating:
            stale.append(f"{entry}: {key} is no longer a control-gating closure")
            continue
        path = APP_ROOT / site.rsplit(":", 1)[0]
        if not path.is_file():
            stale.append(f"{entry}: {path} no longer exists")
    assert stale == [], "stale allowlist entries:\n  " + "\n  ".join(stale)
    missing_reason = sorted(
        e for e, reason in ALLOWED_OMISSIONS.items() if not str(reason).strip()
    )
    assert missing_reason == [], f"entries without a reason: {missing_reason}"
