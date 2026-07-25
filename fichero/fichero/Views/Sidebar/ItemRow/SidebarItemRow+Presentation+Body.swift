import SwiftUI
import UniformTypeIdentifiers
#if canImport(AppKit)
import AppKit
#endif

func sidebarNeedsDeferredDisclosureContent(_ item: SidebarItem) -> Bool {
    item.isExpandable && item.children == nil
}

/// VoiceOver hint for a sidebar row. Kept terse so users don't hear a long
/// recitation each time they land on a row; power actions like export /
/// duplicate stay discoverable via the context menu itself. Wording is
/// per-platform: pointer gestures ("Right-click") mean nothing to touch
/// VoiceOver users, who reach the context menu via double-tap-and-hold.
func sidebarRowAccessibilityHint(canBeRenamed: Bool) -> String {
    #if os(macOS)
    if canBeRenamed {
        return "Double-click to rename. Drag to reorder or move to a folder. Right-click for more actions."
    }
    return "Right-click for actions."
    #else
    if canBeRenamed {
        return "Double tap and hold for actions, including rename. Drag to reorder or move to a folder."
    }
    return "Double tap and hold for actions."
    #endif
}

extension SidebarItemRow {
    var body: some View {
        bodyContent
            // DisclosureGroup label and the row drag both watch mouse-down
            // and compete with List(selection:) for the tap event, causing
            // intermittent click failures on icon/text (#645). A
            // simultaneousGesture keeps a fallback path, but the write is
            // deferred/idempotent so it does not mutate List selection while
            // SwiftUI/AppKit are still resolving the row click (#1165).
            .simultaneousGesture(TapGesture().onEnded {
                requestSelectionFallback(for: item.id)
            })
            // SwiftUI `Text` registers itself as an NSDraggingSource for
            // selectable text on macOS. That AppKit-level drag source
            // wins over the row container's `.draggable`, producing a
            // text-only drag (icon+name preview, not the full row, and
            // bypassing our SidebarDragID Transferable so drops don't
            // fire). Disabling text selection takes Text out of the
            // drag arena so the row's `.draggable` is the sole drag
            // source (#711).
            .textSelection(.disabled)
            .accessibilityLabel(accessibilityLabel)
            .accessibilityHint(accessibilityHint)
            .accessibilityValue(accessibilityValue)
    }

    private func requestSelectionFallback(for id: String) {
        #if canImport(AppKit)
        // The plain-click fallback (#645/#1165) writes a SINGLE selection. When
        // a modifier is held the click is a multi-select gesture that native
        // `List(selection: Set)` owns — writing here would collapse the whole
        // cmd/shift selection back to one row. Let the List handle it.
        let mods = NSEvent.modifierFlags
        if mods.contains(.command) || mods.contains(.shift) { return }
        #endif
        guard sidebarSelectionFallback(current: selectedItemId, tapped: id) != nil else {
            return
        }
        Task { @MainActor in
            if let next = sidebarSelectionFallback(current: selectedItemId, tapped: id) {
                selectedItemId = next
            }
        }
    }

    /// VoiceOver label — the row's displayed name plus its kind so users
    /// who navigate the sidebar non-visually can tell sections apart.
    /// Sidebar plan Step 10 (#584).
    private var accessibilityLabel: String {
        switch item.itemType {
        case .document(let doc):
            return doc.docType == .folder
                ? "\(item.name), folder"
                : "\(item.name), \(doc.fileType?.rawValue ?? "file")"
        case .savedSearch: return "\(item.name), saved search"
        case .conversation: return "\(item.name), conversation"
        case .workflow: return "\(item.name), workflow"
        case .chain: return "\(item.name), workflow chain"
        case .schedule: return "\(item.name), schedule"
        case .trigger: return "\(item.name), trigger"
        case .folder: return "\(item.name), \(item.category.rawValue) folder"
        case .libraryHeader: return "\(item.name), library"
        case .batch, .comparison, .activityRun:
            return item.name
        }
    }

    private var accessibilityHint: String {
        sidebarRowAccessibilityHint(canBeRenamed: item.itemType.canBeRenamed)
    }

    /// Expansion state for folder rows — read as "expanded"/"collapsed"
    /// so arrow-key navigation via VoiceOver correctly reflects the
    /// DisclosureGroup state.
    private var accessibilityValue: String {
        guard isExpandable else { return "" }
        return expandedItems.contains(item.id) ? "expanded" : "collapsed"
    }

    private var isExpandable: Bool {
        item.isExpandable
    }

    @ViewBuilder
    private var disclosureContent: some View {
        if let children = item.children, !children.isEmpty {
            childrenList(children)
        } else if sidebarNeedsDeferredDisclosureContent(item) {
            // Keep the native disclosure chevron visible while descendants are
            // still lazy-loaded from metadata-only childCount state (#3355).
            Color.clear
                .frame(height: 0.5)
                .accessibilityHidden(true)
        }
    }

    // Folders are direct drop targets. Document leaves also accept file drops,
    // which resolve to their parent folder so dropping onto `page1.pdf` imports
    // beside it, matching Finder's sibling-drop behavior.
    @ViewBuilder
    private var bodyContent: some View {
        if isExpandable {
            DisclosureGroup(isExpanded: isExpanded) {
                disclosureContent
            } label: {
                if isFolder {
                    folderLabel
                } else {
                    leafLabel
                }
            }
        } else if isFolder {
            folderLabel
        } else {
            leafLabel
        }
    }

    /// Folder row: drop target always; drag source EXCEPT for the
    /// protected Inbox folder (#621). Inbox stays anchored at the top;
    /// users can drag files INTO it but not drag Inbox itself to
    /// another position or parent.
    ///
    /// UTTypes a sidebar row accepts as drop targets.
    ///
    /// `.utf8PlainText` handles internal sidebar drags. `.fileURL` and `.data`
    /// are listed EXPLICITLY even though `public.file-url` conforms to
    /// `public.item` (verified via `UTType.conforms(to:)`): Finder file drags
    /// (e.g. a PDF, #3390) showed no `isTargeted` feedback with `.item` alone,
    /// and the library-header drop target already accepts `.fileURL` directly.
    /// Explicit acceptance beats relying on conformance walking here; whether
    /// `.item` alone would now suffice is only verifiable with a live drag.
    static let dropTypes: [UTType] = [.utf8PlainText, .item, .fileURL, .data]

    /// Folder row: drop target always; drag source EXCEPT for the
    /// protected Inbox folder (#621). Inbox stays anchored at the top;
    /// users can drag files INTO it but not drag Inbox itself to
    /// another position or parent.
    @ViewBuilder
    private var folderLabel: some View {
        fullWidthLabel
            .sidebarDropHighlight(isDropTargeted, stronger: true)
            .onDrop(
                of: Self.dropTypes,
                isTargeted: $isDropTargeted
            ) { providers in
                handleRowDrop(providers)
            }
            .contextMenu { rowContextMenu }
    }

    /// Leaf row: no inner gestures — `.draggable` is applied one level
    /// up at the row container so clicks on icon/text aren't delayed by
    /// SwiftUI's tap-vs-drag disambiguation (#711 follow-up).
    private var leafLabel: some View {
        fullWidthLabel
            .sidebarDropHighlight(isDropTargeted, stronger: false)
            .onDrop(
                of: Self.dropTypes,
                isTargeted: $isDropTargeted
            ) { providers in
                handleRowDrop(providers)
            }
            .contextMenu { rowContextMenu }
    }
}
