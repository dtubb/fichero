import SwiftUI

/// Inspector for the selected Mind Palace node. Shows the node's kind/label
/// and — always, when the node is backed by a document (`sourceId`) — the
/// get-back-to-source affordances: **Open source** opens the document in the
/// reading surface, **Reveal in Library** selects it in the Library sidebar.
///
/// Both reuse the existing `.ficheroOpenClaimSource` notification, which
/// `ContentView` handles by switching to Library mode and selecting the doc.
struct SpatialNodeInspector: View {
    let node: MindPalaceNode?

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            header
            Divider()
            if let node {
                detail(node)
            } else {
                ContentUnavailableView(
                    "No Selection",
                    systemImage: "cube.transparent",
                    description: Text("Select a node to see its details and source.")
                )
            }
            Spacer()
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .background(.bar)
    }

    private var header: some View {
        HStack {
            Text("Inspector").font(.headline).foregroundStyle(.primary)
            Spacer()
        }
        .padding(.horizontal, 12)
        .frame(height: 44)
    }

    @ViewBuilder
    private func detail(_ node: MindPalaceNode) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 8) {
                Image(systemName: node.nodeType.icon)
                    .foregroundStyle(.white)
                    .frame(width: 22, height: 22)
                    .background(node.nodeType.color, in: RoundedRectangle(cornerRadius: 5))
                VStack(alignment: .leading, spacing: 1) {
                    Text(node.displayLabel).font(.headline).lineLimit(2)
                    Text(node.nodeType.label).font(.caption).foregroundStyle(.secondary)
                }
            }

            LabeledContent("Position") {
                Text(String(format: "%.1f, %.1f, %.1f",
                            node.positionX, node.positionY, node.positionZ))
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(.secondary)
            }

            if let sourceId = node.sourceId, !sourceId.isEmpty {
                Divider()
                Text("Source").font(.caption.weight(.semibold)).foregroundStyle(.secondary)
                Button {
                    openSource(documentId: sourceId)
                } label: {
                    Label("Open source", systemImage: "arrow.up.forward.square")
                }
                .buttonStyle(.borderedProminent)

                Button {
                    openSource(documentId: sourceId)
                } label: {
                    Label("Reveal in Library", systemImage: "sidebar.left")
                }
                .buttonStyle(.bordered)
            } else {
                Divider()
                Text("This node is a native note (no source document).")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(12)
    }

    /// Switch to Library mode and select the source document. Reuses the
    /// existing claim-source navigation path handled by ContentView.
    private func openSource(documentId: String) {
        NotificationCenter.default.post(
            name: .ficheroOpenClaimSource,
            object: nil,
            userInfo: ["documentId": documentId]
        )
    }
}
