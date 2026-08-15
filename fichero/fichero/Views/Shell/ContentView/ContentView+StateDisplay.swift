import OSLog
import SwiftUI

// MARK: - ContentView Display State

extension ContentView {

    var activeLocationDocument: Document? {
        switch focusedPane {
        case .preview, .reading:
            pageFocusDocument ?? detailDocument ?? inspectorDocument
        case .sidebar, .content, .chat, .inspector, .none:
            inspectorDocument
        }
    }

    /// Toolbar/window title showing only the current view/item name
    var toolbarTitle: String {
        let viewName: String
        switch viewMode {
        case .library(let document):
            // When a PDF page (or multiple pages) is selected in the grid,
            // reflect that in the window title so the user knows exactly what
            // is in context. The parent PDF comes from `document` (the sidebar-
            // selected item). Page count shows when the browser selection has
            // more than one page document.
            // The title is the LEAF; the path is `breadcrumbSubtitle` (#4416).
            // Composing "<page> — <document>" here while the breadcrumb also
            // appended a page label is what put "Page 1" on screen twice, with
            // two different separators. And `document.name` for a page row is
            // the engine's upload temp name, so it read `fichero_upload_…pdf`
            // where the sidebar read `18590129.pdf`.
            if let page = activeLocationDocument, page.docType == .page {
                let selectedPageCount = browserSelection.filter { id in
                    documentStore.currentDocuments.first(where: { $0.id == id })?.docType == .page
                }.count
                viewName = DocumentTitle.windowTitle(
                    leaf: page,
                    parent: document,
                    selectedPageCount: selectedPageCount
                )
            } else if let document {
                viewName = DocumentTitle.displayName(for: document)
            } else {
                viewName = "Library"
            }
        case .chat(let conversation):
            viewName = conversation?.title ?? "Chat"
        case .comparison(let comparison):
            if let comp = comparison {
                let truncated = comp.prompt.count > 30 ? String(comp.prompt.prefix(30)) + "..." : comp.prompt
                viewName = truncated
            } else {
                viewName = "Comparison"
            }
        case .workflow(let workflow):
            viewName = workflow?.name ?? "Workflow"
        case .chain(let chain):
            viewName = chain?.name ?? "Chain"
        case .batches:
            viewName = "Activity"
        case .batch:
            viewName = "Activity"
        case .automation:
            viewName = "Automation"
        case .schedule(let schedule):
            viewName = schedule?.name ?? "Schedule"
        case .trigger(let trigger):
            viewName = trigger?.name ?? "Trigger"
        case .activity(let selectedRun):
            if let run = selectedRun {
                viewName = run.name
            } else {
                viewName = "Activity"
            }
        }

        return viewName
    }

    /// Breadcrumb trail showing full navigation path from library root to current selection.
    /// Returns "Library › Folder › Subfolder › File" or empty string if not applicable.
    /// Only for library mode; returns empty string for other modes.
    var breadcrumbSubtitle: String {
        guard case .library(let document) = viewMode, let doc = document else {
            return ""
        }

        // Build a lookup function for parent documents from currentDocuments + cache
        // ContentView is a struct (value type) — capture by value, no weak/retain-cycle concern.
        let parentLookup: BreadcrumbBuilder.DocumentLookup = { parentId in
            // Check currentDocuments first (most likely case)
            if let found = documentStore.currentDocuments.first(where: { $0.id == parentId }) {
                return found
            }
            // Fallback to collections if not found in current docs
            if let found = documentStore.collections.first(where: { $0.id == parentId }) {
                return found
            }
            return nil
        }

        let pageLabel: String? = if let page = activeLocationDocument, page.docType == .page {
            page.pageThumbnailLabel
        } else {
            nil
        }

        let breadcrumb = BreadcrumbBuilder.buildBreadcrumbForLibraryMode(
            document: doc,
            pageLabel: pageLabel,
            parentLookup: parentLookup
        )

        // Return the breadcrumb minus the leaf name (which is already in navigationTitle)
        // Split on " › " and drop the last component
        let components = breadcrumb.split(separator: " › ")
        if components.count > 1 {
            return components.dropLast().joined(separator: " › ")
        }
        return ""
    }

    /// SF symbol name for the current view mode — shown alongside toolbarTitle in the navigation header
    var toolbarIcon: String {
        switch viewMode {
        case .library(let document):
            guard let doc = document else { return "books.vertical" }
            if let active = activeLocationDocument, active.docType == .page {
                return "doc.richtext"
            }
            return doc.docType == .folder ? "folder" : (doc.fileType == .pdf ? "doc.richtext" : "doc.text")
        case .chat:
            return "bubble.left.and.bubble.right"
        case .comparison:
            return "rectangle.split.2x1"
        case .workflow:
            return "bolt"
        case .chain:
            return "link"
        case .batches, .batch, .activity:
            return "clock"
        case .automation:
            return "gearshape.2"
        case .schedule:
            return "calendar"
        case .trigger:
            return "bolt.circle"
        }
    }

    /// What the detail pane says is selected.
    ///
    /// Not `activeLocationDocument?.name` (#4416, found by the producer
    /// guardrail in #4393). `toolbarTitle`, ten lines up in this same file, was
    /// fixed to compose through `DocumentTitle` — and this one was not, so the
    /// title bar and the status line under it disagreed about the name of the
    /// same page: `18590129.pdf` above, `fichero_upload_c84fgjke.pdf` below.
    /// A raw name reached here because it was produced, not rendered, and the
    /// #4416 sweep only looked at renders.
    ///
    /// The parent is the sidebar-selected document, which is what makes a page
    /// with no metadata title resolve to its parent's name rather than
    /// `Untitled`.
    var selectionStatusText: String {
        if browserSelection.count > 1 {
            return "\(browserSelection.count) items selected"
        }
        guard let active = activeLocationDocument else { return toolbarTitle }
        return DocumentTitle.displayName(
            for: active,
            parent: active.parentId.flatMap { parentId in
                documentStore.currentDocuments.first(where: { $0.id == parentId })
            })
    }

}
