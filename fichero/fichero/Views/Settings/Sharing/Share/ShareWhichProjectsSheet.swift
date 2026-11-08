import SwiftUI

/// What the "Which projects do you want to share?" dialog holds and sends
/// (`sharing.host.which-projects-dialog`, #6366). Pure, so the rules are tested without a window.
struct ShareWhichProjectsModel: Equatable {
    struct Grant: Equatable {
        let libraryId: String
        let personId: String
        let role: String
    }

    /// Checked project ids, and for each the chosen people with their role (Editor or Viewer; never Owner).
    var checked: Set<String> = []
    var people: [String: [String: String]] = [:]

    /// The dialog opens only when the engine says no project is shared (`shared_library_count` 0).
    static func opens(sharedCount: Int?) -> Bool { sharedCount == 0 }

    var canShare: Bool { !checked.isEmpty }

    /// With Multi-user off, the projects the ONE link gives, in the sidebar's order: the first one's Share sheet makes it.
    func linkSet(order: [String]) -> [String] { order.filter(checked.contains) }

    /// One share call per checked project and chosen person, in a stable order; nothing for a project with no one.
    func grants(order: [String]) -> [Grant] {
        order.filter(checked.contains).flatMap { libraryId in
            (people[libraryId] ?? [:]).sorted { $0.key < $1.key }
                .map { Grant(libraryId: libraryId, personId: $0.key, role: $0.value) }
        }
    }
}

/// The dialog itself: one row per project this Mac has, a check box each; with accounts, who can open it;
/// Share / Not Now.
/// With Multi-user off the checked projects are shared by ONE link: Share opens the first one's Share sheet, whose link gives
/// the rest too (`onLink`: the first and the others).
struct ShareWhichProjectsSheet: View {
    let libraries: [LibraryManager.LibraryReference]
    let multiuser: Bool
    let usersStore: UsersStore
    let onLink: (LibraryManager.LibraryReference, [LibraryManager.LibraryReference]) -> Void
    @Environment(\.dismiss) private var dismiss
    @State private var model = ShareWhichProjectsModel()
    @State private var isSharing = false
    @Environment(AppState.self) private var appState: AppState?
    /// A failed share, as the one alert (`sharing.host.dialog-errors-are-alerts`); the checks stay for the second try.
    @State private var failurePrompt: FailureAlertPrompt?

    var body: some View {
        NavigationStack {
            Form {
                ForEach(libraries) { library in
                    let id = library.id.uuidString
                    Section {
                        Toggle(library.displayName, isOn: checkedBinding(id))
                            .accessibilityIdentifier("sharing.whichProjects.row.\(id)")
                        if model.checked.contains(id) { whoCanOpen(id) }
                    }
                }
            }
            .formStyle(.grouped)
            .navigationTitle("Which projects do you want to share?")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Not Now") { dismiss() }.accessibilityIdentifier("sharing.whichProjects.notNow")
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Share") { Task { await share() } }
                        .disabled(!model.canShare || isSharing)
                        .accessibilityIdentifier("sharing.whichProjects.share")
                }
            }
            .failureAlert($failurePrompt)
        }
        .frame(minWidth: 420, minHeight: 360)
        .accessibilityIdentifier("sharing.whichProjects.sheet")
        .task { if multiuser { await usersStore.load() } }
    }

    @ViewBuilder
    private func whoCanOpen(_ libraryId: String) -> some View {
        if multiuser {
            ForEach(usersStore.users.filter { !$0.isOwner && $0.active }, id: \.id) { user in
                Picker(user.displayName.isEmpty ? user.username : user.displayName,
                       selection: roleBinding(libraryId, user.id)) {
                    Text("No access").tag("")
                    Text("Editor").tag("editor")
                    Text("Viewer").tag("viewer")
                }
            }
            .accessibilityIdentifier("sharing.whichProjects.people.\(libraryId)")
        } else {
            Text("Any device you pair with this Mac").font(.caption).foregroundStyle(.secondary)
        }
    }

    private func checkedBinding(_ libraryId: String) -> Binding<Bool> {
        Binding(get: { model.checked.contains(libraryId) },
                set: { if $0 { model.checked.insert(libraryId) } else { model.checked.remove(libraryId) } })
    }

    private func roleBinding(_ libraryId: String, _ personId: String) -> Binding<String> {
        Binding(get: { model.people[libraryId]?[personId] ?? "" },
                set: { model.people[libraryId, default: [:]][personId] = $0.isEmpty ? nil : $0 })
    }

    /// The Share sheet's own action for each grant (`POST /api/authz/share`); a failure keeps the checks (an alert).
    private func share() async {
        isSharing = true
        defer { isSharing = false }
        guard multiuser else {
            let ids = model.linkSet(order: libraries.map(\.id.uuidString))
            let picked = ids.compactMap { id in libraries.first { $0.id.uuidString == id } }
            if let first = picked.first {
                dismiss()
                onLink(first, Array(picked.dropFirst()))
            }
            return
        }
        for grant in model.grants(order: libraries.map(\.id.uuidString)) {
            guard let library = libraries.first(where: { $0.id.uuidString == grant.libraryId }) else { continue }
            do {
                _ = try await library.actionsService.shareLibrary(user: grant.personId, role: grant.role)
            } catch {
                let ownerSignIn = appState?.ownerSignIn
                failurePrompt = SharingFailurePrompt.make(
                    sharing: error, title: "Couldn't share \(library.displayName)", offers: ownerSignIn == nil ? [] : [.signInAsOwner],
                    perform: { _ in Task { await ownerSignIn?.run() } }, copy: { PlatformPasteboard.writeString($0) })
                return
            }
        }
        dismiss()
    }
}

#if DEBUG
#Preview("Which projects, no accounts") {
    let marshall = LibraryManager.LibraryReference(
        url: URL(fileURLWithPath: "/tmp/Marshall Diaries.fichero"), document: FicheroDocument(),
        displayName: "Marshall Diaries")
    let istmina = LibraryManager.LibraryReference(
        url: URL(fileURLWithPath: "/tmp/Istmina.fichero"), document: FicheroDocument(), displayName: "Istmina")
    return ShareWhichProjectsSheet(libraries: [marshall, istmina], multiuser: false,
                                   usersStore: AppState().usersStore, onLink: { _, _ in })
}
#endif
