(AI generated. Not reviewed.)

# Workflows, Activity, and Curation

## Table of Contents

- [Workflow Architecture](#workflow-architecture)
- [Execution and Activity](#execution-and-activity)
- [Notes and Annotations APIs](#notes-and-annotations-apis)
- [Entity and Claim Curation](#entity-and-claim-curation)

## Workflow Architecture

Fichero workflows are visually authored in SwiftUI and executed in Python.

The main backend modules are:

- `workflows/registry.py`: tool definitions and port specs
- `workflows/builder.py`: converts stored workflow definitions into executable graphs
- `workflows/executor.py`: execution engine
- `api/routes/workflow_execution/`: runtime routes for execution, status, thread history, and related operations

The important architectural rule is that the backend owns graph execution semantics. The frontend sends workflow definitions and launch inputs; it does not try to build LangGraph structures itself.

## Execution and Activity

On the Swift side, workflow runs are surfaced through:

- `WorkflowStreamService` for streaming execution events
- `WorkflowExecutionObserver` for app-level run state
- activity views and sidebar indicators

Selection-driven runs in library views pass the full selected document set into the workflow input payload. That behavior is intentional so catalogue-style or aggregation workflows can operate on the whole selection rather than being forced into one-document-at-a-time semantics.

On the backend, workflow execution routes also maintain thread history and run data. Thread deletion and historical run inspection live under the `workflow_execution` route package, not as ad hoc UI-only state.

## Notes and Annotations APIs

Document notes and annotations are separate backend concepts and separate user surfaces.

Annotations:

- route family: `/api/annotations`
- support creation, patching, deletion, crop extraction, and promotion into claims
- are tied to document regions, spans, or page-level references

Notes:

- are document-linked free-text records
- are loaded and updated independently of annotation state

The split is visible in the SwiftUI inspector and is backed by distinct backend responsibilities.

## Entity and Claim Curation

Current curation work is split across entity and claim routes.

On the frontend, the inspector already exposes:

- approve
- reject
- suppress
- merge
- prune trivial claims

On the backend, those actions map to explicit curation services and route families rather than to local-only UI state.

Two implementation details matter for contributors:

1. Library-wide suppression can create persistent rules, so a curation action can outlive the current document view.
2. Entity merge and split operations have audit history and undo semantics in the current design, which is why the app can show curation history instead of treating merges as opaque destructive actions.
