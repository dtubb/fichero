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
            // NO per-row TapGesture fallback any more (removed 2026-08-08,
            // #4571). The #645-era fallback predates textSelection(.disabled)
            // and the allowsHitTesting(false) pass-throughs that now let
            // clicks reach the List natively — and it was itself a second
            // write path in the gesture arena: a MODIFIER click over the
            // label was consumed there (the fallback correctly bailed on
            // cmd/shift, but bailing is not the same as never competing), so
            // shift/cmd-click on the NAME could not extend a selection while
            // the same click beside the name could. One selection path:
            // List(selection:) owns every click, plain or modified.
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
            // Grid-menu parity (#4121): the same picker sheets LibraryView
            // hosts, presented per-row so the clicked row's OWN library
            // services are injected (sidebar rows span libraries).
            .sheet(item: $workspacePickerDocument) { document in
                if let library {
                    WorkspaceItemPicker(document: document)
                        .environment(library.documentService)
                }
            }
            .sheet(item: $bookmarkPickerDocument) { document in
                if let library {
                    BookmarksView(document: document, onOpen: { target in
                        selectedItemId = "doc:\(target.id)"
                    })
                    .environment(library.documentService)
                    .environment(library.bookmarkService)
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
            // Children are known to exist (childCount) but not fetched yet.
            // NO synthetic spinner ROW any more (Daniel, 2026-08-09: "it adds
            // row for spinner then adds in files. the spinner should be on
            // the icon of the row I am opening") — the row's OWN iconView
            // shows the spinner while this state holds (see childrenLoading
            // in SidebarItemRow+Label). The clear view keeps the chevron
            // rendered (#3355), but must occupy NO row: the List's minimum
            // row height turned the old 0.5pt frame into a visible blank row
            // (green-highlighted, then replaced when pages arrived — Daniel,
            // 2026-08-10: "don't open an empty row"). Zero height, zero
            // insets, no separator, selection disabled = an invisible slot.
            Color.clear
                .frame(height: 0)
                .listRowInsets(EdgeInsets())
                .listRowSeparator(.hidden)
                .listRowBackground(Color.clear)
                .selectionDisabled(true)
                .environment(\.defaultMinListRowHeight, 0)
                .accessibilityHidden(true)
        }
    }

    // Folders are direct drop targets. Document leaves also accept file drops,
    // which resolve to their parent folder so dropping onto `page1.pdf` imports
    // beside it, matching Finder's sibling-drop behavior.
    @ViewBuilder
    private var bodyContent: some View {
        if isExpandable {
            // #571 (restored): drop target and context menu sit on the OUTER
            // DisclosureGroup so the chevron/indent strip is part of the row's
            // drop and right-click surface — a refactor before the #1703 file
            // split had moved them inside the label, leaving that strip dead.
            // The label here is bare `fullWidthLabel` (NOT folderLabel/
            // leafLabel) so the modifiers aren't doubled. Child rows attach
            // their own handlers, which win within their bounds.
            //
            // The HIGHLIGHT is the exception (#4229): on the group it painted
            // the group's whole frame — which, expanded, is the folder PLUS its
            // entire child subtree, an accent wash indistinguishable from a
            // mass selection. It lives on the LABEL so only the actual target
            // row lights up (Finder behavior); the group keeps the wider drop
            // surface.
            DisclosureGroup(isExpanded: isExpanded) {
                disclosureContent
            } label: {
                fullWidthLabel
                    .sidebarDropHighlight(isDropTargeted, selected: isRowInSelection, mergeAbove: mergeSelectionAbove, mergeBelow: mergeSelectionBelow)
            }
            .modifier(SidebarRowDropGate(enabled: rowIsDropTarget, delegate: rowDropDelegate))
            // #4544: menu built at OPEN, not per render — see
            // SidebarDeferredMenuContent.
            .contextMenu { SidebarDeferredMenuContent { rowContextMenu } }
            // Chevron stays ACCENT on a selected row (Daniel, 2026-08-10:
            // "the chevron turns white though. white is invisible on tahoe
            // and golden gate. make it the same green"). The native selection
            // still marks the row emphasized even though our grey platter
            // covers its platter, so system chrome (the disclosure chevron)
            // flips to white. Standard prominence + the accent tint keep it
            // the same accent as the name and icon.
            .environment(\.backgroundProminence, .standard)
            .tint(Color.accentColor)
        } else if isFolder {
            folderLabel
        } else {
            leafLabel
        }
    }

    /// UTTypes a sidebar row accepts as drop targets.
    ///
    /// `.utf8PlainText` handles internal sidebar drags. `.fileURL` and `.data`
    /// are listed EXPLICITLY even though `public.file-url` conforms to
    /// `public.item` (verified via `UTType.conforms(to:)`): Finder file drags
    /// (e.g. a PDF, #3390) showed no `isTargeted` feedback with `.item` alone,
    /// and the library-header drop target already accepts `.fileURL` directly.
    /// Explicit acceptance beats relying on conformance walking here; whether
    /// `.item` alone would now suffice is only verifiable with a live drag.
    ///
    /// `.ficheroDragItem` FIRST (#4401 multi-drag): the named in-app flavor.
    /// It conforms to `.data` so the older lists would match anyway, but the
    /// accepted set must NAME the flavor the reader loads by name, or the two
    /// sides drift. `.item` keeps external files AND folders activating the
    /// row (`public.folder` conforms to `public.item`, not to `public.data`).
    static let dropTypes: [UTType] = [.ficheroDragItem, .utf8PlainText, .item, .fileURL, .data]

    /// Only CONTAINERS are drop targets (Daniel, 2026-08-10: "if you try to
    /// add a file or image to a pdf it should do a cursor negative or pop
    /// back"). A document leaf — PDF, image, file — refuses the drop
    /// natively: no .onDrop means the forbidden cursor and the snap-back,
    /// exactly Finder's grammar. Read-only system folders refuse too
    /// (#4514, `acceptsItemDrops`). Non-document rows (sections, workflow
    /// containers) keep their existing drop surfaces.
    var rowIsDropTarget: Bool {
        if case .document(let doc) = item.itemType { return doc.acceptsItemDrops }
        return true
    }

    /// Folder row: drop target always; drag source EXCEPT for the
    /// protected Inbox folder (#621). Inbox stays anchored at the top;
    /// users can drag files INTO it but not drag Inbox itself to
    /// another position or parent.
    @ViewBuilder
    private var folderLabel: some View {
        fullWidthLabel
            .sidebarDropHighlight(isDropTargeted, selected: isRowInSelection, mergeAbove: mergeSelectionAbove, mergeBelow: mergeSelectionBelow)
            .modifier(SidebarRowDropGate(enabled: rowIsDropTarget, delegate: rowDropDelegate))
            .contextMenu { SidebarDeferredMenuContent { rowContextMenu } }
    }

    /// Leaf row: no inner gestures — `.draggable` is applied one level
    /// up at the row container so clicks on icon/text aren't delayed by
    /// SwiftUI's tap-vs-drag disambiguation (#711 follow-up).
    private var leafLabel: some View {
        fullWidthLabel
            .sidebarDropHighlight(isDropTargeted, selected: isRowInSelection, mergeAbove: mergeSelectionAbove, mergeBelow: mergeSelectionBelow)
            .modifier(SidebarRowDropGate(enabled: rowIsDropTarget, delegate: rowDropDelegate))
            .contextMenu { SidebarDeferredMenuContent { rowContextMenu } }
    }

    /// One delegate for all three row shapes (#4401). `.onDrop(of:isTargeted:)`
    /// cannot propose an operation, so every sidebar row painted a `+` copy
    /// badge over what the handler then performed as a MOVE. The delegate form
    /// is the only one that can answer `dropUpdated`; the accepted types, the
    /// providers, the handler and the `isTargeted` binding are unchanged.
    private var rowDropDelegate: LibraryItemDropDelegate {
        LibraryItemDropDelegate(
            acceptedTypes: Self.dropTypes,
            isTargeted: $isDropTargeted,
            surface: "sidebar-row",
            onDropProviders: { handleRowDrop($0) }
        )
    }
}

/// Attaches the row drop delegate only when the row genuinely accepts drops
/// — a leaf gets NO drop surface, so AppKit shows the forbidden cursor and
/// snaps the item back (Daniel's PDF ruling, 2026-08-10).
struct SidebarRowDropGate: ViewModifier {
    let enabled: Bool
    let delegate: LibraryItemDropDelegate

    func body(content: Content) -> some View {
        if enabled {
            content.onDrop(of: SidebarItemRow.dropTypes, delegate: delegate)
        } else {
            content
        }
    }
}
