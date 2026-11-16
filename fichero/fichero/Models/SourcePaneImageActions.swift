import Foundation

/// What the Source pane's bottom bar offers for the page it shows when edit mode is off (`image.enhance.editor-enhance-is-the-new-step`,
/// `image.enhance.batch-preview-undo`, #6362): Enhance for an image page, and Clean up the folder when the page sits in one.
enum SourcePaneImageAction: String, Equatable {
    case enhance
    case cleanUpFolder
}

enum SourcePaneImageActions {
    static func items(for document: Document) -> [SourcePaneImageAction] {
        guard document.fileType == .image, document.fileType != .pdf else { return [] }
        return document.parentId == nil ? [.enhance] : [.enhance, .cleanUpFolder]
    }
}

/// `image.enhance` with nothing touched: the ported local-contrast cleanup, handwritten (Step 4.3's default).
struct ImageEnhanceRequest: Encodable, Equatable {
    let documentId: String
    var method = EnhanceChoice().method
    var profile = EnhanceChoice().profile

    enum CodingKeys: String, CodingKey { case documentId = "document_id", method, profile }
}
