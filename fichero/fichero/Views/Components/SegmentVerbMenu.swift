import SwiftUI

/// The segment verbs beyond Correct, Show and Delete, as ONE menu body for every surface that lists lines
/// (`source.editor.segment-verbs-are-the-same-everywhere`, Step 1.25): the Order list's row menu and the Reader's line
/// menu both mount it, so no surface has a verb another lacks. A verb that cannot apply to `ids` is absent, never greyed.
/// Each is the one audited call (`SegmentMover`, `SegmentEdit`), one ⌘Z.
struct SegmentVerbMenu: View {
    /// The segments the verb means: the row, or the selection when it holds the row (`SegmentDeleter.ids`).
    let ids: [String]
    let documentId: String
    /// Why a verb did nothing, or nil when it was sent; the host says it under its list.
    var onNote: (String?) -> Void = { _ in }

    @Environment(SegmentService.self) private var segmentService: SegmentService?
    @Environment(ActionStore.self) private var actionStore: ActionStore?
    @Environment(WindowSteps.self) private var windowSteps: WindowSteps?
    @Environment(WindowState.self) private var windowState: WindowState?

    var body: some View {
        let segments = store?.workingSegments(documentId: documentId) ?? []
        let targets = SegmentMover.targets(for: ids, in: segments)
        if let first = targets.first {
            // What the selection can go into is one level coarser than it: a line into a region, a word into a line, a
            // letter into a word. Named by kind and by place among that kind on the page, as the lists name them.
            let noun = InspectorPath.name(of: first)
            Menu("Move Into \(noun)") {
                ForEach(targets, id: \.id) { target in
                    let position = (segments.filter { $0.kind == target.kind }.firstIndex { $0.id == target.id } ?? 0) + 1
                    Button("\(noun) \(position)") { move(into: target.id) }
                }
            }
        }
        if SegmentMover.canLift(ids, in: segments) {
            let byId = Dictionary(segments.map { ($0.id, $0) }, uniquingKeysWith: { first, _ in first })
            let parent = ids.lazy.compactMap { byId[$0]?.parentSegmentId }.compactMap { byId[$0] }.first
            Button("Lift Out of \(parent.map(InspectorPath.name(of:)) ?? "Region")") { move(into: nil) }
        }
        if ids.count >= 2 {
            Button("Join") { run("Join Lines", selectingJoined: true) { SegmentEdit.join($0) } }
        }
        let kinds = ids.compactMap { id in segments.first { $0.id == id }?.kind }
        ForEach(Self.regionVerbs(kinds: kinds), id: \.self) { verb in
            Button(verb.title) { run(verb) }
        }
        if ids.count >= 2 {
            Button("Join Lines in the Same Row") {
                run("Join Lines in the Same Row", selectingJoined: true) { SegmentEdit.joinRows($0) }
            }
        }
        if !ids.isEmpty {
            Divider()
            Button("Convert to Line") { run("Convert to Line") { SegmentEdit.convertLevel($0, to: "line") } }
            Button("Convert to Region") { run("Convert to Region") { SegmentEdit.convertLevel($0, to: "region") } }
            Divider()
            SegmentAttributeMenu.Items(apply: { attribute in
                run("Set Segment") { SegmentEdit.set(attribute, on: $0) }
            })
        }
    }

    /// Make Region from Lines and Ungroup Region, the same two the Edit menu and the page's menu carry
    /// (`segment-editor.make-region-in-every-menu`).
    enum RegionVerb { case makeRegion, ungroupRegion

        var title: String { self == .makeRegion ? "Make Region from Lines" : "Ungroup Region" }
    }

    /// What the menu offers for a selection of these kinds: Make Region for two or more, Ungroup for any region.
    static func regionVerbs(kinds: [String]) -> [RegionVerb] {
        var verbs: [RegionVerb] = []
        if kinds.count >= 2 { verbs.append(.makeRegion) }
        if kinds.contains("region") { verbs.append(.ungroupRegion) }
        return verbs
    }

    private func run(_ verb: RegionVerb) {
        guard let store, let actionsService = actionStore?.actionsService else { return }
        let segments = SegmentDeleter.segments(ids, documentId: documentId, store: store)
        let steps = windowSteps, documentId = documentId
        let note = onNote, windowState = windowState
        let calls: [(SegmentEdit.Call, String)]
        switch verb {
        case .makeRegion:
            guard case .success(let call) = SegmentEdit.groupLines(segments) else { return note("Select two or more lines") }
            calls = [(call, "Make Region from Lines")]
        case .ungroupRegion:
            calls = segments.filter { $0.kind == "region" }.compactMap { region in
                guard case .success(let call) = SegmentEdit.ungroupRegion(region) else { return nil }
                return (call, "Ungroup Region")
            }
        }
        Task {
            do {
                for (call, name) in calls {
                    let answer = try await SegmentEditRunner(actionsService: actionsService, store: store).runAnswering(
                        call, documentId: documentId, actionName: name, steps: steps
                    )
                    let region = SegmentEdit.selectionAfterGroup(regionId: answer.resultStrings["region_id"])
                    if verb == .makeRegion, !region.isEmpty, let windowState {
                        windowState.pickInReader(region, documentId: documentId, store: store)
                    }
                }
                note(nil)
            } catch { note("That did not happen: \(error.localizedDescription)") }
        }
    }

    private var store: SegmentStore? { segmentService.map { SegmentStore.shared(for: $0) } }

    private func move(into parent: String?) {
        guard let store else { return }
        let segments = SegmentDeleter.segments(ids, documentId: documentId, store: store)
        let actionsService = actionStore?.actionsService, steps = windowSteps, documentId = documentId
        let note = onNote
        Task {
            note(await SegmentMover.run(
                segments, into: parent, documentId: documentId, store: store, services: (actionsService, steps)
            ))
        }
    }

    private func run(
        _ actionName: String, selectingJoined: Bool = false, plan: @escaping ([Segment]) -> Result<SegmentEdit.Call, SegmentEdit.Refusal>
    ) {
        guard let store, let actionsService = actionStore?.actionsService else { return }
        let segments = SegmentDeleter.segments(ids, documentId: documentId, store: store)
        let steps = windowSteps, documentId = documentId
        let note = onNote, windowState = windowState
        // After each re-read (the join, its undo, its redo): the kept line, or the joined lines once undone.
        let joined = segments.map(\.id)
        let reselect: @MainActor () async -> Void = {
            guard selectingJoined, let windowState else { return }
            let live = Set(store.segments(documentId: documentId).map(\.id))
            windowState.pickInReader(
                SegmentEdit.selectionAfterJoin(joined: joined, live: live), documentId: documentId, store: store
            )
        }
        Task {
            switch plan(segments) {
            case .failure(let refusal): note(SegmentMover.problem(refusal))
            case .success(let call):
                do {
                    try await SegmentEditRunner(actionsService: actionsService, store: store).run(
                        call, documentId: documentId, actionName: actionName, steps: steps, afterChange: reselect
                    )
                    note(nil)
                } catch { note("That did not happen: \(error.localizedDescription)") }
            }
        }
    }
}

#if DEBUG
#Preview("Two lines picked: Join and the attributes (Move Into / Lift Out need a page's segments)") {
    Menu("Line 2") {
        SegmentVerbMenu(ids: ["line-1", "line-2"], documentId: "page-1")
    }
    .padding()
    .frame(width: 240)
}
#endif
