(AI generated. Not reviewed.)

# MLX On-Device Agent Architecture

> Status: design doc for #2066 / #1814 / #2067. No product code in this change.
> Date: 2026-06-13.
> Scope: backend-facing architecture for local MLX inference and an in-app agent surface that stays local-first, typed, audited, and implementation-ready.

## 1. Decision

Start with an **internal OpenAI-compatible local server adapter** path for MLX-backed inference, not a native in-process Swift or Python MLX integration.

Why this is the right first move in Fichero:

- The backend already supports **keyless OpenAI-compatible local providers** at the `llm.py` choke point (`ollama`, `lmstudio`, `omlx`).
- The provider catalog already models `omlx` as a local provider in `fichero.providers`.
- The current engine architecture expects HTTP-shaped provider boundaries and typed request/response models; extending that path is lower-risk than introducing a second native-only execution stack now.
- The Mac app integration work for a native in-process MLX runtime is a separate concern and should be deferred until Daniel and the Mac lane are ready to own lifecycle, UI, and sandbox details together.

Decision statement:

- **P1-P3 implementation target:** app-managed local inference service speaking an OpenAI-compatible API to the existing backend provider path.
- **Deferred:** native in-process MLX Swift integration, direct Foundation Models tool-calling integration, and any app-side model runtime embedded into SwiftUI.

## 2. Goals and Non-Goals

### Goals

- Keep local AI **good-and-cheap** by preferring on-device/local providers first.
- Enforce a real **no-cloud** perimeter for local-only profiles.
- Reuse existing Fichero seams: provider catalog, `llm.py`, model comparison routes, action registry, activity/change streams, and workflow SSE infrastructure.
- Define typed contracts first so backend implementation and later Mac integration do not improvise payload shapes.
- Make the future in-app agent audited and reversible, not a second hidden tool system.

### Non-Goals

- No SwiftUI or Mac app UI implementation in this issue.
- No real model downloads in tests.
- No test that re-embeds or reprocesses real user data.
- No hidden cloud fallback inside a local profile.
- No parallel unaudited tool system outside the action registry / workflow tool surfaces.

## 3. Trust and Privacy Boundary

Local-only must mean **no cloud fallback at runtime**. That rule is load-bearing, not a preference.

Rules:

- A provider profile marked local-only may target only built-in or local providers.
- If a requested local provider is unavailable, unhealthy, or out of memory, the run fails loudly unless the user explicitly chooses a separate paid/cloud profile.
- Any paid/cloud fallback must remain **explicit** and visible in the product, not silently activated by a local profile.
- Activity/audit logs must record the **effective profile, provider, and model** used for a run so a user can see whether a result came from local MLX, Apple on-device models, or a cloud provider.

Implications for implementation:

- The local-only perimeter belongs at the backend choke points, not only in UI affordances.
- The provider/profile resolver must reject cloud providers when `local_only=True`, even if other global defaults would normally fall back.
- Comparison/eval features may compare local and cloud models, but only when the user selects a profile that permits it.

## 4. Process Architecture

The app will manage a **local inference service lifecycle** and point the backend at it as an internal local provider.

### 4.1 Service topology

- The Mac app launches and supervises a local inference process on demand.
- The process exposes an OpenAI-compatible HTTP surface bound to loopback only.
- The backend treats that process as a local provider, analogous to the existing `omlx`/`ollama`/`lmstudio` path.

### 4.2 Lifecycle responsibilities

Required responsibilities for the service manager:

- Start service for a selected local profile if not already healthy.
- Bind to a loopback address and a deterministic or reserved port strategy.
- Perform health checks before first inference.
- Stop the service when the app exits or the profile is disabled.
- Restart after crash, with capped retry/backoff.
- Surface unhealthy/out-of-memory states to the caller instead of silently falling through to cloud.

### 4.3 Health and status

Health checks should answer:

- process reachable
- model loaded or loading
- configured model id
- warm/cold state
- memory pressure / last failure
- uptime / restart count

The service manager should separate:

- `starting`
- `healthy`
- `degraded`
- `failed`
- `stopped`

### 4.4 Model cache and download location

The architecture should reserve a local cache location under app-managed support data, with model artifacts treated as local machine state rather than library content.

Rules:

- Model blobs are not stored inside a Fichero library bundle.
- Profile metadata may reference a configured model id, but not assume the model is already present.
- Download/install is an explicit service-manager concern and remains out of scope for this doc’s implementation phase.

### 4.5 Memory pressure and crash handling

The local provider path must plan for GPU / unified-memory pressure:

- Fail fast on allocation/load failure with a typed error.
- Offer a stop-and-restart path that can unload the model.
- Track repeated crash loops and disable auto-restart after a threshold.
- Prefer one owned local-service process over ad hoc per-run spawning.

## 5. API Contracts

All new backend-facing shapes must be declared as typed Pydantic models and emitted through OpenAPI. Per repo rule: **every persisted or API-visible field must be declared on the Pydantic model**; `extra="allow"` is not enough because undeclared fields are dropped by `model_dump()`.

The exact route names can be chosen during implementation, but the data contracts should cover the following shapes.

### 5.1 Provider profile

`LocalProviderProfile`

- `id`
- `name`
- `provider_type`
- `model_id`
- `base_url`
- `local_only: bool`
- `allows_paid_fallbacks: bool`
- `managed_by_app: bool`
- `startup_policy`
- `healthcheck_path`
- `timeout_seconds`
- `max_concurrency`
- `visible_in_ui: bool`

Notes:

- `allows_paid_fallbacks` must be invalid or ignored when `local_only=True`.
- `provider_type` should extend the existing provider catalog rather than inventing a second enum.

### 5.2 Model catalog entry

`LocalModelCatalogEntry`

- `provider_type`
- `model_id`
- `display_name`
- `capabilities: list[str]`
- `installed: bool`
- `download_size_bytes | None`
- `disk_usage_bytes | None`
- `memory_class | None`
- `license_label | None`
- `source`

### 5.3 Inference request / result

`LocalInferenceRequest`

- `profile_id`
- `provider`
- `model`
- `messages`
- `system_prompt | None`
- `temperature | None`
- `max_tokens | None`
- `response_format | None`
- `tools: list[ToolSpec]`
- `stream: bool`
- `run_id | None`

`LocalInferenceResult`

- `provider`
- `model`
- `output_text`
- `structured_output | None`
- `tool_calls: list[ToolCallEnvelope]`
- `usage`
- `latency_ms`
- `fallback_used: bool`
- `fallback_provider | None`
- `local_only_enforced: bool`
- `activity_log_id | None`

### 5.4 Structured-output / tool-call envelope

`ToolCallEnvelope`

- `tool_name`
- `call_id`
- `arguments_json`
- `validation_error | None`
- `approved: bool | None`

`StructuredOutputEnvelope`

- `schema_name | None`
- `payload`
- `validation_error | None`
- `raw_text | None`

The important constraint is not the exact field names but the contract:

- tool calls and structured payloads are first-class typed fields
- schema validation failures are visible, not swallowed
- downstream code does not read from `additionalProperties`

### 5.5 Health / status response

`LocalInferenceServiceStatus`

- `profile_id`
- `provider_type`
- `state`
- `healthy`
- `base_url`
- `model_id | None`
- `pid | None`
- `started_at | None`
- `restart_count`
- `last_error | None`
- `memory_warning | None`

## 6. Agent Architecture

The in-app agent for #2067 should be built as a **manager-with-workers** system on top of the audited backend primitives already being established elsewhere in the repo.

See [Pi Agent Harness Architecture](./pi_agent_harness.md) for the #2071
decision that Pi supplies this agent loop/package harness. The local MLX service
and profile boundary described here remain underneath Pi; Pi does not replace
the local-only provider resolver, action registry, audit, or undo path.

### 6.1 Core shape

- One manager loop owns the user-facing run.
- The manager can create worker tasks for bounded subproblems.
- Workers operate only through approved workflow tools / action-registry-backed operations.
- The run emits progress over existing SSE-style event infrastructure.

### 6.2 Tool surface

Allowed tool surface:

- read-only workflow tools
- comparison/evaluation tools where appropriate
- audited write actions exposed through the action registry
- workflow execution primitives that already produce progress events and activity log entries

Disallowed:

- arbitrary unaudited shell/tool execution
- a second independent tool registry with different permissions semantics
- hidden writes that bypass action audit / undo hooks

### 6.3 Audit and undo

Every agent run should carry a `run_id` threaded into:

- action invocations
- activity log entries
- streamed progress events
- any persisted agent notes / memory rows

Write-capable tools must remain auditable and, where supported by the action layer, undoable. The design target is **run-scoped undo**: users can inspect which writes a run performed and reverse them through the same audited inverse path, not by best-effort cleanup.

### 6.4 Progress and events

The agent run should publish SSE-friendly events using the existing progress/change-stream patterns already present in workflow execution.

Minimum event kinds:

- run started
- planning
- worker queued
- worker running
- tool call requested
- tool call completed
- approval required
- write action executed
- write action undone
- run completed
- run failed

## 7. Evaluation Path

This issue does not claim quality results. It defines **how to measure them** with repo-grounded tools.

Evaluation should reuse:

- `/model-comparison/compare-vision`
- `/model-comparison/compare-workflow`
- the ICANH Spanish Script ground-truth corpus already used in repo evaluation discussions/tests

Baseline metrics to collect:

- task success rate
- structured-output validation success rate
- tool-call schema validation success rate
- latency per page / per task
- tokens or equivalent usage metadata where available
- crash / restart rate
- peak memory warnings
- local-only compliance: zero cloud calls when local-only profile is selected
- cost estimate for local vs permitted paid profiles

The evaluation document or follow-up issue should compare:

- existing local providers
- app-managed MLX local server path
- Apple on-device path where comparable
- explicit paid fallback path when permitted by profile

## 8. Implementation Phases

### P0. Docs and probes

- Land this architecture doc and pointer from `ai_infrastructure.md`.
- Add small probes/spikes to verify service-launch assumptions and loopback health checks.
- Confirm the current `omlx` provider path is the intended compatibility seam.

### P1. Backend local service manager + tests

- Add typed profile/service-status models.
- Add service-manager abstraction for app-owned local inference process lifecycle.
- Add local-only gating at provider/profile resolution.
- Add fake local-server tests and no-network leak tests.

### P2. Provider/profile UI with Daniel/Mac lane

- Mac-side provider/profile management.
- Visibility for selected profile/model in activity logs and later UI surfaces.
- Explicit fallback affordances only; no silent cloud escape hatch.

### P3. Agent loop

- Manager loop with bounded worker tasks.
- SSE progress/event stream.
- Action-registry-backed write tools and run-scoped audit/undo.

### P4. Distributed workers / multi-Mac

- Future work only after the single-machine audited model is stable.
- Must preserve the same typed contracts, audit semantics, and explicit trust boundary.

## 9. Risks and Open Questions

- Apple Foundation Models APIs may not yet expose the exact tool-calling/structured-output maturity the agent design wants.
- MLX server adapters may need production hardening for health, restart, and warm-model behavior.
- GPU / unified-memory pressure may make some models unusable on lower-end Macs.
- Model licensing and download size may constrain what can ship or auto-install.
- App sandbox and loopback/network permissions need explicit validation during Mac integration.
- Structured-output reliability may differ across local models, especially for tool-call JSON.
- Exact model download/update UX is deferred and should not block the backend contract work.

## 10. Test Plan

Required tests for implementation phases:

- unit tests for provider-profile resolution and local-only/no-cloud gating
- unit tests for `allows_paid_fallbacks` invariants on local-only profiles
- fake local-server tests for health, cold start, inference, timeout, and malformed response handling
- no-network leak tests proving a local-only profile never resolves to cloud providers
- Pydantic/OpenAPI contract tests for new request/response models
- structured-output and tool-call schema validation tests
- crash/restart tests for service-manager backoff and unhealthy-state reporting
- activity/audit tests that record effective provider/model/profile per run
- agent-run tests that prove write-capable tools flow through audited action paths

## 11. Recommended next issues

Implementation should split into small backend-first issues:

1. Add typed local-provider profile and service-status models.
2. Add local-service manager abstraction with fake-server tests.
3. Enforce local-only provider gating in the backend resolver path.
4. Record effective provider/model/profile in activity/audit logs.
5. Add agent-run event schema and run-scoped audit threading.

This keeps #2066/#1814/#2067 aligned with the existing Fichero architecture: one provider choke point, one audited write path, one event-stream pattern, and no silent cloud boundary violations.
