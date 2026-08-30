# 8. Workflows, Activity, and Curation


### Workflow architecture

Workflows are visually authored in SwiftUI and executed in Python. Main backend modules: `workflows/registry.py` (tool definitions and port specs), `workflows/builder.py` (stored definitions → executable graphs), `workflows/executor.py` and `execution/runner.py` (execution engine; the runner compiles the LangGraph `StateGraph`), and `api/routes/workflow_execution/` (runtime routes for execution, status, thread history). The rule: the backend owns graph-execution semantics. The frontend sends workflow definitions and launch inputs; it never builds LangGraph structures itself.

### Execution and activity

On the Swift side, runs surface through `WorkflowStreamService` (streaming execution events), `WorkflowExecutionObserver` (app-level run state), and the activity views and sidebar indicators. Selection-driven runs pass the full selected document set into the workflow input payload, deliberately, so catalogue-style or aggregation workflows can operate on the whole selection. On the backend, thread history, thread deletion, and historical run inspection live under the `workflow_execution` route package — not as ad hoc UI-only state.

### Notes and annotations

Notes and annotations are separate backend concepts and separate user surfaces. Annotations (`/api/annotations` family) support creation, patching, deletion, crop extraction, and promotion into claims, and are tied to document regions, spans, or page references. Notes are document-linked free-text records, loaded and updated independently.

### Entity and claim curation

The inspector exposes approve, reject, suppress, merge, and prune-trivial actions; on the backend those map to explicit curation services and route families, not local UI state. Two details matter: library-wide suppression can create persistent rules that outlive the current document view, and entity merge/split operations carry audit history and undo semantics — which is why the app can show curation history instead of treating merges as opaque destructive actions.
