import FicheroAPIClient
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
        // No disclosure in setup (#5481): each step's menu is on the screen, its name over what it says.
        VStack(alignment: .leading, spacing: 6) {
            Text(menu.name).font(.headline)
            VStack(alignment: .leading, spacing: 6) {
                if let wording = menu.wording { Text(wording).font(.callout) }
                if menu.needsCloudPermission {
                    Button("Allow Cloud for This Project") { Task { await store.allowCloud() } }
                        .controlSize(.small)
                        .accessibilityIdentifier("setup.ready.stepChoice.\(menu.step).allowCloud")
                }
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

/// The preview's fixture, in named, typed pieces: a nested literal of `.init`s is more than the type checker will take.
private enum StepChoiceMenuFixture {
    static let local = StepChoiceMenu.Candidate(
        card: "kraken:catmus", name: "Kraken · CATMuS", runsOn: "this-mac", isLocal: true, isPicked: false,
        isRecommended: true, isAvailable: true, needs: [], costUsd: nil, costWords: nil)
    static let permission = StepChoiceMenu.Need(kind: .permission, words: "Pages may not leave this Mac yet.")
    static let cloud = StepChoiceMenu.Candidate(
        card: "cloud:claude", name: "Claude", runsOn: "cloud:anthropic", isLocal: false, isPicked: true,
        isRecommended: false, isAvailable: false, needs: [permission], costUsd: 4.2, costWords: "Estimate")
    static let candidates: [StepChoiceMenu.Candidate] = [local, cloud]
    static let menu = StepChoiceMenu(step: "read", name: "Read", chosenBy: .person, job: "transcribe", candidates: candidates)
}

#Preview("A step with a pick and a person's choice") {
    let client: FicheroClient = FicheroClient(libraryPath: nil)
    let store: RecipeSetupStore = RecipeSetupStore(client: client)
    StepChoiceMenuSection(menu: StepChoiceMenuFixture.menu, store: store)
        .padding()
        .frame(width: 460)
}
