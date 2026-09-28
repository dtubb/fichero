import SwiftUI
#if canImport(AppKit)
import AppKit
#endif

/// The Inspector's Links section (5.7, #5164): the inspected segment's typed links, both ways, each
/// read from this end; Link (the two segments picked, first to second), Withdraw, and Copy Reference.
/// Each link verb is one audited action, undoable with ⌘Z.
struct InspectorLinksSection: View {
    let segmentId: String
    let documentId: String
    /// The focused pane's selection, in the order picked: the Link menu's two ends.
    let selectedIds: [String]

    @Environment(SegmentService.self) private var segmentService: SegmentService?
    @Environment(ActionStore.self) private var actionStore: ActionStore?
    @Environment(\.undoManager) private var undoManager
    @State private var links: [InspectorLinks.Link] = []
    @State private var types: [InspectorLinks.LinkType] = []

    private var service: LinkService? { segmentService.map { LinkService(client: $0.client) } }

    private var segments: [Segment] {
        segmentService.map { SegmentStore.shared(for: $0).segments(documentId: documentId) } ?? []
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text("Links").font(.headline)
                Spacer()
                linkMenu
                Button("Copy Reference") { Task { await copyReference() } }
                    .buttonStyle(.borderless)
                    .font(.caption)
                    .help("Copy a stable reference to this segment (fichero:segment/…)")
            }
            ForEach(InspectorLinks.rows(links, segments: segments)) { row in
                HStack(alignment: .firstTextBaseline) {
                    VStack(alignment: .leading, spacing: 1) {
                        Text("\(row.sentence) \(row.other)").font(.body)
                        if !row.detail.isEmpty {
                            Text(row.detail).font(.caption).foregroundStyle(.secondary)
                        }
                    }
                    Spacer()
                    Button("Withdraw") {
                        run("typed_link.delete", TypedLinkIdRequest(linkId: row.linkId), "Withdraw Link")
                    }
                    .buttonStyle(.borderless)
                    .font(.caption)
                    .help("Withdraw this link; it is kept in the record, not deleted")
                }
                .accessibilityElement(children: .combine)
            }
            if links.isEmpty {
                Text("No links.").font(.caption).foregroundStyle(.secondary)
            }
        }
        .task(id: segmentId) { await reload() }
    }

    private var linkMenu: some View {
        let pair = InspectorLinks.pair(selectedIds)
        return Menu("Link") {
            ForEach(types) { type in
                Button(type.label) {
                    guard let pair else { return }
                    run("typed_link.create", TypedLinkCreateRequest(fromId: pair.from, toId: pair.to, linkType: type.key),
                        "Link Segments")
                }
            }
        }
        .menuStyle(.button)
        .buttonStyle(.borderless)
        .fixedSize()
        .font(.caption)
        .disabled(pair == nil || types.isEmpty)
        .help(pair == nil ? "Select two segments: the first is linked to the second"
                          : "Link the first segment picked to the second")
    }

    private func reload() async {
        guard let service else { return }
        links = (try? await service.links(of: segmentId)) ?? []
        if types.isEmpty { types = (try? await service.types()) ?? [] }
    }

    private func copyReference() async {
        guard let service, let reference = try? await service.reference(segmentId: segmentId) else { return }
        #if canImport(AppKit)
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(reference, forType: .string)
        #endif
    }

    private func run<Params: Encodable>(_ name: String, _ params: Params, _ actionName: String) {
        guard let actionsService = actionStore?.actionsService else { return }
        let undoManager = undoManager
        Task {
            _ = try? await AuditedAction.run(
                name, params: params, actionName: actionName, actionsService: actionsService,
                undoManager: undoManager, afterChange: { await reload() }
            )
        }
    }
}
