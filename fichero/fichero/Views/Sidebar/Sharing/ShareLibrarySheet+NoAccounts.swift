import SwiftUI

extension ShareLibrarySheet {
    /// With Multi-user off a project is shared by a link, not to a person (#6373): the sheet is the link, and Turn
    /// Sharing On when Sharing is off. A folder is shared to a person, so it keeps the person form.
    static func sharesWithPeople(multiuser: Bool, folder: Bool) -> Bool { multiuser || folder }

    static let noAccountsNote = "Whoever opens this link on their Mac or iPhone connects to this project. "
        + "To share with named people, turn on accounts in Settings › Sharing."

    @ViewBuilder
    var noAccountsSection: some View {
        Section {
            Text(Self.noAccountsNote)
                .font(.caption)
                .foregroundStyle(.secondary)
            if !hostingEnabled, canHostFromHere {
                Button("Turn Sharing On") {
                    Task {
                        await enableHostingForShare()
                        await readSharingState()
                        await mintPairingCodeIfPossible()
                    }
                }
                .accessibilityIdentifier("share.turn-sharing-on")
            }
        }
    }
}
