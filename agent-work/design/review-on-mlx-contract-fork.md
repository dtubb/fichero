# Review-on-MLX vs the #4345 keyless-refusal contract — decision memo

**Date:** 2026-09-06
**Status:** PARKED — awaiting Daniel. No code committed for this fork; the tree is clean.
**For:** Daniel (his #1 return decision)
**Raised by:** backend lane (integration). Driving-execution lead cannot unpark a
documented product contract Daniel explicitly deferred; this memo is the hand-off.

---

## 0. One paragraph

Daniel asked that the "Transcribe + Review (Pipeline)" preset run fully on-device —
Apple Vision for recognition, **local MLX for the generative review pass** ("review
needs a key, but a local one mlx could work, test that"). Making that true, honestly,
requires letting a generative-vision node with no cloud key fall back to a local MLX
VLM. But there is no signal that separates "review" from the other generative-vision
presets — they are the same class — so the change **flips the documented #4345
keyless-refusal contract for ~10 presets at once**. That is a product decision (it
changes clean-install / demo behavior for 9 presets besides review), so it is parked
for Daniel rather than decided under his absence.

---

## 1. Root cause (verified in the integration worktree)

- Shipped `sub_workflow` children (`Transcribe Paleography`, `Paleographer Review`)
  specify **no** provider/model in their preset JSON.
- `WorkflowDef` defaults provider/model to `openai` / `gpt-4o`, and
  `resolve_sub_workflow_ref` (via `WorkflowDef.model_validate(preset)`) injects that.
- So the review/transcribe nodes preflight-resolve to **OpenAI** and fail on a missing
  key on a clean install — `validate_workflow_preflight` →
  `Provider 'OpenAI' requires an API key`.

Fix part 1 (surgical, uncontroversial): keep provider-less preset children
**provider-agnostic** (empty), so per-node/category resolution governs — matches
`apply_default_provider_model`'s own node-workflow rule. This alone makes the gate
pass. **But it is a hollow pass** (see §2).

## 2. Why "just make the gate green" is wrong

`transcribe_review` and the paleography `transcribe` are generative (`vision_mode:
"llm"`) but do **not** declare `requires_generative_model`. With the factory Vision
default = `apple` / `apple-vision`, they resolve to **Apple Vision OCR** — recognition
that ignores the review prompt. The gate goes green while the review silently runs as
OCR, not the MLX generative pass. That is exactly the silent-wrong-instrument outcome
Daniel rejects ("prefer raise over silent fallback"; "AI = instrument, not
interlocutor"). **An honest red beats a green gate that fakes review.** So part 1 must
not land alone.

## 3. To get review on MLX *for real* (two changes)

- (a) Mark `transcribe_review` + the `vision_mode:"llm"` `transcribe` as generative
  (they are — Apple OCR cannot answer their prompt).
- (b) When a generative-vision node has no cloud key and only a recognition-only
  vision default (`apple-vision`), fall back to a local **MLX VLM**
  (`omlx` / `Qwen2.5-VL-3B`) instead of refusing.

## 4. Blast radius — (b) is CLASS-WIDE, not review-only

There is no clean signal separating "review" from the rest of the generative-vision
class, so (b) flips the #4345 keyless-refusal contract for **every** generative-vision
preset. Today these refuse keyless with a clear preflight *"configure a
generation-capable vision model"* (asserted by
`tests/unit/workflows/test_preflight_credentials.py::test_keyless_fresh_install_passes_preflight_for_every_default_workflow`):

- Group Same Documents
- Accounts → Spreadsheet (CSV)
- Extract Table
- AI Convert to HTML
- AI Convert to Markdown
- AI Redraw as SVG
- Regesto (Archival Abstract)
- Modernización (Spanish)
- Translate to English (Historical)
- (+ Transcribe + Review (Pipeline) — the one actually requested)

Under (b), keyless they would resolve to on-device MLX and **pass preflight**; at run
time, if MLX is unprovisioned they fail with a *provision* message instead of the
current *configure* preflight message. `Translate (DeepL)` stays gated (explicit cloud
provider — `provider` is non-empty, so the fallback never fires).

**Demo consideration:** for those 9 other presets this can be a *worse* keyless
experience (spin up a heavy VLM, or fail at run) than today's clear preflight message —
and review-on-MLX is not itself a demo must-have.

## 5. Options

- **A (recommended — matches local-first north star):** implement (a) + (b). Whole
  generative-vision class falls back to local MLX when no cloud key and only a
  recognition-only vision default. Update the #4345 keyless test to expect these
  presets resolve to MLX (pass); DeepL stays gated. Coherent, on-brand for MLX-first —
  but a deliberate contract change across ~10 presets.
- **B (narrow):** scope the MLX fallback to only the review/pipeline path. No clean
  signal exists, so this means a preset/tool allowlist — hacky; not recommended.
- **C (no code):** document that Daniel sets an MLX VLM as the **Vision category
  default**; then everything vision (incl. recognition) routes through it. Simple, no
  contract change — but over-routes plain OCR to a heavy VLM and does not pass the
  apple-default gate test out of the box.

## 6. Recommendation

**A** — it is what "runs fully local out of the box" means and matches the MLX-first
direction (memory: local-first MLX; dead-simple UX). But it flips a documented #4345
contract and rewrites one keyless test, and it changes demo-day behavior for 9 presets
that are not the ask, so it is **Daniel's call**, not one to make under his absence.

## 7. What each option touches (for whoever implements the chosen one)

- Root-cause fix (all options that make the pipeline runnable): `resolve_sub_workflow_ref`
  in `workflows/subworkflow.py` — keep provider-agnostic children empty.
- (a): `requires_generative_model=True` on `transcribe_review` (and treat
  `vision_mode:"llm"` as generative) in the tool defs + `_preflight_node_error`.
- (b): a local-MLX fallback branch in `_preflight_node_error`
  (`workflows/validation.py`), using `mlx_model_store.default_local_generative_model`
  (helper drafted during investigation; not committed).
- Test: update `test_preflight_credentials.py::test_keyless_fresh_install_...` buckets
  (generative-vision + delegating presets move from "expect keyless failure" to "expect
  MLX resolution / pass"); DeepL stays in the keyed bucket.
