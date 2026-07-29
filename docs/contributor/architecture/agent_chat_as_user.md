(AI generated. Not reviewed.)

# Agent Chat As User

**Status:** PLANNED design doc. This page describes a target architecture, grounded in the code that exists on `main` today. It does **not** mean the full agent-chat model is already shipped.

## Decision

Treat the AI model as a **real Fichero user account** with a normal role and a normal audit trail, not as a hidden backend superuser.

In the target design, chat can do anything the app can do, but only by going through the same surfaced tools, role checks, and audited mutation path that human users already use. The key product property is attribution: every mutation has an actor, and that actor is a real user or model-user identity.

## What exists today

### 1. Accounts, sessions, and roles already exist

- App-wide user accounts already exist as `AccountUser` rows with `id`, `username`, `display_name`, `is_owner`, and `active` in `fichero-server/src/fichero_server/models.py:1001-1013`.
- App-wide sessions already exist as `AccountSession` rows in `fichero-server/src/fichero_server/models.py:1015-1027`.
- Per-library roles already exist as `LibraryRole` rows in `fichero-server/src/fichero_server/models.py:1045-1055`.
- Per-target ACL overrides already exist as `LibraryAclOverride` rows in `fichero-server/src/fichero_server/models.py:1058-1069`.
- The shipped role vocabulary is `owner`, `editor`, and `viewer` in `fichero-server/src/fichero_server/authz.py:23-30`, and the macOS UI surfaces the same three roles in `fichero/fichero/Views/Settings/Sharing/UsersSettingsView.swift:343-385`.
- Account/session routes already exist behind multi-user mode: login/logout/me in `fichero-server/src/fichero_server/api/routes/auth_accounts.py:243-300`, create/list/update users in `fichero-server/src/fichero_server/api/routes/auth_accounts.py:303-380`.

### 2. The audited mutation choke point already exists

- `ActionRegistry.invoke(...)` is already the central audited write path in `fichero-server/src/fichero_server/actions/registry.py:156-210`.
- That method already:
  - validates typed params (`registry.py:175-176`)
  - runs authz write checks (`registry.py:178-185`)
  - executes the domain action (`registry.py:186`)
  - writes an `ActionAudit` row (`registry.py:188-200`)
  - emits a change event (`registry.py:202-236`)
- The action context already carries `actor`, `run_id`, `origin_window`, and `library_path` in `fichero-server/src/fichero_server/actions/registry.py:39-52`.
- Generic HTTP access to the same registry already exists:
  - `POST /api/actions/invoke` in `fichero-server/src/fichero_server/api/routes/actions_registry.py:103-124`
  - `GET /api/actions/registry` in `fichero-server/src/fichero_server/api/routes/actions_registry.py:127-143`
  - `GET /api/actions/audit` in `fichero-server/src/fichero_server/api/routes/actions_registry.py:164-191`

This is the core foundation for "the model is a user": if the model acts through `registry.invoke(...)`, the actor is explicit and the write is auditable.

### 3. Chat-tool plumbing exists, but the live chat route is not agentic yet

- `fichero-server/src/fichero_server/actions/chat_tools.py:1-31` already defines the intended chat-tool bridge from registered actions to model-callable tools.
- `action_tools(...)` generates one tool definition per registered action in `fichero-server/src/fichero_server/actions/chat_tools.py:91-123`.
- `dispatch_tool_call(...)` already routes a model tool call back through `registry.invoke(...)` in `fichero-server/src/fichero_server/actions/chat_tools.py:153-194`.
- The module is explicit that the live chat endpoint is **not** yet wired to that loop in `fichero-server/src/fichero_server/actions/chat_tools.py:25-30` and `197-224`.
- The shipped `POST /api/chat` handler is still single-shot RAG: it retrieves context and then calls `llm.invoke(messages)` directly in `fichero-server/src/fichero_server/api/routes/chat.py:356-415`.

So the audit/tool foundation exists, but "chat can act" is still a planned wiring step, not a shipped chat behavior.

### 4. An MCP surface already exists

- Fichero already ships an MCP server in `fichero-server/src/fichero_server/mcp_server.py:1-29`.
- That server exposes CLI-backed tools through FastMCP in `fichero-server/src/fichero_server/mcp_server.py:37-73` and throughout the rest of the file.
- The MCP server is intentionally a thin wrapper over `FicheroClient`, not a second backend logic layer, in `fichero-server/src/fichero_server/mcp_server.py:1-8` and `53-64`.
- App-managed MCP server configuration already exists as `MCPServer` rows in `fichero-server/src/fichero_server/models.py:1251-1284`.
- The backend already exposes MCP server management routes in `fichero-server/src/fichero_server/api/routes/mcp_servers.py:22-257`.
- Those routes already require authentication globally and require owner access for loading tools into the workflow registry in `fichero-server/src/fichero_server/api/routes/mcp_servers.py:22` and `221-258`.
- Workflow-facing MCP tool loading already exists in `fichero-server/src/fichero_server/workflows/tools/mcp.py:24-50` and `110-183`.

### 5. Important current limitation: MCP write paths are not uniformly audited yet

- The target design here wants all model writes to flow through `registry.invoke(...)`.
- Some MCP-adjacent mutation paths already fit that direction via the action registry and `chat_tools.py`.
- But the dedicated MCP REST adapter routes in `fichero-server/src/fichero_server/api/routes/mcp_tools.py` still perform direct persistence for at least some writes, for example entity upsert via `db.save(existing)` / `db.save(entity)` in `mcp_tools.py:215-259`.

That means the repo already has the pieces needed for audited model-user writes, but the MCP surface is not yet fully normalized onto the action registry.

## Target model

### Model identity

Each model instance or configured agent persona should get a real `AccountUser` identity, stored in the same app-wide user table already used for humans (`models.py:1001-1013`).

Planned behavior:

- A model-user gets a normal Fichero account row.
- That account gets a normal library role row (`owner` / `editor` / `viewer`) using the existing role system in `authz.py:23-30` and `models.py:1045-1055`.
- The model's requests run under a normal session or equivalent authenticated principal, reusing the existing session/account machinery in `auth_accounts.py:243-300`.
- Mutations executed on behalf of that model-user set `ActionContext.actor` to that model-user identity, so the resulting `ActionAudit.actor` is attributable to that model.

This keeps "which model did this?" and "which user did this?" in the same identity system instead of inventing a parallel actor namespace.

### Tool execution path

Planned write path:

```text
chat turn
  -> model emits tool call
  -> tool resolves to canonical Fichero action
  -> registry.invoke(...)
  -> authz role checks
  -> ActionAudit row
  -> emit_change(...)
  -> UI observers refresh
```

Grounding for that path already exists in:

- action-to-tool generation in `actions/chat_tools.py:91-123`
- tool dispatch back to the registry in `actions/chat_tools.py:153-194`
- authz checks inside `registry.invoke(...)` in `actions/registry.py:178-185`
- audit and change-stream emission in `actions/registry.py:188-236`

Planned rule:

- **Write-capable chat tools** should resolve to registered actions, not to ad hoc route handlers.
- **Read-capable chat tools** may continue to use existing read surfaces such as search, KG query, document read, and MCP-backed read tools, as long as they run under the model-user's authenticated role.

### Role-scoped authority

The existing role model is already strong enough to be the first authority boundary:

- `viewer` can read but not write, because `authz._allowed(..., write=True)` denies writes for viewers in `fichero-server/src/fichero_server/authz.py:217-220` and `240-251`.
- `editor` and `owner` can write at the base role layer in the same code path.
- Per-target ACL overrides already exist as a second layer for content subtree access in `authz.py:127-150` and `255-267`.

Planned behavior:

- A model-user with `viewer` should only receive read tools.
- A model-user with `editor` should receive read tools plus write tools whose actions are allowed by library and subtree ACL.
- A model-user with `owner` may receive owner-only tools, including administrative tools, if explicitly granted.

## MCP mapping in the target design

### Read tools

Existing MCP read surfaces can stay thin wrappers when they are already read-only, because they do not need ActionAudit writes. The important requirement is that they execute under the model-user's authenticated identity and library scope.

### Write tools

Write-capable MCP tools should converge on the same registry-backed mutation surface already used by `actions/chat_tools.py` and `api/routes/actions_registry.py`.

Planned rule:

- MCP tool definitions may stay MCP-shaped.
- Their backend implementation should map to canonical registry actions for mutation.
- A tool that mutates state without going through `registry.invoke(...)` is incomplete relative to this design.

This is the cleanest way to satisfy the "chat can do anything the app can do" vision without creating a second unaudited mutation lane.

## Per-model tool grants

This part is **TO BUILD**.

What exists today:

- There is already a settings surface for users/roles in `fichero/fichero/Views/Settings/Sharing/UsersSettingsView.swift`.
- There is already a settings surface for MCP server management in `fichero/fichero/Views/Settings/MCP/` and backend support in `api/routes/mcp_servers.py:163-257`.

What does **not** exist today:

- no shipped model-user management pane
- no shipped per-model allow/deny table for individual tools
- no shipped backend policy layer that filters the tool catalog per model identity before chat execution

Planned behavior:

- Add a settings pane where an owner can grant or deny specific tools to a specific model-user.
- Tool exposure should be filtered before the tool list is handed to the model, not merely rejected after the call.
- Role remains the coarse authority boundary; per-tool grants are a finer allow/deny layer above it.

## Audit attribution in the target design

The important invariant is simple:

- human user acts -> `ActionAudit.actor` names that human user
- model-user acts -> `ActionAudit.actor` names that model-user

Because `ActionContext` already carries `actor` and `run_id` (`actions/registry.py:39-52`), the existing audit row already has the fields needed to attribute a model-driven run (`actions/registry.py:190-199`). The missing work is not the audit schema; it is the identity and tool-wiring policy around the chat loop.

## Exists vs to build

| Area | Exists on `main` | To build |
|---|---|---|
| User accounts | `AccountUser`, sessions, login/logout/user admin (`models.py:1001-1027`, `auth_accounts.py:243-380`) | first-class model-user provisioning |
| Roles and ACL | `owner` / `editor` / `viewer`, per-target overrides (`authz.py:23-30`, `97-150`) | tool-policy layer derived from role + per-tool grants |
| Audited mutation path | `registry.invoke(...)`, `ActionAudit`, `emit_change(...)` (`actions/registry.py:156-236`) | complete normalization of all model-write surfaces onto that path |
| Action registry HTTP surface | `/api/actions/invoke`, `/api/actions/registry`, `/api/actions/audit` (`actions_registry.py:103-191`) | direct chat-loop use in the shipped chat route |
| Chat-tool bridge | `actions/chat_tools.py` generator + dispatcher (`chat_tools.py:91-194`) | live tool-calling agent loop in `/api/chat` |
| MCP server/tool infrastructure | `mcp_server.py`, `mcp_servers.py`, workflow MCP loading | per-model MCP tool filtering; registry-backed normalization of mutation tools |
| Settings UI | users/roles UI, MCP server UI | model-user settings pane and per-tool grant/deny UI |

## What this design deliberately avoids

- No hidden model superuser.
- No separate "AI audit" table.
- No second mutation pipeline that bypasses `registry.invoke(...)`.
- No reliance on prompt text alone for authorization.
- No claim that the current `/api/chat` route already has this capability; it does not (`api/routes/chat.py:309-415`).

## Recommended implementation order

1. Provision model-users on the existing account/session foundation.
2. Wire the live chat loop to the existing action-tool generator/dispatcher in `actions/chat_tools.py`.
3. Filter the presented tool list by model-user role.
4. Add explicit per-model tool grants in settings and backend policy.
5. Normalize remaining MCP mutation routes onto registry-backed actions so all model writes share the same audit and change-stream contract.
