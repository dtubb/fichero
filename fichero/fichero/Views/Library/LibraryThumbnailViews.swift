import FicheroAPIClient
import SwiftUI

// MARK: - Document Thumbnail View

struct DocumentThumbnailView: View {
    let document: Document
    let isSelected: Bool
    var selectedTint: Color = .accentColor
    var scale: CGFloat = 1.0

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

    init(
        document: Document,
        isSelected: Bool,
        selectedTint: Color = .accentColor,
        scale: CGFloat = 1.0
    ) {
        self.document = document
        self.isSelected = isSelected
        self.selectedTint = selectedTint
        self.scale = scale
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
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
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
                    // Pin to the cell's 3:4 aspect via the inner GeometryReader-
                    // style frame so wide-aspect images (panoramas, landscape
                    // photos) don't blow past the cell width and overlap the
                    // neighbour to the right (#789). `.fill` + `.clipped()`
                    // alone wasn't enough — without an explicit frame, the
                    // intrinsic image size won the layout pass.
                    LibraryImageView(documentId: document.id, imageType: .thumbnail)
                        .aspectRatio(contentMode: .fill)
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
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
            .clipShape(RoundedRectangle(cornerRadius: 6))
            .overlay(
                RoundedRectangle(cornerRadius: 6)
                    .stroke(isSelected ? effectiveSelectedTint : Color.clear, lineWidth: 2)
            )

            // PDF page children label by page number (prefer extracted
            // page_label once #2080 lands), never their internal id/filename.
            // `pageThumbnailLabel` is nil for non-page docs, so top-level
            // documents keep their name. (#2053)
            Text(document.pageThumbnailLabel ?? document.name)
                .font(.caption)
                .lineLimit(2)
                .truncationMode(.middle)
                .multilineTextAlignment(.center)
                .foregroundColor(isSelected ? effectiveSelectedTint : .primary)
        }
        .frame(width: 100 * scale)
        .padding(6)
        .background(
            RoundedRectangle(cornerRadius: 8)
                // #3875: focused tiles get a real Finder-blue highlight (accent
                // via effectiveSelectedTint), not a barely-there wash; collapses
                // to gray when the window isn't key / pane isn't focused.
                .fill(isSelected ? effectiveSelectedTint.opacity(0.2) : Color.clear)
        )
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
            .overlay(
                RoundedRectangle(cornerRadius: 6)
                    .stroke(isSelected ? effectiveSelectedTint : Color.clear, lineWidth: 2)
            )

            VStack(spacing: 2) {
                Text(entity.canonicalName)
                    .font(.caption)
                    .lineLimit(2)
                    .truncationMode(.tail)
                    .multilineTextAlignment(.center)
                .foregroundColor(isSelected ? effectiveSelectedTint : .primary)

                Text(secondaryText)
                    .font(.caption2)
                    .lineLimit(2)
                    .multilineTextAlignment(.center)
                    .foregroundStyle(.secondary)
            }
        }
        .frame(width: 100 * scale)
        .padding(6)
        .background(
            RoundedRectangle(cornerRadius: 8)
                // #3875: focused tiles get a real Finder-blue highlight (accent
                // via effectiveSelectedTint), not a barely-there wash; collapses
                // to gray when the window isn't key / pane isn't focused.
                .fill(isSelected ? effectiveSelectedTint.opacity(0.2) : Color.clear)
        )
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
