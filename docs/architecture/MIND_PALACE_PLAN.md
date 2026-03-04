# Mind Palace Plan

## Product Definition
Mind Palace is a spatial knowledge layer for Fichero. It gives both the user and the AI a shared place to arrange, inspect, and relate notes, documents, media, and semantic groupings.

It may render as map view, spatial view, or full 3D view, but the core product is the same: a manipulable research surface where a human or an AI can place notes, move them around, form visible connections, inspect clusters as the arrangement changes, and zoom into a single note or document without losing its surrounding context.

This is not a generic 3D sandbox. The core object is the research note, with documents and media attached as evidence. The system must preserve provenance back to the source material in Fichero, Tinderbox, or another linked tool.

The governing metaphor is deliberate:
- a large seminar table where evidence can be grouped, stacked, and rearranged
- a room with notes on walls, strings between them, and focal areas for close inspection

The point is to give the AI a place to work, not just a place to look. Mind Palace should function as a practical environment for agentic research: retrieve, compare, cluster, connect, inspect, revise.

It is also a user-facing explanation surface. The AI should be able to expose what it knows from search, RAG, workflows, and cross-tool retrieval by arranging material visually for the user.

This requires a clear split between:
- the Library: the user-facing source-of-truth for documents, notes, folders, smart groups, and stored artifacts
- the AI Workspace: an agent-facing working layer where the AI can create notes for itself, record hypotheses, track relations, stage temporary groupings, and iteratively reason before presenting results back to the user

AI Workspace notes are still user-visible. The distinction is authorship and purpose, not secrecy:
- Library objects are canonical records and source material
- AI Workspace objects are visible, attributable working notes created by the AI to help the user understand and navigate the corpus

The cleanest model is:
- `Document` for source/evidence objects
- `Note` for native Fichero notes created by either the user or the AI

## Fixed Technical Direction

### Platform
- Primary target: macOS desktop
- Implementation language: pure Swift
- Rendering stack: SwiftUI shell with Metal and RealityKit for the spatial layer
- Explicitly out of scope for the first build: web/Three.js, Unity, Godot, Electron

### Why This Stack
- It matches the existing Fichero ecosystem and keeps the integration path native.
- It gives direct access to macOS capture, Accessibility, windowing, and future spatial frameworks without adding a cross-platform engine.
- It keeps the UI, rendering, and tool integration in one language and one deployment model.
- It keeps future expansion open: iPhone/iPad with ARKit, and Vision Pro/visionOS later, without throwing away the core model.

### Rendering Flexibility
- RealityKit remains the preferred scene engine.
- The same spatial model should support both 2D and 3D presentations.
- If useful, the 2D layer can also be implemented using the same scene primitives rather than as a completely separate rendering system.
- The renderer is not the product boundary; the spatial model is.

## Core Model

### First-Class Objects
- Native Fichero `Note` objects are first-class spatial nodes.
- File-backed text documents (`.txt`, `.md`, `.rtf`) remain valid evidence objects and may also be surfaced spatially.
- Images and video are evidence objects that can be attached, previewed, stacked, or pinned in the room.
- Links are first-class relations, not cosmetic lines.
- Virtual folders, smart groups, aliases, and temporary agent-made working sets are also first-class organizational objects.
- User notes, AI workspace notes, hypothesis notes, and summary notes are all variants of the same `Note` system.

### Spatial Model
- Rooms contain walls, clusters, and free-space placements.
- Every node has persistent spatial metadata: `x`, `y`, `z`, `rotation`, `scale`, `room_id`, and timestamps for creation and last movement.
- Connections may exist within a wall, across walls, or across rooms.
- A real folder may map to a room.
- A smart group may map to a live semantic cluster or workspace.
- An alias may appear in multiple spatial contexts without duplicating the underlying source object.

### Interaction Model
- Humans can drag, group, pin, connect, and inspect notes.
- Humans must be able to click and move things directly; direct manipulation is first-class, not secondary to automation.
- AI agents can perform the same operations through MCP tools with full attribution.
- Agent moves must be visible, reversible, and logged with rationale.
- Zoom and focus are first-class actions:
  - zoom from room view to note view
  - inspect a note while retaining neighborhood awareness
  - open an image or document proxy for closer inspection
  - return to the wider room without losing orientation

### Unified Note Model
Fichero should have one first-class native `Note` model rather than separate user-note and agent-note systems.

Recommended shape:
- `Document`
  - imported files, file-backed records, and other canonical evidence objects
- `Note`
  - native text-first record created inside Fichero
  - can be authored by user or AI
  - can be linked, spatially placed, grouped, aliased, and promoted

`Note` should carry explicit taxonomy fields:
- `note_kind`
  - `user`
  - `ai_workspace`
  - `ai_hypothesis`
  - `ai_summary`
  - `ai_relation`
  - `shared`
- `author_type`
  - `user`
  - `ai`
  - `agent_team`
- `status`
  - `draft`
  - `active`
  - `surfaced`
  - `accepted`
  - `archived`
  - `discarded`

This keeps one note system while preserving authorship, lifecycle, and UI filtering.

## Agent Workflows

### Core Agent Behaviors
The AI must be able to:
- create notes for itself inside the AI workspace
- revise, merge, split, and annotate those notes over time
- create and place notes in different parts of a room
- move notes between clusters, walls, and table-like work areas
- stack related notes or media into piles
- create virtual folders and temporary workspaces without changing canonical filing
- pull notes from different folders or sources into one surface to expose hidden relationships
- connect notes with typed links
- zoom into a note or document to inspect it closely
- inspect a note in context by seeing nearby notes, links, and clusters
- open a document/image proxy for closer reading while preserving its location in the larger scene
- surface semantic connections from search, artifacts, workflows, and RAG into a visual arrangement the user can inspect

### AI Workspace Model
The AI Workspace is not the same thing as the Library.

It should support:
- AI-authored notes that are not the same as imported source documents
- working hypotheses and provisional links
- temporary synthesis notes that can later be promoted, archived, or discarded
- internal rationale records tied to spatial actions
- agent-private or agent-team working sets that can later be published to a user-visible spatial workspace

In this project, the notes themselves should be visible to the user by default. What may remain internal is only low-level execution trace or tool chatter, not the substantive notes the AI creates.

The key rule:
- Library objects are evidentiary and user-owned
- AI Workspace notes are native `Note` records with AI authorship metadata; they must remain attributable and inspectable

### Agent Teams
- The spatial layer should support iterative multi-agent work.
- One agent may retrieve and cluster, another may inspect media, another may annotate rationale.
- The shared scene becomes a coordination surface for agent teams as well as a user-facing workspace.

## Storage and Linking

### Storage Strategy
AI-created notes should not live as loose ephemeral memory.

They need durable storage with a clear lifecycle and a clear relationship to source material.

Recommended model:
- Store AI-authored notes in Fichero as first-class persisted `Note` records
- Mark them with explicit authorship and provenance metadata rather than hiding them in transient agent state
- Keep the canonical content in the library data layer, with the spatial layer only referencing placement and presentation

Practical rule:
- The note content lives in the data model
- The room placement lives in the spatial model
- The explanation of why the note exists lives in provenance/audit metadata

This avoids losing AI notes when a scene changes and prevents the spatial layer from becoming the only place where meaning exists.

### Linking Model
Every AI-authored note should support explicit links to:
- source documents
- source notes
- source artifacts (OCR, summaries, entities, extracts)
- related AI notes
- spatial clusters, workspaces, or rooms where it is currently being used

There should be at least three link classes:
- evidentiary links: `derived_from`, `quotes`, `summarizes`, `contrasts_with`
- semantic links: `related_to`, `supports`, `challenges`, `extends`
- organizational links: `appears_in_workspace`, `stacked_with`, `pinned_near`, `alias_of`

This lets the user traverse from an AI note back to what grounded it, and also understand how it fits into the current working surface.

## Integration Boundaries

### Relationship to Fichero
- Fichero remains the library and source-of-truth for stored documents.
- Mind Palace consumes note/document references from Fichero and writes spatial metadata plus explicit relationships.
- The initial integration should be feature-gated inside Fichero rather than split into a separate app immediately.
- It should live alongside the existing Library display modes: list, icon, table, map, and spatial/3D.
- Fichero should also improve its native note support so the AI has a proper substrate for note creation, note-to-note reasoning, and durable internal working records.
- AI-authored notes should be stored inside Fichero’s durable data layer, not only inside the scene state.

### Relationship to Tinderbox
- Tinderbox remains the synthesis and writing surface.
- Mind Palace should support bidirectional references so a spatial cluster can point to Tinderbox notes and a Tinderbox note can point back to the source cluster.

### Backend and API Strategy
Mind Palace should build on existing Fichero backend surfaces instead of bypassing them:

- `/api/documents`
  - source of truth for note/document identity, hierarchy, metadata, and text-bearing objects
  - spatial nodes should reference existing Fichero document IDs whenever possible
  - a native note layer should sit alongside documents so user notes and AI-authored notes can both exist cleanly, with attribution and lifecycle control
  - notes should not be forced to masquerade as file-backed documents
- `/api/search`
  - retrieval path for seeding clusters, semantic grouping, and "find related notes" actions
  - can drive AI proposals for spatial rearrangement before the room is updated
- `/api/storage`
  - existing thumbnail, display, and source endpoints already provide the right foundation for image/document preview and zoomable evidence
  - the spatial layer should reuse these for note proxies and document inspection
- `/api/artifacts`
  - source for summaries, OCR, extracted entities, and other processed context attached to a document
  - useful for agent inspection without reopening the full source file
- `/api/workflows` and workflow-execution
  - a path for agentic tools and agent teams to operate over Fichero content and feed results into the spatial layer
  - spatial grouping and arrangement should be available as callable tools within agentic workflow runs
  - AI note-generation and note-synthesis flows should be able to write into the AI Workspace rather than only returning transient text blobs
- `/api/integrations`
  - bridge for Tinderbox and other external systems when spatial nodes need to point outward or import supporting context

### Exposure Modes
The spatial system should be exposed in three different ways:

1. Native scene controller (Swift)
   - the actual RealityKit/Metal scene layer
   - lowest-latency path for camera control, transforms, and local rendering
2. Fichero REST API
   - structured persistence and retrieval for rooms, nodes, edges, aliases, workspaces, notes, viewport state, and command logs
   - should expose a stable contract to the Swift app and future clients
3. MCP wrapper
   - thin, token-efficient agent-facing tool layer on top of the REST/native surface
   - should expose task-level operations rather than leaking internal rendering details

The existing `fichero.mcp_server` is the right conceptual place to extend. Mind Palace should add a spatial tool namespace there rather than inventing a completely separate agent bridge.

## MCP and Token Discipline

### MCP as a Hard Requirement
The AI must be able to operate the space programmatically. MCP is not an add-on; it is part of the core product surface.

Required tool families:
- Spatial manipulation: create room, place note, move note, stack notes, unstack notes, scale note, pin note, link notes, unlink notes
- Navigation: move camera, focus cluster, focus note, zoom to note, restore prior view, switch room
- Readback: inspect room state, inspect viewport state, inspect node metadata, inspect note context, read active note content, list visible connections
- Organization: create virtual folder, create smart workspace, alias note into workspace, gather related notes, promote cluster to smart group
- AI workspace: create scratch note, create hypothesis note, update note, merge notes, record rationale, publish workspace notes into a user-visible surface
- Capture: capture still image, capture region, capture short video clip
- Audit: log rationale, list recent agent actions, revert last action

### MCP Token Discipline
The AI should not have to spend tokens constantly polling raw scene data or image payloads.

The MCP contract should prefer:
- compact scene summaries rather than full room dumps
- viewport-scoped reads rather than global reads by default
- deltas since last read rather than full snapshots when possible
- stable object handles (`room_id`, `node_id`, `edge_id`, `camera_bookmark_id`)
- explicit on-demand capture for stills/video, never continuous image streaming

Default MCP responses should be structured and terse. Richer image or video output should be opt-in when the agent explicitly needs visual verification.

The default agent interface should be semantic-first:
- "group these together"
- "bring related notes into view"
- "place this near that"
- "open this in context"

Coordinate-level APIs remain available, but as a lower-level layer for precision, replay, visual-model interaction, and advanced control.

## Capture and Perception

### Still Images
- High-resolution still capture is required for AI visual feedback loops.
- Capture must support full room and bounded-region export.
- It must also support note-centered capture, so an agent can request "this note and its immediate context" without rendering the whole room.

### Video
- Short video capture is required for movement review, demos, and agent debugging.
- The first implementation should support bounded recordings of camera moves or animated rearrangements, not continuous streaming.

### Agent Perception Contract
- The AI should not rely on raw pixels alone when structured scene data exists.
- Prefer dual readback:
  - structured scene state for exact positions and relations
  - still/video capture for visual verification and self-correction

## Architecture

### Frontend Layer
- SwiftUI hosts toolbars, inspectors, feature flags, and app navigation.
- RealityKit owns scene entities, transforms, hit testing, and spatial persistence.
- Metal is used where lower-level custom rendering is needed for connection paths, selection effects, or large-scale scene performance.
- The frontend must support both room-scale browsing and focused inspection mode for a single note/document.
- The frontend must support direct user manipulation: click, drag, stack, connect, focus, zoom, and reorganize in place.

### Data Layer
- `Document`: source/evidence object
- `Note`: native note record used for user notes and AI-authored notes
- `SpatialNode`: note or evidence object with persistent transform and provenance
- `SpatialEdge`: explicit typed relationship between nodes
- `SpatialRoom`: container and coordinate namespace
- `SpatialSnapshot`: serializable room state for undo, replay, export, and AI inspection
- `SpatialViewport`: camera, focus target, zoom state, selected cluster, and return bookmark
- `SpatialCommandLog`: ordered record of user/agent actions for attribution, replay, and revert
- `SpatialAlias`: secondary placement of an object in another room/workspace without duplicating source truth
- `SpatialWorkspace`: virtual folder or temporary semantic grouping assembled by user or agent
- `ProposedRelation`: optional AI-authored proposed relationship, distinct from confirmed user-facing links when needed
- `NoteLink`: durable link record connecting notes/documents/artifacts across library and AI workspace
- `ProvenanceRecord`: why a note was created, what source items informed it, and which agent or workflow created it

## Delivery Phases

### Phase 0: Architecture Lock
- Lock the stack to pure Swift + macOS + RealityKit/Metal.
- Lock the product model to a shared spatial layer that supports map and 3D presentations.
- Define the split between Library objects and AI Workspace objects.
- Define where AI-authored notes are stored and how they link back to source evidence.
- Define the unified `Note` model and note taxonomy.
- Define the spatial schema and MCP contract.
- Define the inspection model for room view, focus view, and return-to-context.
- Define the feature-gated entry point inside Fichero.
- Exit condition: one canonical plan, one roadmap milestone, no stack ambiguity.

### Phase 1: Thin Vertical Slice
- Render a single spatial workspace.
- Allow the user and the AI to create and update native notes.
- Place and move text notes in 3D.
- Support direct human click-and-drag movement.
- Support zoom-to-note and return-to-room.
- Persist positions.
- Expose basic MCP commands for room creation, note placement, note movement, and room-state readback.
- Support still-image capture.
- Exit condition: agent can place a note, move it, zoom in to inspect it, and verify the result.

### Phase 2: Research Objects and Relations
- Add markdown/RTF note rendering.
- Add image and video proxies.
- Add explicit connections, stack behavior, and cluster affordances.
- Add rationale logging and undo.
- Add note-context inspection and note-centered capture.
- Exit condition: mixed note/media boards are usable for real clustering and close inspection.

### Phase 3: Live Collaboration
- Add animated agent operations.
- Add short video capture for action review.
- Add cross-room navigation and stronger Fichero/Tinderbox linking.
- Exit condition: human and AI can co-curate a live spatial session.
