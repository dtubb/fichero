import SwiftUI

/// Info tab content for DocumentInspector
struct DocumentInspectorInfoTab: View {
    let document: Document

    var body: some View {
        VStack(alignment: .center, spacing: 0) {
            headerSection
                .padding(.bottom, 8)

            Form {
                Section("Status") {
                    LabeledContent("State") {
                        HStack(spacing: 6) {
                            StatusBadge(status: document.status)
                            if document.status == .processing {
                                ProgressView().scaleEffect(0.7)
                            }
                        }
                    }
                    LabeledContent("Created") {
                        Text(document.createdAt, style: .date)
                    }
                    LabeledContent("Modified") {
                        Text(document.updatedAt, style: .relative)
                    }
                }

                Section("File") {
                    LabeledContent("Kind") {
                        Text(document.docType.rawValue.capitalized)
                    }
                    if let fileType = document.fileType {
                        LabeledContent("Type") {
                            Text(fileType.rawValue.capitalized)
                        }
                    }
                    if let fileSize = document.metadata["File_Size"]?.value as? Int {
                        LabeledContent("Size") {
                            Text(ByteCountFormatter.string(fromByteCount: Int64(fileSize), countStyle: .file))
                        }
                    }
                    if let width = document.metadata["Width"]?.value as? Int,
                       let height = document.metadata["Height"]?.value as? Int {
                        LabeledContent("Dimensions") {
                            Text("\(width) × \(height)")
                        }
                    }
                }
            }
            .formStyle(.grouped)
        }
    }

    // MARK: - Header Section

    private var headerSection: some View {
        VStack(alignment: .center, spacing: 10) {
            ZStack {
                RoundedRectangle(cornerRadius: 12)
                    .fill(Color(.windowBackgroundColor))
                    .frame(width: 80, height: 100)

                LibraryImageView(documentId: document.id, imageType: .thumbnail)
                    .aspectRatio(contentMode: .fill)
                    .frame(width: 80, height: 100)
                    .clipped()
            }
            .frame(width: 80, height: 100)
            .clipShape(RoundedRectangle(cornerRadius: 12))

            Text(document.name)
                .font(.headline)
                .multilineTextAlignment(.center)
                .lineLimit(3)
        }
        .frame(maxWidth: .infinity)
        .padding(.top, 8)
    }
}
