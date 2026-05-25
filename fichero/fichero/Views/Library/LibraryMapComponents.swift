import SwiftUI

// MARK: - Map Card (Tinderbox-style with thumbnail)

struct MapCard: View {
    let document: Document
    let isSelected: Bool
    let position: CGPoint

    @EnvironmentObject private var documentStore: DocumentStore

    /// See `MailStyleRow.resolvedParentPDFPath` — same fallback chain so
    /// page children render the correct PDF page on map cards even when
    /// the metadata path has gone stale or the parent PDF is only
    /// reachable via `selectedCollection`. (#927)
    private func resolvedParentPDFPath(for doc: Document) -> String? {
        let metadataPath = doc.metadata["pdf_path"]?.value as? String
        if let metadataPath, !metadataPath.isEmpty,
           !metadataPath.contains("/fichero-drop-"),
           FileManager.default.fileExists(atPath: metadataPath) {
            return metadataPath
        }
        let parentId = doc.metadata["pdf_parent_id"]?.value as? String ?? doc.parentId
        if let parentId {
            if let selected = documentStore.selectedCollection,
               selected.id == parentId,
               let selectedPath = selected.path,
               !selectedPath.isEmpty {
                return selectedPath
            }
            if let parent = documentStore.currentDocuments.first(where: { $0.id == parentId }),
               let parentPath = parent.path,
               !parentPath.isEmpty {
                return parentPath
            }
        }
        return metadataPath
    }

    var body: some View {
        VStack(spacing: 6) {
            // Thumbnail area
            ZStack {
                RoundedRectangle(cornerRadius: 6)
                    .fill(Color(.windowBackgroundColor))

                // PDFs + PDF page children render locally via PDFKit;
                // everything else loads thumbnail from backend API.
                if document.fileType == .pdf, let path = document.path, !path.isEmpty {
                    PDFThumbnailView(path: path, size: CGSize(width: 200, height: 280))
                        .clipped()
                } else if document.docType == .page,
                          let pdfPath = resolvedParentPDFPath(for: document),
                          !pdfPath.isEmpty {
                    let pageIndex = max(0, (document.sequence ?? 1) - 1)
                    PDFThumbnailView(
                        path: pdfPath,
                        size: CGSize(width: 200, height: 280),
                        pageIndex: pageIndex
                    )
                    .clipped()
                } else {
                    LibraryImageView(documentId: document.id, imageType: .thumbnail)
                        .aspectRatio(contentMode: .fill)
                        .clipped()
                }

                // Status indicator overlay
                VStack {
                    Spacer()
                    HStack {
                        Spacer()
                        Circle()
                            .fill(statusColor)
                            .frame(width: 12, height: 12)
                            .overlay(
                                Circle()
                                    .stroke(Color.white, lineWidth: 1.5)
                            )
                            .padding(4)
                    }
                }
            }
            .frame(width: 80, height: 80)
            .clipShape(RoundedRectangle(cornerRadius: 6))
            .overlay(
                RoundedRectangle(cornerRadius: 6)
                    .stroke(isSelected ? Color.accentColor : Color.gray.opacity(0.2), lineWidth: isSelected ? 2 : 1)
            )

            // Name label
            Text(document.name)
                .font(.caption)
                .lineLimit(2)
                .truncationMode(.middle)
                .multilineTextAlignment(.center)
                .frame(width: 90)
        }
        .padding(6)
        .background(
            RoundedRectangle(cornerRadius: 8)
                .fill(isSelected ? Color.accentColor.opacity(0.15) : Color.clear)
        )
        .shadow(color: .black.opacity(isSelected ? 0.15 : 0.05), radius: isSelected ? 4 : 2, x: 0, y: 1)
        .position(position)
    }

    private var statusColor: Color {
        switch document.status {
        case .pending: return .gray
        case .processing: return .blue
        case .completed: return .green
        case .failed: return .red
        }
    }
}

// MARK: - Map Grid Background

struct MapGridBackground: View {
    let gridSpacing: CGFloat = 40

    var body: some View {
        Canvas { context, size in
            // Draw grid
            let path = Path { path in
                // Vertical lines
                var xPos: CGFloat = 0
                while xPos < size.width {
                    path.move(to: CGPoint(x: xPos, y: 0))
                    path.addLine(to: CGPoint(x: xPos, y: size.height))
                    xPos += gridSpacing
                }

                // Horizontal lines
                var yPos: CGFloat = 0
                while yPos < size.height {
                    path.move(to: CGPoint(x: 0, y: yPos))
                    path.addLine(to: CGPoint(x: size.width, y: yPos))
                    yPos += gridSpacing
                }
            }

            context.stroke(path, with: .color(.gray.opacity(0.15)), lineWidth: 0.5)
        }
    }
}
