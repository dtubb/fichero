# Orphan + Dead-File Triage

Scope: `scripts/check_xcode_registration.py` KNOWN_VIOLATIONS and `scripts/check_dead_files.py` KNOWN_VIOLATIONS.

Method: grep the file name in `fichero/fichero.xcodeproj/project.pbxproj` and scan the primary type name(s) across `fichero/fichero/**/*.swift`, excluding the file itself from the reference count.

## Counts

- Orphan backlog entries: 8
- Dead-file backlog entries: 32
- `FALSE_POSITIVE`: 0
- `NEEDS_REGISTRATION`: 8
- `DEAD`: 32

## Results

| Backlog | File | In `project.pbxproj`? | Primary type(s) | Referenced elsewhere? | Verdict |
| --- | --- | --- | --- | --- | --- |
| Orphan | `fichero/fichero/Services/APIEndpoints.swift` | no | APIEndpoints, Health, Documents, Workflows, Search, Chat, Providers, Storage, Ingest, Batches, Activity, Schedules, Triggers, Folders, EndpointDefinition | yes | `NEEDS_REGISTRATION` |
| Orphan | `fichero/fichero/Services/FolderService.swift` | no | FolderViewInfo, CodingKeys, FolderViewsResponse, CodingKeys, FolderService | yes | `NEEDS_REGISTRATION` |
| Orphan | `fichero/fichero/Views/Chat/MessageBubble.swift` | no | MessageBubble | yes | `NEEDS_REGISTRATION` |
| Orphan | `fichero/fichero/Views/Chat/ScopedDocumentRow.swift` | no | ScopedDocumentRow | yes | `NEEDS_REGISTRATION` |
| Orphan | `fichero/fichero/Views/Library/ArtifactsBrowserView.swift` | no | ArtifactsBrowserView, ArtifactSortOrder | no | `NEEDS_REGISTRATION` |
| Orphan | `fichero/fichero/Views/Library/ConnectionBanner.swift` | no | ConnectionBanner | no | `NEEDS_REGISTRATION` |
| Orphan | `fichero/fichero/Views/Library/DocumentInspector/DocumentInspectorContentState.swift` | no | n/a | no | `NEEDS_REGISTRATION` |
| Orphan | `fichero/fichero/Views/Workflow/WorkflowNodeView+Preview.swift` | no | n/a | no | `NEEDS_REGISTRATION` |
| Dead | `fichero/fichero/Models/CacheModel.swift` | yes | CacheModel, CacheWrapper | no | `DEAD` |
| Dead | `fichero/fichero/Models/DragDropModel.swift` | yes | DragDropModel | no | `DEAD` |
| Dead | `fichero/fichero/Views/Actions/ActionPickerView.swift` | yes | ActionPickerView, CategoryTab, DraggableActionCard, ActionDragData, CompactActionPicker, CompactActionRow | no | `DEAD` |
| Dead | `fichero/fichero/Views/Agents/AgentConfigurationView.swift` | yes | AgentConfigurationView, ToolSelectionView, ToolRow, ToolCategory, ToolItem | no | `DEAD` |
| Dead | `fichero/fichero/Views/Agents/AgentSettingsView.swift` | yes | AgentSettingsView, AgentTypeSettingsView, AgentTypeConfig, AgentSettings | no | `DEAD` |
| Dead | `fichero/fichero/Views/Automation/ScheduleCreationSheet.swift` | yes | ScheduleCreationSheet | no | `DEAD` |
| Dead | `fichero/fichero/Views/Automation/TriggerCreationSheet.swift` | yes | TriggerCreationSheet | no | `DEAD` |
| Dead | `fichero/fichero/Views/Components/ScheduleRow.swift` | yes | ScheduleAction, ScheduleRow | no | `DEAD` |
| Dead | `fichero/fichero/Views/Components/TriggerRow.swift` | yes | TriggerAction, TriggerRow | no | `DEAD` |
| Dead | `fichero/fichero/Views/ContentView+Actions.swift` | yes | ChatScopeBuilder | no | `DEAD` |
| Dead | `fichero/fichero/Views/Integrations/IntegrationsView.swift` | yes | IntegrationsView | no | `DEAD` |
| Dead | `fichero/fichero/Views/KnowledgeGraph/OntologyBrowser/ClaimSummaryCard+Provenance.swift` | yes | ProvenanceBadge | no | `DEAD` |
| Dead | `fichero/fichero/Views/KnowledgeGraph/OntologyBrowser/EntityDetailView+Biography.swift` | yes | MentionSummary | no | `DEAD` |
| Dead | `fichero/fichero/Views/KnowledgeGraph/OntologyBrowser/OntologyBrowser+Toolbar.swift` | yes | EntityKindChip | no | `DEAD` |
| Dead | `fichero/fichero/Views/Library/ArtifactsBrowserView.swift` | no | ArtifactsBrowserView, ArtifactSortOrder | no | `DEAD` |
| Dead | `fichero/fichero/Views/Library/ConnectionBanner.swift` | no | ConnectionBanner | no | `DEAD` |
| Dead | `fichero/fichero/Views/Library/ImageViewer/ImageZoomToolbar.swift` | yes | ImageZoomToolbar | no | `DEAD` |
| Dead | `fichero/fichero/Views/Library/LibraryView+ColumnConfig.swift` | yes | ColumnDefinition | no | `DEAD` |
| Dead | `fichero/fichero/Views/Library/LibraryView+DisplayModes.swift` | yes | KgKindMapping | no | `DEAD` |
| Dead | `fichero/fichero/Views/Library/LibraryView+KeyboardShortcuts.swift` | yes | ArrowDirection, LibrarySelectAllKey, LibraryDeleteSelectionKey, LibrarySortFieldKey, LibrarySortAscendingKey | no | `DEAD` |
| Dead | `fichero/fichero/Views/Library/ScrollWheelZoom.swift` | yes | ScrollWheelZoomView, ScrollWheelCaptureView | no | `DEAD` |
| Dead | `fichero/fichero/Views/MCPServers/MCPToolsCatalogView.swift` | yes | MCPToolsCatalogView, MCPToolRow | no | `DEAD` |
| Dead | `fichero/fichero/Views/Menu/ImagePreviewMenuCommands.swift` | yes | MagnifierLimits | no | `DEAD` |
| Dead | `fichero/fichero/Views/Search/SearchFiltersPanel.swift` | yes | SearchFiltersPanel | no | `DEAD` |
| Dead | `fichero/fichero/Views/Settings/AISettingsView+Helpers.swift` | yes | TierCapability | no | `DEAD` |
| Dead | `fichero/fichero/Views/Sidebar/ActivityDataProcessing.swift` | yes | ActivityWorkflowGroup | no | `DEAD` |
| Dead | `fichero/fichero/Views/Sidebar/SidebarView+ActivityRows.swift` | yes | ActivityRunGridCell | no | `DEAD` |
| Dead | `fichero/fichero/Views/Sidebar/SidebarView+UnifiedLibrarySections.swift` | yes | UnifiedLibraryBuckets | no | `DEAD` |
| Dead | `fichero/fichero/Views/Toolbars/SearchViewToolbar.swift` | yes | SearchViewToolbar | no | `DEAD` |
| Dead | `fichero/fichero/Views/Workflow/DynamicConfigView+FieldRendering.swift` | yes | DynamicFolderPickerOption | no | `DEAD` |
| Dead | `fichero/fichero/Views/Workflow/SimpleWorkflowView.swift` | yes | SimpleWorkflowView, SimpleWorkflow | no | `DEAD` |
| Dead | `fichero/fichero/Views/Workflow/WorkflowExecutionView.swift` | yes | WorkflowExecutionView, ThreadRow, ThreadDetailSheet, ThreadDetailContent, DetailRow | no | `DEAD` |

## Triage Summary

- Every orphan backlog entry is still absent from `project.pbxproj`, so the registration backlog is still real.
- Every dead-file backlog entry still has no external type reference in the Swift tree, so none of those entries are false positives.
