import SwiftUI

/// The Inspector's Making section at SEGMENT level (#5163): the segment's picture, cut from the page to
/// its shape; its baseline in words; and its own history -- each kept version with what the change
/// after it did, and Restore, the audited `segment.restore_version` with ⌘Z. The ninth section of the
/// ruled nine at the page level (`InspectorMakingSection`) is the same section here, one level down.
struct InspectorSegmentMakingSection: View {
    let segmentId: String
    let documentId: String

    @Environment(SegmentService.self) private var segmentService: SegmentService?
    @Environment(ActionStore.self) private var actionStore: ActionStore?
    @Environment(\.undoManager) private var undoManager
    @State private var live: Segment?
    @State private var versions: [SegmentHistory.Version] = []
    @State private var picture: Data?
    @State private var failure: String?

    var body: some View {
        // Always present, so the load below runs; empty until the segment has been read.
        VStack(alignment: .leading, spacing: 8) {
            if let live {
                Text("Making").font(.headline)
                if let picture, let image = PlatformImage(data: picture) {
                    Image(platformImage: image)
                        .resizable()
                        .scaledToFit()
                        .frame(maxHeight: 80)
                        .accessibilityLabel("The segment's picture, cut from the page")
                }
                if let baseline = SegmentHistory.baselineDescription(live.baseline) {
                    Text(baseline).font(.caption).foregroundStyle(.secondary)
                }
                if let version = live.version {
                    Text("Version \(version), now").font(.subheadline)
                }
                ForEach(SegmentHistory.rows(versions, live: SegmentHistory.state(of: live)), id: \.version.id) { row in
                    versionRow(row.version, then: row.then, live: live)
                }
                if let failure {
                    Text(failure).font(.caption).foregroundStyle(.secondary)
                }
            }
        }
        .task(id: segmentId) { await reload() }
    }

    private func versionRow(_ version: SegmentHistory.Version, then: [String], live: Segment) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack(alignment: .firstTextBaseline) {
                Text("Version \(version.version)").font(.subheadline)
                Spacer(minLength: 8)
                if SegmentHistory.restore(version, of: live) != nil {
                    Button("Restore") { Task { await restore(version, of: live) } }
                        .buttonStyle(.borderless)
                        .font(.caption)
                        .help("Put the segment back as it was at version \(version.version)")
                }
            }
            Text(detail(version, then: then)).font(.caption).foregroundStyle(.secondary)
        }
        .accessibilityElement(children: .combine)
    }

    private func detail(_ version: SegmentHistory.Version, then: [String]) -> String {
        var parts: [String] = []
        if !then.isEmpty { parts.append("then " + then.joined(separator: ", ")) }
        if let actor = version.actor { parts.append(actor) }
        if let reason = version.reason { parts.append(reason) }
        if let createdAt = version.createdAt { parts.append(createdAt.formatted(date: .abbreviated, time: .shortened)) }
        return parts.joined(separator: " · ")
    }

    private func reload() async {
        guard let segmentService else { return }
        live = try? await segmentService.segment(id: segmentId)
        versions = (try? await segmentService.versions(segmentId: segmentId)) ?? []
        picture = try? await SegmentPictureService(client: segmentService.client).picture(segmentId: segmentId)
    }

    private func restore(_ version: SegmentHistory.Version, of live: Segment) async {
        guard let segmentService, let actionsService = actionStore?.actionsService,
              let params = SegmentHistory.restore(version, of: live) else { return }
        let store = SegmentStore.shared(for: segmentService)
        let documentId = documentId
        do {
            try await AuditedAction.run(
                "segment.restore_version", params: params, actionName: "Restore Version",
                actionsService: actionsService, undoManager: undoManager,
                afterChange: {
                    await store.load(documentId: documentId, force: true)
                    await reload()
                }
            )
            failure = nil
        } catch {
            failure = "The version could not be restored: \(error.localizedDescription)"
        }
    }
}

#if DEBUG
#Preview("Making at a line: a curved baseline") {
    Text(SegmentHistory.baselineDescription([[0.1, 0.70], [0.3, 0.71], [0.8, 0.70]]) ?? "")
        .padding()
}
#endif
