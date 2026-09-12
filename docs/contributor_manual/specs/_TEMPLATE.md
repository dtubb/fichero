# <Surface> — Design Spec (#<issue>)

> Milestone: <surface>

> Copy this file to `docs/contributor_manual/specs/<surface>.md` (or `specs/<area>/<surface>.md`)
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

## Prior art / best practices (don't invent from scratch)

Before proposing a novel design, survey how the field already solves this and cite what we build
on. Fichero is a scholarly/archival + AI tool, so look to: **digital humanities** (DH methods,
standards — IIIF, W3C Web Annotation, CIDOC-CRM, TEI, the factoid model), **NLP/NLG** (established
pipelines — e.g. Reiter & Dale; realisers), **Hugging Face** (models, datasets, tokenizers,
`transformers`/`datasets` APIs) and their conventions, and the relevant **standards/libraries**.
State: what established approach we adopt, what we deliberately do differently and why, and what we
reuse rather than rebuild. A spec that invents where the field has a solution is sent back.

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
| Click-around (XCUITest, Mac) | y/n | click → effect, end-to-end | `fichero/Tests/UI/…` (subclass `FicheroUISessionTests`) |
| iPhone (iOS) | y/n | the touch path on iPhone | `fichero/Tests/UI/ios` + `fichero-ui-ios` plan |
| iPad | y/n | the touch path on iPad | `fichero/Tests/UI/ipad` + `fichero-ui-ipad` plan |
| Load (#4634) | y/n | bounded, no peg, timed | `fichero-server/tests/perf/…` |

The surfaces a spec can touch: **server** (pytest) · **MCP** · **CLI** · **Swift** (unit/
availability/snapshot) · **UI-Mac** (XCUITest) · **iPhone** · **iPad**. Tick every one the feature
reaches — a capability that ships on a surface but has no test there is unproven on it.

Hard-gate: the cross-surface **invariant** (same result backend/MCP/CLI/UX) + capability
**availability**. Rest is tracked debt — but listed here so it isn't forgotten.

## Documentation matrix (paste from `../DOC-TEMPLATE.md`, tick the audiences this reaches)

| Audience | Doc leg | This feature? | Lives in |
|----------|---------|---------------|----------|
| User | user manual + screenshot | y/n | `docs/user_manual/guide/<area>.md` |
| Contributor | developer docs | y/n | `docs/contributor_manual/<area>.md` + this spec |
| AI / agent | MCP tool description | y/n | `fichero-mcp/**` (`description=`) |
| Scripter | CLI `--help` | y/n | `fichero-cli/**` (`help=`) |
| Reference | capability/endpoint reference | y/n | generated (`check_capability_reference_current`) |

A feature is met by readers who never read each other's docs — cover the ones it reaches.

**Authorship (who owns which folder).**
- `docs/contributor_manual/` + `docs/reference_manual/` + MCP/CLI help — **AI-authored, as part of the spec.**
  The agent writes and maintains these from the code + this spec; keeping them current is part of
  finishing the surface, not a separate task.
- `docs/user_manual/` — **the maintainer's own.** The final user-facing manual is authored in Tinderbox
  and exported to the `docs/user_manual` GitHub folder; the agent does NOT write or draft it. The spec's
  job for this audience is only to keep the *facts* the maintainer documents accurate to what
  shipped (behaviors, a11y ids, screenshots) — not to author the prose.

## Accessibility identifiers (required for the click-around leg)

List the stable a11y ids the UI test will drive — add them to the views AS YOU BUILD:
- `<surface>.entry` — the control that opens the surface
- `<surface>.row.<id>` — a row/item
- `<surface>.menu.<verb>` — each context-menu verb / button

## UX completeness (required on EVERY surface)

Every user-facing control on this surface ships ALL of the following. Two levels of verification —
be honest about which a given item has:

- **Tooltip / help.** Every control has a `.help("…")` (menu items a help tag). *Today:*
  `scripts/check_tooltips.py` scans for **presence** on icon-only toolbar controls (conservative,
  has a `KNOWN_VIOLATIONS` backlog). *Target:* the spec table below names the intended text so a
  test can pin it.
- **Label.** Every control has a visible or accessibility label — no icon-only control unreachable
  by name.
- **Accessibility.** An `.accessibilityLabel` + the stable `.accessibilityIdentifier` (above) on
  every interactive element. *Today:* `scripts/check_accessibility.py` scans for **presence** of a
  label on icon-only controls (conservative, backlog). *Target (Apple-first-party, NOT YET ADOPTED
  — [MISSING]):* the click-around leg runs `try app.performAccessibilityAudit()`, which catches
  missing labels/identifiers and contrast at runtime. Adopting it is part of the `ui-testing-strategy`
  spec — prefer it over growing the static scanner.
- **Localization-ready.** No hardcoded user-facing strings — every string comes through
  `LocalizedStringKey` / the String Catalog (`.xcstrings`), so the surface is translatable without
  code changes. *Today:* `scripts/check_localization.py` fails on `Text(verbatim:)` and other escapes
  (real, Apple-aligned). (Shipping a locale is a later decision; being *ready* is required now.)

Honesty rule (design-led testing): a **presence scan is not a behavioral test.** Fill the table so
the intended text is on record; where a spec-pinned test or `performAccessibilityAudit()` isn't
wired yet, tag the row `[MISSING]` rather than implying it's proven.

| Control (a11y id) | Label | Tooltip/help text | Localized key | Verified by |
|---|---|---|---|---|
| `<surface>.entry` | … | … | `<key>` | scan / test / audit / [MISSING] |

## Open questions for the creative director
- …
