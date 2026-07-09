(AI generated. Not reviewed.)

# Feature Matrix

This page is generated from `features.yaml`.

Build-tier visibility uses a maturity floor:

- `release` builds show `release` features only.
- `beta` builds show `beta` and `release` features.
- `alpha` builds show `alpha`, `beta`, and `release` features.
- `dev` builds show every tier.

| Feature | Tier | UI flag | Backend route prefixes | Group | Notes |
|---|---|---|---|---|---|
| CLI | `release` | - | - | Clients | Typed CLI over the same HTTP API surface. |
| MCP server | `release` | - | `/api/mcp` | Clients | MCP server surface backed by the engine. |
| Ingest | `release` | - | `/api/ingest` | Core | File and URL import into the library. |
| Library | `release` | - | - | Core | Import, organize, and browse a hierarchy of documents. |
| Library advanced views | `release` | `fichero.features.library_advanced_views` | - | Core | Grid, list, table, and map views in the library. |
| Library icon zoom controls | `release` | `fichero.features.library_icon_zoom_controls` | - | Core | Zoom controls for icon-based library layouts. |
| Reader | `release` | - | - | Core | PDFs, page images, extracted text, artifacts, and inspector. |
| Search | `release` | `fichero.features.search` | `/api/search` | Core | Keyword and semantic search across the library. |
| Search advanced views | `release` | `fichero.features.search_advanced_views` | - | Core | Search results in all supported presentation modes. |
| Curation | `release` | - | `/api/claims` | Knowledge | Persist corrections as rules that future imports obey. |
| Knowledge graph | `release` | `fichero.features.knowledge_graph` | `/api/kg`, `/api/hermeneutics` | Knowledge | Entities, claims, provenance, and ontology surfaces. |
| Model comparison | `release` | - | `/api/model-comparison` | Models | Compare model behavior and metadata in-app. |
| Providers | `release` | - | `/api/providers`, `/api/models` | Models | Local and cloud model providers plus model catalog. |
| Batches | `release` | `fichero.features.batches` | `/api/batches` | Processing | Queue workflow work across many documents. |
| Workflow chains | `release` | `fichero.features.workflow_chains` | `/api/chains` | Processing | Multi-step composed workflow pipelines. |
| Workflow editor advanced views | `release` | `fichero.features.workflow_editor_advanced_views` | - | Processing | Extra presentation modes in the workflow editor. |
| Workflow import and export | `release` | `fichero.features.workflow_import_export` | - | Processing | Import and export workflow definitions. |
| Workflow LangGraph preview | `release` | `fichero.features.workflow_langgraph_preview` | - | Processing | Inspect the compiled LangGraph form of a workflow. |
| Workflow run on selection | `release` | `fichero.features.workflow_run_on_selection` | - | Processing | Run the active workflow on the selected documents. |
| Workflow tools files | `release` | `fichero.features.workflow_tools_files` | - | Processing | File and collection tools enabled in shipped workflows. |
| Workflows | `release` | `fichero.features.workflows` | `/api/workflows`, `/api/workflow-execution` | Processing | Visual workflow editor and execution surface. |
| Research | `beta` | `fichero.features.research` | `/api/research` | Knowledge | KG-backed research workflows and answer surface. |
| Activity | `beta` | `fichero.features.activity` | `/api/activity` | Processing | Execution history and live progress over SSE. |
| Settings capture tab | `beta` | `fichero.features.settings_capture_tab` | - | Settings | Capture and intake settings panel. |
| Settings engine tab | `beta` | `fichero.features.settings_engine_tab` | - | Settings | Engine settings panel. |
| Settings general tab | `beta` | `fichero.features.settings_general_tab` | - | Settings | General settings panel. |
| Settings share tab | `beta` | `fichero.features.settings_share_tab` | - | Settings | Sharing and collaboration settings panel. |
| Settings users tab | `beta` | `fichero.features.settings_users_tab` | - | Settings | Multi-user settings panel. |
| Canvas RealityKit 2D | `alpha` | `fichero.features.canvas_realitykit_2d` | - | Clients | Route the 2D canvas to the RealityKit renderer. |
| Canvas RealityKit 3D | `alpha` | `fichero.features.canvas_realitykit_3d` | - | Clients | Route the 3D space to the contract-based RealityKit renderer. |
| MCP servers UI | `alpha` | `fichero.features.mcp` | `/api/mcp-servers` | Clients | UI for managing MCP server connections. |
| Spatial mode | `alpha` | `fichero.features.spatial_mode` | - | Clients | Spatial library presentation mode. |
| Workspace mode | `alpha` | `fichero.features.workspace_mode` | - | Clients | Alternate workspace-oriented shell mode. |
| Library and search split layouts | `alpha` | `fichero.features.library_search_split_layouts` | - | Core | Split layouts for library and search. |
| Library filter toolbar | `alpha` | `fichero.features.library_filter_toolbar` | - | Core | Advanced filter toolbar in the library. |
| PDF scroll grid sync | `alpha` | `fichero.features.pdf_scroll_grid_sync` | - | Core | Live PDF scroll synchronization into other panes. |
| Chat | `alpha` | `fichero.features.chat` | `/api/chat` | Knowledge | RAG conversation over the active library. |
| Claim highlight sync | `alpha` | `fichero.features.claim_highlight_sync` | - | Knowledge | Bidirectional claim highlight sync across panes. |
| Extended provider catalog | `alpha` | `fichero.features.providers_extended` | - | Models | Expanded provider and model catalog beyond the shipped baseline. |
| Automation | `alpha` | `fichero.features.automation` | `/api/schedules`, `/api/triggers` | Processing | Schedules, triggers, and automated flows. |
| Workflow tools agents | `alpha` | `fichero.features.workflow_tools_agents` | - | Processing | Agent-backed workflow tools still under review. |
| Workflow tools audio | `alpha` | `fichero.features.workflow_tools_audio` | - | Processing | Audio workflow tools still under review. |
| Workflow tools convert | `alpha` | `fichero.features.workflow_tools_convert` | - | Processing | Convert workflow tools still under review. |
| Workflow tools logic | `alpha` | `fichero.features.workflow_tools_logic` | - | Processing | Logic workflow tools still under review. |
| Workflow tools MCP | `alpha` | `fichero.features.workflow_tools_mcp` | - | Processing | MCP-backed workflow tools still under review. |
| Workflow tools outputs | `alpha` | `fichero.features.workflow_tools_outputs` | - | Processing | Output workflow tools still under review. |
| Workflow tools search | `alpha` | `fichero.features.workflow_tools_search` | - | Processing | Search-oriented workflow tools that are not yet shipped by default. |
| Workflow tools transform | `alpha` | `fichero.features.workflow_tools_transform` | - | Processing | Transform workflow tools still under review. |
| Workflow tools video | `alpha` | `fichero.features.workflow_tools_video` | - | Processing | Video workflow tools still under review. |
| Settings backend tab | `alpha` | `fichero.features.settings_backend_tab` | - | Settings | Backend configuration panel. |
| Settings models tab | `alpha` | `fichero.features.settings_models_tab` | - | Settings | Model configuration panel. |
| Integrations | `dev` | `fichero.features.integrations` | `/api/integrations` | Clients | External integrations surface still in the rawest stage. |
| IIIF | `dev` | - | `/api/iiif` | Core | IIIF image and annotation server interoperability. |
| Agents | `dev` | `fichero.features.agents` | - | Knowledge | In-app agent surface still in the rawest stage. |
