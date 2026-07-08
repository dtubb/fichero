(AI generated. Not reviewed.)

# Apple Skills vs AI Skills

> Status: design doc for #2059. No product code in this change.
> Date: 2026-06-14.
> Scope: how Fichero models, selects, audits, and falls back between Apple
> on-device capabilities and general AI capabilities without creating parallel
> tool systems or cloud leaks.

## Decision

Model Apple capabilities and general AI capabilities as implementations of the
same logical capability contract.

Fichero should not expose "Apple Skills" and "AI Skills" as competing product
concepts. The user-facing concept is a capability such as transcribe, summarize,
extract entities, classify script, translate, or run an action. Each capability
can have one or more implementations:

- Apple on-device implementation: Apple Vision, Foundation Models, App Intents,
  or other OS-provided local frameworks.
- Local AI implementation: app-managed MLX/oMLX, Ollama, LM Studio, or another
  loopback provider.
- Remote AI implementation: OpenAI, Anthropic, OpenRouter, DeepL, or other
  explicitly configured cloud provider.

Selection happens through profiles and policy. Fallback is allowed only when the
policy says it is allowed and the user can see what actually ran.

## Goals

- Prefer private, free, offline-capable implementations when they are good
  enough for the task.
- Keep the backend's local-only perimeter authoritative; UI affordances are not
  a security boundary.
- Reuse the existing action registry, workflow tools, provider catalog, audit
  log, and model-comparison infrastructure.
- Make fallback transparent: the effective provider/model/implementation must
  be recorded and explainable.
- Keep App Intents as a Mac/system integration layer, not a second backend action
  registry.

## Non-Goals

- No SwiftUI implementation in this design slice.
- No new App Intent definitions in this design slice.
- No hidden cloud fallback for failed Apple/local runs.
- No parallel "skill runner" outside workflows/actions.
- No real model download or real library reprocessing.

## Vocabulary

Logical capability:

The task Fichero is trying to perform, independent of implementation. Examples:
`transcribe_text_from_image`, `summarize_document`, `extract_entities`,
`translate_text`, `classify_script`, `run_action`.

Implementation:

A concrete way to satisfy a logical capability. Examples: `apple_vision_ocr`,
`apple_foundation_model`, `mlx_openai_compatible`, `openai_chat`,
`openrouter_vision`.

Profile:

A user or workflow-selected policy bundle that controls privacy, cost, quality,
fallback, and preferred implementation order.

Effective run:

The implementation that actually executed after availability checks and policy
resolution.

## Capability Contract

Each logical capability should be represented by a typed contract:

```text
CapabilityContract
- id
- input_schema
- output_schema
- required_capabilities
- supports_batch
- supports_streaming
- side_effects
- audit_level
```

Implementation metadata should be explicit:

```text
CapabilityImplementation
- id
- capability_id
- provider_type
- provider
- model_or_engine
- locality: builtin | local | cloud
- cost_class: free | metered | paid
- quality_tier: small | medium | large | specialist
- requires_network
- supports_batch
- supports_tools
- supports_structured_output
- availability_probe
```

This can be introduced incrementally by mapping existing provider/tool metadata
onto these fields rather than replacing the current registry.

## Selection Rules

Selection order is profile-driven, not hard-coded per feature.

Recommended default profile order:

1. Apple/builtin implementation when it satisfies the capability and quality
   threshold.
2. Local loopback/provider implementation when Apple is unavailable or too weak.
3. Remote/cloud implementation only when the selected profile permits cloud.

Local-only profile:

- May select only `locality in {builtin, local}`.
- Must fail loudly if Apple/local implementations are unavailable.
- Must not fall through to cloud, even if a cloud implementation is configured.

Good-and-cheap profile:

- Starts with Apple/local or `$vision_small` / `$small` equivalents.
- Escalates to stronger local/remote tiers only when the workflow explicitly
  asks for escalation or quality gates fail.
- Records each escalation in activity/audit metadata.

Best-quality profile:

- May start with a larger remote or specialist model if the user selected a
  cloud-permitting profile.
- Still obeys local-only and paid-fallback gates.

## Fallback Rules

Fallback must be typed, policy-checked, and visible.

Allowed fallback examples:

- Apple Vision OCR fails because the image is handwriting-heavy; profile permits
  local MLX; run local MLX vision.
- Local MLX service is not installed; profile permits cloud; ask or use the
  profile's explicit paid-fallback setting before remote execution.
- A small vision tier produces low confidence; workflow requests final
  reconciliation on `$vision_large`.

Disallowed fallback examples:

- Apple Foundation Model refuses content and the backend silently sends the same
  text to a paid remote LLM.
- Local-only profile falls through to OpenAI because no local model is loaded.
- App Intent failure bypasses backend policy by calling a remote provider
  directly from the app layer.

Fallback result metadata:

```text
effective_implementation_id
requested_profile_id
requested_provider
effective_provider
effective_model_or_engine
fallback_reason
fallback_chain
local_only
paid_fallback_allowed
```

## App Intents and Action Registry

App Intents are the Mac/system invocation surface. The action registry is the
backend authority for domain actions.

Rules:

- App Intents should call typed backend actions or workflow routes.
- Backend actions remain the auditable, undo-aware source of truth.
- If an App Intent uses Apple-local reasoning to fill parameters, the final
  mutation still goes through the action registry.
- App Intents must not write library state directly or bypass backend auth,
  validation, audit, undo, and change-stream behavior.

This keeps Siri/Shortcuts/App Intents useful without creating a second command
system that diverges from Fichero workflows and actions.

## Workflow Integration

Workflow nodes should continue to declare logical tools such as `transcribe`,
`transcribe_review`, `extract_all`, or `translate`.

Provider/profile resolution happens at preflight and execution:

- Resolve logical tool -> required capability.
- Resolve profile -> candidate implementation order.
- Apply local-only and paid-fallback gates.
- Resolve aliases such as `$small`, `$vision_small`, `$vision_large`.
- Emit an execution plan with estimated provider/model/cost/privacy.
- Execute through existing tool functions and model/provider choke points.

This matches the current direction from `workflow_multi_pass_engine.md`: aliases
are capability-scoped, and preflight reports effective execution instead of
hiding model choice.

## Comparison and Evaluation

The model-comparison system is the right place to decide whether Apple/local is
good enough for a corpus.

For a capability, comparison should report:

- quality score against ground truth or reviewer rubric
- cost estimate
- latency
- locality and privacy class
- fallback/escalation behavior
- batch throughput when available

For ICANH-style Spanish Script, this means Apple Vision can remain a cheap/local
candidate, but the profile may select a stronger vision LLM when handwriting
quality requires it.

## Typed Backend Shapes

Future API-visible shapes should be Pydantic models and OpenAPI-generated for
Swift. Do not use ad hoc dictionaries for persisted/API-visible fields.

Suggested shapes:

```text
CapabilityProfile
- id
- name
- local_only
- allow_paid_fallbacks
- preferred_implementations
- max_cost_per_run
- quality_target

CapabilityResolutionRequest
- capability_id
- profile_id
- inputs_summary
- workflow_node_id

CapabilityResolutionResult
- selected_implementation
- fallback_chain
- policy_decisions
- estimated_cost
- privacy_class

CapabilityRunAudit
- run_id
- capability_id
- implementation_id
- provider
- model_or_engine
- locality
- fallback_reason
- usage
```

## Implementation Sequence

1. Add a read-only capability registry view over existing providers/tools. No
   new runtime behavior.
2. Add profile-aware resolution/preflight for workflow/model-comparison paths.
3. Record effective implementation metadata in activity/audit records.
4. Let App Intents call backend actions/workflows through the existing typed
   action surfaces.
5. Only after that, add Mac UI for choosing profiles and displaying effective
   local/cloud status.

## Open Questions

- Which capabilities need Apple-specific quality thresholds before local/cloud
  escalation?
- Should profile selection live per workflow, per run, or per library default?
- How should Apple Foundation Model guardrail refusals be represented so they
  are useful but do not leak sensitive refused text to cloud?
- Which action-registry operations are safe enough for App Intent exposure
  without extra confirmation?

## Acceptance Mapping

#2059 asks how Apple skills and AI skills are modeled, selected, and fall back.

- Modeled: one logical capability contract with multiple implementation records.
- Selected: profile-driven resolution with locality, cost, quality, and
  capability constraints.
- Fallback: policy-checked fallback chain with explicit no-cloud and
  paid-fallback gates plus auditable effective-run metadata.
- App Intents: invocation layer over backend actions/workflows, not a second
  mutation system.
