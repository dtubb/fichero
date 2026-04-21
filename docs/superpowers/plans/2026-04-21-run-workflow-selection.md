# Run Workflow — Pass Current Selection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When the user clicks "Run Workflow", pass the currently selected document(s) into the workflow so the Files node fans out over them instead of returning zero files.

**Architecture:** The frontend captures `documentStore.selectedDocument?.id` at execution time and passes it as `inputs["selected_doc_ids"]` in the POST body. `WorkflowStreamService` already serialises `inputs` into the request body as-is. On the backend, `build_initial_state` merges `request.inputs` into LangGraph state, making `state["selected_doc_ids"]` available to every node. The Files tool gets a new priority-0 branch: if `state["selected_doc_ids"]` is non-empty and no explicit upstream `inputs["files"]` is mapped, it loads those documents from the DB and returns them.

**Tech Stack:** Python/FastAPI/LangGraph (backend), SwiftUI/async-await (frontend)

---

## File Map

| File | Change |
|------|--------|
| `fichero-api/src/fichero/workflows/tools/sources.py` | Add `selected_doc_ids` priority-0 branch to `files_tool` |
| `fichero-api/tests/unit/test_workflow_tools.py` | Add tests for the new branch |
| `fichero-swiftui/fichero-swiftui/Views/Workflow/WorkflowEditor+Actions.swift` | Pass `selected_doc_ids` in `execute()` call |

---

## Task 1: Failing test — files_tool with selected_doc_ids

**Files:**
- Modify: `fichero-api/tests/unit/test_workflow_tools.py`

- [ ] **Step 1: Add the two failing tests at the end of `test_workflow_tools.py`**

Find the end of the file and append:

```python
# =============================================================================
# Tests: files_tool with selected_doc_ids
# =============================================================================

@pytest.mark.asyncio
async def test_files_tool_uses_selected_doc_ids(mock_state, mock_llm_config, mock_documents):
    """files_tool resolves documents from selected_doc_ids in state."""
    doc = mock_documents[0]  # doc1, path="/test/image1.jpg"
    state = {**mock_state, "selected_doc_ids": [doc.id]}

    mock_db = MagicMock()
    mock_db.get.return_value = doc

    with patch("fichero.workflows.tools.sources.db_manager") as mock_dm:
        mock_dm.get_database.return_value = mock_db
        from fichero.workflows.tools.sources import files_tool
        result = await files_tool(inputs={}, state=state, llm_config=mock_llm_config)

    assert result["files"] == ["/test/image1.jpg"]
    assert result["count"] == 1
    assert result["documents"][0]["id"] == doc.id


@pytest.mark.asyncio
async def test_files_tool_selected_doc_ids_skips_missing(mock_state, mock_llm_config, mock_documents):
    """files_tool skips doc IDs that the DB cannot resolve."""
    state = {**mock_state, "selected_doc_ids": ["missing-id", mock_documents[1].id]}

    mock_db = MagicMock()
    # First call returns None (not found), second returns a real doc
    mock_db.get.side_effect = [None, mock_documents[1]]

    with patch("fichero.workflows.tools.sources.db_manager") as mock_dm:
        mock_dm.get_database.return_value = mock_db
        from fichero.workflows.tools.sources import files_tool
        result = await files_tool(inputs={}, state=state, llm_config=mock_llm_config)

    assert result["count"] == 1
    assert result["files"] == [mock_documents[1].path]


@pytest.mark.asyncio
async def test_files_tool_explicit_inputs_override_selected_doc_ids(mock_state, mock_llm_config, mock_documents):
    """Explicit inputs['files'] takes priority over selected_doc_ids."""
    state = {**mock_state, "selected_doc_ids": [mock_documents[0].id]}

    from fichero.workflows.tools.sources import files_tool
    result = await files_tool(
        inputs={"files": ["/explicit/override.pdf"]},
        state=state,
        llm_config=mock_llm_config,
    )

    assert result["files"] == ["/explicit/override.pdf"]
    assert result["count"] == 1
```

- [ ] **Step 2: Run the tests to confirm they fail**

```bash
cd /Users/danieltubb/code/fichero-0.0.2
PYTHONPATH=fichero-api/src .venv/bin/pytest fichero-api/tests/unit/test_workflow_tools.py::test_files_tool_uses_selected_doc_ids fichero-api/tests/unit/test_workflow_tools.py::test_files_tool_selected_doc_ids_skips_missing fichero-api/tests/unit/test_workflow_tools.py::test_files_tool_explicit_inputs_override_selected_doc_ids -v
```

Expected: All 3 FAIL (the first two will return empty files, the third should already pass since explicit inputs work).

- [ ] **Step 3: Commit the failing tests**

```bash
git add fichero-api/tests/unit/test_workflow_tools.py
git commit -m "test: failing tests for files_tool selected_doc_ids resolution (#609)"
```

---

## Task 2: Implement — files_tool selected_doc_ids branch

**Files:**
- Modify: `fichero-api/src/fichero/workflows/tools/sources.py:67-98`

- [ ] **Step 4: Replace the `files_tool` body with the new priority order**

In `sources.py`, replace the entire `files_tool` function body (lines 72–98) with:

```python
async def files_tool(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Return files/documents already provided to this workflow execution.

    Priority:
    1. Explicit inputs["files"] from mapped upstream data
    2. state["selected_doc_ids"] — document IDs passed from the UI selection
    3. state["input_files"] from executor initialization
    """
    # Priority 1: explicit upstream mapping
    raw_files = inputs.get("files")
    if raw_files is not None:
        if isinstance(raw_files, str):
            files = [raw_files]
        else:
            files = list(raw_files or [])
        raw_documents = inputs.get("documents") or state.get("documents", [])
        documents = list(raw_documents or [])
        logger.info(f"Files source tool: {len(files)} files from explicit inputs")
        return {"files": files, "documents": documents, "count": len(files)}

    # Priority 2: UI selection passed via execute inputs
    selected_doc_ids = state.get("selected_doc_ids", [])
    if selected_doc_ids:
        library_path = state.get("library_path")
        if library_path:
            db = db_manager.get_database(library_path)
            docs = [db.get(Document, doc_id) for doc_id in selected_doc_ids]
            docs = [d for d in docs if d is not None]
            files = [d.path for d in docs if d.path]
            documents = [d.model_dump() for d in docs]
            logger.info(f"Files source tool: {len(files)} files from selected_doc_ids")
            return {"files": files, "documents": documents, "count": len(files)}

    # Priority 3: executor-level input_files
    raw_files = state.get("input_files", [])
    if isinstance(raw_files, str):
        files = [raw_files]
    else:
        files = list(raw_files or [])

    raw_documents = state.get("documents", [])
    documents = list(raw_documents or [])

    logger.info(f"Files source tool: {len(files)} files from input_files")
    return {"files": files, "documents": documents, "count": len(files)}
```

- [ ] **Step 5: Run the tests — expect all 3 to pass**

```bash
cd /Users/danieltubb/code/fichero-0.0.2
PYTHONPATH=fichero-api/src .venv/bin/pytest fichero-api/tests/unit/test_workflow_tools.py::test_files_tool_uses_selected_doc_ids fichero-api/tests/unit/test_workflow_tools.py::test_files_tool_selected_doc_ids_skips_missing fichero-api/tests/unit/test_workflow_tools.py::test_files_tool_explicit_inputs_override_selected_doc_ids -v
```

Expected: All 3 PASS.

- [ ] **Step 6: Run the full unit suite to check for regressions**

```bash
cd /Users/danieltubb/code/fichero-0.0.2
PYTHONPATH=fichero-api/src .venv/bin/pytest fichero-api/tests/unit/ --ignore=fichero-api/tests/unit/_archived -x -q
```

Expected: All pass (or same failures as before this change).

- [ ] **Step 7: Lint**

```bash
cd /Users/danieltubb/code/fichero-0.0.2
ruff check fichero-api/src/
```

Expected: No new errors.

- [ ] **Step 8: Commit**

```bash
git add fichero-api/src/fichero/workflows/tools/sources.py
git commit -m "fix: files_tool resolves documents from UI selection via selected_doc_ids (#609)"
```

---

## Task 3: Frontend — pass selected_doc_ids in execute call

**Files:**
- Modify: `fichero-swiftui/fichero-swiftui/Views/Workflow/WorkflowEditor+Actions.swift:54-56`

- [ ] **Step 9: Capture selection and pass it in the execute call**

In `WorkflowEditor+Actions.swift`, find this block (around line 49–56):

```swift
let workflowId = editingWorkflow.id  // Capture ID before closure

// Track completion with a continuation
var streamCompleted = false

let response = try await workflowStreamService.execute(
    workflowId: workflowId,
    inputs: [:],
```

Replace with:

```swift
let workflowId = editingWorkflow.id  // Capture ID before closure

// Capture current selection — the Files node reads this from state["selected_doc_ids"]
let selectedIds: [String]
if let docId = documentStore.selectedDocument?.id {
    selectedIds = [docId]
} else {
    selectedIds = []
}

// Track completion with a continuation
var streamCompleted = false

let response = try await workflowStreamService.execute(
    workflowId: workflowId,
    inputs: ["selected_doc_ids": selectedIds],
```

- [ ] **Step 10: Build the Swift target**

Use Xcode MCP `mcp__xcode__BuildProject` or:

```bash
xcodebuild build \
  -workspace fichero-swiftui/fichero-swiftui.xcodeproj/project.xcworkspace \
  -scheme fichero-swiftui \
  -destination "platform=macOS" \
  -derivedDataPath /tmp/fichero-build \
  | tail -5
```

Expected: `** BUILD SUCCEEDED **`

- [ ] **Step 11: Run SwiftLint**

```bash
swiftlint lint fichero-swiftui/fichero-swiftui/
```

Expected: No new errors or warnings.

- [ ] **Step 12: Commit**

```bash
git add fichero-swiftui/fichero-swiftui/Views/Workflow/WorkflowEditor+Actions.swift
git commit -m "fix: pass selected_doc_ids to workflow execute so Files node receives UI selection (#609)"
```

---

## Task 4: Manual verification

- [ ] **Step 13: Start the backend**

```bash
cd /Users/danieltubb/code/fichero-0.0.2
PYTHONPATH=fichero-api/src .venv/bin/uvicorn fichero.api.main:app --port 8765
```

- [ ] **Step 14: On-device test**

1. Open Fichero.
2. Select a document in the library.
3. Open a workflow that uses the Files node.
4. Click Run Workflow.
5. Confirm in the output log that the Files node shows `> 0` files and the fan_out node processes the selected document.

Previously the log showed: `No files from <id> to fan out`
Expected now: The selected document appears in the node progress.

- [ ] **Step 15: Close issue #609**

```bash
gh issue close 609 --comment "Fixed: Files node now reads selected_doc_ids from workflow execute inputs. Selected document is passed from the toolbar at run time."
```
