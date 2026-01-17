# Workflow Execution & Progress Plan

## Design Principle

**Leverage LangGraph/LangChain's native capabilities - don't reinvent the wheel.**

LangGraph provides:
- **Streaming**: Real-time token/event streaming
- **Checkpointing**: Automatic state persistence & resume
- **Map-Reduce**: Built-in parallel processing pattern
- **Human-in-the-loop**: Pause, review, resume workflows

Our job: Make this power **visible and intuitive** in the UI.

---

## Current State

```
Collection → Transcribe → [output]
     │            │
     └── 2 files ─┘ (processed sequentially)
```

**Problem**: With 400 folders × 200-300 files = 80,000+ files, we need:
- Parallel processing
- Progress indication
- Scalable architecture

---

## Part 1: Execution Model Options

### Option A: Sequential (Current)
```
file1 → transcribe → done
file2 → transcribe → done
file3 → transcribe → done
...
```
- **Pros**: Simple, easy to debug
- **Cons**: 80,000 files × 5 sec = 111 hours

### Option B: Parallel Within Node (Recommended for MVP)
```
┌─ file1 → transcribe ─┐
├─ file2 → transcribe ─┼→ collect results → done
├─ file3 → transcribe ─┤
└─ file4 → transcribe ─┘
```
- **Pros**: Fast, single workflow, easy progress tracking
- **Cons**: Memory usage with many files
- **Implementation**: `asyncio.gather()` with semaphore for rate limiting

### Option C: Batch per Folder
```
LangGraph 1: folder1 (200 files) → parallel transcribe
LangGraph 2: folder2 (200 files) → parallel transcribe
...
```
- **Pros**: Natural batching, can checkpoint per folder
- **Cons**: More complex orchestration

### Option D: Per-File Workflows
```
80,000 separate LangGraph executions
```
- **Pros**: Maximum parallelism, easy resume
- **Cons**: Overhead, complex coordination

**Recommendation**: Start with **Option B** (parallel within node), add folder batching later.

---

## Part 2: LangGraph Native Features to Use

### 2.1 Streaming Events (Already Supported)

LangGraph streams events automatically via `astream_events()`:

```python
async for event in graph.astream_events(initial_state, version="v2"):
    kind = event["event"]
    if kind == "on_chain_start":
        # Node started
    elif kind == "on_chain_end":
        # Node completed
    elif kind == "on_chat_model_stream":
        # LLM token streaming
```

**UI Mapping**:
- `on_chain_start` → Highlight node, show "Running"
- `on_chain_end` → Mark node complete, show results
- `on_chat_model_stream` → Live text preview (optional)

### 2.2 Checkpointing (Built-in)

LangGraph can persist state automatically:

```python
from langgraph.checkpoint.sqlite import SqliteSaver

# Create checkpointer
checkpointer = SqliteSaver.from_conn_string(":memory:")  # or real DB

# Compile with checkpointing
graph = workflow.compile(checkpointer=checkpointer)

# Resume from checkpoint
config = {"configurable": {"thread_id": "my-thread"}}
result = await graph.ainvoke(state, config)
```

**UI Mapping**:
- Show "Resume" button for interrupted workflows
- Display checkpoint timestamp
- Allow "Restart from beginning" option

### 2.3 Map-Reduce Pattern (For Parallel Processing)

LangGraph's `Send` API enables parallel fan-out:

```python
from langgraph.constants import Send

def route_to_parallel(state):
    """Fan out to process each file in parallel."""
    return [
        Send("process_file", {"file": f, "index": i})
        for i, f in enumerate(state["files"])
    ]

# In graph definition
graph.add_conditional_edges("collection", route_to_parallel)
```

This creates parallel branches that LangGraph manages automatically.

**UI Mapping**:
- Show "Processing 10 items in parallel"
- Badge with progress: "5/10 complete"

### 2.4 Interrupt & Resume (Human-in-the-loop)

```python
# Compile with interrupt points
graph = workflow.compile(
    checkpointer=checkpointer,
    interrupt_before=["review_step"],  # Pause before this node
)

# Resume after human review
await graph.ainvoke(None, config)  # Continues from checkpoint
```

**UI Mapping**:
- "Paused for review" indicator
- Show intermediate results
- "Continue" / "Cancel" buttons

---

## Part 3: Parallel Execution Implementation

### 2.1 Add Concurrency Control to Tools

```python
# In transcribe.py
async def transcribe(inputs, state, llm_config):
    files = inputs.get("files", [])

    # Configurable concurrency (default: 10 parallel)
    max_concurrent = inputs.get("max_concurrent", 10)
    semaphore = asyncio.Semaphore(max_concurrent)

    async def process_one(file_path):
        async with semaphore:
            # Process single file
            return await _transcribe_file(file_path, llm_config)

    # Process all files in parallel
    results = await asyncio.gather(
        *[process_one(f) for f in files],
        return_exceptions=True
    )

    return {"results": results, "count": len(results)}
```

### 2.2 Add Progress Events

```python
async def process_one(file_path, progress_callback):
    async with semaphore:
        await progress_callback("started", file_path)
        try:
            result = await _transcribe_file(file_path, llm_config)
            await progress_callback("completed", file_path, result)
            return result
        except Exception as e:
            await progress_callback("failed", file_path, error=str(e))
            raise
```

### 2.3 Rate Limiting by Provider

Different providers have different rate limits:
- OpenAI: 500 RPM (requests per minute)
- Anthropic: 50 RPM
- OpenRouter: varies by model
- Local (Ollama): unlimited

```python
PROVIDER_RATE_LIMITS = {
    "openai": 500,
    "anthropic": 50,
    "openrouter": 60,  # conservative default
    "ollama": 1000,    # effectively unlimited
}
```

---

## Part 3: Progress Indication in UI

### 3.1 Backend → Frontend Communication

**Current**: Polling for status
**Better**: Server-Sent Events (SSE) for real-time updates

```
Backend                          Frontend
   │                                │
   ├─ SSE: node_started ──────────→│ Highlight node
   ├─ SSE: file_progress ─────────→│ Update counter
   ├─ SSE: file_completed ────────→│ Increment done
   ├─ SSE: file_failed ───────────→│ Show error badge
   ├─ SSE: node_completed ────────→│ Mark node done
   └─ SSE: workflow_done ─────────→│ Show results
```

### 3.2 Progress Event Schema

```json
{
  "event": "file_progress",
  "node_id": "963C5C41...",
  "data": {
    "file_path": "/path/to/file.jpg",
    "status": "completed",
    "index": 5,
    "total": 100,
    "duration_ms": 2340
  }
}
```

### 3.3 UI Options for Progress

#### Option 1: Badge Counter on Node
```
┌─────────────────────┐
│  [42/100]           │  ← Small badge top-right
│    📝               │
│  Transcribe         │
│  ████████░░ 42%     │  ← Optional progress bar
└─────────────────────┘
```

#### Option 2: Pulsing Animation
- Node pulses/glows while processing
- Color indicates status:
  - Blue pulse: Running
  - Green: Completed
  - Red: Has errors

#### Option 3: Output Log Table (Current, Enhanced)
```
┌──────────────────┬────────────┬────────────┬──────────┐
│ Document         │ Collection │ Transcribe │ Status   │
├──────────────────┼────────────┼────────────┼──────────┤
│ file_001.jpg     │     ✓      │    ⏳      │ Running  │
│ file_002.jpg     │     ✓      │     ✓      │ Done     │
│ file_003.jpg     │     ✓      │     ✗      │ Failed   │
│ ... 97 more      │            │            │          │
└──────────────────┴────────────┴────────────┴──────────┘
```

**Recommendation**: Combine all three:
1. Badge counter for quick visibility
2. Pulse animation for "alive" feeling
3. Detailed log for debugging

---

## Part 4: Implementation Phases

### Phase 1: Parallel Execution (Backend)
1. Add `asyncio.gather()` to transcribe tool
2. Add `max_concurrent` config option
3. Add per-file progress callbacks
4. Test with 100+ files

### Phase 2: SSE Progress Events
1. Add SSE endpoint for workflow progress
2. Emit events for: node_started, file_progress, file_completed, file_failed, node_completed
3. Frontend subscribes and updates state

### Phase 3: UI Progress Indicators
1. Add badge counter component to workflow nodes
2. Add pulse animation when node is active
3. Enhance output log with per-file status
4. Add "X errors" warning badge

### Phase 4: Scale & Reliability
1. Add checkpointing (resume from failure)
2. Add retry logic for transient errors
3. Add batch API support (OpenAI Batch)
4. Add folder-level batching for huge collections

---

## Part 5: Swift UI Changes Needed

### 5.1 WorkflowNode View Enhancement

```swift
struct WorkflowNodeView: View {
    let node: WorkflowNode
    @State var progress: NodeProgress?  // From SSE

    var body: some View {
        ZStack(alignment: .topTrailing) {
            // Existing node content
            nodeContent
                .overlay(pulseOverlay)  // Pulse when running

            // Progress badge
            if let progress = progress {
                ProgressBadge(
                    completed: progress.completed,
                    total: progress.total,
                    errors: progress.errors
                )
            }
        }
    }
}
```

### 5.2 Progress Badge Component

```swift
struct ProgressBadge: View {
    let completed: Int
    let total: Int
    let errors: Int

    var body: some View {
        HStack(spacing: 2) {
            Text("\(completed)/\(total)")
                .font(.caption2)
            if errors > 0 {
                Image(systemName: "exclamationmark.circle.fill")
                    .foregroundColor(.red)
            }
        }
        .padding(4)
        .background(.regularMaterial)
        .cornerRadius(4)
    }
}
```

### 5.3 SSE Subscription

```swift
func subscribeToWorkflowProgress(threadId: String) -> AsyncStream<WorkflowEvent> {
    AsyncStream { continuation in
        let url = URL(string: "\(baseURL)/workflow-execution/\(threadId)/events")!
        let source = EventSource(url: url)

        source.onMessage { event in
            if let data = event.data?.data(using: .utf8),
               let event = try? JSONDecoder().decode(WorkflowEvent.self, from: data) {
                continuation.yield(event)
            }
        }

        source.connect()
    }
}
```

---

## Summary: Recommended Approach

1. **Execution**: Parallel within node using `asyncio.gather()` with semaphore
2. **Progress**: SSE events streaming file-by-file progress
3. **UI**: Badge counter + pulse animation + detailed log
4. **Scale**: Start with 10 concurrent, tune based on provider rate limits

**Estimated Effort**:
- Phase 1 (Parallel): 2-3 hours
- Phase 2 (SSE): 3-4 hours
- Phase 3 (UI): 4-6 hours
- Phase 4 (Scale): Future iteration

---

## Part 6: Research Findings - LangGraph Native Patterns

### 6.1 Send API for Map-Reduce (Recommended)

The `Send` API is LangGraph's native way to fan-out parallel processing. This is cleaner than `asyncio.gather()` inside a node because LangGraph manages the parallelism:

```python
from langgraph.types import Send

def continue_to_transcribe(state):
    """Fan out to process each file in parallel."""
    return [
        Send("transcribe_file", {"file": f, "index": i})
        for i, f in enumerate(state["files"])
    ]

# Graph definition
builder.add_conditional_edges("collection", continue_to_transcribe, ["transcribe_file"])
builder.add_edge("transcribe_file", "aggregate_results")
```

**Key insight**: Each `Send()` creates an independent branch. LangGraph streams results as each completes:
```
{'transcribe_file': {'result': 'file1 done'}}
{'transcribe_file': {'result': 'file2 done'}}
{'transcribe_file': {'result': 'file3 done'}}
{'aggregate_results': {'total': 3}}
```

### 6.2 Subgraphs for Multiple Concurrent Workflows

For running multiple workflows at once, use **subgraphs**:

```python
# Each workflow becomes a subgraph
workflow_1 = build_graph(workflow_def_1).compile()
workflow_2 = build_graph(workflow_def_2).compile()

# Orchestrator graph runs them
class OrchestratorState(TypedDict):
    workflow_requests: list[dict]
    results: list[dict]

def run_workflow(state):
    # Transform state and invoke subgraph
    result = workflow_1.invoke({"files": state["files"]})
    return {"results": [result]}

orchestrator = StateGraph(OrchestratorState)
orchestrator.add_node("workflow_1", workflow_1)  # Direct add if shared schema
orchestrator.add_node("workflow_2", run_workflow)  # Wrapper if different schema
```

**Two patterns**:
1. **Shared schema**: Add compiled graph directly as node
2. **Different schema**: Wrap in function that transforms state

### 6.3 Streaming from Subgraphs

Stream outputs from all levels with `subgraphs=True`:

```python
for chunk in graph.stream(
    {"files": file_list},
    subgraphs=True,
    stream_mode="updates",
):
    namespace, update = chunk
    # namespace = () for parent, ('node_name:uuid',) for subgraph
    print(f"[{namespace}] {update}")
```

Output includes parent path, so UI can track which subgraph/node is active:
```
((), {'collection': {'files': [...]}})
(('transcribe:abc123',), {'file_1': {'status': 'done'}})
(('transcribe:abc123',), {'file_2': {'status': 'done'}})
((), {'transcribe': {'results': [...]}})
```

### 6.4 Persistence Propagates Automatically

Only need checkpointer on the **parent** graph - subgraphs inherit it:

```python
from langgraph.checkpoint.memory import MemorySaver

checkpointer = MemorySaver()
parent_graph = builder.compile(checkpointer=checkpointer)
# All subgraphs automatically get checkpointing!
```

For subgraphs with **their own memory** (e.g., per-agent message history):
```python
subgraph = subgraph_builder.compile(checkpointer=True)  # Own memory
```

---

## Part 7: Revised Recommendation

Based on research, the **optimal approach** combines LangGraph native patterns:

### For Parallel File Processing (within single workflow)
Use **Send API** instead of `asyncio.gather()`:
- Cleaner separation of concerns
- LangGraph handles parallelism, rate limiting, retries
- Native streaming of per-file progress
- Built-in checkpointing per parallel branch

### For Multiple Concurrent Workflows
Use **Subgraphs** with an orchestrator:
- Each user-defined workflow becomes a subgraph
- Orchestrator manages concurrent execution
- Stream from all levels with `subgraphs=True`
- Single checkpointer handles all persistence

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Orchestrator Graph                        │
│  (manages multiple workflows, handles persistence)           │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │
│  │  Workflow 1  │  │  Workflow 2  │  │  Workflow 3  │       │
│  │  (subgraph)  │  │  (subgraph)  │  │  (subgraph)  │       │
│  └──────────────┘  └──────────────┘  └──────────────┘       │
│         │                │                 │                 │
│    ┌────┴────┐      ┌────┴────┐       ┌────┴────┐           │
│    │ Send()  │      │ Send()  │       │ Send()  │           │
│    │ fan-out │      │ fan-out │       │ fan-out │           │
│    └─────────┘      └─────────┘       └─────────┘           │
│                                                              │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
                    SSE Stream to UI
              (namespaced by workflow/node)
```

### Revised Implementation Phases

**Phase 1: Send API for Parallel Files**
1. Modify builder.py to use `Send()` for multi-file nodes
2. Add `aggregate` node pattern for collecting results
3. Stream per-file progress via existing SSE

**Phase 2: Subgraph Architecture**
1. Refactor `build_graph()` to return compilable subgraph
2. Create orchestrator graph for multi-workflow execution
3. Add workflow queue management

**Phase 3: UI Integration**
1. Parse namespaced stream events to update correct node
2. Track multiple workflows in activity panel
3. Show per-workflow progress badges
