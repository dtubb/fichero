import FicheroAPIClient
import SwiftUI

// MARK: - Document Thumbnail View

struct DocumentThumbnailView: View {
    let document: Document
    let isSelected: Bool
    var selectedTint: Color = .accentColor
    var scale: CGFloat = 1.0
    /// Inline rename (#4160): the context menu's Rename set state only the
    /// table (and now list) consumed — icon mode rendered a plain Text, so
    /// Rename silently did nothing while still blocking type-select/Space.
    var isRenaming: Bool = false
    var editingName: Binding<String> = .constant("")
    var onCommitRename: () -> Void = {}
    var onCancelRename: () -> Void = {}

    /// The SQUARE image well, at scale 1 (Daniel's Finder screenshots,
    /// 2026-08-09: 'all icons should be square (a squircle) so the icon
    /// thumbnail is centred in the square and a bit smaller, like in
    /// Finder'). Every branch pins to this size so no image's intrinsic
    /// dimensions can distort the grid; the content INSETS inside the well.
    static let wellWidth: CGFloat = 108
    static let wellHeight: CGFloat = wellWidth
    /// The inset that makes the thumbnail 'a bit smaller' inside the well.
    static let wellContentInset: CGFloat = 10

    #if os(macOS)
    @Environment(\.controlActiveState) private var controlActiveState
    #endif

    /// #1840: de-emphasize the selection tint to gray when the window isn't key
    /// (matching List/NSTableView), so the user can see which window drives
    /// keyboard input — HIG: only key-window controls carry color. macOS-only;
    /// iOS has no key-window concept, so the selection stays tinted.
    private var effectiveSelectedTint: Color {
        // V3 (2026-08-09): NO controlActiveState re-gate — selectedTint is
        // selectionTint from the pane-focus test every row uses; a second
        // key-window gate made a tile grey while the equivalent list row
        // stayed accent. One focus test everywhere.
        selectedTint
    }

    var body: some View {
        VStack(spacing: 6) {
            ZStack {
                // Use a portrait aspect (3:4) so document/photo thumbnails
                // get a rectangle that matches typical page proportions —
                // not a square. Square forced one-row icon list to crop
                // photos awkwardly. (#718)
                // NO base card (Daniel, 2026-08-09: 'no white background') —
                // Finder's unselected icons sit directly on the canvas; the
                // grey squircle appears ONLY as the selection backdrop below.
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .fill(Color.clear)
                    .aspectRatio(1, contentMode: .fit)

                // Symbol for the nodes that HAVE no picture — folders and
                // workflow mirrors — thumbnail for everything else.
                //
                // #4516: a workflow mirror is a `.file` with no `fileType`, so
                // it fell through to a thumbnail fetch that returns nothing and
                // rendered an empty well. The glyph comes from
                // `Document.displaySymbol`, the same ladder the sidebar reads,
                // so one node is one symbol in every view mode.
                // #4514: a read-only system folder gets the sidebar's purple
                // gear-badged treatment here too, rather than being
                // indistinguishable from a folder the user may edit.
                if document.docType == .folder || document.isWorkflowNode {
                    Image(systemName: document.displaySymbol())
                        .font(.system(size: 48 * scale))
                        // The grid has always drawn FILLED folders. That is a
                        // rendering choice, not a different symbol, so it is
                        // `.symbolVariant` on the shared glyph rather than a
                        // second icon ladder that can drift from the sidebar's.
                        .symbolVariant(.fill)
                        .symbolRenderingMode(document.isLockedSystemNode ? .hierarchical : .monochrome)
                        .foregroundColor(document.isLockedSystemNode ? .purple : .accentColor)
                } else if document.fileType == .image {
                    // Scale-to-FIT (#4197, the user 2026-07-28): show the whole
                    // page letterboxed in the well; cropping a landscape
                    // page's sides off beats nothing in an archive. The well
                    // keeps its fixed size — only the image letterboxes.
                    LibraryImageView(documentId: document.id, imageType: .thumbnail)
                        .aspectRatio(contentMode: .fit)
                        // Explicit frame, not maxWidth/maxHeight (#789 class):
                        // a LANDSCAPE image's intrinsic width wins the layout
                        // pass and blows the tile past its cell. Inset makes
                        // the thumbnail 'a bit smaller' inside the square
                        // well (Finder).
                        .frame(
                            width: (Self.wellWidth - 2 * Self.wellContentInset) * scale,
                            height: (Self.wellHeight - 2 * Self.wellContentInset) * scale
                        )
                        .clipped()
                } else if document.docType != .page, document.fileType != .pdf, let preview = document.pageContent, !preview.isEmpty {
                    // Text-preview thumbnail (#625) is only for genuinely text
                    // documents (JSON/plain text) with no page image. A PDF page
                    // ALWAYS renders its page image via the storage endpoint
                    // below — never its extracted `pageContent` text. (#2052)
                    // A mini PAGE centered in the well, like Finder's text-file
                    // icons — not full-bleed text across the square (the
                    // preview catalog showed it as raw floating text once the
                    // base card went clear, 2026-08-09).
                    TextPreviewThumbnail(text: preview)
                        .frame(
                            width: (Self.wellHeight - 2 * Self.wellContentInset) * scale * 0.77,
                            height: (Self.wellHeight - 2 * Self.wellContentInset) * scale
                        )
                } else {
                    // Load thumbnail from backend API with library path header.
                    // Scale-to-fit (#4197): whole page visible, letterboxed.
                    // Explicit frame (#789): without it, the intrinsic image
                    // size wins the layout pass and landscape pages overlap
                    // the neighbour. Required with .fit too.
                    LibraryImageView(documentId: document.id, imageType: .thumbnail)
                        .aspectRatio(contentMode: .fit)
                        .frame(
                            width: (Self.wellWidth - 2 * Self.wellContentInset) * scale,
                            height: (Self.wellHeight - 2 * Self.wellContentInset) * scale
                        )
                        .clipped()
                }

                VStack {
                    Spacer()
                    HStack {
                        if document.isLinked {
                            Image(systemName: "arrow.up.right.square")
                                .font(.system(size: 9, weight: .semibold))
                                .foregroundStyle(.secondary)
                                .shadow(color: Color(.windowBackgroundColor), radius: 1)
                                .padding(5)
                        }
                        Spacer()
                        statusIndicator
                            .padding(4)
                    }
                }
            }
            // Pin the whole well, not just the image branch — the ZStack
            // otherwise grows to its largest child's intrinsic size.
            .frame(width: Self.wellWidth * scale, height: Self.wellHeight * scale)
            .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
            // Finder's icon-view selection, half one (Daniel's screenshot,
            // 2026-08-08, #4563): a grey rounded backdrop behind the ICON —
            // never a wash over the whole tile.
            .padding(3)
            .background(
                RoundedRectangle(cornerRadius: LibrarySelectionStyle.cornerRadius)
                    .fill(isSelected ? LibrarySelectionStyle.fill : Color.clear)
            )

            // PDF page children label by page number (prefer extracted
            // page_label once #2080 lands), never their internal id/filename.
            // `pageThumbnailLabel` is nil for non-page docs, so top-level
            // documents keep their name. (#2053)
            if isRenaming {
                EditableDocumentName(
                    document: document,
                    isRenaming: true,
                    editingName: editingName,
                    font: .caption,
                    alignment: .center,
                    onCommit: onCommitRename,
                    onCancel: onCancelRename
                )
            } else {
                // `pageThumbnailLabel ?? name` still fell through to the
                // storage name for a page with no sequence (#4416).
                Text(DocumentTitle.displayName(for: document))
                    // .callout, not .caption (Daniel, 2026-08-09: "name font
                    // size for icon is too small") — Finder's icon label size.
                    .font(.callout)
                    // Fixed two-line label (#4191 density cap): short and
                    // long names produce identical tile heights, so the grid
                    // never re-pitches between rows.
                    .lineLimit(2, reservesSpace: true)
                    .truncationMode(.middle)
                    .multilineTextAlignment(.center)
                    // Finder's icon-view selection, half two (Daniel's
                    // screenshot, 2026-08-08, #4563): the NAME gets the
                    // accent pill with white text when the pane is key,
                    // grey pill when it isn't (effectiveSelectedTint
                    // already encodes that switch).
                    .foregroundColor(isSelected ? .white : .primary)
                    .padding(.horizontal, 5)
                    .background(
                        // ACCENT pill whenever selected (Daniel's Finder
                        // screenshots, 2026-08-09: the label pill is the
                        // system color — pane focus greying it read as "the
                        // wrong color"). Finder keys this on the WINDOW, and
                        // the window is key when the user is clicking.
                        RoundedRectangle(cornerRadius: LibrarySelectionStyle.cornerRadius)
                            .fill(isSelected ? Color.accentColor : Color.clear)
                    )
                    // Middle-truncated labels reveal in full on hover (#4160).
                    .help(DocumentTitle.displayName(for: document))
            }
        }
        .frame(width: 100 * scale)
        .padding(6)
        // No whole-tile wash: Finder highlights the icon and the name pill,
        // never the tile (replaces the #4191 grey tile fill).
        // VoiceOver reads one coherent tile (#4160), same shape as list rows.
        .accessibilityElement(children: .combine)
        .accessibilityLabel(tileAccessibilityLabel)
        .accessibilityValue(document.status.rawValue.capitalized)
        .accessibilityHint(tileAccessibilityHint)
        .accessibilityAddTraits(isSelected ? .isSelected : [])
        .accessibilityIdentifier("libraryTile.\(document.id)")
    }

    private var tileAccessibilityLabel: String {
        // The visible label three lines above composes through DocumentTitle;
        // this one did not, so VoiceOver read `fichero_upload_c84fgjke.pdf`
        // for the tile a sighted user saw as "Page 1" (#4416). Two readings of
        // the same tile is worse than one wrong one.
        let name = DocumentTitle.displayName(for: document)
        if document.docType == .folder { return "\(name), folder" }
        if let fileType = document.fileType { return "\(name), \(fileType.rawValue)" }
        return name
    }

    private var tileAccessibilityHint: String {
        #if os(macOS)
        "Press Return to open, Space to preview. Right-click for actions."
        #else
        "Double tap and hold for actions."
        #endif
    }

    @ViewBuilder
    private var statusIndicator: some View {
        switch document.status {
        case .processing:
            ProgressView()
                .scaleEffect(0.5)
                .background(.ultraThinMaterial)
                .cornerRadius(4)
        case .completed:
            Image(systemName: "checkmark.circle.fill")
                .foregroundColor(.green)
                .font(.caption)
        case .failed:
            Image(systemName: "xmark.circle.fill")
                .foregroundColor(.red)
                .font(.caption)
        case .pending:
            EmptyView()
        }
    }
}

struct EntityThumbnailKindStyle {
    let label: String
    let systemName: String
    let tint: Color
}

struct EntityThumbnailView: View {
    let entity: Components.Schemas.KnowledgeEntity
    let isSelected: Bool
    let secondaryText: String
    let kindStyle: EntityThumbnailKindStyle
    var selectedTint: Color = .accentColor
    var scale: CGFloat = 1.0

    #if os(macOS)
    @Environment(\.controlActiveState) private var controlActiveState
    #endif

    /// #1840: de-emphasize the selection tint to gray when the window isn't key
    /// (matching List/NSTableView). macOS-only; iOS keeps the tint.
    private var effectiveSelectedTint: Color {
        // V3 (2026-08-09): NO controlActiveState re-gate — selectedTint is
        // selectionTint from the pane-focus test every row uses; a second
        // key-window gate made a tile grey while the equivalent list row
        // stayed accent. One focus test everywhere.
        selectedTint
    }

    init(
        entity: Components.Schemas.KnowledgeEntity,
        isSelected: Bool,
        secondaryText: String,
        kindStyle: EntityThumbnailKindStyle,
        selectedTint: Color = .accentColor,
        scale: CGFloat = 1.0
    ) {
        self.entity = entity
        self.isSelected = isSelected
        self.secondaryText = secondaryText
        self.kindStyle = kindStyle
        self.selectedTint = selectedTint
        self.scale = scale
    }

    var body: some View {
        VStack(spacing: 6) {
            ZStack {
                RoundedRectangle(cornerRadius: 6)
                    .fill(Color(.windowBackgroundColor))
                    .aspectRatio(3.0 / 4.0, contentMode: .fit)

                VStack(spacing: 10) {
                    ZStack {
                        Circle()
                            .fill(kindStyle.tint.opacity(0.16))
                            .frame(width: 50 * scale, height: 50 * scale)

                        Image(systemName: kindStyle.systemName)
                            .font(.system(size: 24 * scale, weight: .semibold))
                            .foregroundStyle(kindStyle.tint)
                    }

                    Text(kindStyle.label.uppercased())
                        .font(.system(size: 9 * scale, weight: .semibold))
                        .tracking(0.6)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                        .padding(.horizontal, 8)
                }
                .padding(12)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
            .clipShape(RoundedRectangle(cornerRadius: 6))
            // Finder's icon-view selection (Daniel's screenshot, 2026-08-08,
            // #4563): grey backdrop behind the ICON — see
            // DocumentThumbnailView.
            .padding(3)
            .background(
                RoundedRectangle(cornerRadius: LibrarySelectionStyle.cornerRadius)
                    .fill(isSelected ? LibrarySelectionStyle.fill : Color.clear)
            )

            VStack(spacing: 2) {
                Text(entity.canonicalName)
                    .font(.caption)
                    // Fixed two-line label (#4191 density cap) — see
                    // DocumentThumbnailView.
                    .lineLimit(2, reservesSpace: true)
                    .truncationMode(.tail)
                    .multilineTextAlignment(.center)
                    // Finder's name pill — accent + white whenever selected;
                    // see DocumentThumbnailView.
                    .foregroundColor(isSelected ? .white : .primary)
                    .padding(.horizontal, 5)
                    .background(
                        RoundedRectangle(cornerRadius: LibrarySelectionStyle.cornerRadius)
                            .fill(isSelected ? Color.accentColor : Color.clear)
                    )

                Text(secondaryText)
                    .font(.caption2)
                    .lineLimit(2, reservesSpace: true)
                    .multilineTextAlignment(.center)
                    .foregroundStyle(.secondary)
            }
        }
        .frame(width: 100 * scale)
        .padding(6)
        // No whole-tile wash: Finder highlights the icon and the name pill,
        // never the tile (replaces the #4191 grey tile fill).
        // VoiceOver: one coherent tile, same shape as document tiles (#4160).
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(entity.canonicalName), \(kindStyle.label)")
        .accessibilityValue(secondaryText)
        .accessibilityAddTraits(isSelected ? .isSelected : [])
        .accessibilityIdentifier("libraryEntityTile.\(entity.stableInspectorId)")
    }
}
