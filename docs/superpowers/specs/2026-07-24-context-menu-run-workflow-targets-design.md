# Context-menu workflow targets

## Goal

Let people run a workflow from a file or folder context menu in the Sidebar and Library. The action uses the clicked target rather than stale unrelated selection.

## Scope

- Files contribute their document ID.
- Folders contribute IDs of their direct child files only.
- When the clicked target is selected, all selected files and folders contribute targets.
- When the clicked target is not selected, it is the only target.
- Target IDs are de-duplicated and passed once to the existing batch workflow executor.
- Empty folders do not offer **Run Workflow**.

## Deliberate exclusions

- Do not recurse into nested folders.
- Do not run a separate workflow per folder.
- Do not change workflow execution, provider/model selection, SSE handling, or Activity behavior.
- Do not alter workflow-catalogue management menus.

## Design

A small pure target resolver will accept the context-clicked item, the active selection, and the current visible document collection. It returns direct file document IDs after applying the selection rule above.

Both Sidebar and Library context menus will use that resolver before showing the existing Run Workflow submenu. Existing workflow/provider menu grouping and the existing batch executor remain the single execution path.

## Error and empty states

No workflow action is shown when resolution returns no files. The existing executor remains responsible for reporting execution failures.

## Regression coverage

Unit coverage will prove:

1. one file resolves to itself;
2. one folder resolves to direct files only;
3. nested descendants are excluded;
4. file and folder selections union and de-duplicate;
5. a right-clicked unselected target ignores unrelated selection;
6. empty folders resolve to no action.

Focused integration/source coverage will prove both Sidebar and Library use the shared resolver before invoking the existing batch workflow path.
