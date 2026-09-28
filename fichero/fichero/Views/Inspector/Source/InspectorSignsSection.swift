import SwiftUI

/// The Inspector's Signs section (5.6): the declared signs this segment uses or was declared from,
/// and -- on a character segment -- its letterform, read-only. Hidden when it has nothing to say.
struct InspectorSignsSection: View {
    let segmentId: String
    /// The counting reading's text: which signs this segment uses.
    let reading: String?

    @Environment(SegmentService.self) private var segmentService: SegmentService?
    @Environment(WindowState.self) private var windowState: WindowState?
    @State private var rows: [InspectorSigns.Row] = []
    @State private var letterforms: [InspectorSigns.LetterformLine] = []

    var body: some View {
        // The container always exists (empty, it takes no room), so the load runs even while the
        // section has nothing to show: a `.task` on a view that is not there never runs.
        VStack(alignment: .leading, spacing: 0) {
            if !rows.isEmpty || !letterforms.isEmpty {
                content
            }
        }
        .task(id: "\(segmentId)|\(reading ?? "")") { await reload() }
    }

    private var content: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Signs").font(.headline)
            ForEach(rows) { row in
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    if let glyph = row.glyph {
                        Text(glyph).font(.title3).accessibilityHidden(true)
                    }
                    VStack(alignment: .leading, spacing: 1) {
                        Text(row.title).font(.body)
                        Text(row.detail).font(.caption).foregroundStyle(.secondary)
                    }
                    Spacer()
                    Button("Every Instance") { windowState?.segmentsGather = .sign(id: row.signId, name: row.title) }
                        .buttonStyle(.borderless)
                        .font(.caption)
                        .help("List every use of this sign in the Segments pane")
                }
            }
            ForEach(letterforms) { line in
                VStack(alignment: .leading, spacing: 1) {
                    Text(line.chain).font(.body).textSelection(.enabled)
                    if !line.detail.isEmpty {
                        Text(line.detail).font(.caption).foregroundStyle(.secondary)
                    }
                }
                .accessibilityElement(children: .combine)
                .accessibilityLabel("Letterform: \(line.chain). \(line.detail)")
            }
        }
    }

    private func reload() async {
        guard let segmentService else { return }
        let service = SignService(client: segmentService.client)
        let signs = (try? await service.signs()) ?? []
        var shown = InspectorSigns.rows(signs: signs, segmentId: segmentId, reading: reading)
        var totals: [String: Int] = [:]
        for row in shown {
            if let total = try? await service.totalUses(signId: row.signId) { totals[row.signId] = total }
        }
        if !totals.isEmpty {
            shown = InspectorSigns.rows(signs: signs, segmentId: segmentId, reading: reading, usedInProject: totals)
        }
        rows = shown
        let forms = (try? await service.letterforms(segmentId: segmentId)) ?? []
        guard !forms.isEmpty else {
            letterforms = []
            return
        }
        let allographs = (try? await service.allographNames()) ?? [:]
        let hands = (try? await HandService(client: segmentService.client).hands()) ?? []
        letterforms = InspectorSigns.lines(
            forms, allographs: allographs,
            hands: Dictionary(hands.map { ($0.id, $0.label) }, uniquingKeysWith: { first, _ in first })
        )
    }
}

#if DEBUG
#Preview("Signs: the MUFI sign on a line, and a character's letterform") {
    let rows = InspectorSigns.rows(
        signs: [.init(id: "s1", name: "MUFI abbreviation sign", pictureSegmentId: "l1", codePoint: "U+F1AC",
                      listReferences: [.init(authority: "MUFI", number: "F1AC")])],
        segmentId: "l1", reading: "⁋ ꝓc̾atur \u{F1AC} ⁋", usedInProject: ["s1": 50]
    )
    let forms = InspectorSigns.lines(
        [.init(id: "d1", character: "ܐ", allographId: "a1", handId: "h1",
               features: [(component: "stem", feature: "wedged")], describedBy: "owner")],
        allographs: ["a1": "Estrangela alaph"], hands: ["h1": "hand B"]
    )
    VStack(alignment: .leading, spacing: 6) {
        Text("Signs").font(.headline)
        ForEach(rows) { row in
            Text(row.title)
            Text(row.detail).font(.caption).foregroundStyle(.secondary)
        }
        ForEach(forms) { line in
            Text(line.chain)
            Text(line.detail).font(.caption).foregroundStyle(.secondary)
        }
    }
    .padding()
    .frame(width: 340)
}
#endif
