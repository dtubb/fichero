import SwiftUI

/// One group of the Inspector's segment pane (`source.editor.inspector-segment-pane-is-laid-out-in-groups`, #6413): a
/// titled box, as the system's grouped forms draw them.
struct InspectorGroupBox<Content: View>: View {
    let group: InspectorSegmentLayout.Group
    @ViewBuilder let content: Content

    var body: some View {
        GroupBox {
            VStack(alignment: .leading, spacing: 10) {
                content
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(4)
        } label: {
            Text(group.title).font(.subheadline.weight(.semibold))
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel(group.title)
    }
}

/// The Details group's first row: language, script and direction in words on one line, where each came from in its
/// tooltip ("Spanish · Latin · Left to Right").
struct InspectorDetailsLine: View {
    let rows: [InspectorLanguage.Row]

    var body: some View {
        if let line = InspectorSegmentLayout.detailsLine(rows) {
            Text(line)
                .font(.body)
                .textSelection(.enabled)
                .help(InspectorSegmentLayout.detailsHelp(rows))
                .accessibilityHint(InspectorSegmentLayout.detailsHelp(rows))
        } else {
            Text("Language, script and direction are not determined.")
                .font(.caption)
                .foregroundStyle(.secondary)
                .help(InspectorSegmentLayout.detailsHelp(rows))
        }
    }
}

/// The inspected segment's picture, cut from the page to its shape: the first thing in the head.
struct InspectorSegmentPicture: View {
    let segmentId: String

    @Environment(SegmentService.self) private var segmentService: SegmentService?
    @State private var picture: Data?

    var body: some View {
        Group {
            if let picture, let image = PlatformImage(data: picture) {
                Image(platformImage: image)
                    .resizable()
                    .scaledToFit()
                    .frame(maxWidth: .infinity, maxHeight: 64, alignment: .leading)
                    .accessibilityLabel("The segment's picture, cut from the page")
            }
        }
        .task(id: segmentId) {
            picture = nil
            guard let segmentService else { return }
            picture = try? await SegmentPictureService(client: segmentService.client).picture(segmentId: segmentId)
        }
    }
}

#Preview("Inspector groups: boxes, Details on one line") {
    ScrollView {
        VStack(alignment: .leading, spacing: 12) {
            InspectorGroupBox(group: .readings) {
                Text("Item dixo que la capilla")
            }
            InspectorGroupBox(group: .details) {
                InspectorDetailsLine(rows: [
                    .init(key: "language", title: "Language", value: "es", origin: "set by a person, for the project", basis: ""),
                    .init(key: "script", title: "Script", value: "Latn", origin: "set by a person, for the project", basis: ""),
                    .init(key: "direction", title: "Direction", value: "Left to Right", origin: "from the script", basis: "")
                ])
            }
            InspectorGroupBox(group: .history) {
                Text("Version 2, now").font(.subheadline)
            }
        }
        .padding(8)
    }
    .frame(width: 300, height: 320)
}
