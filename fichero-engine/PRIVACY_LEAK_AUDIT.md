# Privacy / Cloud-Leak Audit

Scope audited on 2026-07-05:

- `fichero-engine/src/fichero/llm.py`
- `fichero-engine/src/fichero/providers.py`
- `fichero-engine/src/fichero/llm_models.py`
- `fichero-engine/src/fichero/llm_embeddings.py`
- `fichero-engine/src/fichero/workflows/validation.py`
- `fichero-engine/src/fichero/workflows/tools/llm_prompting.py`
- `fichero-engine/src/fichero/workflows/tools/translate.py`
- `fichero-engine/src/fichero/workflows/tools/text_reflow.py`
- `fichero-engine/src/fichero/workflows/tools/extract.py`
- `fichero-engine/src/fichero/workflows/tools/classify_script.py`
- `fichero-engine/src/fichero/workflows/tools/vision_base.py`

## Verified gated paths

- `fichero-engine/src/fichero/llm.py:986-1015` — `is_local_only()` + `_enforce_local_only_provider()` are the central fail-closed gate for chat/vision calls.
- `fichero-engine/src/fichero/llm.py:1324-1389` — `chat()` enforces the local-only gate before any provider call.
- `fichero-engine/src/fichero/llm.py:2185-2245` — `vision()` enforces the local-only gate before any provider call.
- `fichero-engine/src/fichero/llm.py:926-958` — fallback tier escalation is also gated; local-only blocks remote fallback and paid fallback is opt-in.
- `fichero-engine/src/fichero/llm_embeddings.py:37-60, 83-101, 104-112` — embedding calls correctly refuse remote providers when local-only is enabled.
- `fichero-engine/src/fichero/workflows/validation.py:232-316` — workflow preflight checks provider/model privacy before execution.
- `fichero-engine/src/fichero/workflows/tools/llm_prompting.py:335-345` — document metadata/text are intentionally included in prompts, so remote provider choice is a real content-egress decision; this is acceptable only when the above gating is honored.
- I found no outbound telemetry/analytics SDK in this scope. Usage/activity tracking is local process/app-db logging, not a remote analytics sink.

## Findings

1. High — DeepL translation bypasses `local_only` fail-closed gating.
   - File: `fichero-engine/src/fichero/llm.py:1613-1627`
   - `translate_text()` sends raw source text to `_translate_with_deepl()` without calling `_enforce_local_only_provider()`.
   - Impact: a workflow/tool using provider `deepl` can send private document text to DeepL even when `FICHERO_LOCAL_ONLY` / `local_only_ai` is enabled.
   - Fix: enforce the same local-only gate here before the DeepL branch, exactly like `chat()`/`vision()`.

2. Medium — direct Hugging Face vision helper relies on caller discipline instead of enforcing privacy locally.
   - File: `fichero-engine/src/fichero/llm.py:2407-2491`
   - `vision_inference_api()` posts prompt + image bytes directly to `https://api-inference.huggingface.co/...` but never calls `_enforce_local_only_provider()`.
   - Today this is usually reached through workflow preflight, but the helper itself is exported and fail-open if called directly or from a new call site without the preflight.
   - Fix: enforce the local-only gate inside `vision_inference_api()` before any network request.

3. Low — model-output parse failures can write private content into local logs.
   - File: `fichero-engine/src/fichero/workflows/tools/extract.py:153-155`
   - On JSON parse failure, the warning logs the first 100 chars of model output. That output can contain document text, names, or other sensitive content derived from the source.
   - Fix: log a structured parse failure without content preview; include tool/document identifiers instead of payload text.

4. Low — script-classification parse failures can write private content into local logs.
   - File: `fichero-engine/src/fichero/workflows/tools/classify_script.py:155-156`
   - On JSON parse failure, the warning logs the first 200 chars of model output.
   - Fix: same as above — no payload preview in logs; log identifiers/context only.

## Conclusion

- Core chat/vision/embedding egress policy is mostly correct and centrally enforced.
- The real privacy bug is helper-level drift: `translate_text()` and `vision_inference_api()` do not themselves enforce the local-only boundary.
- The remaining issues in this pass are local log hygiene, not additional cloud egress.
