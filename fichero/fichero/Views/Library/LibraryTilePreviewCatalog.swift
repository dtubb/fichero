import SwiftUI

// MARK: - Library tile preview catalog (Daniel, 2026-08-08)
//
// The REAL DocumentThumbnailView in its selection states, so the Finder
// icon-view grammar (#4563: grey backdrop behind the ICON, accent pill with
// white text behind the NAME, no whole-tile wash) is reviewable in the canvas
// or via RenderPreview without running the app.
//
// Fixture docs deliberately take the FOLDER and TEXT-PREVIEW thumbnail
// branches: the image branch is `LibraryImageView`, whose required
// `@Environment(StorageService.self)` is fatal in a bare preview (crashed
// live, 2026-08-08). The grammar under review is the platter and the pill,
// which every branch shares.

#Preview("Tile selection states") {
    let selected = Document(id: "sel", docType: .folder, name: "Slipbox Backup", childCount: 12)
    let plain = Document(id: "plain", docType: .folder, name: "Templates", childCount: 4)
    let text = Document(
        id: "text", docType: .file, fileType: .text, name: "Field notes.md",
        pageContent: "Rain again. The archive closes at noon; Sergio's notebook\ngoes back to the vault tomorrow."
    )

    return HStack(alignment: .top, spacing: 12) {
        DocumentThumbnailView(document: selected, isSelected: true)
        DocumentThumbnailView(document: plain, isSelected: false)
        DocumentThumbnailView(document: text, isSelected: true)
    }
    .padding(20)
    .frame(width: 420, height: 220)
}
