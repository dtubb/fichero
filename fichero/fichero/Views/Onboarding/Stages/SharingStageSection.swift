import FicheroAPIClient
import SwiftUI

/// The grey line under a Sharing and accounts question (`SharingStageModel.note`); nothing for any other question.
struct SharingStageNote: View {
    let questionKey: String

    var body: some View {
        if let text = SharingStageModel.note(forQuestion: questionKey) {
            Text(text).font(.caption).foregroundStyle(.secondary)
                .accessibilityIdentifier("setup.sharing.note")
        }
    }
}

extension SetupStagePage {
    /// Whether the person answered Yes to one of the page's two yes/no questions (default No).
    static func answeredYes(_ key: String, _ stage: Components.Schemas.SetupStage, _ answers: RecipeSetupAnswers.JobAnswers) -> Bool {
        guard let question = stage.questions.first(where: { $0.key == key }),
              case .yesNo(true)? = answer(to: question, in: answers) else { return false }
        return true
    }
}

#if os(macOS)
/// What follows the two questions: the lines each answer earns, on Yes the Settings pane's own controls in place (one switch,
/// one address choice, one link, so a change here or in Settings shows in both at once), the accounts action, and where to
/// change it later (`sharing.setup-answers-change-later`, `sharing.setup-asks-accounts`).
struct SharingStageControls: View {
    @Environment(AppState.self) private var appState
    let wantsSharing: Bool
    let wantsAccounts: Bool
    @AppStorage(RemoteAccessConfig.hostingEnabledKey) private var hostingEnabled = false
    @State private var showTurnOn = false
    @State private var askTurnOff = false
    @State private var showAddPerson = false
    @State private var failure: String?

    private var accountsOn: Bool { appState.identityStore.multiuserEnabled }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            if let line = SharingStageModel.alreadySharesLine(sharingIsOn: hostingEnabled, wantsSharing: wantsSharing) {
                Text(line).font(.callout).accessibilityIdentifier("setup.sharing.alreadyShares")
            }
            if let said = SharingStageModel.mismatch(wantsSharing: wantsSharing, sharingIsOn: hostingEnabled) {
                Text(said).font(.callout).accessibilityIdentifier("setup.sharing.mismatch")
            }
            if SharingStageModel.showsSharingControls(wantsSharing: wantsSharing) {
                ShareSettingsView().frame(minHeight: 420)
            }
            ForEach(SharingStageModel.accountLines(wantsSharing: wantsSharing, wantsAccounts: wantsAccounts, accountsOn: accountsOn),
                    id: \.self) { Text($0).font(.callout) }
            accountsAction
            if wantsAccounts, accountsOn {
                Button(SharingStageModel.addPersonTitle) { showAddPerson = true }.accessibilityIdentifier("setup.accounts.addPerson")
            }
            if let failure { Text(failure).font(.caption).foregroundStyle(.red) }
            Text(SharingStageModel.settingsFooter).font(.caption).foregroundStyle(.secondary)
        }
        .sheet(isPresented: $showTurnOn) {
            TurnOnAccountsSheet(store: appState.usersStore, identityStore: appState.identityStore) { showTurnOn = false }
        }
        .sheet(isPresented: $showAddPerson) {
            AccountsAddSheet(store: appState.usersStore, multiUserOn: true) { showAddPerson = false }
        }
        .confirmationDialog(SharingStageModel.turnOffAsk, isPresented: $askTurnOff, titleVisibility: .visible) {
            Button("Turn Off Accounts", role: .destructive) { Task { await turnOff() } }
        }
    }

    @ViewBuilder
    private var accountsAction: some View {
        switch SharingStageModel.accountsAction(wantsAccounts: wantsAccounts, accountsOn: accountsOn) {
        case .turnOn: Button(AccountsOnSequence.buttonTitle) { showTurnOn = true }.accessibilityIdentifier("setup.accounts.turnOn")
        case .turnOff: Button("Turn off accounts…") { askTurnOff = true }.accessibilityIdentifier("setup.accounts.turnOff")
        case nil: EmptyView()
        }
    }

    private func turnOff() async {
        failure = nil
        do {
            try await MultiuserSwitch.set(false, pairing: PairingService(apiRoot: EngineConfig.host), service: nil, steps: nil)
        } catch {
            failure = error.localizedDescription
        }
        await appState.checkBackendHealth()
        await appState.identityStore.load()
    }
}
#endif
