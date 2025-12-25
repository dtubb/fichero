
## Workflow Editor View

When user clicks on a Workflow in the sidebar, the **Editor pane** shows a **node-based canvas**:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ EDITOR: Workflow "Full Analysis"                                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                        NODE CANVAS                                   │    │
│  │                                                                     │    │
│  │   ┌──────────┐      ┌──────────┐      ┌──────────┐                 │    │
│  │   │  START   │──────│TRANSCRIBE│──────│ ENTITIES │─────┐           │    │
│  │   │          │      │          │      │          │     │           │    │
│  │   │ 50 docs  │      │ Qwen VL  │      │ GPT-4o   │     │           │    │
│  │   └──────────┘      └──────────┘      └──────────┘     │           │    │
│  │                                                         │           │    │
│  │                                       ┌──────────┐     │           │    │
│  │                                       │ SUMMARIZE│◄────┘           │    │
│  │                                       │          │                 │    │
│  │                                       │ Claude 3 │                 │    │
│  │                                       └────┬─────┘                 │    │
│  │                                            │                       │    │
│  │                                       ┌────▼─────┐                 │    │
│  │                                       │   END    │                 │    │
│  │                                       │          │                 │    │
│  │                                       │  Export  │                 │    │
│  │                                       └──────────┘                 │    │
│  │                                                                     │    │
│  │  [+ Add Step]                                         [▶ Run]      │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│ STEP EDITOR (when step selected)                                            │
├─────────────────────────────────────────────────────────────────────────────┤
│  Step: TRANSCRIBE                                                           │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ Tool:     [Transcribe OCR ▾]                                        │    │
│  │ Provider: [DashScope ▾]         Model: [Qwen VL Max ▾]              │    │
│  │ Prompt:   [Default transcription prompt...                     ]    │    │
│  │ Options:  ☐ Skip existing  ☑ High concurrency (30 requests)        │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Workflow Execution View (Animated)

When **[▶ Run]** is clicked, the canvas **animates** showing progress through nodes:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ RUNNING: Workflow "Full Analysis"                    [⏹ Stop] [⏸ Pause]    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                        NODE CANVAS (animated)                        │    │
│  │                                                                     │    │
│  │   ┌──────────┐      ┌──────────┐      ┌──────────┐                 │    │
│  │   │  ✓ DONE  │━━━━━▶│🔄 RUNNING│- - - │ PENDING  │                 │    │
│  │   │  START   │      │TRANSCRIBE│      │ ENTITIES │                 │    │
│  │   │ 50/50    │      │ 23/50    │      │ 0/50     │                 │    │
│  │   └──────────┘      └──────────┘      └──────────┘                 │    │
│  │       ✓                 🔄                 ○                        │    │
│  │                                                                     │    │
│  │   Progress: ████████████░░░░░░░░░░░░░░░░░░ 46%                     │    │
│  │   ETA: 2m 15s remaining                                            │    │
│  │                                                                     │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│ OUTPUT (columnar log)                                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│ Document              │ Transcribe    │ Entities      │ Summarize     │    │
│───────────────────────┼───────────────┼───────────────┼───────────────│    │
│ letter_001.jpg        │ ✓ 2.3s        │ ✓ 1.1s        │ ○ pending     │    │
│ letter_002.jpg        │ ✓ 2.1s        │ ✓ 0.9s        │ ○ pending     │    │
│ letter_003.jpg        │ ✓ 3.5s        │ 🔄 running    │ ○ pending     │    │
│ letter_004.jpg        │ 🔄 running    │ ○ pending     │ ○ pending     │    │
│ letter_005.jpg        │ 🔄 running    │ ○ pending     │ ○ pending     │    │
│ letter_006.jpg        │ ○ queued      │ ○ pending     │ ○ pending     │    │
│ ...                   │               │               │               │    │
├───────────────────────┴───────────────┴───────────────┴───────────────┤    │
│ ✓ 23 completed │ 🔄 5 running │ ○ 22 pending │ ⚠ 0 failed            │    │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Animation Details:

1. **Node pulses** when it's the active step
2. **Connector arrows animate** (flowing dots) showing data flow
3. **Progress bar** fills as work completes
4. **Status icons** in nodes update:
   - ○ Pending (grey)
   - 🔄 Running (blue, animated spinner)
   - ✓ Done (green checkmark)
   - ✗ Failed (red X)

---

## Output Log (Bottom Panel)

The bottom panel shows **columnar output** - one column per workflow step:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ OUTPUT LOG                                          [Export CSV] [Clear]   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│ ┌──────────────────┬───────────────┬───────────────┬───────────────┐       │
│ │ Document         │ 1. Transcribe │ 2. Entities   │ 3. Summarize  │       │
│ │                  │    (Qwen)     │    (GPT-4o)   │    (Claude)   │       │
│ ├──────────────────┼───────────────┼───────────────┼───────────────┤       │
│ │ letter_001.jpg   │ ✓ 2.3s $0.002 │ ✓ 1.1s $0.01  │ ✓ 0.8s $0.003 │       │
│ │                  │ 847 tokens    │ 234 tokens    │ 156 tokens    │       │
│ ├──────────────────┼───────────────┼───────────────┼───────────────┤       │
│ │ letter_002.jpg   │ ✓ 2.1s $0.002 │ ✓ 0.9s $0.008 │ 🔄 running... │       │
│ │                  │ 623 tokens    │ 187 tokens    │               │       │
│ ├──────────────────┼───────────────┼───────────────┼───────────────┤       │
│ │ letter_003.jpg   │ ✗ ERROR       │ ○ skipped     │ ○ skipped     │       │
│ │                  │ Rate limited  │               │               │       │
│ │                  │ [Retry]       │               │               │       │
│ ├──────────────────┼───────────────┼───────────────┼───────────────┤       │
│ │ letter_004.jpg   │ 🔄 running... │ ○ pending     │ ○ pending     │       │
│ │                  │               │               │               │       │
│ └──────────────────┴───────────────┴───────────────┴───────────────┘       │
│                                                                             │
│ TOTALS: 23 ✓ completed │ 5 🔄 running │ 22 ○ pending │ 1 ✗ failed          │
│         $0.47 spent │ 12,456 tokens │ ETA: 2m 15s                          │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Clicking a Cell:

When you click on a completed cell, shows the **artifact preview**:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Artifact: letter_001.jpg → Transcription                      [✓] [Copy]   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Dear Mary,                                                                 │
│                                                                             │
│  I am writing to you from Liverpool. The journey was long but I arrived    │
│  safely yesterday evening. The weather here is quite cold, much colder     │
│  than I expected for this time of year.                                    │
│                                                                             │
│  I have found lodgings near the docks as you suggested. The landlady is    │
│  a kind woman named Mrs. Henderson who reminds me somewhat of your         │
│  mother...                                                                  │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│ Provider: Qwen VL Max │ Tokens: 847 │ Cost: $0.002 │ Confidence: 0.94      │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## LangGraph Integration

The visual nodes map directly to LangGraph StateGraph:

```python
# src/fichero/workflows/executor.py

from langgraph.graph import StateGraph, START, END

class WorkflowExecutor:
    """Execute workflows using LangGraph with visual feedback."""

    def build_graph(self, workflow: Workflow) -> StateGraph:
        """Build LangGraph from Workflow model."""

        builder = StateGraph(WorkflowState)

        # Add nodes from workflow steps
        for step in workflow.steps:
            builder.add_node(step["name"], self._make_node(step))

        # Chain nodes: START → step1 → step2 → ... → END
        steps = workflow.steps
        builder.add_edge(START, steps[0]["name"])
        for i in range(len(steps) - 1):
            builder.add_edge(steps[i]["name"], steps[i + 1]["name"])
        builder.add_edge(steps[-1]["name"], END)

        return builder.compile()

    def _make_node(self, step: dict):
        """Create a node function that processes documents."""

        async def node_fn(state: WorkflowState) -> WorkflowState:
            provider = db.get(Provider, step["provider_id"])
            model = db.get(Model, step["model_id"])
            api_key = get_api_key(provider.name)

            if not api_key and provider.provider_type not in ["ollama", "lmstudio"]:
                raise MissingAPIKeyError(provider.name)

            # Process documents
            for doc_id in state["pending_docs"]:
                # Emit progress event (for UI animation)
                self._emit_progress(step["name"], doc_id, "running")

                result = await self._process_doc(doc_id, step, api_key, model)

                # Save artifact
                artifact = Artifact(
                    document_id=doc_id,
                    artifact_type=step["artifact_type"],
                    content=result["content"],
                    provider=provider.name,
                    model=model.model_id,
                    run_id=state["run_id"]
                )
                db.save(artifact)

                self._emit_progress(step["name"], doc_id, "completed")

            return state

        return node_fn
```