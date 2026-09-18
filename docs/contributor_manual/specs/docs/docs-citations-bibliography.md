# Docs Citations & Bibliography — crediting the work we build on — Design Spec (#TBD)

> Milestone: docs-citations-bibliography
> Manual: TBD — a "Credits & bibliography" page the docs site can link from every manual: the DH
> methods, projects, and code libraries Fichero builds on, each with its licence and citation.
>
> Design-led (Testing Constitution). **Status: DRAFT — awaiting creative-director approval.**
> Tags: [OK] built · [PARTIAL] exists · [MISSING] not built.
>
> **Scope boundary:** this is SCHOLARLY / dependency attribution for the DOCS — crediting the DH
> methods, projects, and code libraries Fichero builds on. It is NOT source-provenance (a claim
> back to its archival page-segment) — that lives in `kg-readable-representation.md`
> (`kg.read.cite-to-segment`). Two different "citations"; keep them apart.

## Why this spec exists

Fichero stands on a large body of prior work — the factoid model, the Reiter & Dale NLG pipeline,
Six Degrees of Francis Bacon, MapLibre, Grape, HGIS de las Indias, and the code libraries in the
manifests. Today that credit is scattered in prose or absent. Scholarship (and good manners)
require it be **explicit, resolvable, and exportable** — readable for a person AND emittable as
BibTeX for a paper.

## Intent (the design)

One canonical bibliography (`docs/references.bib`, BibTeX) is the single source of truth. Docs in
`docs/user_manual/` and `docs/contributor_manual/` cite entries by key; a guardrail proves every citation
resolves and the file parses. Docs render a human-readable **References** section (not raw keys),
and the bibliography **exports** (BibTeX now; CSL/other later) for papers and for the "sources"
surfaces. References are **categorized** by what they inform (a spec, a feature, a doc) so
"what are we building on for X?" is answerable. Code/library dependencies are credited too, drawn
from the dependency manifests, kept distinct from the scholarly entries.

## Behaviors

- `cite.bibtex-canonical` [MISSING] (#4654) — `docs/references.bib` is the one BibTeX store; every
  scholarly/tool reference is an entry with a stable key (e.g. `six-degrees-francis-bacon`).
- `cite.docs-resolve` [MISSING, hard] (#4655) — every citation key used in `docs/user_manual/**` and
  `docs/contributor_manual/**` resolves to a `.bib` entry; an orphan citation fails the gate
  (`scripts/check_doc_citations.py`). Mirrors how `check_specs_have_tests` binds specs to tests.
- `cite.human-readable` [MISSING] (#4656) — a doc renders its References as author/title/year/URL a person
  can read, generated from the `.bib` — the key is the source, the rendering is derived.
- `cite.code-deps` [MISSING] (#4658) — code/library dependencies (from `pyproject.toml` / SwiftPM) are
  credited in a generated "Dependencies & credits" doc, distinct from the scholarly entries.
- `cite.categorized` [MISSING] (#4658) — each entry is tagged with what it informs (spec/feature slug), so
  a spec's "Related work" list is generated, not hand-maintained.
- `cite.exportable` [MISSING] (#4658) — the bibliography exports as BibTeX (and later CSL-JSON) for papers
  and for the app's future "sources / where this comes from" surface.
- `cite.surfaces` [MISSING] (#4657) — the credits render in THREE places from the one `.bib`: the app's
  **About box**, the **user guide** (`docs/user_manual/`), and the **website** — generated, never
  hand-copied, so they never drift.
- `cite.people-first` [MISSING] (#4654) — ordering puts **specific people / articles first** (the
  scholarship and the humans behind it), then projects, then code libraries — credit the thinking
  before the tooling.

## Test matrix

| Leg | This surface? | Pins | File |
|-----|---------------|------|------|
| Guardrail (py) | y | every doc citation key resolves to a `.bib` entry; `.bib` parses | `scripts/check_doc_citations.py` |
| Pure rule (py) | y | `.bib` → human-readable reference string; categorization lookup | `fichero-server/tests/unit/scripts/test_check_doc_citations.py` |
| Gate wiring | y | the guardrail runs in `verify_all.sh` | (auto-discovered) |

Hard-gate: `cite.docs-resolve` (no orphan citations — a claimed source must exist).

## Open questions for the creative director
1. Citation syntax in Markdown docs — Pandoc-style `[@key]`, or a plainer `{{cite:key}}`?
   (Pandoc `[@key]` is the standard and gives free rendering/export via pandoc-citeproc.)
2. Should the guardrail also flag UNUSED `.bib` entries (dead references), or only orphans?
3. Do code-dependency credits live in the same `.bib` (as `@software` entries) or a separate
   generated file? (Lean: separate generated file from manifests; `.bib` is for scholarship.)
4. Is the app's "where this comes from" surface in scope now, or docs-only first? (Lean: docs
   first; the export makes the app surface cheap later.)
