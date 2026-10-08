# Surfaces from OpenAPI — Design Spec (#5453)

> Milestone: SwiftUI/Engine - OpenAPI
> Manual: TBD — the reference manual's MCP and CLI pages must say every tool and command comes
> from the engine's contract, and list the toolsets.
> Facts for the maintainer to write it from (no user-manual page yet): `docs/contributor_manual/manual-facts/2026-10-05.md`, section 4.
> Status: DRAFT

## Intent (the design)

Everything Fichero can do is an engine route in one OpenAPI contract
(`fichero-server/tests/contracts/openapi.json`, 831 operations). The CLI is already generated
from that contract (`fichero-server/scripts/generate_openapi_cli.py` writes
`fichero-cli/src/fichero_cli/openapi_surface_generated.py`: one command per operation). The MCP
is not. About fifty tools are written by hand in `fichero-mcp/src/fichero_mcp/` and fall behind
every time a route is added. So an agent driving a recipe finds no tool for training, evaluation,
clusters or the recipe itself (#5453), and someone has to write each missing one.

The MCP is generated the same way as the CLI, from the same contract. Adding a route adds its
tool. An agent picks **toolsets** (OpenAPI tags) at start, so it sees the tools for its job and
not all 831. Hand-written tools retire as generated ones cover their routes: one route, one tool.

Two surfaces drive the app rather than the engine, and they are not routes:

- AppleScript: `fichero/fichero/Fichero.sdef`.
- App Intents: `fichero/fichero/Intents/`, which run on Mac, iPhone and iPad.

Their verbs open a node, select, reveal a line, or open a pane or Inspector tab. Each verb calls
the same store method the click calls. They are how an agent, a script or a UI test checks what
a person would see. This is the only way to drive iPhone and iPad from outside.

## Prior art / best practices

- The CLI generator in this repo is the model. Its exclusion list (stream and debug routes) and
  its `x-cli-required` handling of request bodies are reused, not rebuilt.
- FastMCP 2.x (`fastmcp`) has `FastMCP.from_openapi`. It is not installed: we run the official
  `mcp` SDK (`mcp.server.fastmcp`, pinned `<2` in `fichero-mcp/pyproject.toml`). A second MCP
  framework for one feature costs more than a generator of about 200 lines writing calls to
  `FicheroClient.request`.
- GitHub's MCP server exposes toolsets chosen at start (`--toolsets`). Tags as toolsets follow that
  convention.
- App Intents (`AppIntent`, `AppShortcutsProvider`) are Apple's cross-platform automation surface.
  Shortcuts and XCUITest both drive them.

## Behaviors

### A. MCP generated from the contract

- `openapi.mcp.one-tool-per-operation` **[OK]** (#5453) every operation in the contract, outside the
  shared exclusion list, has exactly one MCP tool. It is named from its tag and operation, and its
  description and parameter docs come from the route's summary, description and schema. The tool
  makes one `FicheroClient.request` call and holds no logic of its own. Built:
  `fichero-server/scripts/generate_openapi_mcp.py` writes
  `fichero-mcp/src/fichero_mcp/openapi_tools_generated.py` (825 tools; the event streams are left
  out with the exclusion list, which lives in `fichero-server/scripts/openapi_operations.py`,
  shared with the CLI generator). A tool is `fichero_<tag>_<handler>`. Pinned by
  `fichero-mcp/tests/test_mcp_generated.py` and, against the real routes,
  `fichero-server/tests/unit/mcp/test_generated_mcp_tools_reach_the_engine.py`.
- `openapi.mcp.toolsets-by-tag` **[OK]** (#5453) the MCP server starts with `--toolsets`, a list of
  OpenAPI tags, and lists only those tags' tools. The default is the recipe golden path (recipes,
  training, check, segments, documents, activity, local-models and hpc) plus what organising a
  project needs (#5568): canvas and classifications. `--toolsets all` lists every tool.
  An unknown tag is refused, naming the known ones. Pinned by `fichero-mcp/tests/test_mcp_generated.py`.
- `openapi.mcp.pictures-are-images` **[OK]** (#5568) a generated tool for a GET that answers a picture
  (a 200 offering `image/*`: a folder's canvas, a segment, a thumbnail, a run's diagram) returns MCP
  image content, so the agent sees the picture rather than a count of bytes; an answer that is not a
  picture is returned parsed, and a refusal is the same typed error. Built: the generator emits
  `_rt.image` for those routes (`generate_openapi_mcp.py`'s `image_routes`), which fetches the bytes
  with `FicheroClient.get_bytes`. Pinned by `test_a_picture_route_answers_the_agent_with_an_image` in
  `fichero-mcp/tests/test_mcp_generated.py`.
- `openapi.mcp.organise-a-project` **[OK]** (#5568) an agent organises a project through the default
  MCP surface as a historian does in the app: it groups pages into a document in their order
  (`fichero_documents_create_group`, `_reorder`, `_move`; `_ungroup` undoes it), gives the document
  a prototype (`fichero_classifications_list_values` / `_create_value` with `attributes`,
  `fichero_documents_assign_prototype`) and attribute values (`fichero_documents_update` with
  `attributes`; `_get_effective_attributes` reads them resolved), lays the folder's board out
  (`fichero_canvas_get_folder_layout`, `_save_folder_layout`, `_arrange_folder_layout`), labels it
  (`fichero_canvas_create_folder_item` and its update, delete and list), and LOOKS at it:
  `fichero_canvas_get_folder_picture` returns the board as one PNG, drawn by the engine from the
  saved layout and the stored thumbnails (`GET /api/canvas/folders/{id}/canvas-picture`: cards at
  their saved centres labelled with name and id, groups outlined with their member count, notes as
  yellow boxes, unplaced pages in a strip below, longest side bounded). Every tool is the route's
  generated tool; the picture is the one new route. Pinned end to end through the MCP protocol
  against the real routes by `fichero-server/tests/unit/mcp/test_mcp_organises_a_project.py`, and
  the picture's pixels by `fichero-server/tests/unit/api/test_canvas_picture.py`.
- `openapi.mcp.current-with-the-contract` **[OK]** (#5453) a guard regenerates the MCP module and fails
  if it differs from the committed one, as the CLI's does. A route added without regenerating
  fails the gate. Built: `scripts/check_mcp_generated_current.py` (run by
  `test_every_guard_passes_on_the_real_tree.py`); `sync_openapi_schema.sh` regenerates both
  surfaces. Pinned failing on a stale module by `fichero-mcp/tests/test_mcp_generated.py`.
- `openapi.mcp.one-route-one-tool` **[PARTIAL]** (#5453) no route has both a generated tool and a
  hand-written one. A guard lists any hand-written tool whose route a generated tool covers. That
  hand-written tool is removed, or kept only where it composes several routes, and then says
  which routes. Built: the covered hand-written tools are retired, and
  `test_one_route_one_tool` in `fichero-mcp/tests/test_mcp_generated.py` fails on any left that
  names one covered route and is not in `KEPT_SINGLE_ROUTE`. Still partial: four stay on one route
  each for what the route does not do (`fichero_docs_list` and `fichero_workflow_list` answer lean
  summaries the routes have no view for; `fichero_page_import` sends the YOLO dataset file found
  beside the labels; `fichero_use_library` sets the session's library, by its path or by the name
  the sidebar shows, #5567), and `OPERATOR_ALIASES`
  keeps the old tool names an agent configuration still calls, pointing at the generated tools.
- `openapi.mcp.mutations-act-as-the-agent` **[OK]** (#5453) a generated tool that changes data
  calls as the agent account (`_agent_client` in `fichero-mcp/src/fichero_mcp/server.py`), so the
  audit log names the agent. Reads may use the default client. Built through `_mutating_client`:
  the agent account when one is signed in; on a single-user engine with no accounts, the owner,
  labelled `client=fichero-mcp` in the audit (#4469). Pinned by
  `fichero-mcp/tests/test_mutating_client_attribution.py`.
- `openapi.mcp.reads-say-so` **[OK]** (#5584) a generated tool says whether it reads or changes
  data. A GET reads; a route that takes its question as a body but writes nothing (`POST
  /api/recipes/assemble`) is marked a read in the contract (`x-fichero-reads: true` through the
  route's `openapi_extra`), and its tool says it reads rather than "changes data". Built: the
  shared parse reads the mark into `Operation.reads` (`openapi_operations.py`) and
  `generate_openapi_mcp.py` words the tool from it. Pinned, the contract's mark and the tool's words,
  by `fichero-mcp/tests/test_mcp_reads_say_so.py`.
- `openapi.mcp.errors-reach-the-agent` **[OK]** (#5453) a refused or failed call returns the
  engine's typed error (status and detail) as an MCP tool error. It is never an empty result.
  The error text is `{"status", "detail", "route"}` as JSON. Pinned through the MCP protocol by
  `fichero-mcp/tests/test_mcp_generated.py` and against the real routes by
  `fichero-server/tests/unit/mcp/test_generated_mcp_tools_reach_the_engine.py`.

### B. CLI (already generated)

- `openapi.cli.one-command-per-operation` **[OK]** `generate_openapi_cli.py` writes one command per
  operation, pinned by the `test_cli_generated_*` integration tests.
- `openapi.cli.operator-rough-edges` **[OK]** (#5567) what an operator found running reads through the
  CLI. A trained model's id is accepted as the app shows it: `--model fichero-trained/<name>` (or
  the whole id with no provider) runs on the local MLX server with the whole id, because the engine's
  execute request keeps a split trained id whole (`run_model_choice`), whichever client split it.
  `workflow run <workflow> <doc>...` runs ONE run over several pages, as the Run menu runs a
  selection. A project is opened by the name the sidebar shows as well as by its path: `--library`,
  `library open` and MCP `fichero_use_library` resolve a name through `GET /api/registry/resolve`
  (404 naming the known projects; 409 naming the paths when two share the name). Pinned by
  `fichero-server/tests/unit/api/test_run_model_trained_id.py`,
  `fichero-server/tests/unit/api/test_resolve_project_by_name.py`,
  `fichero-server/tests/unit/cli/test_cli_commands.py` and `fichero-mcp/tests/test_mcp_server.py`.
- `openapi.cli.path-ids-positional` **[OK]** (#5584) every path parameter of a generated command
  is positional (`fichero docs get-children <doc_id>`, as `docs get <doc_id>`), and every
  body field and query parameter an option. The MCP tools take every argument by name, the path's
  ids under the same names (`doc_id` for both `fichero_documents_get` and
  `fichero_documents_get_children`). The rule already held for `get-children`; it did not for a `{name}`
  inside a segment (`/api/citations/document/{document_id}.bib`, the IIIF image request's
  `{quality}.{format}`), whose commands and tools sent the braces literally. Built: the shared parse
  takes every `{name}` in the path (`openapi_operations.py`). Pinned on every generated command by
  `fichero-cli/tests/test_cli_path_ids_positional.py`.

### C. Driving the app: AppleScript and App Intents

- `openapi.ui.verbs-are-the-click` **[PARTIAL]** (#5453) each UI verb (open a node, select nodes,
  reveal a line in Preview, open a pane, show an Inspector tab) is an `AppIntent` in shared code.
  It calls the same store method its click calls, never a second path. On the Mac the same verb is
  an AppleScript command. Built: `fichero/fichero/Intents/UIVerbs.swift` is the one path, called by
  the intents (`Intents/FicheroUIVerbIntents.swift`: Open Project, Open Node, Select Nodes, Reveal
  Lines in Preview, Show Pane, Show Inspector Tab, Take Screenshot) and the AppleScript commands
  (`Services/AppleScriptUIVerbs.swift`: `open project`, `open node`, `select nodes`, `reveal
  segments`, `show pane`, `show inspector tab`). Open project is File ▸ Open's `openLibrary(at:)`,
  open node the sidebar's reveal, reveal a line `WindowState.revealSegments`; select, pane and tab
  are a request on the front window's `WindowState` that `ContentView.applyUIVerb` does through the
  click's own method (`setPaneVisible`, the Inspector button, the tab's scene storage). Pinned
  through the real `LibraryManager`, `WindowState` and `SegmentStore` by
  `fichero/Tests/Unit/general/Intents/UIVerbsTests.swift`, and the commands by
  `fichero/Tests/Unit/mac/AppleScriptSurfaceTests.swift`. Still partial: no UI test yet checks that
  the window's `applyUIVerb` changes what is on screen.
- `openapi.ui.verbs-on-every-device` **[PARTIAL]** (#5453) the UI verbs build and run on Mac, iPhone and
  iPad. A UI test on each device drives at least *open a node* and *reveal a line* through its
  intent and checks what is on screen. Built: the intents are shared code and compile for the iOS
  Simulator; on iPhone and iPad the one window state is the front one. Still partial: no UI test
  on any device drives an intent yet.
- `openapi.ui.mcp-reaches-the-verbs` **[OK]** (#5453) on the Mac, MCP `ui` tools call the AppleScript
  verbs (`fichero-mcp/src/fichero_mcp/ui_control.py` grows from its four commands). An agent can
  then check on screen what it did through the engine tools. Built: `--toolsets ui` lists
  `fichero_ui_open_project`, `fichero_ui_open_node`, `fichero_ui_select_nodes`,
  `fichero_ui_reveal_segments`, `fichero_ui_show_pane`, `fichero_ui_show_inspector_tab` and
  `fichero_ui_screenshot` (`FICHERO_UI_APP` names a built app by path). Pinned by
  `fichero-mcp/tests/test_mcp_ui_control.py`: each builds the command the sdef declares, quoted.
- `openapi.ui.screenshot` **[PARTIAL]** (#5453) an agent can ask the app for a picture of the
  window, or of one pane (Library, Preview, Reader, Inspector, Activity), saved as a PNG at a path it
  names, through the same UI verb surface (AppleScript on the Mac, an App Intent everywhere). It is
  how an agent checks on screen what it did, and how documentation screenshots are made
  (`docs/assets/<milestone>/`), never a second capture path. Ruled 2026-10-04. Built: `screenshot
  "<path>" of pane "<name>"` and Take Screenshot call `UIVerbs.screenshot`; the app draws its own
  window (`Services/FicheroUICapture.swift`: `cacheDisplay` on the Mac, `drawHierarchy` on iOS) and
  crops to the frame each pane records as it is laid out (`WindowState.paneFrames`); Activity is its
  own window on the Mac. Pinned by `UIVerbsTests` (a test window's PNG at its pixel size; a pane's
  crop is that pane's pixels; a pane not shown is refused, naming those shown). Still partial: the
  live panes' recorded frames are not yet checked in the running app.
- `openapi.ui.agents-connect-as-accounts` **[GAP]** (#5453) with Multi-user on, an agent connects to
  the engine as its own account, which the owner adds in Settings' accounts list like a person's;
  its MCP writes are audited under that account and its device. No new switch: sharing and
  Multi-user stay the only two. With Multi-user off the MCP acts as the owner, labelled
  `fichero-mcp`. Driving the app this way is also how Multi-user gets tested end to end. Ruled
  2026-10-04.
- `openapi.applescript.engine-verbs-from-the-contract` **[GAP]** (#5453) any AppleScript command that
  reaches the engine calls the generated Swift client, never a hand-built URL (see
  `automation.applescript.*` in `ui/automation.md` for the dictionary's own checks: #5258, #5259).

### D. The golden path is drivable

- `openapi.golden-path.every-step-has-a-tool` **[GAP]** (#5453) every step of
  `recipe.distil.golden-path` (recipe, Start plan, the teacher-line check, the clean set,
  training, evaluation, model nodes, cluster submit and status) has a route and therefore a
  generated tool. A missing route is engine work, filed against the step's own spec.

## Test matrix

| Leg | This surface? | Pins | File |
|-----|---------------|------|------|
| Pure rule (Python) | y | generator: naming, exclusions, toolsets; drift guard | `fichero-mcp/tests/test_mcp_generated.py` |
| Backend (pytest) | y | a generated tool calls the live route and returns its result | `fichero-server/tests/unit/mcp/test_generated_mcp_tools_reach_the_engine.py` |
| MCP | y | toolsets list the right tools; errors are typed | `fichero-mcp/tests/test_mcp_generated.py`, `fichero-server/tests/integration/test_mcp_server_contract.py` |
| CLI | y | one command per operation | `fichero-server/tests/integration/test_cli_generated_*` |
| Click-around (XCUITest, Mac) | y | an intent drives what the click drives | planned |
| iPhone (iOS) | y | open a node, reveal a line through intents | planned |
| iPad | y | same | planned |

## Order of work

1. The generator plus toolsets plus the drift guard (A1–A3), with tests.
2. Retire the hand-written tools that are now covered (A4), and move mutations to the agent
   account (A5).
3. UI verbs as App Intents and AppleScript commands (C).
4. Fill the golden path's missing routes (D), each in its owning spec.
