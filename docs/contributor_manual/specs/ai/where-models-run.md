# Where Models Run — the model and the place it runs — Design Spec (#5582)

> Milestone: ai-settings
> Manual: TBD — a "Where your models run" section in the Settings part: that choosing a model is
> choosing where it runs too; the places Fichero knows (this Mac, a provider with your key, a model
> server on another of your machines, Hugging Face, a cluster); what each offer on the Ready screen
> means (cost for your pages, time, whether pages leave this Mac, which account it needs); what
> Activity shows while a model runs anywhere; and what Fichero does by itself when a place is busy,
> full or down.

> Design-led (Testing Constitution). **Status: DRAFT, 2026-10-07 — awaiting the maintainer.**
> Written read-only against the integration tree (`lead`, at 88e340e08). Server paths are relative
> to `fichero-server/src/fichero_server/`; app paths name the Swift file. Every claim about code was
> read for this spec on 2026-10-07 unless marked *(spec)*, which means taken from the named spec
> without a second read.
> Tags: **[OK]** built and tested · **[PARTIAL]** built, unproven or partly wired · **[GAP]**
> intended, never built · **[BROKEN]** the code contradicts the intent. Every non-OK line cites an
> issue.
>
> **This spec consolidates.** It owns one thing the others do not: the **pair** (a model and the
> place it runs) and how one is chosen, run and shown. It does not restate what it builds on:
> - `ai/local-runtimes.md` — how each runtime on this Mac ships, loads and stays resident (card ids,
>   `runtime.*`).
> - `ai/ai-settings.md` — the Settings rows, keys and runtime status (`settings.*`, `keys.*`).
> - `compute/remote-compute.md` and its slice files — targets, packages, Slurm and Hugging Face Jobs
>   (`compute.*`), including "Models in memory" in `compute/jobs-and-fine-tuning.md`.
> - `source/models-chains-and-projects.md` — the card, the rules, the bake-off, discovery, the
>   egress gate (`source.model.*`, `source.find.*`, `source.egress.*`), and #5582's paragraph,
>   "The best model, and the best place to run it", which this spec expands.
> - `ui/activity-and-automatic-work.md` — the one job model and its lanes (`activity.*`).

## Intent

A researcher picks a reader, a name finder or a corrector. Fichero treats that as two decisions
made together: **which model**, and **where it runs**. Where can be this Mac (when its memory and a
runtime in this build allow), any provider in the catalogue that serves that model or the same
weights (Gemini, Anthropic, OpenAI, Mistral, OpenRouter, Hugging Face's inference providers or a
dedicated endpoint, an Ollama or LM Studio server on another of the person's machines), or, for a
whole archive, Hugging Face Jobs or a cluster such as ACENET's. Each offer says, before anything
runs, what it will cost for this project's pages, how long it will take, whether the pages leave
this Mac (the project's own rule decides), and whether the account it needs is set up.

Whatever is chosen, the work runs through **one job model**: the same lanes, the same memory rules,
the same waits and retries, the same run account and the same rows in Activity. A person sees the
same thing wherever a model runs. Fichero, not the person, keeps memory in order and decides what
to do when a place is full, busy or down, within what the person agreed to at Start.

## Prior art

- **OpenRouter** and **Hugging Face Inference Providers** already separate *the model* from *who
  serves it*: one model id, several providers, each with its own price, latency and data policy;
  the router picks by price or throughput, and a request can pin or exclude providers. Hugging
  Face's Hub API exposes, per model, which inference providers serve it. We adopt the split (card
  = the model, place = who serves it) and the per-place price and data policy. We do **not** adopt
  silent routing: the person's project rule decides which places may see pages.
- **Hugging Face Inference Endpoints** (dedicated, billed by the hour, scale to zero with a cold
  start) are a different place from Inference Providers (shared, billed by the token).
- **LiteLLM's router** and **LangChain's `with_fallbacks`** fall back across deployments of the
  *same* model on errors and rate limits. That is the fallback we want; falling back to a
  different model is what the maintainer ruled out on 2026-09-07 (`llm/__init__.py:1919-1927`).
- **Ollama** reports what it holds in memory (`/api/ps`, with each model's size in memory);
  LM Studio exposes the loaded models through its own API. A model server on this Mac can be
  measured, not guessed.
- **Slurm** and **Hugging Face Jobs** bill by allocation or by the hour, not by the token; their
  cost is hours × rate, and their speed is pages per hour measured on a sample.

What we do differently: every place, local or remote, token-priced or hour-priced, is one row
type with the same five facts (fits, allowed, account, cost, speed), so one ranking rule and one
Ready row cover them all.

## 1. Inventory: every place a model can run today (read 2026-10-07)

### 1.1 The places

| Place | How it is configured | How a call is routed | Lane / job | Memory check | Cost | Egress check |
|---|---|---|---|---|---|---|
| **MLX on this Mac** (`omlx`, the engine's own `mlx_vlm`/`mlx_lm` server) | catalogue `MANAGED_MLX_MODELS`, Settings' local model (`llm/local_model_choice.py:167-186`) | `_ensure_managed_local_provider_ready` switches the server to the requested model (`llm/__init__.py:4229-4279`) | `local-ml` lane (`llm/__init__.py:1500`) plus a read slot sized by memory (`:1382-1405`, `llm/local_inference.py:236-254`) | yes: weights + 1 GB against macOS's free count, 75 % ceiling, waits up to 5 min (`llm/local_inference.py:90-134,159-204`) | free (`llm/usage.py:46-60`) | n/a (loopback) |
| **Kraken** (in-process) | bundled; readers by DOI | `jobs.run_on_lane` with `kraken:` models | `local-ml` | yes: `throttle.memory_short` at 2.5 GB (`execution/throttle.py:68-105`, `llm/kraken_runtime.py:345,392`) | free | n/a |
| **Apple** (Vision, FoundationModels, translation) | OS | fm-bridge per call *(spec: `ai/local-runtimes.md`)* | **no lane**: built-in providers take no slot (`llm/__init__.py:1485-1488`) | none ("system") | free | n/a |
| **spaCy, embeddings** | bundled / model store | in-process | `local-ml` families (`execution/jobs.py:1113-1117`) | released on switch | free | n/a |
| **Whisper on this Mac** | MLX runtime venv | `transcribe_with_whisper` in a subprocess (`workflows/tools/audio_base.py:128-168`) | **no lane, no job row** | none | free | n/a |
| **Ollama / LM Studio** | Settings row with an optional Server URL (`AddProviderSheet+Helpers.swift:62-67`) | `ChatOpenAI` at `config.api_base or localhost` (`llm/__init__.py:4187-4188,4675-4693`) | **always `local-ml`**, because the provider *type* is `is_local` (`llm/providers.py:161-190`, `llm/__init__.py:1500`, `execution/jobs.py:1093`) | **none** (the memory wait and read slots are `omlx`-only, `llm/__init__.py:1392,4230`) | free | **skipped**: local by type |
| **Cloud APIs** (OpenAI, Anthropic, Google, Mistral, Cohere, Bedrock, Azure, Groq, Together, DeepSeek, xAI, Fireworks, DashScope, Perplexity) | Settings row + key | `init_chat_model` or `ChatOpenAI` (`llm/__init__.py:4593-4712`) | `network` lane, 4 slots, share per provider (`execution/jobs.py:82,1399-1411`); outside a project a 12-call process semaphore (`llm/__init__.py:138,1363-1378,1509`) | none needed | token price list, one pricer (`llm/usage.py:227-272`) | `local_only_ai` only (see 1.3) |
| **OpenRouter** | row + key | `ChatOpenAI` at openrouter.ai (`llm/__init__.py:4639-4671`) | `network` | — | price list (gateway-keyed, `llm/usage.py:193-224`) | as cloud |
| **Hugging Face inference** | row + key | `ChatOpenAI` at `router.huggingface.co/v1` (`llm/__init__.py:4197`): Inference Providers only | `network` | — | price list (often unpriced) | as cloud |
| **Hugging Face Jobs** (train; read at scale) | the `huggingface` row's token (`training/hf_jobs.py:62-71`) | `HfJobsTarget` (`training/hf_jobs.py:83-140`) | `remote` lane rows, phases in `detail` (`training/job.py:84-105`, `remote_read/job.py:95-111`) | n/a | price per hour read before sending (`training/hf_jobs.py:115-121`); **not in the run account** | per-request `pages_may_leave` flag (`training/job.py:90-92`, `remote_read/job.py:99-101`) |
| **Slurm / ACENET** | `hpc.clusters` setting, no app screen *(spec: `compute/remote-compute.md`)* | described only: Test returns `ok=True` without connecting (`api/routes/ai/hpc.py:254-285`); `remote_read/slurm.py` describes an array, sends nothing | none live | n/a | none | none |

### 1.2 How a choice is made today

- **Setup's rules** rank **cards**, not pairs: hard constraints, then accuracy band, then
  local before remote, cost, speed (`recipes/assemble.py:197-215,282-297`); a remote card is
  considered only when no local one passes (`:311`). No seed card is a cloud card
  (`recipes/seed/cards.yaml`: no `runs_on` line), so the rules never offer a cloud reader by
  themselves.
- **A card's place is one string** (`runs_on: this-mac | cloud:<provider> | cluster |
  gpu-service`, `recipes/assemble.py:124`; `recipes/recipe.py:24`). One card cannot say "this
  model also runs on OpenRouter and on Hugging Face".
- **Discovery** offers only MLX builds from the Hub and lists the rest for the person without
  handing them to the rules (`recipes/discovery.py:19-23,306-337`). A model this Mac cannot run
  (PyLaia, TrOCR, a 32B vision model) is never offered with a place where it could run.
- **The bake-off** prices a remote candidate but cannot score it: "a remote model target is not
  built in the evaluation job yet" (`recipes/bakeoff.py:101-102`).
- **Speed** is measured per model, from finished job rows (`recipes/routes.py:29-34`,
  `execution/jobs.py:1014`); a cloud model's speed is never measured (`recipes/routes.py:63`).
- **Memory fit** has three rules: setup's (`card.memory_gb` against the Mac's memory less 2 GB,
  `recipes/assemble.py:74,213`), `runs_here` (the MLX catalogue's `min_memory_bytes` /
  `page_memory_bytes`, `llm/local_model_choice.py:49-63`) and the load gate (download size + 1 GB
  against 75 % of memory, `llm/local_inference.py:90-134`). Kraken's card says 3.6 GB
  (`recipes/seed/cards.yaml:16`) and its guard 2.5 GB (`llm/kraken_runtime.py:345`).

### 1.3 Egress today: three mechanisms that do not consult each other

1. **An engine-wide switch**, `is_local_only()`, reading `FICHERO_LOCAL_ONLY` or the
   `local_only_ai` setting (`llm/__init__.py:1192-1207`). Nothing writes `local_only_ai` and no
   surface shows it (searched: one reader, no writer). It is checked in `chat`, `chat_batch`,
   `translate_text`, `vision`, `audio_transcription`, `vision_batch`, `vision_inference_api` and
   `chat_structured`, but **not** in `chat_with_tools` (`:3127-3173`) or `structured_output`
   (`:3223-3255`). It judges by provider **type** (`:1210-1222`), so an Ollama at another
   machine's address always passes.
2. **The project's rule**, `cloud_allowed` in setup's answers, read only when a recipe's Start is
   planned (`recipes/runner.py:49`, `api/routes/system/recipes.py:795`, `recipes/start.py:121-123`)
   and by setup's rules (`recipes/assemble.py:211`). A workflow started from the workflow bar,
   chat or MCP on a project that keeps its pages never meets it.
3. **A per-request yes** for Hugging Face Jobs, `pages_may_leave`, recorded on the row
   (`training/job.py:90-105`, `remote_read/job.py:99-111`). It does not read the project's rule:
   a caller can send a "keep pages here" project's pages to Hugging Face by passing `true`.

### 1.4 What is broken or inconsistent (the findings)

1. **Locality is decided by provider type, not by address.** `ollama`, `lmstudio` (and `omlx`)
   are `is_local=True` (`llm/providers.py:161-204`). An Ollama on another machine is therefore:
   exempt from the egress switch (`llm/__init__.py:1220`), scheduled on the one-slot `local-ml`
   lane beside Kraken (`:1500`, `execution/jobs.py:1093`), grouped as a "local-model" heavy family
   that frees Kraken on a switch (`execution/jobs.py:1096-1101,1124-1126`), and priced as free
   (`llm/usage.py:46-60`). Pages leave the Mac with no check, and the Mac's lane waits on a
   network call.
2. **A provider row's Server URL never reaches a workflow run.** Settings saves it
   (`AddProviderSheet+Helpers.swift:62-67`); the model list reads it
   (`api/routes/ai/provider_models.py:360-369`) and chat uses it (`api/routes/system/chat.py:431-443`);
   but every `LLMConfig` a workflow builds carries no `api_base` (`workflows/builder.py:270,298,306,326,551`),
   so a run calls `localhost:11434` with a model the person picked from a server elsewhere.
3. **`runs_on` is a label, not a route.** Start echoes it (`recipes/start.py:129,131,163`) and
   nothing dispatches on it (searched: no reader outside `recipes/`). The place actually used is
   inferred from the model pin (`recipes/start.py:69-82`): a step that says `runs_on: cluster` (any
   job but training) runs on this Mac; a step that says `cloud:openrouter` with a Hub pin runs on
   the local MLX server.
4. **The estimate prices every place that is not `cloud:` at $0** (`recipes/start.py:286-289`),
   cluster and gpu-service included, and Activity's cost roll-up counts only token usage
   (`execution/jobs.py:421-426`), so an hour-billed Hugging Face Job never appears in a run's cost.
5. **Three egress mechanisms** (1.3), none of which is the one gate `source.egress.one-gate` asks
   for.
6. **A silent fallback to "the first configured provider"** remains: a node with no model and no
   defaults takes the first enabled provider with an enabled model, cloud or not
   (`workflows/builder.py:313-328`), contradicting the 2026-09-07 fail-loud ruling.
7. **Memory is checked for MLX and Kraken only.** Ollama and LM Studio on this Mac, Whisper and
   Apple's bridge load beside them unmeasured (1.1). Three memory-fit rules disagree (1.2).
8. **Retries live in four places with different meanings:** LangChain's `max_retries=10` inside
   one call, holding its lane slot (`llm/__init__.py:4568-4573`); `page_retry` once for a passing
   cause (`compute.run.retry-passing-cause-once`); a stored job's `MAX_ATTEMPTS = 3`
   (`execution/jobs.py:66`); and a person's "send the failed shards again" for Hugging Face Jobs.
9. **Two caps on cloud concurrency**: the `network` lane's 4 slots inside a project, a 12-call
   process semaphore outside one (`llm/__init__.py:138,1504-1510`).
10. **Remote audio records no usage** (`llm/__init__.py:2792-2833` never calls `_record_usage`),
    so a transcription by OpenAI's Whisper is unpriced.
11. **Four vocabularies for "where"**: `runs_on` strings on cards and steps; the provider
    registry's `is_local`/`is_builtin`; the jobs table's lanes; a trained model's `builds` with
    their own `runs_on` ("Apple silicon", "Linux GPU", `training/mlx_landing.py:119-120`).
12. **Settings' status dot** is still `isLocalProvider || hasApiKey`
    (`ProvidersView+ProviderDetailView.swift:136`, `ProvidersView+ProviderSettingsRow.swift:40`);
    a remote Ollama that is down shows green.
13. **No dedicated Hugging Face Inference Endpoint** can be named: the `huggingface` row always
    goes to the shared router (`llm/__init__.py:4197`) unless a Server URL is set, which (2.) runs
    ignore.

What works and is kept: the one pricer for tokens (`llm/usage.py:227-272`), the memory waits and
release for MLX and Kraken (`compute.memory.*`, #5537), the lanes and their group-by-model
scheduling, the run account's peaks (`compute.memory.run-peak`), Hugging Face Jobs as rows with
phases and a stored far-side id, the fail-loud fallback ruling in `chat_with_fallback` and
`chat_structured_with_fallback` (`llm/__init__.py:1913-1941,3555-3633`), and the one Hugging Face
token (`training/hf_jobs.py:62-71`).

## 2. The design

### 2.1 The pair

A recipe step's choice is a **pair**: a **card** (the model, pinned as today, `source.model.card-id`)
and a **place** (where it runs). The recipe stores the card and a **kind of place**; the project
binds the kind to a concrete place, so a shared recipe never names a person's account
(`source.recipe.runs-on-binds-to-a-target`, `recipes/recipe.py:23-24`).

```yaml
- id: read-a-line
  job: read-a-line
  model: {hf: Qwen/Qwen2.5-VL-7B-Instruct, revision: 5b5f…}
  runs_on: endpoint          # this-mac | endpoint | batch
  alternatives:              # optional, the person saw them at Start
    - {runs_on: this-mac}    # same card, another place
```

The place is resolved **once, before Start**, and recorded on the run; it is never inferred from
the pin again, and a step is never run anywhere its `runs_on` does not name.

### 2.2 The catalogue of places

One list, one row type. Every place has:

| Field | Meaning |
|---|---|
| `id`, `name` | a concrete place: `this-mac`, `openrouter`, `ollama@studio.tailnet`, `hf-endpoint/<name>`, `hf-jobs`, `acenet-rorqual` |
| `kind` | `this-mac` · `endpoint` (answers one request at a time) · `batch` (takes a package, returns results later) |
| `serves` | how it names a card's weights: an MLX snapshot path, an OpenRouter or provider model id, an Ollama tag, an image + runner for batch |
| `egress` | worked out from the **address**, never the provider type: `stays` (this Mac: loopback or in-process), `own-machine` (an address on the person's LAN or tailnet, added by them), `company` (who, and where, from the catalogue), `cluster` (the institution's administrators) |
| `account` | `ready` · `needs-key` · `needs-credit` · `not-reachable`, from a real probe (`keys.test-connection-real-probe`) |
| `cost_model` | `free` · `per-token` (the one price list) · `per-hour` (the service's listed price) · `allocation` (hours of the person's allocation, $0 but stated) |
| `lane` | `this-mac` → `local-ml`; `endpoint` with `egress: stays` → `local-ml` (a server on this Mac holds memory); any other `endpoint` → `network`, with its share counted **per place**; `batch` → `remote` |
| `memory` | `this-mac` only: the model's resident size from the one memory table (2.5) |

The provider registry keeps describing **kinds of provider** (how to talk to them). Places are
rows the person adds (or this Mac, always present); a provider row with a Server URL **is** a
place. `is_local` stops being used to decide egress, lane or price.

### 2.3 How a card says where it is served

A card gains `served_as`: for each kind of place, the id that serves **the same weights**, and the
build (`bf16`, `4-bit MLX`, `Q4_K_M`). Same weights in another build is an *equivalent*, shown with
its build, and measured separately in the bake-off (quantisation moves CER). A different model is
never an equivalent. Discovery fills `served_as` from the Hub (its MLX conversions, and the
inference providers that serve the repo), from OpenRouter's model list, and from a reachable
Ollama's tags; a seed card may state it by hand.

### 2.4 How a choice is made

One engine function lists the **offers** for a step: every (card, place) where the place serves the
card. Each offer carries five facts, each with its basis (`measured` / `estimate` / `unknown`,
as `recipes/routes.py:25-26` already does):

1. **Fits**: the runtime is in this build and, on this Mac, the model's resident size fits
   (2.5); for a batch place, the card's hardware need is listed by the service.
2. **Allowed**: the one egress gate says yes for this project and this place's `egress` class.
3. **Account**: the place's account state.
4. **Cost for the volume**: per-token price × the project's pages × per-page tokens; per-hour
   price × hours (pages ÷ measured pages per hour, plus start-up); allocation hours for a cluster.
   One pricer for all three (`llm/usage.py` grows an hourly method). Unknown is `None`, never 0.
5. **Speed**: pages per hour **for this pair**, measured from finished rows of the same card at the
   same place; until measured, "unmeasured", never borrowed from another place.

Ranking keeps setup's order (`recipes/assemble.py:282-297`), applied to offers: hard filters
(fits, allowed, licence), accuracy band (the bake-off's measurement **for this pair**, else the
card's published one), this Mac before elsewhere, cost, speed, carbon. The bake-off scores any
offer whose place can answer (#5533), so "best" is measured on the project's own checked pages
wherever the model runs. An offer filtered out is **shown with why** (too big for this Mac's 8 GB;
pages may not leave; no OpenRouter key), never dropped.

### 2.5 Memory: one number per model, kept by the app

One table holds each card's **measured resident size** (falling back to a labelled estimate);
setup's rule, `runs_here`, the load gate and Start's peak all read it, so they cannot disagree. A
model server Fichero did not start but that runs on this Mac (Ollama, LM Studio) is measured by
asking it what it holds (`/api/ps` and its peers) and counts in the same sum. The rules of
"Models in memory" (`compute/jobs-and-fine-tuning.md`, #5537) apply to every `local-ml` place;
nothing new is asked of the person.

### 2.6 Running under the one job model

Every call, wherever it runs, is a row under its step (`activity.one-job-model`), on the lane its
place names (2.2). The row records the **place** beside the model (`model` today holds
`provider:model`; it becomes the card id and a `place` column), its usage priced by the one pricer
(tokens, or seconds for an hourly place), and, when pages left the Mac, where they went. A batch
place's job (Hugging Face Jobs, a cluster) is a `remote` row whose cost accrues by the hour into the
same run account. Retries follow **one table by error kind**: a transient network error or a 429 is
retried with backoff *outside* the lane slot; a passing local cause once (`page_retry`); a shard is
re-sent; a refusal (memory too small, no key, egress) is never retried, it is the page's reason.

### 2.7 Fallbacks

Decided **at Start**, shown on the Ready screen, never invented mid-run:

- A step may carry `alternatives`: other places for **the same card**, and only places the egress
  gate already allows. When the primary place fails for a reason of the place (server down,
  quota, memory refused, key missing), the page runs at the next alternative, the row says so
  (`collect_model_fallbacks`, `llm/__init__.py:292-406`, already records it), and the run account
  counts each place.
- A **different model** is used only if the person accepted a plan that named it as the step's
  alternative. No resolver picks one by itself (`workflows/builder.py:313-328` goes).
- A cost ceiling from the plan holds: an alternative that would cost more than the plan stated is
  not taken without asking.

This reconciles "the app manages fallbacks" with the 2026-09-07 ruling against fallback ladders;
Ruled 2026-10-08 (question 1): another place only when it is free, and only after asking the
person, never silently (`ai.where.fallback-free-and-asked`).

### 2.8 What the person sees

- **Ready** (`source/models-chains-and-projects.md` §7b): each step's row names the model and the
  place, with cost for the volume, time, "pages leave this Mac: to OpenRouter (US)" or "stays on
  this Mac", and the account state; the next-best offer beside it; an offer not taken because of
  memory or the project's rule says so.
- **Activity**: every call row and run row names its place; the run account sums cost per place
  (tokens and hours), peak memory on this Mac, and pages sent per place.
- **Settings, AI, "Where models run"**: the places, each with an honest state from a probe
  (`runtime.status-from-the-endpoint`, `compute.target.lives-in-ai-settings`), its egress class
  and its account; adding a server on another machine asks for its address and labels it "your
  machine".

## 3. Behaviours

### A. Places

- `ai.where.place-is-by-address` — **[OK]** (#5586) whether a place keeps pages on this
  Mac, which lane it uses and whether it is free are worked out from its address (loopback or
  in-process = this Mac; an address the person added as theirs = own machine; anything else = the
  company or cluster that runs it), never from the provider type. Built: one rule,
  `llm/places.py` (`place_of`: loopback, `::1`, `localhost` or a unix socket = this Mac; a model
  server type elsewhere = `own_machine`; a cloud type stays the provider's even behind a loopback
  proxy, which may forward), read by the local-only gate, the lane (`local-ml` vs `network`, in
  `model_call_slot` and a page read), the vision pool and pricing (a call off this Mac records its
  `place` and is unpriced, never $0); the providers route names each row's `place`. The project's
  own rule is slice 2 (`.one-egress-gate`); Settings showing it is `.settings-lists-places`.
  *Test:* `fichero-server/tests/unit/llm/test_where_models_run.py` (an `ollama` row at
  `http://10.0.0.5:11434` is refused under local-only, a run at an address off loopback takes the
  `network` lane and is unpriced, the route says `own_machine`).
- `ai.where.row-address-reaches-runs` — **[OK]** (#5587) a provider row's Server URL is
  the address every call to that row uses, in a workflow run as in chat and the model list. Built:
  one lookup (`llm/places.py` `row_server_url`/`with_row_address`) used by a node's resolved
  config (`workflows/builder.py` `_resolve_node_llm_config`), chat (`_chat_config`, which read the
  library database before), the model list (`provider_models._configured_api_base`) and the model
  factory (`get_langchain_model`, an Ollama/LM Studio root gaining its `/v1`). *Test:*
  `fichero-server/tests/unit/llm/test_where_models_run.py::test_a_run_reaches_the_row_server_url_off_this_mac`
  (a run with an `ollama` row whose URL is a stub server off loopback reaches the stub).
- `ai.where.one-list-of-places` — **[GAP]** (#5454, #5238) one engine list of places (this Mac,
  each endpoint row, Hugging Face Jobs, each cluster), each with kind, egress class, account state,
  cost model and lane (2.2); the four vocabularies of 1.4 (11) map onto it.
- `ai.where.hf-endpoint-is-a-place` — **[GAP]** (#5588) a dedicated Hugging Face Inference
  Endpoint can be added as a place (its URL, the one Hugging Face token, its hourly price and
  cold start shown), distinct from the shared Inference Providers router (`llm/__init__.py:4197`).
- `ai.where.place-status-is-probed` — **[BROKEN]** (#5367, #4303) a place's state in Settings is a
  probe's result; today the dot is `isLocalProvider || hasApiKey`
  (`ProvidersView+ProviderSettingsRow.swift:40`), so a stopped remote Ollama shows green.

### B. The pair

- `ai.where.step-names-a-pair` — **[PARTIAL]** (#5582) a recipe step names a card and a kind of
  place, and the project binds the kind to a concrete place. Built: the card pin and a `runs_on`
  string (`recipes/recipe.py:23-36`). Not built: the binding, and `endpoint`/`batch` kinds.
- `ai.where.runs-on-is-honoured` — **[BROKEN]** (#5589) a step runs where its place says or
  not at all, with the reason. Today nothing dispatches on `runs_on` (`recipes/start.py:129-163`);
  the place is inferred from the pin (`:69-82`), so `runs_on: cluster` runs on this Mac and
  `cloud:openrouter` with a Hub pin runs on the local MLX server. *Test:* each mismatch is refused
  by the recipe check with the step named.
- `ai.where.card-says-where-it-is-served` — **[GAP]** (#5582, #4948) a card lists, per kind of
  place, the id that serves the same weights and the build, filled by discovery (Hub conversions
  and inference providers, OpenRouter's list, a reachable Ollama's tags) or by hand on a seed card.
- `ai.where.equivalent-is-same-weights` — **[GAP]** (#5582) an "equivalent" offer is the same
  weights in another build, labelled with the build and measured on its own in the bake-off; a
  different model is never offered as an equivalent.

### C. Choosing

- `ai.where.offers-every-place` — **[GAP]** (#5582) for each step, the engine lists every offer
  (card × place) with fits, allowed, account, cost for the volume and speed, each with its basis.
  The Start plan, setup, MCP and the command line read the same list.
- `ai.where.never-dropped-silently` — **[BROKEN]** (#5582, #5519) a model this Mac cannot run is
  offered with the places that can run it, and an offer that is filtered out says why. Today
  discovery keeps only MLX builds and lists the rest outside the rules
  (`recipes/discovery.py:19-23,318-337`).
- `ai.where.rank-pairs` — **[PARTIAL]** (#5582) the rules rank offers, not cards: hard filters,
  accuracy for the pair, this Mac first, cost, speed. Built for cards
  (`recipes/assemble.py:282-311`).
- `ai.where.bakeoff-scores-any-place` — **[GAP]** (#5533) the bake-off scores an offer at any place
  that can answer, on the project's checked pages, at the place's own cost; today a remote
  candidate is "priced, not scored" (`recipes/bakeoff.py:101-102`).
- `ai.where.speed-per-pair` — **[PARTIAL]** (#5582) pages per hour are measured per card and place
  from finished rows; built per model on this Mac (`recipes/routes.py:29-34`); a cloud model's
  speed is never measured (`:63`).
- `ai.where.one-pricer-every-place` — **[PARTIAL]** (#5240, #5582) token and hourly prices go
  through one pricer. Built: tokens (`llm/usage.py:227-272`); Hugging Face's hourly price is read
  separately (`training/hf_jobs.py:115-121`); cluster allocation is not counted.
- `ai.where.estimate-names-the-place` — **[BROKEN]** (#5590) Start's estimate states each
  step's place and its cost basis; today every place that is not `cloud:` is priced at $0
  (`recipes/start.py:286-289`), a cluster step included.
- `ai.where.remote-audio-priced` — **[BROKEN]** (#5591) a transcription sent to a provider
  records its usage like any other call; today `audio_transcription` records none
  (`llm/__init__.py:2792-2833`), so its cost is unknown.
- `ai.where.account-on-the-offer` — **[GAP]** (#5582, #5369) each offer shows the account it needs
  and its state, read through the same key lookup a call uses.

### D. Egress

- `ai.where.one-egress-gate` — **[BROKEN]** (#4949, #5368) one gate decides whether pages may go to
  a place, from the project's rule and the place's egress class; the engine-wide switch, the
  start-time `cloud_allowed` check and the per-request `pages_may_leave` (1.3) become callers of
  it. Same rule as `source.egress.one-gate`, which owns it; this line owns that places, not
  providers, are what it judges.
- `ai.where.egress-at-every-call` — **[BROKEN]** (#5368) every model call meets the gate, from a
  workflow, chat, MCP or the command line; today `chat_with_tools` and `structured_output` skip
  it (`llm/__init__.py:3127-3173,3223-3255`) and workflow runs never read the project's rule.
- `ai.where.batch-sends-ask-the-project` — **[PARTIAL]** (#5239) a training or reading package is
  sent only when the project's rule allows that place; today a per-request `pages_may_leave`
  suffices (`training/job.py:90-92`, `remote_read/job.py:99-101`).
- `ai.where.no-first-provider-fallback` — **[OK]** (#5368) a node with no model refuses,
  naming what to set (the step, or the category default in Settings > AI > Defaults); it no longer
  takes the first enabled provider with a model, which may be a cloud one. *Test:*
  `fichero-server/tests/unit/llm/test_where_models_run.py::test_a_step_with_no_model_refuses_rather_than_take_the_first_provider`,
  `fichero-server/tests/unit/workflows/test_builder_llm_config.py`.

### E. One job model, wherever it runs

- `ai.where.lane-from-the-place` — **[PARTIAL]** (#5353, #5358) the lane is the place's: this Mac
  and model servers on it → `local-ml`; other endpoints → `network`, shared per place; batch →
  `remote`. Built: `local-ml` vs `network` by the place's address (`llm/places.py`, #5586). Not
  built: the `network` share per place (it is per provider) and the `remote` lane for batch.
- `ai.where.every-runtime-on-a-lane` — **[PARTIAL]** (#5353, #5370) every model call is a row on a
  lane; local Whisper (`workflows/tools/audio_base.py:128-168`) and Apple's bridge
  (`llm/__init__.py:1485-1488`) take none today.
- `ai.where.one-memory-number` — **[BROKEN]** (#5537) one measured resident size per model feeds
  setup's rule, `runs_here`, the load gate and Start's peak; today three rules read three numbers
  (`recipes/assemble.py:213`, `llm/local_model_choice.py:49-63`, `llm/local_inference.py:90-134`).
- `ai.where.local-servers-measured` — **[GAP]** (#5537) Ollama and LM Studio on this Mac are asked
  what they hold and count in the memory sum and the reads-at-once rule; today both are
  `omlx`-only (`llm/__init__.py:1392,4230`).
- `ai.where.one-retry-policy` — **[PARTIAL]** (#5353, #5555) one table by error kind decides
  retries; a transient error is retried outside the lane slot. Built: `page_retry` and stored
  jobs' attempts; LangChain's ten retries still run inside the slot (`llm/__init__.py:4568-4573`).
- `ai.where.one-cloud-cap` — **[PARTIAL]** (#5358) one cap on calls to a place, inside or outside a
  project; today the lane's 4 and a process semaphore of 12 (`llm/__init__.py:138,1504-1510`).
- `ai.where.row-names-the-place` — **[GAP]** (#5582) every call row and the run account name the
  place, and pages sent per place; today a row carries `provider:model` only (`llm/__init__.py:1499`).
- `ai.where.hourly-cost-in-the-account` — **[GAP]** (#5240) a batch place's hours, at its listed
  price, roll into the run's cost in Activity beside token costs; today the roll-up counts tokens
  only (`execution/jobs.py:421-426`).

### F. Fallbacks and memory, managed by the app

- `ai.where.fallback-free-and-asked` — **[OK]** (#5592; ruled 2026-10-08, question 1) a step may
  fall back to another place only when that place is free, and only after asking the person, never
  silently. Built at Start: a step whose model this Mac cannot run (its card says this Mac's memory
  cannot) is offered the same model at each free place in the plan's `elsewhere[].instead`
  (`free: true`, its `place` and provider), and Start stays refused until the person presses one
  (`POST /api/recipes/project/start/use-instead` with `provider`), which keeps it as a
  project-scope override said "chosen by you" (as `source.onboard.auto.installed-model-first`
  does). A place is one of the person's enabled provider rows off this Mac that lists the model by
  the same id; it is free only when the price list says its input and output cost 0
  (`llm/usage.py`). A paid place, or one the price list does not price, is never offered (the
  refusal names it and says why); a project that keeps its pages on this Mac is offered no other
  place. Built: `recipes/start.py` (`places_elsewhere`, `use_place_instead`). *Test:*
  `fichero-server/tests/unit/recipes/test_fallback_free_and_asked.py`.
- `ai.where.fallback-across-places` — **[GAP]** (#5592) when a step's place fails during a run
  for a reason of the place (server down, quota, key missing), its page runs at the step's next
  alternative place for the same card, only one the person accepted at Start and only a free one
  (`.fallback-free-and-asked`); the row and the run account say so. Not built: a run never moves
  a page by itself; only the Start offer above is.
- `ai.where.app-keeps-memory` — **[PARTIAL]** (#5537) a local model that does not fit now waits
  while the engine releases its own idle models; built for MLX and Kraken
  (`llm/local_inference.py:137-204`), not for other runtimes or local servers.

### G. What the person sees

- `ai.where.ready-shows-the-pair` — **[GAP]** (#5582) Ready names each step's model and place, cost,
  time, egress and account, and the next-best offer.
- `ai.where.activity-shows-the-place` — **[GAP]** (#5582) Activity's rows and run account show the
  place for every call and the cost per place.
- `ai.where.settings-lists-places` — **[GAP]** (#5454, #5367) Settings, AI, "Where models run" lists
  the places with probed state, egress class and account.

### H. Batch places

- `ai.where.batch-is-an-offer` — **[GAP]** (#5566, #5398) for a volume above a stated size,
  Hugging Face Jobs and a bound cluster appear as offers for read-at-scale, priced by the hour (or
  allocation) × measured pages per hour, under the same gate; built today only as separate routes
  (`remote_read/job.py:95-111`), and the cluster is described, not sent
  (`api/routes/ai/hpc.py:254-285`; `compute.job.live-submit`).

## 4. Build order (ranked slices; engine first; each builds, tests and commits alone)

1. **Places by address, and the address reaches the run** (`ai.where.place-is-by-address`,
   `.row-address-reaches-runs`, `.no-first-provider-fallback`). Smallest change with a privacy
   consequence: workflows carry the row's URL; egress, lane and "free" read the address. Pinned by
   a stub server off loopback.
2. **The one egress gate at every call** (`ai.where.one-egress-gate`, `.egress-at-every-call`,
   `.batch-sends-ask-the-project`; #4949, #5368, #5239). The project's rule is read at the call;
   `local_only_ai` and `pages_may_leave` become inputs to it.
3. **`runs_on` honoured** (`ai.where.runs-on-is-honoured`, `.estimate-names-the-place`): the
   recipe check refuses a pin and place that disagree; the estimate states each place's basis.
4. **One memory number** (`ai.where.one-memory-number`, `.local-servers-measured`; #5537).
5. **Offers** (`ai.where.card-says-where-it-is-served`, `.offers-every-place`, `.rank-pairs`,
   `.never-dropped-silently`, `.account-on-the-offer`; #5582, #5519): `served_as` on cards,
   discovery filling it, the offers list in the Start plan and MCP.
6. **The bake-off at any place** (`ai.where.bakeoff-scores-any-place`, `.speed-per-pair`; #5533).
7. **Ready and Activity show the pair** (`ai.where.ready-shows-the-pair`, `.activity-shows-the-place`,
   `.row-names-the-place`, `.one-pricer-every-place`, `.hourly-cost-in-the-account`,
   `.remote-audio-priced`).
8. **Batch places as offers** (`ai.where.batch-is-an-offer`; #5566, #5398), after the Slurm slices of
   `compute/remote-compute.md`.
9. **Fallback across places**: at Start, free and asked (`ai.where.fallback-free-and-asked`, built);
   during a run (`ai.where.fallback-across-places`), to an accepted free place only.
10. **The rest of the job model** (`ai.where.every-runtime-on-a-lane`, `.one-retry-policy`,
    `.one-cloud-cap`, `.lane-from-the-place`) and Settings' list (`ai.where.settings-lists-places`,
    `.place-status-is-probed`, `.one-list-of-places`, `.hf-endpoint-is-a-place`).

## Test matrix

| Leg | This surface? | Pins | File |
|-----|---------------|------|------|
| Backend (pytest) | y | place class from address; row URL reaches a run; gate at every model-factory caller; `runs_on` mismatch refused; offers list with bases; one memory number; hourly cost in the account | `fichero-server/tests/unit/llm/`, `tests/unit/recipes/`, `tests/unit/jobs/` (new `test_where_models_run.py`) |
| Pure rule (Swift) | y | a Ready row's text from an offer; a place row's dot from its probed state | `fichero/Tests/Unit/general/Views/Settings/`, the setup tests |
| MCP / CLI | y | the offers and the places come from the same routes as the app | `fichero-mcp/tests/test_mcp_server.py`, `fichero-cli/tests/` |
| Named-machine | y | an Ollama on the M1 Air over Tailscale: refused for a "keep pages here" project; allowed and on the `network` lane otherwise | manual checklist (`ssh air`) |
| Load (#4634) | y | 200 pages split across this Mac and an endpoint: the `local-ml` lane is never held by a network call | `fichero-server/tests/perf/` |
| iPhone / iPad | n | models run on the Mac's engine | — |

## Open questions (with recommendations)

1. **Fallback across places.** *Ruled 2026-10-08:* another place only when that place is free (no
   cost), and only after asking the person, never silently (`ai.where.fallback-free-and-asked`).
2. **Is a server on the person's own machine "leaving the Mac"?** *Recommend:* a third egress
   class, "your machine", which a project that keeps its pages here may allow separately (a lab
   machine on Tailscale is not a company in another country).
3. **Equivalents across builds.** *Recommend:* same weights in another quantisation is offered as
   an equivalent, labelled, and measured on its own; never ranked on the other build's score.
4. **Hugging Face: Inference Providers or dedicated Endpoints?** *Recommend:* both, as two kinds of
   place under the one token: providers by the token, endpoints by the hour with their cold start
   stated.
5. **Where does this spec's milestone live?** It is filed under `ai-settings` with
   `ai/local-runtimes.md`; if the maintainer prefers the `source-model` milestone (where #5582
   sits), the header changes and nothing else.

## Requests to other specs (for the manager to route)

- `source/models-chains-and-projects.md`: `source.find.model-and-where-it-runs` (#5582) points here
  for the design; the card gains `served_as`; `source.egress.one-gate` judges places, not
  providers.
- `ai/ai-settings.md`: "Where work runs" (`compute.target.lives-in-ai-settings`) and the provider
  rows become one "Where models run" list of places.
- `compute/jobs-and-fine-tuning.md`: `compute.job.choose-where` is this spec's offers list for batch
  places; `compute.job.costs-shown-where-known` rolls into `ai.where.hourly-cost-in-the-account`.
- `ui/activity-and-automatic-work.md`: a call row gains a `place`; the `network` lane's share is
  per place, not per provider type.
