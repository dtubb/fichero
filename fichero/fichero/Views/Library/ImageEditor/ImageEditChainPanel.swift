import SwiftUI

/// Lists the document's non-destructive edit operations with a per-op remove
/// affordance and a "Reset all edits" action (#469).
///
/// The chain is read-only data; mutations are delegated to the parent via the
/// `onRemove` / `onReset` callbacks (which call the model, which calls the
/// backend `PUT`/`DELETE /edits`).
struct ImageEditChainPanel: View {
    let chain: ImageEditChain
    let isBusy: Bool
    let onRemove: (Int) -> Void
    let onReset: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            header
            Divider()
            if chain.isEmpty {
                emptyState
            } else {
                opList
            }
        }
        .background(Color(.windowBackgroundColor))
    }

    private var header: some View {
        HStack {
            Label("Edits", systemImage: "slider.horizontal.3")
                .font(.headline)
                .foregroundStyle(.primary)
            Spacer()
            if !chain.isEmpty {
                Text("\(chain.operations.count)")
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(.secondary)
                Button(role: .destructive, action: onReset) {
                    Image(systemName: "trash")
                }
                .buttonStyle(.borderless)
                .disabled(isBusy)
                .help("Reset all edits — restores the original image")
                .accessibilityIdentifier("imageEditChainReset")
            }
        }
        .padding(.horizontal, 12)
        .frame(height: 44)
    }

    private var emptyState: some View {
        VStack(spacing: 8) {
            Image(systemName: "wand.and.stars")
                .font(.title2)
                .foregroundStyle(.tertiary)
            Text("No edits yet")
                .font(.subheadline)
                .foregroundStyle(.secondary)
            Text("Edits are non-destructive — the original is never modified.")
                .font(.caption)
                .foregroundStyle(.tertiary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 24)
        .padding(.horizontal, 12)
    }

    private var opList: some View {
        ScrollView {
            LazyVStack(spacing: 0) {
                ForEach(Array(chain.operations.enumerated()), id: \.element.id) { index, operation in
                    opRow(index: index, op: operation)
                    if index < chain.operations.count - 1 {
                        Divider().padding(.leading, 40)
                    }
                }
            }
        }
    }

    private func opRow(index: Int, op operation: ImageEditOperation) -> some View {
        HStack(spacing: 10) {
            Image(systemName: operation.icon)
                .frame(width: 22)
                .foregroundStyle(.secondary)
            VStack(alignment: .leading, spacing: 1) {
                Text(operation.title)
                    .font(.subheadline)
                if !operation.summary.isEmpty {
                    Text(operation.summary)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            Spacer()
            Button {
                onRemove(index)
            } label: {
                Image(systemName: "minus.circle")
            }
            .buttonStyle(.borderless)
            .disabled(isBusy)
            .help("Remove this edit")
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .contentShape(Rectangle())
    }
}

#Preview("With edits") {
    ImageEditChainPanel(
        chain: ImageEditChain(
            documentId: "doc1",
            operations: [
                ImageEditOperation(raw: AnyCodable(["op": "rotate", "page": 1] as [String: Any])),
                ImageEditOperation(raw: AnyCodable(["op": "enhance", "page": 1] as [String: Any])),
                ImageEditOperation(raw: AnyCodable(["op": "remove_background", "page": 1] as [String: Any]))
            ],
            updatedAt: nil
        ),
        isBusy: false,
        onRemove: { _ in },
        onReset: {}
    )
    .frame(width: 260, height: 400)
}

#Preview("Empty") {
    ImageEditChainPanel(
        chain: ImageEditChain(documentId: "doc1", operations: [], updatedAt: nil),
        isBusy: false,
        onRemove: { _ in },
        onReset: {}
    )
    .frame(width: 260, height: 400)
}
