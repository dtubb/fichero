# How a workflow node decides which provider to call — and why reading a preset cannot tell you (#4503)

Written after classifying 14 presets as "free" from their JSON, running them,
and discovering they billed a paid provider. The classification was not
careless — the answer simply is not in the file. This is where it actually
lives.

**Read from the code, nothing executed.**

## The one-line version

> A preset declares a **tier**. The app database decides the **provider**.
> Nothing in the preset file records, or can record, which one you will get.

## The chain, in precedence order

Two layers of resolution run in sequence. Most confusion comes from treating
them as one.

### Layer 1 — which (provider, model) pair does this node ask for?

`workflows/builder.py::_resolve_node_llm_config_inner`, whose own docstring
states the order:

| # | source | where it lives | visible in the preset? |
|---|---|---|---|
| 1 | node `provider_name` / `model_name` | preset JSON, `nodes[].config` | **yes** |
| 2 | workflow-level default | preset JSON, top-level `config` | **yes** |
| 3 | category default from app settings | **app database** | no |
| 4 | any enabled provider + model in the app DB | **app database** | no |

Steps 3 and 4 exist for a good reason (#704): a shipped preset whose LLM node
names no provider must still run on a fresh install. The cost is that a node
with no provider is not "unconfigured" — it is *configured elsewhere*.

A `model_profile_id` / `profile_id` / `model_profile` on the node short-circuits
into `resolve_model_profile_for_capability` before any of this.

### Layer 2 — if that pair is an alias, what does it resolve to?

`llm/__init__.py::resolve_model_alias` (wrapped by
`resolve_model_alias_for_capability`, which additionally validates capability):

| # | source | precedence | visible in the preset? |
|---|---|---|---|
| 1 | not an alias (no leading `$`) | returned unchanged | **yes** |
| 2 | `FICHERO_<TIER>_PROVIDER` **and** `_MODEL` env vars | **beats the database** | no |
| 3 | app DB `default_<tier>_provider` / `_model` | | no |
| 4 | neither set | **raises** `ValueError` — never silently defaults | n/a |

Note (2): **both** env vars must be set, or the pair is ignored and resolution
falls to the database. Setting only the provider looks like a pin and is not
one. This is the seam to use for a fail-closed test guard — pin both, then
assert the resolved provider before running anything.

Note (4) is good design and worth preserving: an unconfigured tier fails loudly
with "Set one in Settings → AI Defaults" rather than quietly picking something.

### Layer 0 — the factory table

`db/app.py::FACTORY_AI_DEFAULTS` seeds the database on first launch and is
fully on-device (`apple` / `apple-vision` / `apple-intelligence`) for every
tier since #4325, deliberately, so a keyless install can run every default
workflow. It is **not** a fallback consulted at resolution time: it only ever
writes rows into the app DB. Once a row exists, the factory value is out of the
picture — which is exactly how a machine ends up on a paid provider while the
code still reads `"apple"`.

## Why this bit us, precisely

The 39 shipped presets divide into two shapes:

- **A few name a tier**: `"provider_name": "$vision_small"`. Visible in the
  file, and still not an answer — a tier is a pointer into the database.
- **Most name nothing at all.** Every `transcribe` / `convert` / `describe` /
  `table_extract` node in the presets I checked has no provider, so it lands on
  layer-1 step 3 or 4 and takes whatever the app DB holds.

On this machine the app DB holds:

```
default_vision_provider  = openrouter
default_vision_model     = google/gemini-3-flash-preview
```

written 2026-07-31 10:39:05 — all six vision rows within the same second, so
programmatically, not tuned per tier. So presets that read as "on-device OCR"
in the file bill a cloud model on every run.

**Both a tool-name scan and a careful human read of the preset produce the same
wrong answer, because the answer was never in the file either of them read.**

## What is visible to whom

| question | answerable from the preset alone? |
|---|---|
| which tools does this preset run? | **yes** |
| does it call a model at all? | **yes** — from the tool set |
| which tier does it ask for? | sometimes — only if a node names one |
| **which provider will it actually call?** | **no** |
| **will it cost money?** | **no** |
| how many calls will it make? | no — depends on fan-out over files/tiles |

Only the first two are properties of the preset. Everything below the line is a
property of *preset + database + environment*, evaluated at run time.

This is the project's recurring defect in a new denomination: the declared
artifact says intent, another store decides reality, and nothing reconciles
them. Elsewhere that costs correctness. Here it costs money, and it costs it
silently — there is no point in the flow where the difference is surfaced
before the call is made.

## What would actually fix it (#4503)

Both of these already have all their inputs available; neither needs new state.

**1. A resolver that answers "what will this preset really call?"**
Walk each node through layers 1 and 2 exactly as the runner does, and return
per node: `(tool, tier_requested, provider_resolved, model_resolved,
source_of_truth)` where `source_of_truth` ∈ {node, workflow, env, app_db,
factory}. That last field is the one that matters — it is the difference
between "this preset is free" and "this preset is free *on your machine, for
this reason*".

It must reuse `_resolve_node_llm_config_inner` and `resolve_model_alias` rather
than reimplement the precedence. A second copy of this chain would drift, and a
resolver that disagrees with the runner is worse than none — it would be
authoritative-looking and wrong.

**2. A dry-run cost preview.**
Nodes × fan-out × tier, with the resolved provider named. This is what makes an
authorisation like "one gold page, ~8 calls" *enforceable* instead of
aspirational. Two concrete data points from tonight: that run was **12** calls,
not 8, because the review tiers also send images; and the preset that looked
free made ~25–40.

**3. Until (1) exists, the only safe validation protocol** is to pin every tier
by env (BOTH `_PROVIDER` and `_MODEL`), assert the resolved provider is
on-device, and abort before executing a single node if it is not. That is a
workaround, not a fix: it protects the test harness and does nothing for a user
clicking Run.

## For whoever picks this up

The precedence tables above are the whole specification; the two functions to
read are `_resolve_node_llm_config_inner` (builder.py) and `resolve_model_alias`
(llm/__init__.py). Between them they are about eighty lines.

The label work in #4501 is blocked on (1), and should stay blocked: removing
"(Untested)" from a preset whose cost depends on the reader's database means
the label is making a promise the file cannot keep. A validated preset needs to
say *validated under which configuration* — and that sentence is unwritable
until something can name the configuration.
