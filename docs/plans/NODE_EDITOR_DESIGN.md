# Powerful Node Editor Design

## Vision

A visual workflow editor inspired by Audio Hijack Pro that leverages LangGraph's full power for document processing pipelines. Users can freely place nodes, connect them with edges, create branches and conditionals, and process thousands of documents.

---

## Core Capabilities

### 1. Free Node Placement
- Nodes can be placed anywhere on an infinite canvas
- Drag to reposition
- Zoom in/out (pinch gesture, scroll wheel)
- Pan canvas (two-finger drag, scroll)
- Grid snapping (optional, configurable)

### 2. Edge Connections (Audio Hijack Style)
- Each node has input/output ports (circles on sides)
- Drag from output port to input port to connect
- Visual feedback during drag (dotted line following cursor)
- Edge validation (prevent invalid connections)
- Multiple outputs from one node (fan-out)
- Multiple inputs to one node (fan-in with merge behavior)

### 3. Branching & Conditionals (LangGraph Power)
```
                    ┌─> [Summarize] ─> [Export PDF]
[Transcribe] ─> [IF]
                    └─> [Translate] ─> [Export Word]
```

- **IF Node**: Routes based on condition expression
  - Condition syntax: `$.nodes.transcribe.language == "en"`
  - Multiple branches (if/elif/else)

- **Switch Node**: Multi-way routing
  - Match on value: `$.nodes.classify.category`
  - Cases: "invoice" -> A, "receipt" -> B, default -> C

- **Loop Node**: Process items in collection
  - For each item in `$.nodes.split.pages`
  - Configurable parallelism

### 4. Document Sources (Entry Points)
- **Drag & Drop**: Drop files/folders onto canvas
- **Search Node**: Pull from search results
- **Collection Node**: Pull from library collection
- **URL Node**: Fetch from URLs
- **Watch Folder**: Monitor folder for new files

### 5. Document Sinks (Exit Points)
- **Library Node**: Save to library collection
- **Export Node**: Export to folder (PDF, Word, JSON, etc.)
- **Webhook Node**: POST results to URL
- **Email Node**: Send results via email

---

## Node Types

### Source Nodes (Green)
| Node | Description | Outputs |
|------|-------------|---------|
| Files | Drag/drop files or folders | `$.files[]` |
| Collection | Library collection | `$.files[]` |
| Search | Search query results | `$.files[]` |
| URL List | Fetch from URLs | `$.files[]` |
| Watch Folder | Monitor folder | `$.files[]` (stream) |

### Vision Nodes (Blue)
| Node | Description | Uses LLM |
|------|-------------|----------|
| Transcribe | OCR/text extraction | Yes (vision) |
| Describe | Image description | Yes (vision) |
| Analyze | Document analysis | Yes (vision) |
| Detect Objects | Find objects in images | Yes (vision) |
| Read Barcode | Extract barcodes/QR | No (local) |

### Transform Nodes (Pink)
| Node | Description | Uses LLM |
|------|-------------|----------|
| Enhance | Image enhancement | No (PIL) |
| Crop | Crop to region | No (PIL) |
| Rotate | Rotate image | No (PIL) |
| Resize | Resize image | No (PIL) |
| Split Pages | Split multi-page docs | No |
| Merge | Combine documents | No |
| Segment | Split by content | Yes (vision) |

### LLM Nodes (Purple)
| Node | Description |
|------|-------------|
| Summarize | Generate summary |
| Translate | Translate text |
| Classify | Categorize document |
| Extract Entities | Pull named entities |
| Extract Fields | Structured extraction |
| Custom Prompt | Free-form LLM call |

### Convert Nodes (Orange)
| Node | Description |
|------|-------------|
| To PDF | Export as PDF |
| To Word | Export as DOCX |
| To Excel | Export as XLSX |
| To JSON | Export as JSON |
| To Markdown | Export as MD |
| To HTML | Export as HTML |

### Logic Nodes (Yellow)
| Node | Description |
|------|-------------|
| IF | Conditional branch |
| Switch | Multi-way branch |
| Loop | For-each iteration |
| Filter | Filter by condition |
| Sort | Sort items |
| Group | Group by field |
| Merge | Combine branches |

### Integration Nodes (Gray)
| Node | Description |
|------|-------------|
| MCP Tool | Call any MCP tool |
| Webhook | HTTP request |
| Email | Send email |
| Slack | Post to Slack |
| S3 | Upload to S3 |

---

## State & Data Flow

### Structured Output Schemas

Each node defines its output schema. For LLM nodes, users can customize the schema to extract exactly the fields they need.

**Example: Named Entity Extraction**
```json
{
  "output_schema": {
    "type": "object",
    "properties": {
      "people": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Names of people mentioned"
      },
      "organizations": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Organization names"
      },
      "dates": {
        "type": "array",
        "items": {"type": "string", "format": "date"},
        "description": "Dates mentioned"
      },
      "locations": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Place names"
      }
    }
  }
}
```

**LLM nodes use structured output mode** (via LangChain's `with_structured_output`) to guarantee the response matches the schema.

### Input Mapping (Flexible References)

Nodes can reference output from ANY previous node, not just the immediately preceding one:

```
┌──────────┐     ┌───────────┐     ┌───────────┐     ┌──────────────┐
│ Transcribe│────>│ Entities  │────>│ Summarize │────>│ Final Report │
└──────────┘     └───────────┘     └───────────┘     └──────────────┘
      │                                                      ▲
      └──────────────────────────────────────────────────────┘
                    (Final Report uses Transcribe output directly)
```

Each input port can specify which output to use:

```python
class InputMapping(BaseModel):
    """Maps a node input to a previous output."""
    source_path: str  # e.g., "$.nodes.transcribe.text" or "$.nodes.entities.people"
    transform: str | None = None  # e.g., "| join:\", \"" or "| json_extract:\"$.name\""
```

### Path Expression Syntax (already in resolver.py)
```
$.files                      # Input files list
$.nodes.transcribe.text      # Output of transcribe node
$.nodes.classify.category    # Classification result
$.config.language            # Workflow config
$.inputs.query               # Runtime input
```

### Transform Pipes (already in resolver.py)
```
$.nodes.transcribe.text | upper          # Uppercase
$.nodes.list.items | join:", "           # Join array
$.nodes.data | json_extract:"$.name"     # JSONPath
$.nodes.transcribe.text | trim           # Trim whitespace
```

### Conditional Expressions
```
$.nodes.transcribe.language == "en"
$.nodes.classify.confidence > 0.8
$.nodes.extract.entity_count >= 5
$.files.length > 0
```

---

## SwiftUI Implementation

### Canvas View
```swift
struct WorkflowCanvasView: View {
    @Binding var workflow: Workflow
    @State private var canvasOffset: CGSize = .zero
    @State private var canvasScale: CGFloat = 1.0
    @State private var selectedNodeIds: Set<String> = []
    @State private var draggedEdge: DraggedEdge? = nil

    var body: some View {
        GeometryReader { geometry in
            ZStack {
                // Grid background
                GridPattern()

                // Edges (connections between nodes)
                ForEach(workflow.edges) { edge in
                    EdgeView(edge: edge, nodes: workflow.nodes)
                }

                // Dragged edge preview
                if let dragged = draggedEdge {
                    DraggedEdgeView(from: dragged.startPoint, to: dragged.currentPoint)
                }

                // Nodes
                ForEach(workflow.nodes) { node in
                    NodeView(
                        node: node,
                        isSelected: selectedNodeIds.contains(node.id),
                        onPortDragStart: { port in
                            startEdgeDrag(from: node, port: port)
                        },
                        onPortDrop: { port in
                            completeEdge(to: node, port: port)
                        }
                    )
                    .position(x: node.positionX, y: node.positionY)
                    .gesture(nodeDragGesture(for: node))
                }
            }
            .scaleEffect(canvasScale)
            .offset(canvasOffset)
            .gesture(canvasPanGesture)
            .gesture(canvasZoomGesture)
            .onDrop(of: [.fileURL], delegate: CanvasDropDelegate(...))
        }
    }
}
```

### Node View with Ports
```swift
struct NodeView: View {
    let node: WorkflowNode
    let isSelected: Bool
    let onPortDragStart: (Port) -> Void
    let onPortDrop: (Port) -> Void

    var body: some View {
        HStack(spacing: 0) {
            // Input ports (left side)
            VStack(spacing: 8) {
                ForEach(node.inputPorts) { port in
                    PortView(port: port, type: .input)
                        .onDrop(of: [.text], delegate: PortDropDelegate(onDrop: { onPortDrop(port) }))
                }
            }

            // Node body
            VStack(spacing: 8) {
                Image(systemName: node.icon)
                    .font(.title2)
                    .foregroundColor(node.color)

                Text(node.name)
                    .font(.caption)
                    .fontWeight(.medium)
            }
            .padding(16)
            .background(
                RoundedRectangle(cornerRadius: 12)
                    .fill(Color(.windowBackgroundColor))
                    .shadow(radius: isSelected ? 8 : 4)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 12)
                    .stroke(isSelected ? node.color : .clear, lineWidth: 2)
            )

            // Output ports (right side)
            VStack(spacing: 8) {
                ForEach(node.outputPorts) { port in
                    PortView(port: port, type: .output)
                        .onDrag {
                            onPortDragStart(port)
                            return NSItemProvider(object: port.id as NSString)
                        }
                }
            }
        }
    }
}
```

### Edge View (Bezier Curve)
```swift
struct EdgeView: View {
    let edge: WorkflowEdge
    let nodes: [WorkflowNode]

    var body: some View {
        Path { path in
            let startPoint = portPosition(nodeId: edge.sourceNodeId, portId: edge.sourcePortId, type: .output)
            let endPoint = portPosition(nodeId: edge.targetNodeId, portId: edge.targetPortId, type: .input)

            // Bezier curve for smooth connection
            let controlPoint1 = CGPoint(x: startPoint.x + 50, y: startPoint.y)
            let controlPoint2 = CGPoint(x: endPoint.x - 50, y: endPoint.y)

            path.move(to: startPoint)
            path.addCurve(to: endPoint, control1: controlPoint1, control2: controlPoint2)
        }
        .stroke(
            edge.isConditional ? Color.orange : Color.secondary,
            style: StrokeStyle(lineWidth: 2, lineCap: .round)
        )
    }
}
```

---

## Backend Changes

### Updated WorkflowDef Model
```python
# src/fichero/workflows/types.py

class PortDef(BaseModel):
    """Input or output port on a node."""
    id: str
    name: str
    type: Literal["input", "output"]
    data_type: str = "any"  # any, files, text, json, image

class NodeDef(BaseModel):
    """Node in workflow graph."""
    id: str
    tool: str                      # Tool function name
    name: str = ""                 # Display name (defaults to tool name)
    config: dict = {}              # Tool-specific config
    position_x: float = 0          # Canvas X position
    position_y: float = 0          # Canvas Y position
    input_ports: list[PortDef] = []   # Input connections
    output_ports: list[PortDef] = []  # Output connections

class EdgeDef(BaseModel):
    """Connection between nodes."""
    id: str
    source_node: str
    source_port: str
    target_node: str
    target_port: str
    condition: str | None = None   # For conditional edges

class WorkflowDef(BaseModel):
    """Complete workflow definition."""
    id: str
    name: str
    description: str = ""
    nodes: list[NodeDef]
    edges: list[EdgeDef]

    # Default LLM settings
    provider: str = "openai"
    model: str = "gpt-4o"

    # Canvas settings
    zoom: float = 1.0
    offset_x: float = 0
    offset_y: float = 0
```

### Tool Registry with Port Definitions
```python
# src/fichero/workflows/registry.py

@dataclass
class ToolDef:
    """Tool definition with ports."""
    name: str
    display_name: str
    category: str
    icon: str
    color: str
    description: str
    input_ports: list[PortDef]
    output_ports: list[PortDef]
    config_schema: dict  # JSON Schema for config
    handler: Callable

TOOLS: dict[str, ToolDef] = {}

def register_tool(
    name: str,
    display_name: str,
    category: str,
    icon: str,
    color: str,
    description: str,
    input_ports: list[PortDef],
    output_ports: list[PortDef],
    config_schema: dict = {},
):
    """Decorator to register a tool."""
    def decorator(fn):
        TOOLS[name] = ToolDef(
            name=name,
            display_name=display_name,
            category=category,
            icon=icon,
            color=color,
            description=description,
            input_ports=input_ports,
            output_ports=output_ports,
            config_schema=config_schema,
            handler=fn,
        )
        return fn
    return decorator
```

### Example Tool Registration
```python
# src/fichero/workflows/tools/transcribe.py

@register_tool(
    name="transcribe",
    display_name="Transcribe",
    category="vision",
    icon="text.viewfinder",
    color="blue",
    description="Extract text from images using vision LLM",
    input_ports=[
        PortDef(id="files", name="Files", type="input", data_type="files"),
    ],
    output_ports=[
        PortDef(id="text", name="Text", type="output", data_type="text"),
        PortDef(id="boxes", name="Boxes", type="output", data_type="json"),
    ],
    config_schema={
        "type": "object",
        "properties": {
            "language": {"type": "string", "default": "en"},
            "return_boxes": {"type": "boolean", "default": False},
        }
    }
)
async def transcribe(state: State, config: dict) -> dict:
    """Transcribe text from images."""
    files = state["outputs"].get(config["input_node"], {}).get("files", [])
    # ... implementation
    return {"text": result, "boxes": boxes}
```

### Logic Nodes

```python
# src/fichero/workflows/tools/logic.py

@register_tool(
    name="if",
    display_name="IF",
    category="logic",
    icon="arrow.triangle.branch",
    color="yellow",
    description="Conditional branching based on expression",
    input_ports=[
        PortDef(id="input", name="Input", type="input", data_type="any"),
    ],
    output_ports=[
        PortDef(id="true", name="True", type="output", data_type="any"),
        PortDef(id="false", name="False", type="output", data_type="any"),
    ],
    config_schema={
        "type": "object",
        "properties": {
            "condition": {
                "type": "string",
                "description": "Condition expression, e.g. $.nodes.classify.category == 'invoice'"
            },
        },
        "required": ["condition"]
    }
)
async def if_node(state: State, config: dict) -> dict:
    """Evaluate condition and route."""
    from fichero.workflows.resolver import evaluate_condition

    result = evaluate_condition(config["condition"], state)
    # LangGraph handles routing based on which output port has data
    return {"_route": "true" if result else "false"}


@register_tool(
    name="loop",
    display_name="Loop",
    category="logic",
    icon="repeat",
    color="yellow",
    description="Iterate over a collection",
    input_ports=[
        PortDef(id="items", name="Items", type="input", data_type="array"),
    ],
    output_ports=[
        PortDef(id="item", name="Item", type="output", data_type="any"),
        PortDef(id="done", name="Done", type="output", data_type="any"),
    ],
    config_schema={
        "type": "object",
        "properties": {
            "parallel": {"type": "integer", "default": 1, "description": "Max parallel iterations"},
        }
    }
)
async def loop_node(state: State, config: dict) -> dict:
    """Process items in loop."""
    # LangGraph's map-reduce pattern handles this
    pass
```

---

## API Endpoints

```python
# src/fichero/api/routes/workflows.py

@router.get("/tools")
async def list_tools() -> list[ToolDef]:
    """List all available tools with their port definitions."""
    return list(TOOLS.values())

@router.get("/tools/{name}")
async def get_tool(name: str) -> ToolDef:
    """Get tool definition by name."""
    if name not in TOOLS:
        raise HTTPException(404, f"Tool not found: {name}")
    return TOOLS[name]

@router.post("/workflows")
async def create_workflow(workflow: WorkflowDef) -> WorkflowDef:
    """Save workflow definition."""
    # Store in DuckDB
    pass

@router.post("/workflows/{id}/run")
async def run_workflow(id: str, inputs: dict = {}) -> str:
    """Start workflow execution, returns task_id."""
    # Build LangGraph and execute
    pass

@router.get("/workflows/{id}/stream")
async def stream_workflow(id: str):
    """SSE stream of workflow progress."""
    # Stream node execution updates
    pass
```

---

## Implementation Phases

### Phase 1: Canvas Foundation (SwiftUI)
- [ ] Free node placement with drag
- [ ] Canvas zoom and pan
- [ ] Node selection (single and multi)
- [ ] Grid background
- [ ] Save/restore canvas state (zoom, offset)

### Phase 2: Edge Connections (SwiftUI)
- [ ] Port views on nodes (input left, output right)
- [ ] Drag from output port to create edge
- [ ] Drop on input port to complete edge
- [ ] Bezier curve edge rendering
- [ ] Delete edges (select + delete key)
- [ ] Edge validation (prevent cycles, type mismatch)

### Phase 3: Node Popover Editor (SwiftUI)
- [ ] Click node to show Audio Hijack style popover
- [ ] Provider/model selection for LLM nodes
- [ ] Tool-specific config form (from JSON Schema)
- [ ] Delete/duplicate actions

### Phase 4: Tool Registry (Python)
- [ ] Port-aware tool definitions
- [ ] Register existing tools with ports
- [ ] Config schema for each tool
- [ ] Tool discovery API endpoint

### Phase 5: Logic Nodes (Python + SwiftUI)
- [ ] IF node with condition expression
- [ ] Switch node with multiple cases
- [ ] Loop node for iteration
- [ ] Filter node
- [ ] Merge node

### Phase 6: Source Nodes (SwiftUI + Python)
- [ ] Files source (drag/drop onto canvas)
- [ ] Collection source (select from library)
- [ ] Search source (query)
- [ ] URL source

### Phase 7: LangGraph Builder Updates (Python)
- [ ] Port-based state routing
- [ ] Multi-output node handling
- [ ] Conditional edge routing by port
- [ ] Loop/iteration with map-reduce

### Phase 8: Execution & Streaming
- [ ] Run workflow API
- [ ] SSE progress stream
- [ ] Node execution status in UI
- [ ] Error handling and retry
- [ ] Cancel workflow

### Phase 9: MCP Integration
- [ ] MCP tool discovery
- [ ] Dynamic MCP node creation
- [ ] MCP tool execution in workflow

### Phase 10: Polish
- [ ] Keyboard shortcuts (delete, duplicate, undo)
- [ ] Copy/paste nodes
- [ ] Workflow templates
- [ ] Export/import workflows
- [ ] Mini-map for large workflows

---

## Data Model Summary

```
┌─────────────────────────────────────────────────────────┐
│                     WorkflowDef                          │
├─────────────────────────────────────────────────────────┤
│ id: string                                               │
│ name: string                                             │
│ nodes: NodeDef[]                                         │
│ edges: EdgeDef[]                                         │
│ provider: string (default LLM)                           │
│ model: string (default LLM)                              │
└─────────────────────────────────────────────────────────┘
              │
              ├──────────────────────┐
              ▼                      ▼
┌─────────────────────────┐  ┌─────────────────────────┐
│        NodeDef          │  │        EdgeDef          │
├─────────────────────────┤  ├─────────────────────────┤
│ id: string              │  │ id: string              │
│ tool: string            │  │ source_node: string     │
│ name: string            │  │ source_port: string     │
│ config: dict            │  │ target_node: string     │
│ position_x: float       │  │ target_port: string     │
│ position_y: float       │  │ condition: string?      │
│ input_ports: PortDef[]  │  └─────────────────────────┘
│ output_ports: PortDef[] │
└─────────────────────────┘
              │
              ▼
┌─────────────────────────┐
│        PortDef          │
├─────────────────────────┤
│ id: string              │
│ name: string            │
│ type: input | output    │
│ data_type: string       │
└─────────────────────────┘
```

---

## Key Files to Create/Modify

| File | Action | Description |
|------|--------|-------------|
| `Fichero-Swift/.../WorkflowCanvasView.swift` | MODIFY | Add free placement, zoom, pan |
| `Fichero-Swift/.../NodeView.swift` | CREATE | Node with input/output ports |
| `Fichero-Swift/.../EdgeView.swift` | CREATE | Bezier curve connections |
| `Fichero-Swift/.../PortView.swift` | CREATE | Draggable port circles |
| `Fichero-Swift/.../Models/Workflow.swift` | MODIFY | Add ports to node model |
| `src/fichero/workflows/types.py` | MODIFY | Add PortDef, update NodeDef |
| `src/fichero/workflows/registry.py` | MODIFY | Add port definitions to tools |
| `src/fichero/workflows/tools/logic.py` | CREATE | IF, Switch, Loop, Filter nodes |
| `src/fichero/workflows/tools/sources.py` | CREATE | Files, Collection, Search sources |
| `src/fichero/api/routes/workflows.py` | MODIFY | Add tool list with ports |

---

## Success Criteria

1. **Visual**: Canvas feels responsive, nodes drag smoothly, edges curve elegantly
2. **Functional**: Can build complex branching workflows visually
3. **Powerful**: Supports conditionals, loops, parallel processing
4. **Integrated**: Works with all existing tools + MCP
5. **Scalable**: Handles 1000s of documents efficiently
6. **Intuitive**: Audio Hijack Pro users feel at home
