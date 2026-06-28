# Worker Report

## 2026-06-28

- Audited `docs/user/*.md` against the current SwiftUI client and merged engine routes, focusing on the user-facing pages most likely to drift.
- Corrected the stale onboarding/startup claims in [docs/user/getting-started.md](/Users/danieltubb/code/fichero-worktrees/ms-docs/docs/user/getting-started.md) to match the shipped local-library-first flow and the current backend connection behavior.
- Corrected the inspector/sidebar wording in [docs/user/interface-tour.md](/Users/danieltubb/code/fichero-worktrees/ms-docs/docs/user/interface-tour.md) and [docs/user/reading-and-editing.md](/Users/danieltubb/code/fichero-worktrees/ms-docs/docs/user/reading-and-editing.md) to match the current tab set and note metadata behavior.
- Corrected the AI settings and remote-access wording in [docs/user/ai-and-privacy.md](/Users/danieltubb/code/fichero-worktrees/ms-docs/docs/user/ai-and-privacy.md), and softened macOS-only wording in [docs/user/what-fichero-is.md](/Users/danieltubb/code/fichero-worktrees/ms-docs/docs/user/what-fichero-is.md).
- Verified claims against these code paths:
  - onboarding/library startup: `fichero/fichero/Views/Onboarding/FirstRunWindow.swift`, `fichero/fichero/Models/LibraryManager.swift`, `fichero/fichero/Models/LibraryManager+Operations.swift`
  - backend connection states: `fichero/fichero/Views/ContentView.swift`, `fichero/fichero/Views/Components/BackendConnectionView.swift`
  - sidebar modes and shortcuts: `fichero/fichero/Views/Sidebar/SidebarModeBar.swift`, `fichero/fichero/Views/Menu/ViewMenuCommands.swift`, `fichero/fichero/Models/SidebarViewTypes.swift`
  - inspector tabs and note/annotation surfaces: `fichero/fichero/Views/Library/InspectorTab.swift`, `fichero/fichero/Views/Library/DocumentInspector/DocumentNotesTab.swift`, `fichero/fichero/Views/Notes/NotesInspectorPane.swift`, `fichero/fichero/Views/Library/DocumentInspector/DocumentInspectorAnnotationsTab.swift`, `fichero/fichero/Views/Library/AnnotationsInspectorPane.swift`
  - search/import/provider settings: `fichero/fichero/Views/Search/SearchView.swift`, `fichero/fichero/Views/Menu/AddItemMenu.swift`, `fichero/fichero/Services/ImportServiceGenerated.swift`, `fichero/fichero/Views/Settings/AISettingsView.swift`, `fichero/fichero/Views/AIProviders/ProvidersView.swift`
  - platform/remote access: `fichero/fichero.xcodeproj/project.pbxproj`, `fichero/fichero/FicheroApp_iOS.swift`, `fichero/fichero/Views/Settings/BackendSettingsRemoteAccessSection.swift`
- Gate: `~/.venv/bin/mkdocs build --strict` passed.
