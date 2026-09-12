(AI generated. Not reviewed.)

# Pi Agent Harness Architecture

> Status: design doc for #2071. No runtime implementation in this change.
> Date: 2026-06-14.
> Scope: how Fichero adopts Pi (`pi.dev`) as the in-app agent harness while
> preserving the existing local-model, action-registry, audit, ACL, and undo
> architecture.

## Decision

Adopt **Pi as Fichero's in-app agent loop harness**, hosted behind Fichero's
backend contracts and local-model policy.

Pi should sit between the selected model profile and Fichero's audited tool
surface:

```text
Fichero app
  -> Fichero backend agent-run API
  -> local provider profile / app-managed MLX-oMLX service
  -> Pi runner process
  -> Fichero Pi packages
  -> action-registry-backed tools
```

The important boundary is not "Pi can call tools." The important boundary is
that **Pi can only mutate a library through the same action registry used by the
UI, CLI, workflows, App Intents, tests, audit log, ACL checks, and undo path**.

## Source Facts and Constraints

The manager-verified Pi read for this issue:

- Pi is a minimal terminal coding harness.
- Pi supports TypeScript extensions, skills, prompt templates, themes, packages,
  custom models/providers, programmatic SDK, RPC, and JSON event stream modes.
- Pi intentionally omits sub-agents and plan mode so users or packages can add
  those in the shape they want.
- OpenClaw is the reference real-world SDK integration.
- OpenClaw's docs emphasize runtime boundaries and plugin SDK boundaries.

Fichero's already-shipped constraints:

- #2058: dynamic model profiles and provider selection exist.
- #1814 / #2199: local inference profiles, typed local-inference contracts, and
  an app-managed local-service manager exist for local MLX/oMLX-style providers.
- #1848: `ActionRegistry` is the single audited write path.
- #2015: registry-driven undo exists for undoable action audits.
- #2022 / #2023 / #2024: accounts, actor attribution, and ACL checks are part
  of the write boundary.
- #2074: grouped undo is the right follow-up for agent-run-level reversal.

## Goals

- Run the in-app agent on the selected local model profile by default.
- Keep local-only / no-cloud enforcement in the backend, not in the UI or prompt.
- Let Pi provide the loop, package, skill, prompt-template, event-stream, and
  extension machinery.
- Expose Fichero domain tools through Pi packages generated from typed backend
  contracts.
- Make manager-with-workers and plan mode Fichero-owned Pi extensions.
- Stream agent sessions, plan state, worker activity, model calls, and tool calls
  into the app through backend event contracts.
- Treat agents as accountable principals, not anonymous background code.
- Make agent writes auditable, ACL-checked, and undoable by construction.

## Non-Goals

- No Mac/SwiftUI implementation in this design slice.
- No direct runtime Pi integration in this design slice.
- No cloud-provider enablement.
- No second mutation registry, filesystem-write API, shell bridge, or hidden
  local bypass for Pi.
- No replacement of the existing `llm.py`, local-inference, workflow, action,
  auth, or change-stream primitives.

## Embedding Choice: RPC Boundary, SDK Inside the Runner

Use **Pi RPC / JSON event stream as Fichero's embedding boundary**.

Use the **Pi SDK inside a small TypeScript Pi runner/package layer**, not as a
library imported directly into the Python backend.

Rationale:

- Fichero's backend is Python/FastAPI with typed Pydantic/OpenAPI contracts.
- Pi's extension/package ecosystem is TypeScript-native.
- RPC keeps the Python backend and Pi runtime as separate failure domains.
- JSON event streaming matches Fichero's existing SSE/change-stream direction.
- The SDK remains useful where it belongs: inside the Pi runner and Fichero Pi
  packages that adapt Pi extension APIs to backend HTTP/action contracts.

Concretely:

- The backend owns `AgentRun` creation, profile resolution, ACL context, and
  event persistence/stream fan-out.
- The backend launches or connects to a Pi runner process with a resolved local
  model endpoint and a Fichero package manifest.
- The Pi runner uses Pi's SDK/package APIs to run the loop and emit structured
  events.
- Fichero consumes the Pi event stream and republishes app-facing typed events.
- Tool calls from Pi go back through backend action/tool endpoints, never
  directly to DuckDB, LanceDB, or library files.

## Model and Privacy Boundary

The selected Fichero model profile is the authority. Pi must not independently
decide to use a cloud model when the run is local-only.

Run startup order:

1. Resolve the requested model profile through Fichero's existing provider
   profile machinery.
2. If the profile is local-managed, ensure the local MLX/oMLX service is
   healthy through the local-inference service manager.
3. Reject startup if `local_only=True` and the resolved provider is not
   builtin/local/loopback.
4. Pass Pi only the effective model endpoint and credentials allowed by the
   profile.
5. Record the effective provider, model, profile id, local-only flag, and
   fallback policy in agent-run metadata.

Rules:

- A local-only Pi run fails loudly if the local service is unavailable.
- Pi packages must not carry their own cloud API keys.
- Remote model providers are allowed only in an explicitly cloud-permitting
  profile selected by the user.
- Paid fallback remains profile-gated and visible. It is never a package-level
  convenience fallback.
- Package install/update operations are not runtime model-provider authority.

## Fichero Pi Packages

Fichero should ship Pi packages in narrow layers:

| Package | Responsibility | Boundary |
|---|---|---|
| `fichero-tools` | Read tools and action-registry-backed write tools | Calls backend typed endpoints only |
| `fichero-skills` | Domain skills for research, transcription, extraction, curation, reconciliation | Prompts/workflows; no direct mutation |
| `fichero-planner` | Plan mode, task decomposition, approval checkpoints | Emits plan events; delegates writes to tools |
| `fichero-workers` | Manager-with-workers orchestration | Bounded worker sessions; inherits run policy |
| `fichero-themes` | Optional Pi terminal/app presentation themes | No tool authority |

Package rules:

- Packages declare capabilities they need: read, write, network, model, worker,
  package-install.
- Write-capable package tools are generated from the backend action registry or
  hand-authored as thin wrappers over registered actions.
- Read tools may use typed backend read endpoints and search/KG APIs.
- Packages do not get raw filesystem access to library package contents.
- Packages do not get database handles.
- Packages do not get unrestricted shell execution.
- Package version, checksum/source, enabled state, and requested capabilities
  should be persisted so an agent run is reproducible and auditable.

## Tool Surface: Action Registry Only for Mutation

Pi's tool list should be derived from Fichero's backend tool authority:

- Read-only tools: search, KG lookup, document/page read, model-comparison
  summaries, workflow status, and safe metadata inspection.
- Write tools: only `ActionRegistry` actions exposed through typed schemas.
- Workflow tools: allowed when they already enforce model/profile policy and
  emit activity/progress events.

Write call flow:

```text
Pi tool call
  -> Fichero Pi tool wrapper
  -> backend action invoke route
  -> ActionRegistry.invoke(...)
  -> authz / ACL checks
  -> domain action
  -> ActionAudit row with actor + run_id
  -> change-stream event
  -> optional undo path
```

Disallowed:

- Direct DuckDB/LanceDB writes from Pi packages.
- Direct file mutation in `.fichero` libraries.
- A Pi-local "actions" registry with different permissions semantics.
- Tool arguments hidden in `additionalProperties` instead of declared schemas.
- Best-effort audit on successful mutation. If audit fails, the action fails.

## Plan Mode and Manager-Worker Mode

Pi intentionally omits plan mode and sub-agents. Fichero should add them as Pi
packages/extensions so the behavior matches Fichero's manager/worker operating
model instead of importing a generic agent hierarchy.

Plan mode package:

- Builds a typed plan with steps, required tools, risk flags, and approval
  checkpoints.
- Emits plan events before execution.
- Can be paused, revised, approved, rejected, or converted into worker tasks.
- Must perform privacy/cost preflight before any model/tool execution that could
  leave the machine or mutate the library.

Manager-worker package:

- One manager owns the user-facing run and event stream.
- Workers inherit the manager's model profile, local-only policy, package
  allowlist, actor context, ACL scope, and run id.
- Workers can be restricted by tool subset, document scope, and budget.
- Workers cannot escalate model locality, install packages, or widen ACL scope.
- Worker outputs return to the manager as events/artifacts before any write is
  executed.

This maps the current session-start-manager/worker discipline into the app:
planning and delegation are product features, but mutation remains a backend
action.

## Event and Session Streaming

Fichero should normalize Pi events into backend-owned agent events before the app
renders them.

Minimum event kinds:

- `agent.run.started`
- `agent.plan.proposed`
- `agent.plan.updated`
- `agent.worker.queued`
- `agent.worker.started`
- `agent.model.requested`
- `agent.model.completed`
- `agent.tool.requested`
- `agent.tool.validated`
- `agent.action.executed`
- `agent.approval.required`
- `agent.package.loaded`
- `agent.package.rejected`
- `agent.undo.group.created`
- `agent.run.completed`
- `agent.run.failed`

Each event should carry:

- `run_id`
- `session_id`
- `parent_run_id | None`
- `worker_id | None`
- `actor_id`
- `profile_id`
- `provider`
- `model`
- `local_only`
- `package_id | None`
- `tool_name | None`
- `action_audit_id | None`
- `undo_group_id | None`
- redacted payload / summary

The app should subscribe to the backend event stream, not directly to a Pi
process. That lets Fichero persist, redact, replay, and authorize event data
consistently.

## Agents as Principals

Agent runs must be accountable identities at the action boundary.

Recommended model:

- The authenticated human user remains the owner/on-behalf-of principal.
- Each agent run gets an `agent:<run_id>` principal derived from that user.
- Each worker gets an `agent:<run_id>:worker:<worker_id>` actor id.
- `ActionContext.actor` records the effective agent actor.
- Audit metadata records the human initiator, agent actor, role, profile, model,
  package versions, and run id.
- ACL checks use the effective actor plus the user's delegated scope. Agents do
  not bypass `authz.assert_can_write`.

This keeps actor attribution transparent: a user can distinguish "Daniel edited
this" from "agent run 123 worker 2 edited this on Daniel's behalf."

## Grouped Undo Implications

Current registry-driven undo is per action audit. Agent runs need a grouped
layer on top, not a replacement.

Target behavior:

- Every write action inside a Pi run stores `run_id`.
- A grouped undo record orders the action audit ids created by the run.
- "Undo run" applies inverse actions in reverse order through the existing undo
  endpoint/path.
- Partial failure leaves a visible grouped-undo state, not silent cleanup.
- A user can still inspect and undo individual actions when that is safer than
  undoing the full run.

Design implication for #2074:

- Add `undo_group_id` or equivalent grouping metadata before large agent-write
  surfaces ship.
- Grouping should be run-scoped and optionally phase-scoped: plan, worker,
  final-apply.
- Grouped undo must preserve the per-action audit chain and redo semantics from
  #2015.

## OpenClaw Reference Lessons

Use OpenClaw as an integration reference, but do not clone its product shape.
The lessons to carry over:

- Keep the host application boundary explicit.
- Put plugin/SDK capabilities behind declared interfaces.
- Treat runtime process boundaries as safety boundaries.
- Stream activity as structured events, not terminal text scraping.
- Keep package/plugin authority narrower than application authority.

For Fichero this means Pi is a harness under Fichero's policy, not the policy
engine. The backend remains the authority for model profile, local-only mode,
actions, ACL, audit, and undo.

## Staged Backend Implementation Slices

### P0. Architecture and contracts

- Land this document and architecture links.
- Define `AgentRun`, `AgentSession`, `AgentEvent`, `AgentPrincipal`, and
  `AgentPackageRef` Pydantic shapes.
- Define allowed event kinds and redaction rules.
- Decide the persisted location for agent-run metadata versus ephemeral stream
  buffers.

### P1. Pi runner process boundary

- Add a backend `PiRunner` abstraction with fake runner tests.
- Launch/connect to a local Pi runner process via RPC/JSON event stream.
- Pass only backend-resolved model endpoint/profile metadata to the runner.
- Refuse startup when local-only/profile invariants fail.
- Normalize runner events into Fichero `AgentEvent` records.

### P2. Fichero tools package

- Generate or hand-author the first `fichero-tools` package from a small
  allowlist of action-registry actions plus read-only tools.
- Validate tool arguments against declared Pydantic/OpenAPI schemas.
- Thread `ActionContext(actor, run_id, origin_window, library_path)` through
  every write tool.
- Test that attempted direct mutation and unknown tools are rejected.

### P3. Session streaming and audit UI contract

- Persist agent-run events enough for replay/inspection.
- Stream normalized events to the app-facing endpoint.
- Include model/provider/profile/package/action audit metadata in events.
- Add redaction tests for prompt/tool payload fields that may contain user data.

### P4. Plan and manager-worker packages

- Implement plan mode as a Fichero Pi package with typed plan events.
- Implement manager-with-workers as a Fichero Pi package.
- Enforce inherited policy for workers.
- Add tests for worker scope, budget, model-profile inheritance, and forbidden
  policy escalation.

### P5. Grouped undo and agent principals

- Add grouped undo metadata for run-scoped action audits.
- Add explicit agent principal records or derivation helpers.
- Prove ACL checks still run for agent actions.
- Prove "undo run" reuses the existing audited undo path in reverse order.

### P6. Package lifecycle hardening

- Persist package source/version/checksum/capabilities.
- Add package allowlist and capability approval.
- Add package reload/update behavior that cannot silently widen authority for an
  already-running agent session.

## Test Plan for Runtime Follow-Ups

- Unit tests for model-profile/local-only enforcement before Pi startup.
- Fake Pi runner tests for start, event stream, malformed event, crash, and
  timeout handling.
- Contract tests for `AgentRun` / `AgentEvent` Pydantic models and OpenAPI
  schema generation.
- Action tool tests proving writes go through `ActionRegistry.invoke`.
- Authz tests proving agent actors cannot write outside delegated scope.
- Actor attribution tests proving audit rows store agent actor and human
  initiator metadata.
- Grouped undo tests across multiple action domains.
- No-network tests proving local-only Pi runs cannot resolve cloud providers or
  package-supplied cloud keys.
- Package capability tests for read-only, write, worker, package-install, and
  network permissions.

## Open Questions

- Exact Pi runner installation location and packaging mechanism for the Mac app.
- Whether package install/update should be app-managed only or exposed to
  advanced users inside Fichero.
- How much of existing LangGraph-based workflow agent tooling should be retired,
  wrapped, or kept as workflow-only once Pi is the app agent harness.
- Event retention policy for large agent runs that may emit many model/tool
  events.
- Whether package capability approval is global, per-library, or per-run.

## Decision Summary

Pi becomes the loop and package harness. Fichero remains the authority.

The safe architecture is:

- backend-resolved local model profile
- RPC/JSON boundary to a Pi runner
- Pi SDK inside Fichero Pi packages
- action registry as the only mutation tool surface
- backend-normalized event streaming
- agent actors with ACL and audit context
- grouped undo layered over existing per-action undo

This gives Fichero Pi's customization model without weakening the existing
local-only, typed-contract, audit, and undo commitments.
