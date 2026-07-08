(AI generated. Not reviewed.)

# Workflow Multi-Pass Engine Primitives

> Status: design doc for #2198. No engine code is implemented by this document.
> Scope: backend workflow architecture for reusable sub-workflows, vision-safe
> model aliases, multi-pass transcription, and cost/privacy reporting.

## Decision

Fichero should extend the existing workflow graph system, not create a second
orchestration layer.

Build three small primitives on top of the current `WorkflowDef` / `NodeDef` /
`EdgeDef` model:

1. A first-class `sub_workflow` node that runs another saved workflow/template
   behind a declared input/output contract.
2. Explicit capability-scoped vision aliases, starting with
   `$vision_small`, `$vision_medium`, and `$vision_large`.
3. A preflight planner that resolves aliases, checks privacy policy, estimates
   cost/activity, and reports the effective execution plan before a batch run.

The shipped Spanish Script multi-pass preset should keep working as-is. It can
later migrate to these primitives without changing its visible behavior.

## Current Constraints

The existing workflow engine already has the right extension points:

- `types.py` defines typed ports, nodes, edges, workflow defaults, and per-node
  provider/model override fields.
- `validation.py` validates port compatibility from the tool registry.
- `builder.py` resolves a node's effective LLM config before invoking a tool and
  already preserves visual graph wiring as runtime dataflow.
- `executor.py` streams progress with LangGraph subgraph namespaces, which can
  represent child workflow execution.
- `llm.py::resolve_model_alias` resolves `$small`, `$medium`, and `$large` from
  app settings/env, but those aliases are text-tier aliases and are unsafe for
  image-processing nodes.
- `app_db.get_default_model_for_category("vision")` supports one vision default,
  but not distinct cheap/strong vision tiers.

The Spanish Script preset currently uses three explicit vision nodes:

- draft transcription
- review against image plus reference hits
- final reconciliation that writes page content

All three intentionally omit `provider_name` so they fall back to the user's
vision default instead of forcing text aliases onto image nodes. That must remain
valid.

## Sub-Workflow Node Contract

Add a registry tool named `sub_workflow` with `category="workflow"` and
`uses_llm=False`. The child workflow's own nodes declare whether they use LLMs.

Node config:

```json
{
  "workflow_ref": "workflow-id-or-system-template-name",
  "workflow_version": "optional pinned version",
  "input_contract": [
    {"id": "files", "data_type": "files", "required": true},
    {"id": "context", "data_type": "text", "required": false}
  ],
  "output_contract": [
    {"id": "text", "data_type": "text", "required": true},
    {"id": "documents", "data_type": "array", "required": false}
  ],
  "output_mapping": {
    "text": "$.nodes.final.text",
    "documents": "$.nodes.reference-search.documents"
  },
  "max_depth": 4
}
```

Runtime behavior:

- The parent node exposes only the declared contract ports. Internal child node
  ids and outputs are private unless mapped through `output_mapping`.
- Parent inputs are resolved normally, then validated against `input_contract`
  before the child graph is built.
- The child graph receives a fresh child state with:
  - `task_id`: a child run id
  - `workflow_id`: the child workflow id
  - `parent_task_id`: parent run id
  - `parent_workflow_id`: parent workflow id
  - `parent_node_id`: the sub-workflow node id
  - `lineage_path`: ordered run/node path, for example
    `parent-run/sub-workflow-node/child-run`
- Child outputs are validated against `output_contract` after `output_mapping`
  is applied. Missing required outputs fail the sub-workflow node.
- The parent state receives a normal node output:

```json
{
  "text": "...",
  "documents": [],
  "_run": {
    "child_task_id": "...",
    "child_workflow_id": "...",
    "lineage_path": "..."
  }
}
```

Schema validation:

- Use the existing `DataType` port validation for graph edges.
- Add optional JSON Schema on contract entries for structured values:

```json
{"id": "claims", "data_type": "json", "schema": {"type": "object", "required": ["items"]}}
```

- Validate contracts at save/import time and again at execution preflight.
- Validation errors must be returned as typed workflow validation failures, not
  delayed until a model/tool call.

Activity and run lineage:

- Every activity/progress event emitted inside the child includes the child
  `task_id` plus `parent_task_id`, `parent_node_id`, and `lineage_path`.
- SSE consumers can render a collapsed parent node while preserving drill-down
  into child node events.
- The parent node starts when the child workflow starts and completes only after
  all required mapped outputs validate.

Cycle prevention:

- Build a workflow-reference graph during validation.
- Reject direct and transitive cycles, including template aliases:
  `A -> B -> A`, `A -> B -> C -> A`, and self-reference.
- Enforce `max_depth` at runtime as a second guard against stale persisted
  definitions or concurrent edits.
- Do not allow dynamic `workflow_ref` expressions in phase 1. References must be
  literal ids/template names so cycle checks are deterministic.

Error propagation:

- Child node errors keep their original child event and also fail the parent
  `sub_workflow` node.
- The parent output must include no partial success unless the sub-workflow node
  config explicitly sets `allow_partial=true` and the output contract marks which
  ports are optional.
- A privacy/cost preflight failure is a hard validation error before execution.
- A child execution failure should surface as:
  `Sub-workflow '<name>' failed at '<child node label>': <message>`.

## Vision-Tier Alias Contract

Add capability-scoped model aliases:

- `$vision_small`: cheap/fast vision pass, suitable for draft OCR/transcription.
- `$vision_medium`: review pass or moderate-quality image reasoning.
- `$vision_large`: strongest configured vision pass, suitable for final review
  when the user explicitly chooses it.

Settings/env resolution:

| Alias | App settings | Env override |
|---|---|---|
| `$vision_small` | `default_vision_small_provider`, `default_vision_small_model` | `FICHERO_VISION_SMALL_PROVIDER`, `FICHERO_VISION_SMALL_MODEL` |
| `$vision_medium` | `default_vision_medium_provider`, `default_vision_medium_model` | `FICHERO_VISION_MEDIUM_PROVIDER`, `FICHERO_VISION_MEDIUM_MODEL` |
| `$vision_large` | `default_vision_large_provider`, `default_vision_large_model` | `FICHERO_VISION_LARGE_PROVIDER`, `FICHERO_VISION_LARGE_MODEL` |

Resolver behavior:

- Resolve aliases through a new capability-aware resolver, for example
  `resolve_model_alias(provider, model, required_capability="vision")`.
- Existing `$small`, `$medium`, and `$large` remain text-tier aliases.
- If a node's tool category is `vision`, text-tier aliases are invalid. A vision
  node with `provider_name="$small"` must fail validation with an actionable
  message.
- If a text/LLM node uses `$vision_small`, validation must fail for the same
  reason.
- After alias resolution, the concrete provider/model must be checked against
  provider capability metadata. Vision nodes cannot run on text-only providers.
- The resolver must then apply the local-only/no-cloud policy at the model-access
  choke point. Aliases are not a policy bypass.

Fallback behavior:

- If `$vision_small` is unconfigured, fall back to the existing single
  `default_vision_provider/default_vision_model` only when the node did not
  explicitly request a tier alias.
- If a node explicitly requests `$vision_small`, missing configuration is an
  error. Explicit tier selection should never silently collapse to another tier.
- Paid/cloud fallback from a local vision alias is forbidden unless the selected
  run profile explicitly permits paid/cloud use and the preflight report shows
  the fallback path.

## Optional Thinking and Final Reconciliation

Fichero should not make hidden chain-of-thought a workflow primitive. The useful
primitive is explicit reconciliation.

Allowed shape:

- A draft node produces `text`.
- One or more review nodes produce corrected `text` and optional structured
  review metadata.
- A final reconciliation node consumes the draft/review outputs and, when needed,
  the original image/source material.

Optional config:

```json
{
  "reconciliation_role": "final",
  "thinking_mode": "low|medium|high",
  "publish_intermediate_rationale": false
}
```

Rules:

- `thinking_mode` is a provider hint only. It does not create a stored hidden
  reasoning artifact.
- Use it for final synthesis/reconciliation when the selected provider supports
  a reasoning knob and the user accepts the cost/privacy profile.
- Do not use it for raw OCR/transcription when the goal is faithful capture from
  the page. Extra invisible reasoning can hide hallucinated completions.
- Do not make `$thinking` a universal default tier. If a future alias is added,
  it should be a text/reasoning capability alias, not a vision alias, and must
  pass the same local-only and paid-fallback checks.

## Cost and Privacy Boundaries

Preflight is required before multi-pass batch execution.

The preflight planner should return:

- workflow id/name/version
- expanded sub-workflow tree
- effective provider/model per LLM/vision node after alias resolution
- local/cloud classification per node
- paid fallback paths, if allowed
- estimated input count and node invocation count
- estimated token/image/page usage where available
- estimated cost range, with unknowns called out
- expected activity/run lineage shape
- cache policy and whether cached nodes are expected

Local-only/no-cloud enforcement:

- Local-only is a backend policy, enforced in `llm.py` and any other model
  choke point used by workflow tools.
- A local-only run must reject concrete cloud providers and cloud-resolving
  aliases before execution.
- A local-only run must reject fallback chains that include paid/cloud providers.
- The activity log records the effective provider/model, alias source, local/cloud
  classification, and whether fallback was used.
- A failed local provider does not silently fall through to cloud. The run fails
  with a visible remediation message.

Paid fallback visibility:

- If paid fallback is enabled, the preflight report must list which nodes may
  use it, from which provider/model to which provider/model, and why.
- Batch execution should require explicit confirmation when the preflight
  includes any paid/cloud path or unknown cost.
- The Spanish Script preset remains safe by default because it uses vision
  defaults and the existing paid-fallback policy.

## Migration Path

Phase 1 must not modify the shipped Spanish Script preset.

Compatibility rules:

- Existing nodes with no `provider_name` continue to use category defaults.
- Existing `$small`, `$medium`, `$large` behavior for text tools is preserved.
- Existing presets that intentionally omit provider aliases on vision nodes keep
  running against `default_vision_provider/default_vision_model`.
- New validation may warn on text aliases attached to vision tools, but should
  only fail at import/save/run for definitions that actually contain the unsafe
  alias.

Later migration:

1. Add a new system template, for example `Transcribe Spanish Script Passes`,
   implemented as a reusable child workflow with declared ports:
   - inputs: `files`, `documents`, optional `context`, optional `metadata`
   - outputs: `text`, optional `documents`, optional `quality_warnings`
2. Create a parent preset that uses a `sub_workflow` node for the transcription
   passes and keeps `reference-search` either outside or inside the child based
   on whether the reference corpus should be reusable.
3. Optionally set:
   - draft node: `$vision_small`
   - review node: `$vision_medium`
   - final node: `$vision_large`
4. Keep the current preset installed for at least one release as the stable
   compatibility preset.

## Implementation Phases and Tests

### Phase 1: Validation and Alias Resolver

Implement:

- capability-aware alias resolver
- app/env settings for vision tiers
- validation that rejects text aliases on vision nodes and vision aliases on text
  nodes
- provider capability checks after alias resolution
- local-only/no-cloud policy checks after alias resolution

Tests:

- unit: `$vision_small` resolves from env and app settings.
- unit: `$small` on a `category="vision"` tool fails validation.
- unit: `$vision_small` on a `category="llm"` tool fails validation.
- unit: a resolved text-only provider cannot satisfy a vision node.
- structural: aliases cannot bypass local-only/no-cloud policy. Configure
  `$vision_large` to a cloud provider, enable local-only, and assert preflight
  and execution both reject before any model call.
- regression: existing Spanish Script preset still has no hard-coded provider
  alias on its vision nodes and still validates.

### Phase 2: Preflight Plan and Cost/Activity Report

Implement:

- dry-run expansion of workflow plus sub-workflow references
- effective provider/model table per LLM/vision node
- node invocation counts for batch/page fan-out
- cost estimate plumbing using existing pricing helpers where possible
- activity lineage preview

Tests:

- unit: preflight expands aliases without invoking providers.
- unit: preflight reports cloud/paid fallback paths.
- unit: local-only preflight rejects a cloud alias.
- unit: batch node counts reflect fan-out count times pass count.
- contract: API response declares every preflight field in Pydantic/OpenAPI.

### Phase 3: Sub-Workflow Node

Implement:

- `sub_workflow` tool definition and typed config model
- save/import validation for contract shape
- child workflow loading by id/template name
- deterministic cycle detection
- child graph execution with lineage fields and LangGraph namespace propagation
- output mapping and output contract validation

Tests:

- unit: parent sees only declared child outputs.
- unit: missing required child output fails the sub-workflow node.
- unit: invalid parent input type fails before child execution.
- unit: direct and transitive workflow-reference cycles are rejected.
- unit: child node error propagates to parent node failure with child context.
- integration: parent workflow can run a small child workflow with mocked tools,
  no model calls.
- event: child progress events include parent and child lineage ids.

### Phase 4: Spanish Script v2 Template

Implement:

- new reusable child template for draft/review/final transcription passes
- parent template demonstrating `sub_workflow` composition
- optional use of `$vision_small`, `$vision_medium`, `$vision_large` only after
  Phase 1 policy tests pass

Tests:

- preset structural tests for declared contracts and edges.
- regression tests that old Spanish Script preset remains installed and valid.
- preflight test showing draft -> review -> final with distinct configured
  vision tiers when the user configures them.

## Deferred Follow-Up Issues

Separate issues should cover:

- UI for configuring `$vision_small`, `$vision_medium`, and `$vision_large`.
- UI for rendering sub-workflow nodes with expandable child-run activity.
- API route shape for workflow preflight if it needs a new endpoint.
- Global local-only/no-cloud perimeter if not already implemented before this
  work starts.
- Provider capability metadata hardening for every provider/model pair.
- Batch provider calls or LangChain `.abatch()` optimization. This design counts
  calls and reports cost, but does not make batching faster.
- Native MLX model lifecycle and downloads. The workflow contract should work
  with local OpenAI-compatible providers first.
- Any Mac/SwiftUI workflow canvas changes.

## Non-Goals

- No model calls during tests for these primitives.
- No cloud calls during tests.
- No real user data reprocessing.
- No replacement of the workflow engine.
- No changes to Mac/SwiftUI in #2198.
