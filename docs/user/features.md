# Feature Matrix

What Fichero actually does today, and what is still being built.

Every status on this page is derived from the code, not from a roadmap:

- **Live** — enabled by default in a release build. `FeatureManager.resetToV001()`
  sets the flag `true`, so a user who installs Fichero sees it without changing
  anything.
- **Beta** — on by default, but recently flipped on and still moving. These are the
  flags `scripts/check_feature_flags.py` reports as `[NEW]` — enabled in release
  before being ratcheted into the guardrail's known list.
- **In progress** — implemented and reachable behind a flag that is `false` in
  release defaults. The engine routes exist; the UI is built or half-built. Turn it
  on with `FICHERO_ALL_FEATURES=1`.
- **Planned** — a milestone exists; there is no shipping UI surface yet.

!!! note "Where the flags live"
    `fichero/fichero/Models/FeatureManager.swift`. Release defaults are applied by
    `resetToV001()` on every `releaseProfileVersion` bump. Engine-side, routes are
    gated by `FICHERO_FEATURE_TIER` (`release` | `dev`) in
    `fichero-engine/src/fichero/api/main.py` — today only IIIF is `dev`-only.

## Core

| Capability | Status | Flag | Milestone |
|---|---|---|---|
| **Library** — import, organize, browse a hierarchy of documents | Live | *always on* | [Library & Reading Surface](https://github.com/dtubb/fichero/milestone/60) |
| **Reader** — PDFs, page images, extracted text, artifacts, inspector | Live | *always on* | [Library & Reading Surface](https://github.com/dtubb/fichero/milestone/60) |
| **Ingest** — 37 file extensions, link-in-place or copy (APFS clone) | Live | *always on* | [Importers](https://github.com/dtubb/fichero/milestone/57) |
| **Library views** — grid, list, table, map | Live | `library_advanced_views` | [Library & Reading Surface](https://github.com/dtubb/fichero/milestone/60) |
| **Icon zoom controls** | Live | `library_icon_zoom_controls` | [Library & Reading Surface](https://github.com/dtubb/fichero/milestone/60) |
| **Search** — keyword + semantic, across the whole library | Live | `search` | [Search](https://github.com/dtubb/fichero/milestone/17) |
| **Search results in all views** | Live | `search_advanced_views` | [Search](https://github.com/dtubb/fichero/milestone/17) |

## Processing

| Capability | Status | Flag | Milestone |
|---|---|---|---|
| **Workflows** — visual node editor, run across a corpus | Live | `workflows` | [Workflows](https://github.com/dtubb/fichero/milestone/54) |
| **Workflow editor advanced views** | Live | `workflow_editor_advanced_views` | [Workflows](https://github.com/dtubb/fichero/milestone/54) |
| **Workflow chains** — compose workflows into pipelines | Live | `workflow_chains` | [Workflows](https://github.com/dtubb/fichero/milestone/54) |
| **Workflow import / export** | Live | `workflow_import_export` | [Workflows](https://github.com/dtubb/fichero/milestone/54) |
| **Run workflow on selection** | Live | `workflow_run_on_selection` | [Workflows](https://github.com/dtubb/fichero/milestone/54) |
| **LangGraph preview** — inspect the compiled graph | Live | `workflow_langgraph_preview` | [Workflows](https://github.com/dtubb/fichero/milestone/54) |
| **Batches** — queue work across many documents | Live | `batches` | [Workflows & Catalogue Hardening](https://github.com/dtubb/fichero/milestone/91) |
| **Activity** — execution history, live progress over SSE | Beta | `activity` | [Activity & Automation](https://github.com/dtubb/fichero/milestone/56) |
| **Workflow tools — files** | Live | `workflow_tools_files` | [Workflows](https://github.com/dtubb/fichero/milestone/54) |
| **Workflow tools — transform, convert, logic, outputs, search** | In progress | `workflow_tools_*` | [Workflows](https://github.com/dtubb/fichero/milestone/54) |
| **Workflow tools — audio, video** | In progress | `workflow_tools_audio` / `_video` | [Importers](https://github.com/dtubb/fichero/milestone/57) |
| **Workflow tools — MCP, agents** | In progress | `workflow_tools_mcp` / `_agents` | [MCP](https://github.com/dtubb/fichero/milestone/52) |

## Knowledge

| Capability | Status | Flag | Milestone |
|---|---|---|---|
| **Knowledge graph** — entities, claims, provenance to the source page | Live | `knowledge_graph` | [KG & Hermeneutics](https://github.com/dtubb/fichero/milestone/55) |
| **Curation** — corrections persist as rules later imports obey | Live | *part of KG* | [Curation](https://github.com/dtubb/fichero/milestone/73) |
| **Researcher** — ask questions, answers grounded in your sources | Beta | `research` | [Researcher](https://github.com/dtubb/fichero/milestone/53) |
| **Notes** | In progress | *no flag* | [KG & Hermeneutics](https://github.com/dtubb/fichero/milestone/55) |
| **Claim ↔ page highlight sync** | In progress | `claim_highlight_sync` | [UI Reform — Inspector & Annotation](https://github.com/dtubb/fichero/milestone/94) |
| **Bibliography & citations** | In progress | *no flag* | [Bibliography & Citations](https://github.com/dtubb/fichero/milestone/68) |
| **Chat** — RAG conversation over the library | In progress | `chat` | [Chat](https://github.com/dtubb/fichero/milestone/22) |
| **Mind Palace** | Planned | *no flag* | [Mind Palace](https://github.com/dtubb/fichero/milestone/12) |

## Models and providers

| Capability | Status | Flag | Milestone |
|---|---|---|---|
| **Model-agnostic providers** — local (Apple Foundation Models, MLX, Ollama, LM Studio) and cloud (OpenAI, Anthropic, Google, OpenRouter) | Live | *always on* | [Settings & Providers](https://github.com/dtubb/fichero/milestone/20) |
| **Keys in the macOS Keychain** | Live | *always on* | [Security](https://github.com/dtubb/fichero/milestone/69) |
| **Model comparison** | Live | *core route tier* | [Chat & Agent](https://github.com/dtubb/fichero/milestone/102) |
| **Extended provider catalog** | In progress | `providers_extended` | [Settings & Providers](https://github.com/dtubb/fichero/milestone/20) |
| **Settings — Models tab** | In progress | `settings_models_tab` | [Settings & Providers](https://github.com/dtubb/fichero/milestone/20) |

## Clients and surfaces

| Capability | Status | Flag | Milestone |
|---|---|---|---|
| **macOS app** — engine embedded in the app bundle | Live | — | [Mac App Shell](https://github.com/dtubb/fichero/milestone/62) |
| **`fichero` CLI** — typed CLI over the same HTTP surface | Live | — | [API Surface & Test Harness](https://github.com/dtubb/fichero/milestone/70) |
| **`fichero-mcp`** — MCP server exposing engine capabilities | Live | — | [MCP](https://github.com/dtubb/fichero/milestone/52) |
| **iPhone / iPad** — connects to an engine on a Mac; cannot embed one | In progress | — | [iOS/iPad Embedding & Multi-Library](https://github.com/dtubb/fichero/milestone/105) |
| **Device pairing & discovery** | In progress | — | [Device Pairing & Discovery](https://github.com/dtubb/fichero/milestone/96) |
| **Remote / self-hosted engine** (`tailscale serve`) | In progress | — | [Remote & Self-Hosting](https://github.com/dtubb/fichero/milestone/74) |
| **MCP servers UI** — manage MCP servers from the app | In progress | `mcp` | [MCP](https://github.com/dtubb/fichero/milestone/52) |
| **visionOS** | Planned | — | [visionOS — Apple Vision Pro port](https://github.com/dtubb/fichero/milestone/95) |
| **tvOS** | Planned | — | [tvOS — Apple TV port](https://github.com/dtubb/fichero/milestone/114) |

## Settings

| Capability | Status | Flag | Milestone |
|---|---|---|---|
| **General** | Beta | `settings_general_tab` | [Settings & Providers](https://github.com/dtubb/fichero/milestone/20) |
| **Engine** | Beta | `settings_engine_tab` | [Connection & Startup Bulletproofing](https://github.com/dtubb/fichero/milestone/110) |
| **Share** | Beta | `settings_share_tab` | [Sharing & Collaboration](https://github.com/dtubb/fichero/milestone/75) |
| **Users** | Beta | `settings_users_tab` | [Multi-user & Shared Libraries](https://github.com/dtubb/fichero/milestone/111) |
| **Capture** | Beta | `settings_capture_tab` | [Archive Capture — Mobile & Camera Intake](https://github.com/dtubb/fichero/milestone/97) |
| **Backend** | In progress | `settings_backend_tab` | [Connection & Startup Bulletproofing](https://github.com/dtubb/fichero/milestone/110) |

## Not yet reachable

| Capability | Status | Flag | Milestone |
|---|---|---|---|
| **Canvas (2D) / Space (3D)** — spatial view modes for a library | In progress | `spatial_mode`, `canvas_realitykit_2d`, `canvas_realitykit_3d` | [Canvas & Space](https://github.com/dtubb/fichero/milestone/115) |
| **Workspace mode** | In progress | `workspace_mode` | [Mac App Shell](https://github.com/dtubb/fichero/milestone/62) |
| **PDF scroll ↔ grid sync** | In progress | `pdf_scroll_grid_sync` | [Library & Reading Surface](https://github.com/dtubb/fichero/milestone/60) |
| **Library filter toolbar** | In progress | `library_filter_toolbar` | [Window Chrome & Toolbars](https://github.com/dtubb/fichero/milestone/71) |
| **Library / search split layouts** | In progress | `library_search_split_layouts` | [Library & Reading Surface](https://github.com/dtubb/fichero/milestone/60) |
| **Agents** — in-app agent acting through audited tools | Planned | `agents` | [Chat & Agent](https://github.com/dtubb/fichero/milestone/102) |
| **Automation** — schedules, triggers, watchlists | In progress | `automation` | [Activity & Automation](https://github.com/dtubb/fichero/milestone/56) |
| **Integrations** | Planned | `integrations` | [Activity & Automation](https://github.com/dtubb/fichero/milestone/56) |
| **IIIF** — interchange with IIIF image/annotation servers | Planned | *engine `dev` tier only* | [Source Archives](https://github.com/dtubb/fichero/milestone/65) |
| **Export to static site** | Planned | — | [Exporter](https://github.com/dtubb/fichero/milestone/14) |

---

*Turn everything on at once for exploration:* launch with `FICHERO_ALL_FEATURES=1`
(app) and `FICHERO_FEATURE_TIER=dev` (engine). Flagged-off surfaces are unfinished —
expect rough edges and no upgrade guarantees for anything they write.
