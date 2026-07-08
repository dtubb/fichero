(AI generated. Not reviewed.)

# Fichero — UI Map & Bug-Filing Cheat Sheet

Use this to file precise bugs. Tell the manager **region + what's wrong**; the
manager picks `type:bug` + `client:swiftui`/`backend` + area label + milestone.
**You don't pick milestones — hand the bug to the manager and it decides.**

---

## Window layout (Library mode)

```
┌───────────────────────────────────────────────────────────────────────────────────────┐
│ MAIN TOOLBAR  (window top)                       MainToolbar.swift                        │
│ ⊞sidebar  ⌃‹ ›history  ＋add  ▶run  …            🔍Search          ⊟inspector            │
├──────────────┬──────────────────────────────────────────────────────┬─────────────────┤
│  SIDEBAR     │  CENTER WORKSPACE  (changes by mode)                  │  DOCUMENT        │
│              │                                                        │  INSPECTOR       │
│  Sidebar/    │  ── Library mode ──                                    │  (right, tabbed) │
│   Modes/     │  LibraryView  (grid / list / table / map)             │                  │
│  SidebarItem │   FolderContentsGrid, LibraryView+DisplayModes        │  ℹ Info          │
│   Row.swift  │                                                        │  ✎ Content       │
│              │  ── When a doc is open ──                              │  ⚙ Metadata      │
│  • Library   │  DocumentCanvas  (image AND pdf viewer/editor)        │  ◫ Artifacts     │
│    tree      │   ImageEditor/  (edit chain, crop, A/B)               │  ✐ Annotations   │
│  • Inbox     │   PDFReadingView / PDFPageView                        │  🗒 Notes         │
│  • Workflows │   PageContentPane / DocumentKGWebPane (WebKit)        │  🔗 KG surface   │
│  • Batches   │   MagnifierPanel · PDFLoupeOverlay · ScrollWheelZoom  │    (Timeline/Map)│
│  • Activity  │                                                        │                  │
│              │                                                        │  DocumentInspect │
│  mode switch │                                                        │   or/            │
│  at bottom   │                                                        │                  │
└──────────────┴──────────────────────────────────────────────────────┴─────────────────┘
```

---

## Region → View name → file (for bugs)

| You see / say | View name | File | Label |
|---|---|---|---|
| **Whole window / panes** | ContentView | `Views/ContentView*.swift` | area:swiftui-app |
| **Main toolbar** (top) | MainToolbar | `Views/Toolbars/MainToolbar.swift` | area:toolbar |
| Context toolbars | Search/Chat/Workflow/Mini Toolbar | `Views/Toolbars/*Toolbar.swift` | area:toolbar |
| **Sidebar** (left) | SidebarItemRow / Sidebar Modes | `Views/Sidebar/` | area:sidebar |
| **Library display modes: grid / list / table / map / 3D** (the cube = 3D, beside Map — a LibraryView display mode, NOT the WebKit/reading pane) | LibraryView | `Views/Library/LibraryView*.swift` | area:swiftui-library |
| Folder thumbnails grid | FolderContentsGrid | `Views/Library/FolderContentsGrid.swift` | area:swiftui-library |
| **Doc viewer + editor — ONE canvas, ONE toolbar** (image AND pdf; the toolbar adapts to content type; the **edit toolbar is part of it**; always editable — a page, or pages of a folder/PDF) | DocumentCanvas (+ ImageEditor tools/chain + PDF pages) | `Views/Library/DocumentCanvas.swift`, `ImageEditor/`, `PDF*.swift` | area:document-canvas / area:image-editing |
| WebKit transcript / knowledge pane | DocumentKGWebPane / PageContentPane *(rename pending #1450)* | `Views/Library/` | area:reading-surface |
| Loupe / magnifier / zoom | PDFLoupeOverlay, MagnifierPanel, ScrollWheelZoom | `Views/Library/` | area:reading-surface |
| **Document Inspector** (right) | DocumentInspector | `Views/Library/DocumentInspector/` | area:inspector |
| — Info tab | DocumentInspectorInfoTab | `.../DocumentInspectorInfoTab.swift` | area:inspector |
| — Content tab | DocumentInspectorContentTab | `.../DocumentInspectorContentTab.swift` | area:inspector |
| — Metadata tab | DocumentInspectorMetadataTab | `.../DocumentInspectorMetadataTab.swift` | area:inspector |
| — Artifacts tab | DocumentInspectorArtifactsTab | `.../DocumentInspectorArtifactsTab.swift` | area:inspector |
| — Annotations tab | DocumentInspectorAnnotationsTab | `.../DocumentInspectorAnnotationsTab.swift` | area:inspector |
| — Notes tab | DocumentNotesTab | `.../DocumentNotesTab.swift` | area:inspector |
| — KG surface (Timeline/Map) | DocumentKGSurface | `Views/Library/DocumentKGSurface.swift` | area:inspector |

---

## Mode workspaces (full-screen, swap the CENTER)

| Mode | View dir | Milestone |
|---|---|---|
| **Knowledge Graph** (OntologyBrowser, graph viz) | `Views/KnowledgeGraph/` | KG & Hermeneutics |
| **Mind Palace** (spatial 2D/3D) | `Views/MindPalace/` | Mind Palace |
| **Research** (browser + chat + tasks) | `Views/Research/` | Researcher |
| **Chat** | `Views/Chat/` | Chat |
| **Search** | `Views/Search/` | Search |
| **Workflow editor** (node graph) | `Views/Workflow/` | Workflows |
| **Activity** (runs/automation) | `Views/Activity/`, `Views/Automation/` | Activity & Automation |
| **Model Comparison** | `Views/ModelComparison/` | Chat / Workflows |

---

## Settings & AI models

| You see / say | View | File | Milestone |
|---|---|---|---|
| **Settings window** | SettingsView | `Views/Settings/SettingsView.swift` | Settings & Providers |
| General settings | GeneralSettingsView | `Views/Settings/GeneralSettingsView.swift` | Settings & Providers |
| **AI settings / model defaults** | AISettingsView (+Tabs) | `Views/Settings/AISettingsView*.swift` | Settings & Providers |
| Local models | LocalModelsSettingsView | `Views/Settings/LocalModelsSettingsView.swift` | Settings & Providers |
| Backend settings | BackendSettingsView | `Views/Settings/BackendSettingsView.swift` | Settings & Providers |
| **Providers list / add** | ProvidersView, AddProviderSheet | `Views/AIProviders/` | Settings & Providers |
| **Model picker / catalog** | AIModelSelectionView, AIModelCatalog | `Views/AIProviders/` | Settings & Providers |

---

## How to file (just give the manager this)

> **Region:** Document Inspector → Artifacts tab
> **What happened:** the "ruler" toggle hides artifact bodies
> **Expected:** bodies stay visible

The manager turns that into: `type:bug` + `client:swiftui` + `area:inspector`,
milestone **Library & Reading Surface**, and routes it to the claude (frontend)
worker. Backend/data bugs → codex (backend). You don't pick the milestone.
