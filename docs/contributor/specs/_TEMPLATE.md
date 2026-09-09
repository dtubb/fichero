# <Surface> — Design Spec (#<issue>)

> Milestone: <surface>

> Copy this file to `docs/contributor/specs/<surface>.md` (or `specs/<area>/<surface>.md`)
> to start a surface under design-led testing. Delete this quote block and fill every
> section. `_`-prefixed files are scaffolds — the guardrail ignores them.
>
> Design-led (Testing Constitution). Creative director owns intent; tests enforce it; code
> makes them pass. **Status: DRAFT — awaiting approval before tests/code.**
> Flip to `Status: APPROVED` only after the creative director approves the intent; an
> APPROVED spec MUST: carry a filled Test matrix; be cited by ≥1 test; and declare a
> `Milestone: <name>` matching a GitHub milestone of the SAME name (spec name == milestone
> name == test tag — guardrails `check_specs_have_tests.py` + `check_spec_milestones.py`
> enforce). Create/rename the milestone when you approve the spec, and point its description
> back at this file (the link is bidirectional). Tag the tests to match: Swift `@Tag` in
> `fichero/Tests/Unit/general/TestTags.swift`, pytest markers in `fichero-server/pyproject.toml`.
> Tags: [OK] built · [MISSING] not built · [PARTIAL] exists elsewhere / not wired.

## Intent (the design)

One paragraph: what the user should be able to OBSERVE on this surface, and why. Name the
concrete files/types the surface lives in.

## Behaviors

One line per behavior, each with a stable id and a tag. The id is what a test cites.
- `<surface>.<behavior>` [MISSING] — what the user observes.
- `<surface>.<behavior-2>` [PARTIAL] — …

## Test matrix (paste from `../TEST-TEMPLATE.md`, tick the legs this surface touches)

| Leg | This surface? | Pins | File |
|-----|---------------|------|------|
| Pure rule (Swift) | y/n | the rule off-main | `fichero/Tests/Unit/…/<Surface>Tests.swift` |
| Availability (Swift) | y/n | capability reachable in the surface | same, `AppSource.root()` |
| Backend (pytest) | y/n | endpoint contract + delivery | `fichero-server/tests/…` |
| MCP | y/n | tool maps + routes | `fichero-mcp/tests/test_mcp_full.py` |
| CLI | y/n | command wires endpoint | `fichero-cli/tests/test_*.py` |
| Click-around (XCUITest) | y/n | click → effect, end-to-end | `fichero/Tests/UI/…` (subclass `FicheroUISessionTests`) |
| iPad/iOS | y/n | the touch path | `fichero/Tests/UI/ios`, `…/ipad` |
| Load (#4634) | y/n | bounded, no peg, timed | `fichero-server/tests/perf/…` |

Hard-gate: the cross-surface **invariant** (same result backend/MCP/CLI/UX) + capability
**availability**. Rest is tracked debt — but listed here so it isn't forgotten.

## Documentation matrix (paste from `../DOC-TEMPLATE.md`, tick the audiences this reaches)

| Audience | Doc leg | This feature? | Lives in |
|----------|---------|---------------|----------|
| User | user manual + screenshot | y/n | `docs/user/guide/<area>.md` |
| Contributor | developer docs | y/n | `docs/contributor/<area>.md` + this spec |
| AI / agent | MCP tool description | y/n | `fichero-mcp/**` (`description=`) |
| Scripter | CLI `--help` | y/n | `fichero-cli/**` (`help=`) |
| Reference | capability/endpoint reference | y/n | generated (`check_capability_reference_current`) |

A feature is met by readers who never read each other's docs — cover the ones it reaches.

## Accessibility identifiers (required for the click-around leg)

List the stable a11y ids the UI test will drive — add them to the views AS YOU BUILD:
- `<surface>.entry` — the control that opens the surface
- `<surface>.row.<id>` — a row/item
- `<surface>.menu.<verb>` — each context-menu verb / button

## Open questions for the creative director
- …
