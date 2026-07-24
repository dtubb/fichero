(AI generated. Not reviewed.)

# AI Infrastructure — Architecture Review (EPIC #2056)

> Status: **review doc**, written 2026-06-13. Describes what is **BUILT** in
> `fichero-engine/src/fichero/` today vs what is **PLANNED** under EPIC #2056.
> Every "BUILT" claim is grounded in a `file:symbol` reference verified against
> source. Sections marked **PLANNED** / **GAP** are not yet implemented.

## 1. Current-state map

### 1.1 The model-access choke point — `llm.py` (BUILT)

`fichero-engine/src/fichero/llm/` is the shipped entry layer for LLM calls.
The current public call surface is the set of coroutines in `llm.py`; provider
construction sits underneath them.

For workflow tools and agent/tool execution, the important built entry points
are `chat(...)`, `chat_structured(...)`, `chat_with_tools(...)`, and the helper
`chat_workflow(...)`. `chat_workflow(...)` dispatches to those shared functions
instead of each workflow building its own model path.

Every provider-backed path still bottoms out in `get_langchain_model(...)` for
LangChain model construction, but that factory is now an internal model-builder
under the higher-level chat functions, not the top-level workflow API.

Current public coroutines:

| Capability | Entry symbol (`llm.py`) | Notes |
|---|---|---|
| Chat | `chat` | Main unstructured entry point; Apple branch dispatches to fm-bridge before LangChain |
| Chat + Apple→cloud fallback | `chat_with_fallback` | **GAP: no paid-fallback gate — see §3** |
| Structured output | `chat_structured` | Main structured entry point; Apple branch or LangChain structured output |
| Structured + fallback chain | `chat_structured_with_fallback` | correctly gated by `_paid_remote_fallbacks_enabled` |
| Tool/function calling | `chat_with_tools` | |
| Workflow/tool dispatch | `chat_workflow` | Shared workflow/tool entry point that delegates to `chat`, `chat_structured`, or `chat_with_tools` |
| Vision | `vision` → `_apple_vision_dispatch` / `get_langchain_model` | Apple-routed by `config.provider == "apple"` |
| HF vision (direct) | `vision_inference_api` | **bypasses LangChain** — second vision path |
| Translation | `translate_text` / `_translate_with_deepl` | |
| Apple Intelligence | `_apple_intelligence_chat`, `_apple_intelligence_structured` | subprocess fm-bridge |
| Model construction | `get_langchain_model` | internal LangChain ChatModel factory used by the shared chat helpers |

Provider selection funnels through:
- `LLMConfig` (the typed config object; `god-node` — `get_blast_radius` before changing).
- `resolve_model_alias` — resolves `$small`/`$medium`/`$large` against app settings
  (`default_<tier>_provider` / `default_<tier>_model`) or `FICHERO_<TIER>_*` env.
- `get_langchain_model` — the canonical ChatModel factory under the shared chat
  helpers, with
  OpenAI-compatible base-URL handling (`_OPENAI_COMPATIBLE_BASE_URLS`,
  `_KEYLESS_OPENAI_COMPATIBLE = {ollama, lmstudio, omlx}`) and OpenRouter quirks
  (`_make_openrouter_http_client`, `_openrouter_strip_parallel_tool_use`).

Provider **metadata** lives separately in `fichero-engine/src/fichero/llm/providers.py`
(`ProviderType`, `PROVIDERS`, `get_provider_info`, `get_cloud_providers`,
`get_local_providers`, `get_vision_providers`, `get_embedding_providers`). This is
the static capability registry; `_is_local_or_builtin_provider` (llm.py) reads it
to decide free-vs-paid.

`litellm` is present in this module, but on current `main` it is not the model
routing layer. The routing and model construction path is LangChain plus the
Apple fm-bridge branch; `litellm` is used for cost/model metadata helpers, not
as the canonical workflow/provider dispatch path.

**Verdict:** `llm.py` is the canonical text/vision choke point, and the shipped
workflow/tool convention is "call `chat(...)` / `chat_structured(...)`" rather
than "call `get_langchain_model(...)` directly".

### 1.2 Embeddings — a SEPARATE, duplicated path (BUILT, two layers)

There are **two** embedding entry points that do not share a choke point with
`llm.py`:

1. **Local / canonical search + KG path** — `fichero-engine/src/fichero/db/embeddings.py`,
   `DatabaseEmbeddingMixin._embed_text` / `_embed_texts`. Uses **FastEmbed (ONNX)**,
   process-global shared embedder (`_get_shared_embedder`, `_EMBEDDER_CACHE`).
   - Live default model: `DEFAULT_MODEL = "intfloat/multilingual-e5-large"`
     (`db/embeddings.py`) — **not bge-m3**. The header comment in that file
     states bge-m3 is a *later* switch via `FICHERO_EMBED_MODEL`. So **#2117 (bge-m3
     wiring) is PLANNED, not built**; e5-large is current.
   - Model name is resolved at call time from `FICHERO_EMBED_MODEL` env or the
     mutable `default_embeddings_model` app setting (`_get_embedding_model_name`).
   - Input formatting: `format_for_model` adds `query:`/`passage:` prefixes for the
     E5 family **only**; bge-m3 and others get raw text.
   - Pooling is **whatever FastEmbed's `TextEmbedding` default is** for the model —
     there is **no explicit pooling pin in Fichero code**. Vectors are L2-normalised
     (`_l2_normalize`) and optionally int8-quantised (`_quantize_int8`).

2. **Cloud path** — `fichero-engine/src/fichero/llm_embeddings.py::embed`, LangChain,
   **defaults to OpenAI `text-embedding-3-small`**. (No live importers found via
   `find_references` — appears to be a legacy/secondary path, but still callable.)

Vectors land in LanceDB tables `embeddings`, `kg_entity_embeddings`,
`kg_claim_embeddings`. **No model name or pooling identifier is stored alongside the
vectors**, and there is no dimension/model guard on write — see §4.

### 1.3 Vision N+1 / per-page fan-out (BUILT)

Vision OCR/transcription is **per page**. `workflows/tools/vision_base.py` exposes
`apple_vision_ocr_pages_async` and `apple_vision_ocr_pdf_page_async` (one call per
page index). The Catalogue/Transcribe workflows fan out **one workflow branch per
page** (#891), and structured extraction runs per-section/per-page
(`chat_structured_with_fallback` callers: `book_index.py`, `citations_extract.py`,
`extract_entities_only.py`). Concurrency is governed by the **workflow** `concurrency`
parameter, not by request-level batching. There is **no use of LangChain
`.abatch()`** at the `llm.py` layer — see §2.

### 1.4 Telemetry (BUILT)

`collect_usage` / `_record_usage` provide a usage-collector context manager;
`estimate_cost` (llm_models.py) estimates spend. Apple usage is estimated/derived
(`_log_apple_usage_estimate`, `_log_apple_usage_from_bridge`).

### 1.5 On-device MLX & in-app Agent (PLANNED)

- **MLX (#1814 / #2066):** the OpenAI-compatible local providers `omlx`, `ollama`,
  `lmstudio` are already first-class in `get_langchain_model` (`_KEYLESS_OPENAI_COMPATIBLE`)
  and `fichero-engine/src/fichero/llm/providers.py`. So a local MLX server speaking the OpenAI API works **today** as a
  configured provider. A *native in-process* `mlx-lm` path is **not built**.
- **In-app Agent (#2067):** no agent-loop scaffolding found in the engine beyond the
  workflow executor + action registry (#1848). PLANNED.

See also: [MLX On-Device Agent Architecture](./mlx_on_device_agent.md), which turns
that current-state read into the implementation plan for #2066 / #1814 / #2067.
The short version: start with an app-managed OpenAI-compatible local MLX service
because the backend already supports keyless local providers, keep local-only as a
hard no-cloud boundary, and build the future in-app agent on the existing action
registry + audit + SSE/change-stream seams instead of inventing a parallel tool
system.

See also: [Pi Agent Harness Architecture](./pi_agent_harness.md), which makes Pi
the in-app agent loop/package harness while keeping Fichero's backend as the
authority for model profiles, local-only enforcement, action-registry tools,
agent principals, audit, event streaming, and grouped undo.

See also: [Apple Skills vs AI Skills](./apple_vs_ai_skills.md), which defines how
Apple on-device capabilities, local AI providers, and remote AI providers should
coexist as implementations of the same logical capability contract. App Intents
remain an invocation layer over typed backend actions/workflows, not a second
mutation system.

See also: [Image Editing Backend Strategy](./image_editing_backend_strategy.md),
which decides the Pillow / Quartz / Core Image / OpenCV split for image
editing at scale, including preview and batch behavior.

## 2. Reuse / batching / concurrency

**BUILT:** model reuse is solid — `_get_shared_embedder` pools the embedder
process-globally; #2050/#2055 addressed local-model and client reuse.

**GAP:** there is **no batched LLM/vision call path**. `chat`, `vision`,
`chat_structured` are all single-item `ainvoke`. The 1000s-of-images lever the EPIC
names (LangChain `.abatch()` / provider batching) is unbuilt. Per-page fan-out gives
parallelism via the workflow scheduler's `concurrency` knob, but each item is still a
separate HTTP round-trip — N+1 by page. Embeddings ARE batched at the FastEmbed layer
(`_embed_texts`), but callers that embed passage-by-passage don't all use it.

## 3. Cloud-leak audit (#2065) — FINDINGS

The repo has **no global local-only / no-cloud perimeter**. A `search_text` for
`local_only|no_cloud|offline_mode|FICHERO_LOCAL_ONLY` returned **zero** matches. The
only consent gate is the per-call `_paid_remote_fallbacks_enabled()` flag
(env `FICHERO_ALLOW_PAID_AI_FALLBACKS`, default **OFF**, or app setting
`allow_paid_ai_fallbacks`).

**Leak path 1 — asymmetric fallback gate (HIGH).**
`chat_structured_with_fallback` correctly checks `_paid_remote_fallbacks_enabled()`
before routing to a paid `$medium`/`$large` cloud provider. Its plain-text twin
`chat_with_fallback` does **NOT** — on any `AppleUnavailableError` (guardrail refusal
/ unsupported locale) it builds `$large` and calls `chat(prompt, large_config)`
unconditionally. Document content that Apple's on-device filter refused is then sent
to a paid cloud provider **with no consent gate**. → Issue filed.

**Leak path 2 — no global local-only mode (HIGH, EPIC thread #10).**
Even with paid fallbacks disabled, a workflow node can be *explicitly configured* with
a cloud provider, and `chat`/`vision`/`embed` will honour it. There is no single
switch a privacy-sensitive user can flip to guarantee nothing leaves the machine. The
choke point exists (`get_langchain_model`) but enforces no perimeter. → Issue filed.

**Leak path 3 — cloud embedding default (MEDIUM).**
`llm_embeddings.embed` defaults to OpenAI `text-embedding-3-small`. It has no current
importers, but it is public and would silently exfiltrate text if wired in. Should be
gated by the same local-only perimeter or removed/aliased onto the local path. → Issue filed.

## 4. Embedding vector-space consistency (#2117 / #2049) — FINDINGS

**GAP (HIGH — silent search corruption).** The embedding model is resolved from a
**mutable** source (`FICHERO_EMBED_MODEL` env or `default_embeddings_model` setting)
at *call time*, but:
- No model name / pooling tag is stored next to vectors in LanceDB.
- There is no guard that rejects or re-embeds when the configured model changes.
- Pooling is implicit (FastEmbed default per model). e5-large and bge-m3 are both
  1024-dim, so a switch passes the dimension check trivially while landing vectors
  from a *different geometry* into the same table — cosine search silently degrades.

`#2049` (CLS→mean pooling pin / re-embed) and `#2117` (bge-m3 wiring) are therefore
**not closed in code**. The fix is to (a) pin the model + pooling explicitly, (b) stamp
the model id on every vector row, and (c) refuse-or-reindex on mismatch. → Issue filed.

## 5. Canonical model-access design (target)

Keep `llm.py` as the one text/vision choke point; keep
`fichero-engine/src/fichero/db/embeddings.py` as the one embedding choke point.
**Do not introduce a new gateway module.** Add three thin
layers *in place*:

1. **Privacy perimeter** — a single `is_local_only()` predicate (env +
   `app_db` setting) consulted at the top of `chat`, `vision`, `_build_fallback_config`,
   `chat_with_fallback`, and both embed paths. When on, any non-local/non-builtin
   provider is refused loud, never silently downgraded.
2. **Symmetric fallback gate** — `chat_with_fallback` adopts the exact
   `_paid_remote_fallbacks_enabled()` check that `chat_structured_with_fallback`
   already has.
3. **Embedding identity** — pin model+pooling, stamp `embedding_model` on every
   vector row, guard on read/write, provide a `reindex_all` re-embed trigger on change.
4. **Batching** — add `chat_batch` / `vision_batch` over LangChain `.abatch()`,
   routed through the same `LLMConfig`, used by the per-page fan-out.

## 6. Sequenced build plan (dependency-aware)

1. **[P0, safety] Symmetric paid-fallback gate** — add `_paid_remote_fallbacks_enabled`
   check to `chat_with_fallback`. Smallest, highest-value leak fix. (Issue A)
2. **[P0, correctness] Embedding identity + guard** — stamp model id on vectors, refuse/
   reindex on mismatch, pin pooling. Unblocks #2117/#2049. (Issue D)
3. **[P1, privacy] Global local-only perimeter** — `is_local_only()` predicate wired
   into the choke points; UI toggle is frontend follow-up. Depends on (1) for the
   fallback path. (Issue B) — EPIC thread #10.
4. **[P1, leak] Gate/retire cloud embedding default** in `llm_embeddings.embed`.
   Depends on (3)'s predicate. (Issue C)
5. **[P2, scale] Batched call path** — `chat_batch`/`vision_batch` via `.abatch()`,
   adopt in per-page fan-out. The 1000s-of-images lever. (EPIC thread #1)
6. **[P2] Native MLX path** (#1814) — optional; OpenAI-compatible `omlx` already works.
7. **[P3] In-app Agent loop** (#2067) — on top of action registry #1848.

## 7. Risks

- **Embedding migration:** stamping + reindex must not nuke real Marshall-diaries
  vectors; needs an idempotent backfill (per migration policy, rule #9 retired).
- **`LLMConfig` blast radius:** it's a god-node; perimeter checks should wrap call
  sites, not change `LLMConfig`'s shape.
- **Local-only false sense of security:** the perimeter must cover *all* paths
  (chat, vision, both embed paths, translation/DeepL, HF `vision_inference_api`) or
  it's worse than nothing. `_translate_with_deepl` and `vision_inference_api` are easy
  to miss.
- **Apple fallback UX:** refusing instead of silently falling back will surface more
  errors to users who relied on the silent cloud escape; needs a clear message.

## Efficiency & batching plan

> Adversarial pass 2026-06-13 (Fable). Every claim below is grounded in source.
> The headline: model reuse at the LangChain choke point is **NOT** built (despite
> #2055 being closed), there is **zero** `.abatch` usage, and concurrency is bounded
> per-extractor but **not** on the per-page vision fan-out.

### E1. No LangChain ChatModel/client reuse — rebuilt per call (#2055, real, REOPEN)

`get_langchain_model` (`llm.py:2550`) constructs a **fresh** `ChatOpenAI` /
`init_chat_model` (and therefore a fresh underlying httpx client + connection pool)
on **every** call. Both `chat` (`llm.py:609`) and `vision` (`llm.py:1259`) call
`model = get_langchain_model(config)` inline with no caching. The only cache in the
file is the async locale-support probe (`llm.py:2110`, `_LOCALE_SUPPORT_CACHE`) — a
regex search for `lru_cache|_MODEL_CACHE|_CLIENT_CACHE` finds nothing else.

**Quantified blast:** the per-page catalogue/transcribe fan-out
(`_make_parallel_node_function`, `builder.py:837`) runs one node invocation per page,
each of which (via the tool → `chat`/`vision`) builds its own ChatModel + httpx
client + TLS handshake. A 200-page PDF at concurrency 6 ⇒ up to ~200 client
constructions and a churn of TLS handshakes that never get pooled. OpenRouter is worse
— each build also calls `_make_openrouter_http_client()` (a fresh `httpx.AsyncClient`).

**#2055 was closed but the LangChain path is the gap it claimed to close.** #2050/#2055
fixed the FastEmbed embedder (`_get_shared_embedder`, process-global, double-checked
lock) and the Apple fm-bridge — but **not** the remote LangChain clients. Reopen #2055
(or file a follow-up) scoped strictly to `get_langchain_model`.

**Smallest fix:** memoize on a cache key derived from the **identity-affecting** config
fields only — `(provider, model, api_base, api_key-presence, temperature, max_tokens,
timeout, reasoning_effort)`. A module-level `dict` guarded by a lock (mirroring
`_get_shared_embedder`), or `functools.lru_cache` over a frozen key tuple with the model
built in a helper. Do **not** key on the whole `LLMConfig` (unhashable; `extra` is a
dict). ChatOpenAI/init_chat_model instances are safe to share across concurrent
`ainvoke` calls (the httpx client is async-pooled). Caveat: per-request API keys must
stay in the key so two libraries with different keys don't collide.

### E2. Zero `.abatch` — every call is single-item `ainvoke` (#2057, real)

`search_text "abatch"` over the engine returns **0 matches**. `chat`, `vision`,
`chat_structured` all do single-item `model.ainvoke(...)`. The 1000s-of-images lever
named in EPIC #2056 is unbuilt.

**Exact fan-out sites where batching is the win:**
1. **Per-page vision** — `vision` (`llm.py:1259`) is called once per page through the
   Send fan-out (`builder.py:_make_parallel_node_function`). Pages of the *same* PDF go
   to the *same* model with the *same* prompt — a textbook `.abatch([msg1..msgN])`.
2. **Per-chunk embeddings** — `_embed_texts` (`fichero-engine/src/fichero/db/embeddings.py`) already batches at
   the FastEmbed layer (`self._embedder.embed(formatted)`), so embeddings are fine for
   the local path. The **cloud** path `llm_embeddings.embed` uses `embed_documents`
   (also batched). The gap is purely the LLM/vision side.

**Smallest fix:** add `chat_batch(prompts, config)` / `vision_batch(image_lists, prompt,
config)` thin wrappers over `model.abatch(...)` routed through the same (now-cached)
`get_langchain_model`, then teach the per-page fan-out to group same-config pages into
one `.abatch` instead of N Send branches. Cost-tracking must sum `usage_metadata` over
the batch.

### E3. Concurrency: bounded per-extractor, UNBOUNDED on per-page vision (#2062, partial)

`asyncio.Semaphore` **does** exist — `search_text "Semaphore"` finds it in:
- `workflows/batch.py:478` — `Semaphore(batch.max_concurrent)` per batch
- `workflows/executor.py:600/651` — `Semaphore(batch_size)` + a `max_concurrent` gate
- `extract_all.py:1210/1638`, `extract_entities_only.py:200`, `extract_svo_only.py:194`
  — `extraction_sem = Semaphore(max_in_flight)`, default **3**
  (`FICHERO_EXTRACT_MAX_IN_FLIGHT`).

So the structured-extraction fan-out is capped (good). The **gap** is the LangGraph
**Send** per-page vision/catalogue path: `_make_parallel_node_function` (`builder.py:837`)
has **no semaphore** — it relies entirely on the LangGraph scheduler's `concurrency`
knob. There is no single global cap on concurrent model calls, and no memory budget.
A folder run with many PDFs × many pages can open far more concurrent vision calls than
any provider rate limit / local-MLX RAM tolerates.

**Smallest fix:** a single module-level `asyncio.Semaphore` in `llm.py` (size from
`FICHERO_LLM_MAX_IN_FLIGHT`, default e.g. 6) acquired inside `chat`/`vision`/
`chat_structured` right before `ainvoke`. That caps *all* paths at the choke point and
makes the scattered per-extractor semaphores a secondary, finer-grained throttle. This
is the iterate-in-place move: wrap the existing choke point, don't add a scheduler.

### Ranked efficiency wins (impact × cheap-to-run)

1. **Client/model reuse (E1 / #2055-reopen)** — biggest cheap win. One module-level
   cached `get_langchain_model` removes ~N TLS handshakes + client allocations per
   N-page run. Pure in-place memoization, no behaviour change, no new dependency.
2. **Global in-flight semaphore (E3 / #2062)** — one semaphore at the `llm.py` choke
   point caps the unbounded Send fan-out and adds a memory/rate-limit safety floor.
   Tiny diff, large blast-radius protection for 1000s-of-images runs.
3. **`.abatch` on same-config page groups (E2 / #2057)** — the true 1000s-of-images
   throughput lever, but more work (batch cost-accounting + fan-out regrouping), so it
   ranks third on cheapness despite the highest ceiling.

## AI-backend test plan

> Checklist for a test-writing worker. **Do not** let it run on Daniel's desktop GUI;
> these are pure-Python unit tests with mocked providers (no live keys, no server).
> References #1987 (workflows: 175 untested symbols). `get_untested_symbols` on
> `llm.py` reports **reached_pct 60%** — 20 of 50 symbols have no test reference,
> including `_build_fallback_config`, `_resolve_api_key`, `_record_usage`,
> `estimate_token_count`, `_is_provider_quota_error`. The behaviors below MATTER:

| # | Behavior (target) | Assertion the test must make |
|---|---|---|
| T1 | **Provider/key resolution** — `_resolve_api_key`, `get_api_key` (`llm.py`) | Given env key, keychain key, and per-config `api_key`, the documented precedence wins; keyless local providers (`ollama/lmstudio/omlx`) resolve to a placeholder, not an error. |
| T2 | **Symmetric paid-fallback gate** — `chat_with_fallback` (`llm.py:715`) | With paid fallbacks **disabled** (default) and `$large` = a cloud provider, an `AppleUnavailableError` must **raise** (not silently call `chat` on the cloud `$large`). Mirror of the structured test. This is the #2191 regression guard. |
| T3 | **Structured fallback gate (positive)** — `chat_structured_with_fallback` (`llm.py:1805`) | With paid fallbacks disabled, a cloud `$medium`/`$large` tier is **skipped** (asserts the "Skipping $%s ... disabled" branch); with `FICHERO_ALLOW_PAID_AI_FALLBACKS=1`, the cloud tier **is** attempted. |
| T4 | **Fallback config build** — `_build_fallback_config` (`llm.py:517`) | Resolves `$medium`/`$large` alias → provider/model, carries transport overrides, and when the alias resolves to the *same* model as `config`, the caller's same-model short-circuit fires (no pointless retry). |
| T5 | **`.abatch` correctness (once built)** — new `chat_batch`/`vision_batch` | `abatch([a,b,c])` returns results in input order, and `usage_metadata` is summed across the batch into `_record_usage` (no lost cost). Order-preservation is the load-bearing assertion. |
| T6 | **Concurrency bound (once built)** — global `llm.py` semaphore | With the in-flight cap = K, no more than K `ainvoke` coroutines are ever simultaneously in-flight (instrument a fake model that records max-concurrency). Guards the #2062 unbounded-Send regression. |
| T7 | **Cost estimation coverage** — `estimate_token_count` (`llm.py:1987`), `estimate_cost` (`llm_models.py`) | Known token counts → expected cost for at least one cloud model; an **unknown** model id does not crash (returns 0 / None, logged) rather than raising mid-run. |
| T8 | **Usage recording** — `_record_usage` / `collect_usage` (`llm.py:83/105`) | A `chat` call whose mocked response carries `usage_metadata` records input/output/total tokens against `(provider, model, "chat")`; a response **without** `usage_metadata` records nothing and does not crash. |
| T9 | **Embedding model-id stamping** (PLANNED, gates #2194) | After embedding, every written vector row carries the resolved `embedding_model` id; reading with a *different* configured model raises/refuses rather than cosine-comparing across geometries. Currently **fails** (no stamp) — write it as the failing spec for the fix. |
| T10 | **Embedding role/pooling formatting** — `format_for_model` (`fichero-engine/src/fichero/db/embeddings.py`) | E5-family inputs get `query:`/`passage:` prefixes per `role`; non-E5 models (bge-m3) get raw text. Pins the documented behavior so a model switch can't silently drop prefixes. |
| T11 | **Quota-error classification** — `_is_provider_quota_error` (`llm.py:427`) | A 429/quota exception from a provider is classified as `ProviderQuotaError` (so the fallback chain and `SystemicErrorDetected` pause fire); an unrelated 500 is **not** misclassified. |
| T12 | **Cloud-embedding default leak** — `llm_embeddings.embed` (`llm_embeddings.py:52`) | Once the local-only perimeter exists: calling `embed` under local-only must refuse, not silently hit OpenAI `text-embedding-3-small`. Failing spec for #2193. |
