import OSLog
import SwiftUI
import UniformTypeIdentifiers

let sidebarRowLogger = Logger(subsystem: "com.tubb.Fichero", category: "SidebarRow")

extension View {
    /// Applies the sidebar drop-target highlight (accent fill + stroke) to
    /// any view. Placed on the OUTER expression of a SidebarItemRow body
    /// branch so it covers the full List row — including the DisclosureGroup
    /// chevron/indent area that `fullWidthLabel` alone can't reach.
    ///
    /// `.overlay` + `.allowsHitTesting(false)` so the wash renders on top of
    /// whatever chrome the sidebar-style List draws, without blocking drops.
    @ViewBuilder
    func sidebarDropHighlight(_ active: Bool, stronger: Bool) -> some View {
        self.overlay(
            RoundedRectangle(cornerRadius: SidebarConstants.cornerRadius)
                .fill(
                    active
                        ? Color.accentColor.opacity(stronger ? 0.45 : 0.25)
                        : Color.clear
                )
                .overlay(
                    RoundedRectangle(cornerRadius: SidebarConstants.cornerRadius)
                        .stroke(
                            active ? Color.accentColor : Color.clear,
                            lineWidth: active ? 2 : 0
                        )
                )
                .allowsHitTesting(false)
        )
    }
}

struct SidebarItemRow: View {
    let item: SidebarItem
    let allCachedItems: [SidebarItem]
    @Binding var expandedItems: Set<String>
    @Binding var selectedItemId: String?
    @ObservedObject var renameState: RenameStateManager
    @ObservedObject var deleteState: DeleteStateManager
    @ObservedObject var libraryManager: LibraryManager

    @Environment(WorkflowExecutionObserver.self) var executionObserver

    var library: LibraryManager.LibraryReference? {
        guard let libraryId = item.libraryId else { return nil }
        return libraryManager.getLibrary(id: libraryId)
    }

    var documentStore: DocumentStore? { library?.documentStore }
    var savedSearchService: SavedSearchServiceGenerated? { library?.savedSearchServiceGenerated }
    var conversationService: ConversationServiceGenerated? { library?.conversationServiceGenerated }
    var workflowStore: WorkflowStore? { library?.workflowStore }
    var chainService: ChainService? { library?.chainService }
    var automationService: AutomationServiceGenerated? { library?.automationService }
    var importService: ImportServiceGenerated? { library?.importService }

    @State var isDropTargeted = false
    @FocusState var isRenameFocused: Bool
    @State var isCommittingRename = false
    @State var isPulsing = false

    var onItemTapped: ((SidebarItem) -> Void)?
    var onAutomationPause: (() -> Void)?
    var onAutomationResume: (() -> Void)?
    var onAutomationTrigger: (() -> Void)?
    var onAutomationCancel: (() -> Void)?

    var isFolder: Bool {
        guard case .document(let doc) = item.itemType else { return false }
        return doc.docType == .folder
    }

    var workflowIsRunning: Bool {
        guard case .workflow(let workflow) = item.itemType else { return false }
        return executionObserver.isRunning(workflowId: workflow.id)
    }

    var workflowProgress: Double? {
        guard case .workflow(let workflow) = item.itemType else { return nil }
        return executionObserver.getProgress(for: workflow.id)
    }

    private var isExpanded: Binding<Bool> {
        Binding(
            get: { expandedItems.contains(item.id) },
            set: { isExpanded in
                if isExpanded {
                    expandedItems.insert(item.id)
                } else {
                    expandedItems.remove(item.id)
                }
            }
        )
    }

    /// Widens `itemLabel`'s hit region to the full available width so the
    /// dropDestination fires when the cursor is anywhere over the row, not
    /// just the icon+text. Tight vertical padding to match Xcode's dense
    /// sidebar rhythm (~18pt row height).
    private var fullWidthLabel: some View {
        itemLabel
            .padding(.vertical, 1)
            .frame(maxWidth: .infinity, alignment: .leading)
            .contentShape(Rectangle())
    }

    /// Update the drop-target state and log the transition. The log lets Daniel
    /// (or anyone) verify the SwiftUI dropDestination callback is actually
    /// firing via `log stream --subsystem com.tubb.Fichero --predicate
    /// 'category == "SidebarRow"'` — if this line never appears during a drag,
    /// the drop destination isn't registering the hover.
    private func setDropTargeted(_ targeted: Bool) {
        if isDropTargeted != targeted {
            sidebarRowLogger.debug("🎯 \(item.name): dropTargeted=\(targeted)")
            isDropTargeted = targeted
        }
    }

    private var rowContextMenu: some View {
        SidebarItemContextMenu(
            item: item,
            renameState: renameState,
            deleteState: deleteState,
            onPause: onAutomationPause,
            onResume: onAutomationResume,
            onTrigger: onAutomationTrigger,
            onCancel: onAutomationCancel
        )
    }

    var body: some View {
        bodyContent
            .accessibilityLabel(accessibilityLabel)
            .accessibilityHint(accessibilityHint)
            .accessibilityValue(accessibilityValue)
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

    /// Available actions callable via the context menu. Kept terse so
    /// VoiceOver users don't hear a long recitation each time they land
    /// on a row; power actions like export/duplicate stay discoverable
    /// via `.accessibilityAction` on the context menu itself.
    private var accessibilityHint: String {
        if item.itemType.canBeRenamed {
            return "Double-click to rename. Drag to reorder or move to a folder. Right-click for more actions."
        }
        return "Right-click for actions."
    }

    /// Expansion state for folder rows — read as "expanded"/"collapsed"
    /// so arrow-key navigation via VoiceOver correctly reflects the
    /// DisclosureGroup state.
    private var accessibilityValue: String {
        guard isExpandable else { return "" }
        return expandedItems.contains(item.id) ? "expanded" : "collapsed"
    }

    private var isExpandable: Bool {
        guard let children = item.children else { return false }
        return !children.isEmpty
    }

    // Folders (with or without children) are drop targets; leaves
    // (PDFs, images, saved searches, etc.) are drag sources only.
    // Matches Finder semantics: you can drag a file out, but you
    // can't drop anything onto a file.
    @ViewBuilder
    private var bodyContent: some View {
        if let children = item.children, !children.isEmpty {
            DisclosureGroup(isExpanded: isExpanded) {
                childrenList(children)
            } label: {
                folderLabel
            }
        } else if isFolder {
            folderLabel
        } else {
            leafLabel
        }
    }

    /// Folder row: full drag + drop support. Single `.onDrop(of:
    /// isTargeted:perform:)` unifies both internal sidebar drags
    /// (utf8PlainText) and Finder file drags (fileURL and friends)
    /// — attaching both `.dropDestination(for: String.self)` and a
    /// separate `.onDrop(of: [.fileURL])` on the same view causes
    /// SwiftUI to route Finder drags through the String handler
    /// first and silently reject them. One modifier, branching on
    /// advertised UTI inside `handleRowDrop`.
    ///
    /// Highlight + drop target attach to `fullWidthLabel` (not to
    /// the DisclosureGroup's outer body), so the blue hover fill
    /// only covers this row — not expanded children below.
    private var folderLabel: some View {
        fullWidthLabel
            .sidebarDropHighlight(isDropTargeted, stronger: true)
            .draggable(item.id)
            .onDrop(
                of: [
                    UTType.utf8PlainText,  // internal sidebar drags
                    UTType.fileURL,        // Finder file-URL drags
                    UTType.item,           // broadly-typed fallback
                    UTType.movie,
                    UTType.audio,
                    UTType.image
                ],
                isTargeted: $isDropTargeted
            ) { providers in
                handleRowDrop(providers)
            }
            .contextMenu { rowContextMenu }
    }

    /// Leaf row: drag source only. PDFs, images, saved searches,
    /// conversations, workflows can all be DRAGGED to another
    /// folder, but dropping anything onto a leaf doesn't match
    /// Finder semantics — you can't drop a file onto a file.
    private var leafLabel: some View {
        fullWidthLabel
            .draggable(item.id)
            .contextMenu { rowContextMenu }
    }

    /// Routes a drop on THIS FOLDER row to the right handler.
    ///
    /// Uses `canLoadObject(ofClass:)` rather than UTI advertisement
    /// checks: Finder drags of specific file types (`.jpg`, `.mov`,
    /// HEIC, etc.) don't always advertise `public.file-url` alongside
    /// their content UTI, so a `hasItemConformingToTypeIdentifier`
    /// filter misses them and the OS visually rejects the drop
    /// (#600-shaped bug Daniel hit again 2026-04-17).
    ///
    /// `canLoadObject(ofClass: URL.self)` asks the provider directly
    /// whether it can produce a URL, regardless of advertised UTIs —
    /// that's what we actually care about. SwiftUI's `.draggable(_:
    /// String)` uses `String`'s Transferable conformance, which
    /// advertises `public.utf8-plain-text` only and cannot produce
    /// a URL, so internal sidebar drags remain unambiguously
    /// separable from Finder drags.
    ///
    /// Only called from `folderLabel` — leaves don't accept drops.
    private func handleRowDrop(_ providers: [NSItemProvider]) -> Bool {
        let urlProviders = providers.filter { $0.canLoadObject(ofClass: URL.self) }
        let textProviders = providers.filter {
            !$0.canLoadObject(ofClass: URL.self)
                && $0.canLoadObject(ofClass: NSString.self)
        }

        // Finder file drop → existing import pipeline.
        if !urlProviders.isEmpty {
            return handleProvidersDrop(urlProviders, targetFolder: item)
        }

        // Internal sidebar drag → move source into this folder.
        if !textProviders.isEmpty {
            Task {
                var ids: [String] = []
                for provider in textProviders {
                    if let str = try? await Self.loadString(from: provider) {
                        ids.append(str)
                    }
                }
                guard !ids.isEmpty else { return }
                _ = handleDropIntoFolder(itemIDs: ids, targetFolder: item)
            }
            return true
        }

        return false
    }

    /// Async helper to unwrap a plain-text NSItemProvider into a String.
    /// Matches the `loadURL` helper's pattern on `SidebarItemRow+DropHandlers`.
    private static func loadString(from provider: NSItemProvider) async throws -> String {
        try await withCheckedThrowingContinuation { continuation in
            _ = provider.loadObject(ofClass: NSString.self) { value, error in
                if let error {
                    continuation.resume(throwing: error)
                } else if let nsString = value as? NSString {
                    continuation.resume(returning: nsString as String)
                } else {
                    continuation.resume(throwing: NSError(domain: "SidebarRowDrop", code: -1))
                }
            }
        }
    }

    @ViewBuilder
    private func childrenList(_ children: [SidebarItem]) -> some View {
        ForEach(children) { child in
            SidebarItemRow(
                item: child,
                allCachedItems: allCachedItems,
                expandedItems: $expandedItems,
                selectedItemId: $selectedItemId,
                renameState: renameState,
                deleteState: deleteState,
                libraryManager: libraryManager,
                onItemTapped: onItemTapped
            )
            .contentShape(Rectangle())
            .onTapGesture { onItemTapped?(child) }
            .listRowBackground(
                // Finder / Mail sidebar highlight: muted grey rather
                // than accent blue. Adapts to light/dark via the
                // semantic `secondary` colour.
                child.id == selectedItemId
                    ? Color.secondary.opacity(0.18)
                    : Color.clear
            )
            .tag(child.id)
        }
        // `.onMove` removed — it expects synchronous mutation of the
        // ForEach's data source, but `children` here is a parameter
        // computed from `SidebarItemBuilder.buildLibraryHierarchy`,
        // not a binding to mutable state. When the closure returned
        // without mutating the collection, SwiftUI interpreted that
        // as a rejected move and disabled subsequent reorder attempts
        // (reported symptom: blue insertion line flashed once then
        // never appeared again). A correct implementation needs a
        // `@State` shadow of the children that `.onMove` mutates
        // optimistically, with the backend call + cache refresh
        // syncing it back afterwards. Filed separately for a follow-
        // up; not shipping half-working reorder in 0.0.2.
    }
}
