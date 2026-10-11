import FicheroAPIClient
import SwiftUI

/// The small sheet a drop onto another project opens (#2397, #4311, `transfer.app.result-sheet`): what goes, what
/// is cut and listed, the people and places proposed as merges, then Move or Copy; afterwards the result in words.
/// A refusal shows the engine's sentence; ⌘⌥ (an alias) is refused with Copy offered instead.
struct ProjectTransferSheet: View {
    let store: ProjectTransferStore
    let drop: ProjectTransferStore.Pending
    /// The window's step stack, read outside the sheet, where ⌘Z takes the transfer back.
    let steps: WindowSteps?

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(ProjectTransferStore.title(drop)).font(.headline)
            Text("From \(drop.source.displayName)").font(.callout).foregroundStyle(.secondary)
            content
            buttons
        }
        .padding(20)
        .frame(width: 440)
    }

    @ViewBuilder
    private var content: some View {
        if let result = drop.result {
            Text(ProjectTransferStore.resultWords(result, of: drop))
                .fixedSize(horizontal: false, vertical: true)
        } else if let refusal = drop.refusal {
            Label(refusal, systemImage: "exclamationmark.triangle")
                .foregroundStyle(.orange)
                .fixedSize(horizontal: false, vertical: true)
        } else if let plan = drop.plan {
            planSections(plan)
        } else {
            ProgressView("Checking what goes…").controlSize(.small)
        }
    }

    @ViewBuilder
    private func planSections(_ plan: Components.Schemas.TransferResult) -> some View {
        section("What goes", ProjectTransferStore.whatGoes(plan), empty: "Nothing but the items themselves.")
        let cuts = ProjectTransferStore.cuts(plan)
        if !cuts.isEmpty { section("Cut and listed", cuts) }
        let proposals = ProjectTransferStore.proposals(plan)
        if !proposals.isEmpty { section("Proposed as merges, for you to decide", proposals) }
        if drop.mode == .move {
            Text("The originals go to \(drop.source.displayName)'s Trash; ⌘Z puts them back.")
                .font(.callout).foregroundStyle(.secondary)
        }
    }

    private func section(_ title: String, _ lines: [String], empty: String? = nil) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(title).font(.subheadline.weight(.semibold))
            if lines.isEmpty, let empty {
                Text(empty).font(.callout).foregroundStyle(.secondary)
            }
            ForEach(Array(lines.prefix(8).enumerated()), id: \.offset) { _, line in
                Text(line).font(.callout).lineLimit(2)
            }
            if lines.count > 8 {
                Text("and \(lines.count - 8) more").font(.callout).foregroundStyle(.secondary)
            }
        }
    }

    private var buttons: some View {
        HStack {
            Spacer()
            if drop.result != nil {
                Button("Done") { store.cancel() }.keyboardShortcut(.defaultAction)
            } else {
                Button("Cancel", role: .cancel) { store.cancel() }.keyboardShortcut(.cancelAction)
                if drop.offersCopyInstead {
                    Button("Copy Instead") { Task { await store.copyInstead() } }.keyboardShortcut(.defaultAction)
                } else {
                    Button(drop.mode == .move ? "Move" : "Copy") { Task { await store.run(steps: steps) } }
                        .keyboardShortcut(.defaultAction)
                        .disabled(drop.plan == nil || drop.refusal != nil || drop.isWorking)
                }
            }
        }
    }
}

/// The window's one host for the transfer sheet: the sidebar and Items both start a drop on the window's
/// `ProjectTransferStore`, and it shows here. The window's steps are read here, outside the sheet, so ⌘Z after a
/// transfer lands on the window's own step stack.
struct ProjectTransferSheetHost: ViewModifier {
    let store: ProjectTransferStore
    @Environment(WindowSteps.self) private var windowSteps: WindowSteps?

    func body(content: Content) -> some View {
        content.sheet(item: Binding(get: { store.pending }, set: { if $0 == nil { store.cancel() } })) { drop in
            ProjectTransferSheet(store: store, drop: drop, steps: windowSteps)
        }
    }
}

#Preview("Move between projects") {
    let source = LibraryManager.LibraryReference(
        url: URL(fileURLWithPath: "/tmp/Marshall Diaries.fichero"), document: FicheroDocument(),
        displayName: "Marshall Diaries")
    let target = LibraryManager.LibraryReference(
        url: URL(fileURLWithPath: "/tmp/Istmina.fichero"), document: FicheroDocument(), displayName: "Istmina")
    let store = ProjectTransferStore()
    var drop = ProjectTransferStore.Pending(source: source, target: target, items: ["a", "b"], targetParentId: nil,
                                            mode: .move)
    drop.refusal = ProjectTransferStore.aliasRefusal
    drop.offersCopyInstead = true
    return ProjectTransferSheet(store: store, drop: drop, steps: nil)
}
