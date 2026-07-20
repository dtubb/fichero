import OSLog
import SwiftUI

// MARK: - ContentView Display State

extension ContentView {

    var activeLocationDocument: Document? {
        switch focusedPane {
        case .preview, .reading:
            pageFocusDocument ?? detailDocument ?? inspectorDocument
        case .sidebar, .content, .inspector, .none:
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
            if let page = activeLocationDocument, page.docType == .page {
                let selectedPageCount = browserSelection.filter { id in
                    documentStore.currentDocuments.first(where: { $0.id == id })?.docType == .page
                }.count
                if selectedPageCount > 1 {
                    let parentName = document?.name
                    viewName = parentName.map { "\(selectedPageCount) pages — \($0)" }
                        ?? "\(selectedPageCount) pages"
                } else {
                    let pageLabel = page.sequence.map { "Page \($0)" } ?? page.name
                    viewName = document.map { "\(pageLabel) — \($0.name)" } ?? pageLabel
                }
            } else {
                viewName = document?.name ?? "Library"
            }
        case .search(let savedSearch):
            viewName = savedSearch?.name ?? "Search"
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
        case .search:
            return "magnifyingglass"
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

    var selectionStatusText: String {
        if browserSelection.count > 1 {
            return "\(browserSelection.count) items selected"
        }
        return activeLocationDocument?.name ?? toolbarTitle
    }

    var selectionPathText: String {
        let leaf = activeLocationDocument?.name ?? toolbarTitle
        guard !breadcrumbSubtitle.isEmpty else { return leaf }
        return "\(breadcrumbSubtitle) › \(leaf)"
    }
}
