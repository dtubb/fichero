# Paleography Transcription Workflow — buildable spec

Status: DRAFT for Daniel's review, 2026-07-16. Purpose: a reusable, reproducible, multi-agent
transcription workflow for early-modern **Spanish colonial paleography** (procesal, procesal
encadenada, humanística cursiva; 16th–18th c. notarial/administrative hands).

**It enhances the EXISTING `Transcribe Paleography` preset — it does not replace it.** The backbone is
**standard Fichero nodes** already in the workflow builder (`files-source`, `transcribe`,
`reference-search`) with standard config (`vision_mode`, `thinking_mode`, capability-scoped vision
tier, `prompt`). It adds **ONE new tool — `zoom`** — because targeted magnification was the single
biggest accuracy lever in testing (see below). A person can build or modify all of it in the workflow UI.

---

## Why this shape (grounded in real testing + the literature)

Prototyped on a 1694 *venta real* (EAP1740). Findings that drive the design:

- **Cross-model disagreement is a free, accurate uncertainty detector.** Two different models agree on
  the formulaic legal Spanish and disagree *exactly* on the hard spans (a surname, a name, `puerta`
  vs `quenta`). Self-correction (a model re-reading itself) *degrades* accuracy; models must check
  **each other** against the image. (Transcription-Pearl, Generative-History disagreement studies.)
- **Deep, argued deliberation resolves the hard spans.** A high-reasoning agent, zooming to 7×,
  argued each disputed glyph from letter-forms (comparing the disputed `d` to the scribe's own `d` in
  *Ciudad/heredad*) + the notarial formula + historical plausibility — collapsing a whole page's open
  questions to **one letter**, each with a recorded argument.
- **Consistency checks are free accuracy.** The price self-verified: 530 × 3 = 1,590, and the document
  states both figures. Sums, repeated names, and formula-completeness catch even "all-models-agree" errors.
- **Cost discipline:** spend cheap models on breadth, expensive thinking only on the disputed ~10–20%.
- **No HTR.** Frontier vision LLMs already match/beat Transkribus/eScriptorium on this material without
  per-hand fine-tuning; the grounding HTR supposedly provides comes free from the ensemble + the image.

Realistic accuracy: strong draft + a small flagged set you adjudicate → professional-quality *after*
your review of that set. Not push-button perfection; the value is that it **surfaces its own
uncertainty with provenance** instead of hiding it.

---

## The node graph (standard nodes only)

```
files-source ──files/documents──▶ [Z] zoom (auto-tile page → overlapping line strips) ──┐
                                                                                         ├──▶ [T1a] transcribe DRAFT  ($vision_small, thinking medium)  ┐
                                                                                         ├──▶ [T1b] transcribe DRAFT  ($vision_small, different model)   ├─▶ ensemble
                                                                                         └──▶ [T1c] transcribe DRAFT  ($vision_small, different model)   ┘  (2–4)
                                          │
reference-search [R] ◀── (abbreviation/formula corpus, prior pages of the same hand) ──┘
                                          │
                    [T2] transcribe COMPARE + CRITICAL REVIEW  (tier $vision_medium, thinking high)
                         • ingests all drafts + reference; locks agreements; extracts DISPUTED spans;
                           runs consistency checks (sums, repeated-name agreement, formula completeness)
                                          │
                    [T3] transcribe DEEP RECONCILE / PANEL  (tier $vision_large, thinking high/extended)
                         • calls [Z] zoom on each DISPUTED span's bbox (7×) to argue letter-forms;
                         • argues ONLY the disputed spans from letter-forms + formula + plausibility;
                           produces the diplomatic layer + critical apparatus + the argument transcript
                                          │
                    [T4] transcribe EXPAND  (tier $vision_medium)  → semi-diplomatic layer (abbreviations resolved)
                                          │
                    [T5] transcribe/translate REVIEW (optional) → critical/modern layer + English gloss
                                          │
                    OUTPUT: 3 preserved layers + human-review queue (residual [UNCER] spans w/ arguments)
```

Edges connect the standard `files`/`documents` ports (exactly as the existing preset wires
`files-source → transcribe`). The ensemble is just **N `transcribe` draft nodes fed from the same
`files-source`**; the compare/reconcile nodes take the drafts as additional context.

---

## Node-by-node (all `tool: transcribe` unless noted)

| Node | Standard tool | Vision tier | thinking_mode | Role |
|---|---|---|---|---|
| `files-source` | files-source | — | — | page images (+ per-page metadata) |
| `T1a/b/c` DRAFT ensemble | transcribe | `$vision_small` (cheap/local) | medium | independent diplomatic drafts; **different model per node** for genuine cross-check |
| `R` reference | reference-search | — | — | ground against the abbreviation/formula corpus + prior pages of the same hand |
| `T2` compare + critical review | transcribe | `$vision_medium` | high | lock agreements; extract disputes; consistency checks |
| `T3` deep reconcile / panel | transcribe | `$vision_large` | high (extended) | argue disputes from letter-forms; diplomatic + apparatus + argument log |
| `T4` expand | transcribe | `$vision_medium` | medium | abbreviations → semi-diplomatic layer (keep diplomatic intact) |
| `T5` translate/review | transcribe / translate | `$vision_medium` | medium | optional critical/modern layer + gloss |

### New tool to add: `zoom` (the one worth building)

Testing showed whole-page reads underperform and **magnified region reads win** (Fabel reached 72%
only by re-reading regions; the deep panelist resolved glyphs at 7×). So add a `zoom` tool:

- **`zoom`** — input: a page image + a region (bbox, or a line index, or "auto-tile into overlapping
  line strips"); output: a high-res, contrast-normalized crop (optionally upscaled). Deterministic,
  cheap, local (sips/Pillow), reproducible.
- **Two uses in the graph:**
  1. **Tiling before drafts** — `zoom` auto-tiles the page into overlapping line strips; each ensemble
     draft transcribes strips, not the whole page (bigger effective resolution per token).
  2. **Targeted zoom in reconcile** — `T3` calls `zoom` on each *disputed span's* bbox to argue the
     letter-forms at magnification — exactly what the human-in-the-loop panelist did by hand.
- It's a natural sibling of the existing image nodes (`segment_images`, `split_images`,
  `prepare_images_for_ocr`, `enhance_images`); implement it as one more standard-shaped node so it
  composes with everything else. Optional second new tool: a deterministic **`consistency-check`**
  (parse numerals, verify word-sum = figure-sum, check repeated-name spelling) — nice-to-have; the
  `T2` prompt already covers it, but a deterministic version is more reliable for the arithmetic.

**Config knobs a builder can turn (all standard fields):**
- **Ensemble size / models** — 2 (cheap) … 4 (thorough); set each draft node's model/tier.
- **`$vision_small`** = the cheap-local swarm tier (MLX/Ollama when configured) — free + private.
- **Deep-mode toggle** — `T3` on (argue disputes) vs off (fast draft-only).
- **`thinking_mode`** — the "take your time / think longer" lever; raise on `T2`/`T3` for hard hands.
- **Language** = `auto` (preset auto-detects).

---

## Prompts (build on the existing preset's; the deltas that add your ideas)

The existing `Transcribe Paleography` DRAFT prompt is already good (script classification line;
Haggard-1941 rules; abbreviations expanded in `[brackets]`, uncertain kept as-written; two-tier
`[UNCER…]`). Reuse it for the ensemble drafts. The **new** prompts:

**`T2` — compare + critical review** (the "second-guessing", grounded, not solipsistic):
> You are given N independent transcriptions of the SAME manuscript image, plus the image and a
> reference corpus. (1) LOCK every span where the transcriptions AGREE. (2) Extract every span where
> they DISAGREE or any marks `[UNCER]`/`[?]` — this is the dispute set. (3) Run CONSISTENCY CHECKS and
> flag violations: do sums in words match sums in figures? are repeated proper names spelled
> consistently? is the notarial formula complete (`ante mí…`, `otorgan…`, `doy fe…`)? Output: the
> locked text, the dispute set (with each model's reading), and the consistency flags. Do NOT resolve
> disputes yet.

**`T3` — deep reconcile / panel** (the "various agents thinking, arguing"):
> For EACH disputed span only: reason at length from the LETTER-FORMS (compare the disputed letter to
> the SAME letter in securely-read words elsewhere on this page — the alphabet-from-anchors method),
> the notarial FORMULA/context, and historical PLAUSIBILITY. Argue, don't vote. Give a reading, a
> 0–100 confidence, and 1–3 sentences of concrete evidence. If still <80, KEEP it flagged `[UNCER]`
> with both readings + the argument. Produce the reconciled DIPLOMATIC transcription + a critical
> apparatus listing every residual uncertainty and its argument.

(Run `T3` as one high-reasoning node, or fan it into a small **panel of role-scoped nodes** —
paleographer / notarial-formula / skeptic — each a `transcribe` node whose prompt sets its lens, then
a final `transcribe` node reconciles. Both are standard nodes; the panel is more thorough + more
expensive. Default: single deep node; panel as a "deep+" variant.)

---

## Outputs (three preserved layers + the queue)

1. **Diplomatic** — exactly as written, abbreviations preserved, `[UNCER]` marks (the audit trail; never overwritten).
2. **Semi-diplomatic** — abbreviations expanded `[dicho]`, minimal normalization (research/DB layer).
3. **Critical/modern** (optional) — modernized + English gloss.
4. **Human-review queue** — the residual `[UNCER]` spans, each with the argument transcript, so a human
   adjudicates only the hard few per page (one letter on the test page).

---

## Build / modify instructions (for people)

0. Build the **`zoom` tool/node** once (crop+upscale a region / auto-tile into line strips) — the one
   new tool; reuse it everywhere below.
1. In the workflow builder, **duplicate the `Transcribe Paleography` preset** as the starting point.
2. Insert `zoom` (auto-tile) after `files-source`; add 1–3 more `transcribe` DRAFT nodes fed the strips
   (set each to `$vision_small` + a different model) → the ensemble.
3. Retarget the existing Review node into **`T2` (compare + critical review)** with the prompt above;
   feed it the drafts + `reference-search`.
4. Add **`T3` (deep reconcile)** at `$vision_large`, `thinking_mode: high`, with the panel prompt.
5. Optionally add **`T4` expand** and **`T5` translate/review** for the extra layers.
6. Save as a new preset — every step is a standard node, so it's fully reusable + modifiable.

## Validation before trusting it (do these, per the honest assessment)
- **Gold-standard CER**: transcribe a page a paleographer has verified; compute character-error-rate.
- **Harder page**: run a blotted / *procesal encadenada* page to see the real dispute rate.
- **Cheap-tier calibration**: measure how far `$vision_small` (local MLX/Ollama) is off on this
  material — decide if it can carry Tier-1 or needs a mid tier.
