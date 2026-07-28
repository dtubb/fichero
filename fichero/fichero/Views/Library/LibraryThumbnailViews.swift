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

    /// The portrait 3:4 image well, at scale 1. Every branch pins to this
    /// size so no image's intrinsic dimensions can distort the grid.
    static let wellWidth: CGFloat = 100
    static let wellHeight: CGFloat = wellWidth * 4 / 3

    #if os(macOS)
    @Environment(\.controlActiveState) private var controlActiveState
    #endif

    /// #1840: de-emphasize the selection tint to gray when the window isn't key
    /// (matching List/NSTableView), so the user can see which window drives
    /// keyboard input — HIG: only key-window controls carry color. macOS-only;
    /// iOS has no key-window concept, so the selection stays tinted.
    private var effectiveSelectedTint: Color {
        #if os(macOS)
        controlActiveState == .key ? selectedTint : .secondary
        #else
        selectedTint
        #endif
    }

    var body: some View {
        VStack(spacing: 6) {
            ZStack {
                // Use a portrait aspect (3:4) so document/photo thumbnails
                // get a rectangle that matches typical page proportions —
                // not a square. Square forced one-row icon list to crop
                // photos awkwardly. (#718)
                RoundedRectangle(cornerRadius: 6)
                    .fill(Color(.windowBackgroundColor))
                    .aspectRatio(3.0 / 4.0, contentMode: .fit)

                // Show folder icon for folders, thumbnail for files.
                if document.docType == .folder {
                    Image(systemName: "folder.fill")
                        .font(.system(size: 48 * scale))
                        .foregroundColor(.accentColor)
                } else if document.fileType == .image {
                    LibraryImageView(documentId: document.id, imageType: .thumbnail)
                        .aspectRatio(contentMode: .fill)
                        // Explicit frame, not maxWidth/maxHeight (#789 class,
                        // Daniel 2026-07-27): a LANDSCAPE image's intrinsic
                        // width wins the layout pass and blows the tile past
                        // its portrait 3:4 cell, overlapping neighbours.
                        .frame(width: Self.wellWidth * scale, height: Self.wellHeight * scale)
                        .clipped()
                } else if document.docType != .page, document.fileType != .pdf, let preview = document.pageContent, !preview.isEmpty {
                    // Text-preview thumbnail (#625) is only for genuinely text
                    // documents (JSON/plain text) with no page image. A PDF page
                    // ALWAYS renders its page image via the storage endpoint
                    // below — never its extracted `pageContent` text. (#2052)
                    TextPreviewThumbnail(text: preview)
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                        .clipped()
                } else {
                    // Load thumbnail from backend API with library path header.
                    // Explicit frame (#789): `.fill` + `.clipped()` alone isn't
                    // enough — without it, the intrinsic image size wins the
                    // layout pass and landscape pages overlap the neighbour.
                    LibraryImageView(documentId: document.id, imageType: .thumbnail)
                        .aspectRatio(contentMode: .fill)
                        .frame(width: Self.wellWidth * scale, height: Self.wellHeight * scale)
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
            .clipShape(RoundedRectangle(cornerRadius: 6))

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
                Text(document.pageThumbnailLabel ?? document.name)
                    .font(.caption)
                    // Fixed two-line label (#4191 density cap): short and
                    // long names produce identical tile heights, so the grid
                    // never re-pitches between rows.
                    .lineLimit(2, reservesSpace: true)
                    .truncationMode(.middle)
                    .multilineTextAlignment(.center)
                    .foregroundColor(isSelected ? effectiveSelectedTint : .primary)
                    // Middle-truncated labels reveal in full on hover (#4160).
                    .help(document.pageThumbnailLabel ?? document.name)
            }
        }
        .frame(width: 100 * scale)
        .padding(6)
        .background(
            RoundedRectangle(cornerRadius: 8)
                // Mail-style selection (#4191): constant subtle grey fill in
                // every pane state; focus is signalled by the accent label
                // (effectiveSelectedTint) — replaces the #3875 accent wash
                // and the selected-well accent stroke.
                .fill(isSelected ? LibrarySelectionStyle.fill : Color.clear)
        )
        // VoiceOver reads one coherent tile (#4160), same shape as list rows.
        .accessibilityElement(children: .combine)
        .accessibilityLabel(tileAccessibilityLabel)
        .accessibilityValue(document.status.rawValue.capitalized)
        .accessibilityHint(tileAccessibilityHint)
        .accessibilityAddTraits(isSelected ? .isSelected : [])
        .accessibilityIdentifier("libraryTile.\(document.id)")
    }

    private var tileAccessibilityLabel: String {
        let name = document.pageThumbnailLabel ?? document.name
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
        #if os(macOS)
        controlActiveState == .key ? selectedTint : .secondary
        #else
        selectedTint
        #endif
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

            VStack(spacing: 2) {
                Text(entity.canonicalName)
                    .font(.caption)
                    // Fixed two-line label (#4191 density cap) — see
                    // DocumentThumbnailView.
                    .lineLimit(2, reservesSpace: true)
                    .truncationMode(.tail)
                    .multilineTextAlignment(.center)
                .foregroundColor(isSelected ? effectiveSelectedTint : .primary)

                Text(secondaryText)
                    .font(.caption2)
                    .lineLimit(2, reservesSpace: true)
                    .multilineTextAlignment(.center)
                    .foregroundStyle(.secondary)
            }
        }
        .frame(width: 100 * scale)
        .padding(6)
        .background(
            RoundedRectangle(cornerRadius: 8)
                // Mail-style selection (#4191): constant subtle grey fill in
                // every pane state; focus is signalled by the accent label
                // (effectiveSelectedTint) — replaces the #3875 accent wash
                // and the selected-well accent stroke.
                .fill(isSelected ? LibrarySelectionStyle.fill : Color.clear)
        )
        // VoiceOver: one coherent tile, same shape as document tiles (#4160).
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(entity.canonicalName), \(kindStyle.label)")
        .accessibilityValue(secondaryText)
        .accessibilityAddTraits(isSelected ? .isSelected : [])
        .accessibilityIdentifier("libraryEntityTile.\(entity.stableInspectorId)")
    }
}

// MARK: - TextPreviewThumbnail

/// Monospaced text thumbnail for JSON/text documents when no image thumbnail exists (#625).
struct TextPreviewThumbnail: View {
    let text: String

    private static let previewLimit = 600

    private var displayText: String {
        let trimmed = text.trimmingCharacters(in: .whitespaces)
        if trimmed.hasPrefix("{") || trimmed.hasPrefix("["),
           let data = trimmed.data(using: .utf8),
           let obj = try? JSONSerialization.jsonObject(with: data),
           let pretty = try? JSONSerialization.data(withJSONObject: obj, options: [.prettyPrinted]),
           let str = String(data: pretty, encoding: .utf8) {
            return String(str.prefix(Self.previewLimit))
        }
        return String(trimmed.prefix(Self.previewLimit))
    }

    var body: some View {
        Text(displayText)
            .font(.system(size: 6, design: .monospaced))
            .foregroundStyle(.primary)
            .lineSpacing(1)
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
            .padding(4)
            .background(Color(.textBackgroundColor))
            .allowsHitTesting(false)
    }
}
