import SwiftUI

extension ChatInspector {
    var scopedDocumentsView: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 8) {
                Image(systemName: "checkmark.circle.fill")
                    .foregroundColor(.green)

                Text("\(selectedDocuments.count) in scope")
                    .font(.caption)
                    .foregroundColor(.secondary)

                if !listSelection.isEmpty {
                    Text("• \(listSelection.count) selected")
                        .font(.caption)
                        .foregroundColor(.accentColor)
                }

                Spacer()

                if showsTouchScopeActions, pendingSuggestedDocumentCount > 0 {
                    Button {
                        addSuggestedDocumentsToScope()
                    } label: {
                        Label("Add to Chat", systemImage: "plus.circle")
                    }
                    .buttonStyle(.bordered)
                }
            }
            .padding(.horizontal)
            .padding(.vertical, 6)
            .background(Color(.controlBackgroundColor).opacity(0.5))

            List(selection: $listSelection) {
                ForEach(scopedDocuments) { doc in
                    ScopedDocumentRow(document: doc)
                        .tag(doc.id)
                }
                .onDelete { indexSet in
                    let idsToRemove = indexSet.map { scopedDocuments[$0].id }
                    for id in idsToRemove {
                        selectedDocuments.remove(id)
                    }
                }
            }
            .listStyle(.plain)
        }
    }

    var emptyStateView: some View {
        VStack(spacing: 12) {
            Image(systemName: "plus.rectangle.on.folder")
                .font(.system(size: 36))
                .foregroundColor(.secondary)

            Text("No documents in scope")
                .font(.subheadline)
                .foregroundColor(.secondary)

            Text(emptyStateInstructionText)
                .font(.caption)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal)

            if showsTouchScopeActions, pendingSuggestedDocumentCount > 0 {
                Button {
                    addSuggestedDocumentsToScope()
                } label: {
                    Label("Add Current Selection to Chat", systemImage: "plus.circle.fill")
                }
                .buttonStyle(.borderedProminent)
            }

            Divider()
                .padding(.vertical, 8)

            VStack(spacing: 8) {
                Text("Document Maintenance")
                    .font(.caption)
                    .foregroundColor(.secondary)

                if isExtracting {
                    HStack {
                        ProgressView()
                            .scaleEffect(0.7)
                        Text("Extracting text...")
                            .font(.caption)
                    }
                } else {
                    Button {
                        Task { await extractAllText() }
                    } label: {
                        Label("Extract Text from All Documents", systemImage: "doc.text.magnifyingglass")
                            .font(.caption)
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.small)
                }

                if let result = extractionResult {
                    Text(result)
                        .font(.caption2)
                        .foregroundColor(.secondary)
                        .multilineTextAlignment(.center)
                }
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding()
    }

    private var emptyStateInstructionText: String {
        if showsTouchScopeActions {
            return "Search above or tap Add Current Selection to focus your chat."
        }
        return "Search above or drag documents from Library to focus your chat."
    }

    var loadingView: some View {
        VStack {
            ProgressView()
            Text("Loading...")
                .font(.caption)
                .foregroundColor(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    var dropOverlay: some View {
        ZStack {
            Color.accentColor.opacity(0.15)
            VStack(spacing: 8) {
                Image(systemName: "plus.circle.fill")
                    .font(.title)
                    .foregroundColor(.accentColor)
                Text("Drop to add to scope")
                    .font(.subheadline)
                    .foregroundColor(.accentColor)
            }
        }
        .cornerRadius(8)
        .padding(4)
    }
}

struct ScopedDocumentRow: View {
    let document: Document

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: document.fileType?.icon ?? "doc")
                .foregroundColor(.secondary)
                .frame(width: 16)

            VStack(alignment: .leading, spacing: 2) {
                Text(document.name)
                    .font(.subheadline)
                    .lineLimit(1)

                if let fileType = document.fileType {
                    Text(fileType.rawValue.capitalized)
                        .font(.caption2)
                        .foregroundColor(.secondary)
                }
            }

            Spacer()
        }
        .padding(.vertical, 4)
        .contentShape(Rectangle())
    }
}
