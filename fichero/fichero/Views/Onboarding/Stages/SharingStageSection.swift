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
    /// Whether the person answered Yes to "Let other people or your other Macs open this library?" (default No).
    static func wantsSharing(_ stage: Components.Schemas.SetupStage, answers: RecipeSetupAnswers.JobAnswers) -> Bool {
        guard let question = stage.questions.first(where: { $0.key == SharingStageModel.sharingKey }),
              case .yesNo(true)? = answer(to: question, in: answers) else { return false }
        return true
    }
}

#if os(macOS)
/// What follows the two questions: on Yes, the Settings pane's own controls in place (one switch, one address choice, one
/// link, so a change here or in Settings shows in both at once), a line when the Mac's sharing disagrees with the answer,
/// and where to change it later (`sharing.setup-answers-change-later`).
struct SharingStageControls: View {
    let wantsSharing: Bool
    @AppStorage(RemoteAccessConfig.hostingEnabledKey) private var hostingEnabled = false

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            if let said = SharingStageModel.mismatch(wantsSharing: wantsSharing, sharingIsOn: hostingEnabled) {
                Text(said).font(.callout).accessibilityIdentifier("setup.sharing.mismatch")
            }
            if SharingStageModel.showsSharingControls(wantsSharing: wantsSharing) {
                ShareSettingsView().frame(minHeight: 420)
            }
            Text(SharingStageModel.settingsFooter).font(.caption).foregroundStyle(.secondary)
        }
    }
}
#endif
