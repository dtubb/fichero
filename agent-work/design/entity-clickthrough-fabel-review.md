# Entity/SVO click-through — Fabel review (2026-09-04, lane-entity-clickthrough)

Daniel's ruling: a statement must lead to its source (reader AND preview,
passage lit); the inspector must show the quote a statement is drawn from;
a person's name must lead to every source that mentions them. "There is
basically more information there that is not provided to the UX, and the
click-around is not working."

## The finding in one sentence

The plumbing for everything Daniel asked for ALREADY EXISTS — the typed
source cursor (`ClaimSourceNavigationState`, #2105/#4393), the passage
latch that lights reader and preview together (#4666/787b624c2), the
entity-scoped search (`people:"Name"`, #3437) — but three surfaces either
never call it, call the wrong bus, or override the fixed path with the
broken one.

## Audit: stored vs shown, per click surface

| Surface | Click today | Defect |
|---|---|---|
| ClaimSummaryCard (Ontology cards) plain click | focus + `navigateToSource()` — fixed tonight (#4666) | none — UNLESS a host injects `onNavigateToSource` (below) |
| **OntologyBrowser → EntityDetailView** (`OntologyBrowser+Detail.swift:16`) | injected closure calls `kgFocusState.focusEntity(...)` ONLY | **navigates nowhere — the exact #4666 defect, surviving as an injected override that preempts the card's fixed path.** Every card click and every Mentions row inside the Ontology browser dead-ends here. Root cause of "click-around is not working". |
| EntityDetailView Mentions rows | same injected closure | same dead end |
| **Doc inspector claim quote** (`EntityKindRow+ClaimBlock.claimExcerptButton`) | `entitySearchState.request(name: excerpt)` — **searches the library for the quote text** | clicking a statement's quote dumps you into a text search for a 200-char string; the quote should open the source with the passage lit. The row already builds the full anchor (`sourceNavigationRequest`) two functions away. |
| **Entity inspector biography** (`EntityDigestView.composedBiography`) | one joined `Text` — no click at all | statements exist as claims with anchors; the prose renders them unclickable. This is the "biography" Daniel clicked. |
| Digest provenance rows | selection → shared cursor (#4393 pt 2) | correct — the model to copy |
| Chips on a card (subject/verb/object) | subject → expand; verb/object → inline edit; all three `.help` say "Show the source claim" | two behaviors, three identical tooltips; ruling needed (below) |
| Entity name → all sources | `EntityLozenge` fires scoped search — but only in doc-inspector lists; EntityDetailView/Digest HEADERS have no affordance; `focusEntityLozenge` in ClaimSummaryCard+Details is **dead code (zero callers)** | Daniel: "click on people's names → all locations of that person in search" |

Data stored but not shown where he was looking: `source_excerpt` +
`source_char_start/end` (#4666), `source_anchor.rect` (bbox), corroboration
(`also_extracted_by`), `claim_geo` provenance sentences, evidential basis.
The card's expanded drawer shows most; biography/doc-inspector rows do not.

## Design: one click-through contract

1. **A statement leads to its source.** Any rendering of a claim —
   card, mention row, biography sentence, inspector quote — posts
   `ClaimSourceNavigationRequest` (built by
   `ClaimSummaryCard.openClaimSourceRequest(for:)`, the one anchor
   builder) on the per-window `ClaimSourceNavigationState`. The reader
   consumes the latch; the preview re-applies it when geometry arrives
   (both lit, load order irrelevant — tonight's contract).
2. **A quote is a door, not a query.** The inspector quote opens the
   source page with the passage lit. Searching for arbitrary text stays
   what text selection + ⌘F are for.
3. **A name leads to everything.** Entity headers (detail panel, digest)
   get a "Find All in Search" affordance firing the existing scoped
   search (`people:"Name"` etc.). Same path as lozenges; nothing new.
4. **Chips** — PROPOSAL FOR DANIEL (not implemented): the noun chips
   (subject, and object when it resolves to an entity) go to the ENTITY
   (its all-sources view); the verb chip edits the statement (it is the
   claim-specific part); the card body goes to the source. One sentence:
   *nouns navigate, verbs edit, the sentence goes to the page.* Until
   ruled, tooltips now tell the truth about what each chip does.

## Implemented tonight (this lane)

- `OntologyBrowser+Detail`: the injected closure now focuses AND posts
  the source request — Ontology cards and Mentions rows land on the page.
- `EntityKindRow+ClaimBlock`: the quote button opens the source with the
  passage anchor (was: text-search for the quote); help text tells the
  truth; the quote keeps `textSelection` for copy-then-search.
- `EntityDigestView`: biography sentences are individually tappable
  (AttributedString links → the digest's existing shared cursor);
  `composedBiography` retained as the same joined prose for the existing
  contract tests.
- Entity headers (digest + detail panel): "Find All in Search" button →
  scoped search.
- Deleted `focusEntityLozenge` (dead since its caller went away).
- Tests: behavior tests for sentence building; source-scan guards (via
  `AppSource.code`) that the three repaired sites call the cursor and
  that the quote button no longer fires a text search.

## Deliberately not done

- Chip semantics change — awaiting Daniel's ruling on the rule above.
- Dedupe-proposal surface (#4508) — reader lane's morning queue.
- Corroboration/basis display on biography sentences — worth doing after
  the chip ruling settles what a sentence row carries.
