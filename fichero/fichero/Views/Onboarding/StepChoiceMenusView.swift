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
                if let wording = menu.wording { Text(wording).font(.callout) }
                if let bar = menu.certaintyBarText { Text(bar).font(.callout).foregroundStyle(.secondary) }
                if let title = menu.turnOnTitle {
                    Button(title) { Task { await store.turnOn(menu) } }
                        .controlSize(.small)
                        .accessibilityIdentifier("setup.ready.stepChoice.\(menu.step).turnOn")
                }
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

#Preview("A step with a pick and a person's choice") {
    // Typed in small pieces: one big literal of `.init`s is more than the type checker will take.
    let local = StepChoiceMenu.Candidate(
        card: "kraken:catmus", name: "Kraken · CATMuS", runsOn: "this-mac", isLocal: true, isPicked: false,
        isRecommended: true, isAvailable: true, needs: [], costUsd: nil, costWords: nil)
    let permission = StepChoiceMenu.Need(kind: .permission, words: "Pages may not leave this Mac yet.")
    let cloud = StepChoiceMenu.Candidate(
        card: "cloud:claude", name: "Claude", runsOn: "cloud:anthropic", isLocal: false, isPicked: true,
        isRecommended: false, isAvailable: false, needs: [permission], costUsd: 4.2, costWords: "Estimate")
    let menu = StepChoiceMenu(step: "read", name: "Read", chosenBy: .person, job: "transcribe", candidates: [local, cloud])
    let store = RecipeSetupStore(client: FicheroClient(libraryPath: nil))
    return StepChoiceMenuSection(menu: menu, store: store)
        .padding()
        .frame(width: 460)
}
