import SwiftUI

/// Each step's model menu under the plan: Set Up's pick first and marked, "Use" on any other, the need said in place
/// and the row kept, "Use Set Up's pick" only while a person's choice overrides (`source.onboard.step-choice-overrides-the-pick`).
struct StepChoiceMenusView: View {
    let store: RecipeSetupStore

    var body: some View {
        let menus = store.stepMenus
        if !menus.isEmpty {
            VStack(alignment: .leading, spacing: 10) {
                ForEach(menus) { menu in
                    StepChoiceMenuSection(menu: menu, store: store)
                }
            }
            .accessibilityIdentifier("setup.ready.stepChoices")
        }
    }
}

private struct StepChoiceMenuSection: View {
    let menu: StepChoiceMenu
    let store: RecipeSetupStore

    var body: some View {
        DisclosureGroup(menu.name) {
            VStack(alignment: .leading, spacing: 6) {
                ForEach(menu.candidates) { candidate in
                    StepChoiceCandidateRow(menu: menu, candidate: candidate, store: store)
                }
                if menu.offersTakeBack {
                    Button("Use Set Up's pick") { Task { await store.useSetupPick(step: menu.step) } }
                        .controlSize(.small)
                        .accessibilityIdentifier("setup.ready.stepChoice.\(menu.step).useSetupPick")
                }
            }
            .padding(.top, 4)
        }
        .accessibilityIdentifier("setup.ready.stepChoice.\(menu.step)")
    }
}

private struct StepChoiceCandidateRow: View {
    let menu: StepChoiceMenu
    let candidate: StepChoiceMenu.Candidate
    let store: RecipeSetupStore

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 6) {
                    Text(candidate.name).font(.body.weight(candidate.isPicked ? .semibold : .regular))
                    ForEach(menu.marks(of: candidate), id: \.self) { mark in
                        Text(mark).font(.caption).foregroundStyle(.secondary)
                    }
                }
                Text(menu.costText(of: candidate)).font(.callout).foregroundStyle(.secondary)
                if let needs = menu.needsWords(of: candidate) {
                    Label(needs, systemImage: "info.circle").font(.callout).foregroundStyle(.secondary)
                }
            }
            Spacer()
            if menu.canUse(candidate) {
                Button("Use") { Task { await store.choose(candidate, forStep: menu.step) } }
                    .controlSize(.small)
                    .accessibilityIdentifier("setup.ready.stepChoice.\(menu.step).use.\(candidate.card)")
            }
        }
    }
}
