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
| Canvas RealityKit 2D | `release` | `fichero.features.canvas_realitykit_2d` | - | Clients | Route the 2D canvas to the RealityKit-ortho renderer (default; |
| Canvas RealityKit 3D | `release` | `fichero.features.canvas_realitykit_3d` | - | Clients | Route the 3D space to the contract-based RealityKit renderer (default; |
| Ingest | `release` | - | `/api/ingest` | Core | File and URL import into the library. |
| Library | `release` | - | - | Core | Import, organize, and browse a hierarchy of documents. |
| Reader | `release` | - | - | Core | PDFs, page images, extracted text, artifacts, and inspector. |
| Search | `release` | `fichero.features.search` | `/api/search` | Core | Keyword and semantic search across the library. |
| Workflow run on selection | `release` | `fichero.features.workflow_run_on_selection` | - | Processing | Run the active workflow on the selected documents from the library contextual menu. |
| CLI | `beta` | - | - | Clients | Typed CLI over the same HTTP API surface. |
| MCP server | `beta` | - | `/api/mcp` | Clients | MCP server surface backed by the engine. |
| Library advanced views | `beta` | `fichero.features.library_advanced_views` | - | Core | Grid, list, table, and map views in the library. |
| Search advanced views | `beta` | `fichero.features.search_advanced_views` | - | Core | Search results in all supported presentation modes. |
| Chat | `beta` | `fichero.features.chat` | `/api/chat` | Knowledge | RAG conversation over the active library. |
| Curation | `beta` | - | `/api/claims` | Knowledge | Persist corrections as rules that future imports obey. |
| Knowledge graph | `beta` | `fichero.features.knowledge_graph` | `/api/kg`, `/api/hermeneutics` | Knowledge | Entities, claims, provenance, and ontology surfaces. |
| Research | `beta` | `fichero.features.research` | `/api/research` | Knowledge | KG-backed research workflows and answer surface. |
| Model comparison | `beta` | - | `/api/model-comparison` | Models | Compare model behavior and metadata in-app. |
| Providers | `beta` | - | `/api/providers`, `/api/models` | Models | Local and cloud model providers plus model catalog. |
| Activity | `beta` | `fichero.features.activity` | `/api/activity` | Processing | Execution history and live progress over SSE. |
| Batches | `beta` | `fichero.features.batches` | `/api/batches` | Processing | Queue workflow work across many documents. |
| Workflow chains | `beta` | `fichero.features.workflow_chains` | `/api/chains` | Processing | Multi-step composed workflow pipelines. |
| Workflow tools files | `beta` | `fichero.features.workflow_tools_files` | - | Processing | File and collection tools enabled in shipped workflows. |
| Workflows | `beta` | `fichero.features.workflows` | `/api/workflows`, `/api/workflow-execution` | Processing | Visual workflow editor and execution surface. |
| Settings general tab | `beta` | `fichero.features.settings_general_tab` | - | Settings | General settings panel. |
| Integrations | `alpha` | `fichero.features.integrations` | `/api/integrations` | Clients | External integrations surface still in the rawest stage. |
| MCP servers UI | `alpha` | `fichero.features.mcp` | `/api/mcp-servers` | Clients | UI for managing MCP server connections. |
| Settings backend tab | `alpha` | `fichero.features.settings_backend_tab` | - | Settings | Backend configuration panel. |
| Settings capture tab | `alpha` | `fichero.features.settings_capture_tab` | - | Settings | Capture and intake settings panel. |
| Settings engine tab | `alpha` | `fichero.features.settings_engine_tab` | - | Settings | Engine settings panel. |
| Settings models tab | `alpha` | `fichero.features.settings_models_tab` | - | Settings | Model configuration panel. |
| Settings share tab | `alpha` | `fichero.features.settings_share_tab` | - | Settings | Sharing and collaboration settings panel. |
| Settings users tab | `alpha` | `fichero.features.settings_users_tab` | - | Settings | Multi-user settings panel. |
| Spatial mode | `dev` | `fichero.features.spatial_mode` | - | Clients | Spatial library presentation mode. |
| Workspace mode | `dev` | `fichero.features.workspace_mode` | - | Clients | Alternate workspace-oriented shell mode. |
| IIIF | `dev` | - | `/api/iiif` | Core | IIIF image and annotation server interoperability. |
| Library and search split layouts | `dev` | `fichero.features.library_search_split_layouts` | - | Core | Split layouts for library and search. |
| Library filter toolbar | `dev` | `fichero.features.library_filter_toolbar` | - | Core | Advanced filter toolbar in the library. |
| Library icon zoom controls | `dev` | `fichero.features.library_icon_zoom_controls` | - | Core | Zoom controls for icon-based library layouts. |
| PDF scroll grid sync | `dev` | `fichero.features.pdf_scroll_grid_sync` | - | Core | Live PDF scroll synchronization into other panes. |
| Agents | `dev` | `fichero.features.agents` | - | Knowledge | In-app agent surface still in the rawest stage. |
| Claim highlight sync | `dev` | `fichero.features.claim_highlight_sync` | - | Knowledge | Bidirectional claim highlight sync across panes. |
| Extended provider catalog | `dev` | `fichero.features.providers_extended` | - | Models | Expanded provider and model catalog beyond the shipped baseline. |
| Automation | `dev` | `fichero.features.automation` | `/api/schedules`, `/api/triggers` | Processing | Schedules, triggers, and automated flows. |
| Workflow editor advanced views | `dev` | `fichero.features.workflow_editor_advanced_views` | - | Processing | Extra presentation modes in the workflow editor. |
| Workflow import and export | `dev` | `fichero.features.workflow_import_export` | - | Processing | Import and export workflow definitions. |
| Workflow LangGraph preview | `dev` | `fichero.features.workflow_langgraph_preview` | - | Processing | Inspect the compiled LangGraph form of a workflow. |
| Workflow tools agents | `dev` | `fichero.features.workflow_tools_agents` | - | Processing | Agent-backed workflow tools still under review. |
| Workflow tools audio | `dev` | `fichero.features.workflow_tools_audio` | - | Processing | Audio workflow tools still under review. |
| Workflow tools convert | `dev` | `fichero.features.workflow_tools_convert` | - | Processing | Convert workflow tools still under review. |
| Workflow tools logic | `dev` | `fichero.features.workflow_tools_logic` | - | Processing | Logic workflow tools still under review. |
| Workflow tools MCP | `dev` | `fichero.features.workflow_tools_mcp` | - | Processing | MCP-backed workflow tools still under review. |
| Workflow tools outputs | `dev` | `fichero.features.workflow_tools_outputs` | - | Processing | Output workflow tools still under review. |
| Workflow tools search | `dev` | `fichero.features.workflow_tools_search` | - | Processing | Search-oriented workflow tools that are not yet shipped by default. |
| Workflow tools transform | `dev` | `fichero.features.workflow_tools_transform` | - | Processing | Transform workflow tools still under review. |
| Workflow tools video | `dev` | `fichero.features.workflow_tools_video` | - | Processing | Video workflow tools still under review. |
