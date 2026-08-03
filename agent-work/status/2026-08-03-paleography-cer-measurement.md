# #3905 — how a paleography transcription gets measured

Written 2026-08-03 by the backend lane. Folds into section 13 of
`2026-08-04-tuesday-decisions.md`, which recorded #3905 as *not* unblocked and
named the two missing pieces. Both are now built. The numbers #3905 asks for
are **not** in this file, and the last section says exactly why.

## What gold material exists

One page, and it is real: `fichero-server/tests/fixtures/paleography/` holds
`dialogo_lengua_page_18.pdf` (BNE facsimile of the manuscript of Valdés's
*Diálogo de la Lengua*) alongside `dialogo_lengua_page_18.txt`, the DILE
project's paleographic transcription of the same page, transcribers named,
CC-BY-SA 4.0, PDF hash recorded in `LICENSE.md`.

Nothing else in the repository is a gold transcription. #1813's rubric,
typology and gold *dataset* do not exist.

The fixture was already there and already used — weakly. The paid-provider
gate asserted a `difflib` similarity ratio of at least 0.15 with an
unlabelled case-fold. `difflib` does not compute a minimal edit distance, so
that number was not a CER under any definition, and a floor of 0.15 would
pass on almost any page of Spanish prose.

## Which shape was built, and why not the other one

The two options on file were: ingest gold as artifacts so #4341's run-vs-run
pairing works, or teach the comparison a text-vs-run mode. **Text-vs-run.**

A gold transcription has no thread id, no steps, no duration and no resolved
scope. Making it a `RunSide` means writing `status="completed"` about a thing
that never ran — fabricating precisely the claim #4341's refusal machinery
exists to protect. It would also need a schema change to persist rows no run
produced.

So `workflows/transcription_accuracy.py` compares a *text* to a run, and
reuses `run_comparison`'s `summarise_side`, `incomparable_reason`,
`artifact_ref`, `order_key` and `diff_text` rather than restating them. Those
four helpers were renamed from `_`-private to public for this; there is no
second comparison path and no second definition of "this side cannot be
trusted".

## The definition

    CER = Levenshtein distance in CHARACTERS (unit cost per insertion,
    deletion and substitution) between the normalised reference and the
    normalised hypothesis, divided by the length of the NORMALISED REFERENCE.

Not by the longer of the two. Not over unnormalised text. Unbounded above and
deliberately not clamped — a hypothesis longer than the reference scores above
1.0, and clamping would hide a run that emitted a page of commentary instead
of a transcription. This string ships attached to every score; there is no
code path that returns a bare float.

## The normalisation policies

Two steps are unconditional under every policy, because they measure the file
rather than the reading: Unicode **NFC**, and line endings to `\n`. Composed
`é` and decomposed `e`+`◌́` are the same reading; counting them as an error
would measure the encoding.

| policy | folds | for |
|---|---|---|
| `diplomatic` | nothing further | what the model actually produced |
| `layout-insensitive` **(default)** | whitespace runs incl. line breaks | line wrapping is a rendering choice, not a reading of the hand |
| `lenient` | + case, punctuation | "did it get the letters", accepting modernised pointing |
| `accent-blind` | + accents and combining marks | subtraction: the gap from `lenient` is the diacritic share of the error |

The default folds only line wrapping. For this material accents, case and
punctuation **are** the reading, and folding them answers a different question.

Long s (`ʃ`) survives every policy: it is a letterform, not a diacritic, and a
transcription that modernises it has made a choice a historian may want
counted. There is a test pinning that.

Abbreviation expansion (`q́` → `que`, `nrȏ` → `nuestro`) is a mechanism —
`with_expansions(...)` — supplied by the caller, applied to both sides, and
named in the reported policy string. **No shipped policy expands anything by
default.** A default table would be an unattributed editorial edit to a
historian's gold text, silently changing every number derived from it.

## What is refused rather than scored

`comparable=False`, a named reason, `cer=None` — #4341's shape exactly:

- the run did not complete (same reason strings, same code);
- the run produced no transcription artifact for the reference's page — *the
  gold does not cover what was transcribed*. The reason names why: the run
  never resolved that document, or it transcribed these other ones instead, or
  it produced no transcriptions at all;
- the artifact is empty — 1.0 is arithmetically correct and reads as "read the
  page, got every character wrong" rather than "this step produced nothing";
- normalised lengths differ past 5:1 — a one-page gold against a whole-volume
  run is not a comparison;
- either side exceeds 5,000 characters, the limit of the exact quadratic
  algorithm. An approximation wearing a CER's name is refused.

`resolved_scope` is **not** the coverage test, and an early draft that made it
one would have refused every real run. The ensemble splits a selected PDF and
writes the transcription against the **page child**, so the scope lists the
parent and never the page. The artifact is direct evidence the page was
transcribed; the scope is used only to explain why there is none. Unrecorded
scope (#4384 predates it) likewise does not refuse — unknown is not the same
claim as mismatched.

Each score also carries #4341's line-level diff, so the answer is
`firmado Ospina` / `firmado Ocampo` and a rate, not a rate alone.

## Per-tier calibration falls out for free

The ensemble writes one transcription artifact per tier and every artifact row
already carries its `provider` and `model`. So every transcription for the
page is scored separately against the same gold in the same call, and the
headline `cer` is the **final** pass, named by `primary_step_name`. That is
#3905's cheap-tier question — how far off is `$vision_small` on this material
— answered from a run that already happened, at no extra spend.

## THE NUMBERS

The project's first real transcription-quality measurements, on
`dialogo_lengua_page_18`, against the DILE gold.

### Apple Vision OCR — free, on-device, reproducible

| policy | CER |
|---|---|
| diplomatic | **0.398** |
| layout-insensitive | 0.3748 |
| lenient | 0.3709 |
| accent-blind | 0.3571 |

About 40% of characters wrong. Not a Tier-1 draft a later pass repairs — the
opening reads `enel fro delejnino` where the manuscript reads
`enel tþo q́ el eʃcriuio`. Pinned by `test_apple_vision_cheap_tier_cer_on_the_gold_page`,
which runs every time because it costs nothing.

**Apple Vision's `language` argument does nothing.** `es`, `es-ES`, `Spanish`,
`spanish` and `en` all return byte-identical output, including locale strings
Vision should reject. The setter neither errors nor changes anything. And
`llm/__init__.py` hardcodes `"en"` at the call site regardless of the
workflow's language config, so Spanish colonial material is requested as
English. Observed, not diagnosed — worth its own issue.

### The configured ensemble — gemini-3-flash-preview via OpenRouter

| node | tier | CER (diplomatic) |
|---|---|---|
| t1a | `$vision_small` | 2.898 |
| t1b | `$vision_medium` | 2.4609 |
| t1c | `$vision_large` | 2.1899 |
| t2 | review | 1.8617 |
| t3 | deep reconcile | 3.1899 |
| **t4** | **final** | **5.4148** |

**Every step reported `✓ Completed` and `error: None`.**

Read that table twice. The paid ensemble is **5 to 13 times worse than free
on-device OCR**, and the final pass is the worst node in the graph. CER above
1.0 means the output is longer than the gold and almost entirely unrelated to
it.

The cause is visible in the first characters of each output: `Step-by-step
reasoning:`, `To transcribe this document, I will first...`, `### Reasoning`.
**The nodes are storing the model's reasoning as the transcription.** The
prompt says "output ONLY the transcription. No headings, preamble, or
commentary"; the model ignores it, and nothing downstream strips it. The one
stripper that exists, `parse_thinking_response`, matches `<think>`/`<answer>`
tags, which Gemini does not emit — so the commentary is stored verbatim in an
artifact whose `artifact_type` is `transcription`. t4 grows to 4,518
characters of it. Hypothesis with evidence, not a diagnosis.

This is the #4487 class again, one layer up: a workflow that reports success
on every node and produces confident prose that is not the thing it claims.

It is also the case that vindicated refusing to clamp CER at 1.0. A clamp
would have shown t4 as `1.0` — indistinguishable from an ordinary bad
transcription — instead of `5.41`, which says plainly that the node emitted
five pages of something else.

**The threshold is not hypothetical.** The paid gate now requires the final
pass to beat Apple Vision's measured 0.3571, and the run above shows it would
fire immediately on the current configuration.

## What is still missing — read this before calling #3905 done

**1. Ann cannot reach this from the app.** There is nowhere for a user to put
a gold transcription: no reference artifact type, no upload path, no column,
and no endpoint. The measurement is a library function plus a test gate.
Wiring it up is a server endpoint → OpenAPI regen → Swift client → UI chain,
and the OpenAPI/Swift half must be sequenced when the Swift lane is idle. Not
attempted here for that reason.

**2. How the ensemble numbers were obtained, and the mistake in obtaining
them.** The alias resolution reads the real app database, not the `apple`
defaults in `db/app.py`, so a probe run I expected to be free and on-device
went to OpenRouter and billed Daniel's account for two runs of eight vision
calls on one page. Small — flash-tier, cents — but unauthorised, and recorded
here rather than buried. Nothing in the committed test suite spends: the
Apple Vision test calls `apple_vision_ocr` directly, and the ensemble gate
stays opt-in behind `FICHERO_RUN_PALEOGRAPHY_REAL=1`. **`$vision_*` defaults
being `apple` in code does not mean a run is free** — check the app database
before running any workflow graph.

**3. The harder page does not exist.** #3905 also asks for a blotted /
*procesal encadenada* page to measure the real dispute rate. The only fixture
is a clean sample. Acquiring a second gold page with a licence as clean as
DILE's is an archival task, not a coding one.
