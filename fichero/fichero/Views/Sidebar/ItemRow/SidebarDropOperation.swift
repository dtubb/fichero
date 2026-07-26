import Foundation
#if os(macOS)
import AppKit
#else
import GameController
#endif

/// Whether Option (⌥) is held RIGHT NOW — read at drop time so the existing
/// drag machinery (#711/#713 workarounds, NSTableView row drag) stays
/// untouched. macOS reads the live AppKit modifier flags; iPadOS/visionOS
/// read the hardware keyboard through GameController, since SwiftUI drop
/// callbacks never expose the session's modifiers. No hardware keyboard →
/// false → drops stay moves.
func sidebarOptionKeyIsHeld() -> Bool {
    #if os(macOS)
    return NSEvent.modifierFlags.contains(.option)
    #else
    guard let keyboard = GCKeyboard.coalesced?.keyboardInput else { return false }
    return keyboard.button(forKeyCode: .leftAlt)?.isPressed == true
        || keyboard.button(forKeyCode: .rightAlt)?.isPressed == true
    #endif
}

/// What an internal sidebar drop should do with its payload.
enum SidebarDropOperation: Equatable {
    case move
    case copy
}

/// Option-copy applies to DOCUMENT payloads only — the one kind with a
/// targeted duplicate endpoint (`document.duplicate` + `parent_id`). Other
/// kinds keep move semantics even under Option.
func sidebarDropOperation(optionHeld: Bool, kind: SidebarItemKind) -> SidebarDropOperation {
    optionHeld && kind == .document ? .copy : .move
}

private struct DocumentDuplicateActionParams: Encodable {
    let docId: String
    let parentId: String

    enum CodingKeys: String, CodingKey {
        case docId = "doc_id"
        case parentId = "parent_id"
    }
}

extension SidebarItemRow {
    /// Option-drag copy executor: deep-copies the document into the target
    /// folder through the audited `document.duplicate` action (the same
    /// invokeAction path document.delete uses — no generated-client wrapper
    /// needed). The engine enforces cycle/lock rules and keeps the name for
    /// cross-folder copies (Finder suffixes only same-folder copies).
    func copyDocumentIntoFolder(documentId: String, folderId: String) async {
        guard let library else { return }
        do {
            _ = try await library.actionsService.invokeAction(
                name: "document.duplicate",
                params: DocumentDuplicateActionParams(docId: documentId, parentId: folderId)
            )
            await library.documentStore.refresh()
        } catch {
            sidebarRowLogger.error("⌥-copy failed: \(error.localizedDescription)")
            sidebarState.dropErrorMessage = error.localizedDescription
        }
    }
}
