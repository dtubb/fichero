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
    /// Two callout lines — the #4191 uniform-tile reservation, held by an
    /// outer frame so the name pill can hug the actual text (2026-08-09).
    static let labelBlockHeight: CGFloat = 38

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
                        // Folders stack like PDFs do (Daniel, 2026-08-09:
                        // "folders should work the same way") — sheets peek
                        // out behind a fuller folder.
                        .background {
                            if document.docType == .folder,
                               stackSheetCount(forChildCount: document.childCount) > 0 {
                                PDFStackSheets(
                                    scale: scale * 0.7,
                                    count: stackSheetCount(forChildCount: document.childCount)
                                )
                                .padding(8 * scale)
                            }
                        }
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
                        // Finder's light thumbnail edge (Daniel #119).
                        .overlay(
                            RoundedRectangle(cornerRadius: 3)
                                .strokeBorder(Color.primary.opacity(0.12), lineWidth: 0.5)
                        )
                        // Finder's grey squircle "jail" (#23, Daniel #125-128):
                        // an image thumbnail sits centered in a light grey
                        // rounded square filling the WHOLE well, so odd
                        // aspect ratios read as one consistent square tile
                        // with equal margins (wellContentInset on every side).
                        // Images only — PDFs/folders keep their page-stack and
                        // glyph treatments on the bare canvas.
                        .frame(width: Self.wellWidth * scale, height: Self.wellHeight * scale)
                        .background(
                            RoundedRectangle(cornerRadius: 9, style: .continuous)
                                .fill(.quaternary.opacity(0.5))
                        )
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
                    LibraryImageView(documentId: document.id, imageType: .thumbnail)
                        .aspectRatio(contentMode: .fit)
                        // Edge + sheets attach BEFORE the framing (Daniel
                        // #121-123: "the shape of the paper around the paper
                        // is not the same shape as the icon"): the
                        // aspectRatio(.fit) node sizes itself to the fitted
                        // PAGE rect, so the hairline hugs the page and the
                        // stack sheets behind are page-shaped — never the
                        // square well.
                        .overlay(
                            // Finder's light thumbnail edge (#119).
                            RoundedRectangle(cornerRadius: 3)
                                .strokeBorder(Color.primary.opacity(0.12), lineWidth: 0.5)
                        )
                        // A multi-page PDF reads as a STACK, deeper for
                        // bigger documents ("a 500 page pdf is larger than
                        // a 2 page pdf").
                        .background {
                            if document.fileType == .pdf, document.docType != .page,
                               stackSheetCount(forChildCount: document.childCount) > 0 {
                                PDFStackSheets(
                                    scale: scale,
                                    count: stackSheetCount(forChildCount: document.childCount)
                                )
                            }
                        }
                        // Explicit frame AFTER the page-hugging chrome (#789
                        // class): the fitted content centers in the fixed
                        // well slot so landscape pages can't blow the tile.
                        .frame(
                            width: (Self.wellWidth - 2 * Self.wellContentInset) * scale,
                            height: (Self.wellHeight - 2 * Self.wellContentInset) * scale
                        )
                        // Re-center the composition (Daniel #119: "not quite
                        // centred"): the sheets fan up-right, so the cover
                        // shifts down-left by half the deepest sheet offset
                        // and the GROUP sits centered in the well.
                        .offset(
                            x: -1.5 * CGFloat(stackSheetCount(forChildCount: document.childCount)) * scale,
                            y: 1.5 * CGFloat(stackSheetCount(forChildCount: document.childCount)) * scale
                        )
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
                    // lineLimit WITHOUT reservesSpace here (Daniel,
                    // 2026-08-09: "text should be centred with the green" —
                    // the reserved empty second line lived INSIDE the text
                    // frame, so the pill wrapped it and one-line names sat
                    // high with dead pill below). The density cap moves to
                    // the fixed-height frame OUTSIDE the pill instead.
                    .lineLimit(2)
                    .truncationMode(.middle)
                    .multilineTextAlignment(.center)
                    // Finder's icon-view selection, half two (Daniel's
                    // screenshot, 2026-08-08, #4563): the NAME gets the
                    // accent pill with white text when the pane is key,
                    // grey pill when it isn't (effectiveSelectedTint
                    // already encodes that switch).
                    .foregroundColor(isSelected ? .white : .primary)
                    .padding(.horizontal, 5)
                    .padding(.vertical, 1)
                    .background(
                        // ACCENT pill whenever selected (Daniel's Finder
                        // screenshots, 2026-08-09: the label pill is the
                        // system color — pane focus greying it read as "the
                        // wrong color"). Finder keys this on the WINDOW, and
                        // the window is key when the user is clicking.
                        RoundedRectangle(cornerRadius: LibrarySelectionStyle.cornerRadius)
                            .fill(isSelected ? Color.accentColor : Color.clear)
                    )
                    // The #4191 density cap, now OUTSIDE the pill: every tile
                    // reserves the same two-line block whether the name uses
                    // one line or two, and the pill hugs the actual text.
                    .frame(height: Self.labelBlockHeight * scale, alignment: .top)
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
            // NO green done-check (Daniel, 2026-08-09): "it's not clear that
            // it means anything… we want things are operating or there are
            // errors." Activity and failure stay; quiet success is quiet.
            // FUTURE: togglable per-icon workflow-metadata overlays.
            EmptyView()
        case .failed:
            Image(systemName: "xmark.circle.fill")
                .foregroundColor(.red)
                .font(.caption)
        case .pending:
            EmptyView()
        }
    }
}
