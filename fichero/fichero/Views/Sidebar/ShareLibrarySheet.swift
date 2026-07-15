import FicheroAPIClient
import SwiftUI

// swiftlint:disable file_length

/// "Share this library…" surface (#3149, plan §5 F1).
///
/// Pick an existing account — or create a new person inline — assign a role,
/// and share: the engine grants the per-library role through the audited
/// `acl.set` action and returns a `share_url`, shown here to copy / send. The
/// members list manages current roles (change / revoke) via the *same* audited
/// ACL methods the sidebar `LibrarySharingBadge` uses (`setLibraryRole` /
/// `revokeLibraryRole`) — this iterates on that #2869 surface, it does not
/// replace it.
///
/// Presented from the badge popover, so it only appears when multi-user mode is
/// on for this library.
struct ShareLibrarySheet: View {
    let library: LibraryManager.LibraryReference
    let usersStore: UsersStore

    @Environment(\.dismiss) private var dismiss

    // The reachable-host + pin state that turns a role grant into a link someone
    // can actually open. Same @AppStorage keys the one pairing surface owns
    // (ShareSettingsView), so this reflects whether sharing is on and where.
    @AppStorage(RemoteAccessConfig.publicBaseURLKey) private var publicBaseURL = ""
    @AppStorage(RemoteAccessConfig.hostingEnabledKey) private var hostingEnabled = false
    @AppStorage(RemoteAccessConfig.bonjourEnabledKey) private var bonjourEnabled = false

    // Optional so this cross-platform sheet never traps if presented outside the
    // main window's environment (e.g. iOS). When present (the macOS sidebar case),
    // "Share" can do its OWN host/cert setup instead of sending the user to Settings
    // — you share a thing by sharing it, not by first enabling a subsystem (#3776).
    @Environment(EmbeddedBackendService.self) private var backendService: EmbeddedBackendService?
    @Environment(AppState.self) private var appState: AppState?
    @Environment(LibraryManager.self) private var libraryManager: LibraryManager?

    // Share form
    @State var personChoice: String = ""
    @State var role = "viewer"
    @State var isSharing = false
    // Set once the role grant succeeds — the "Share Link" section appears then.
    @State var didShare = false
    // The short-lived, single-use pair code minted for the link — SAME code
    // semantics as the QR. nil until minted; the link cannot exist without it.
    @State var pairingCode: PairingCodeRecord?
    @State var spkiPin = ""
    @State var shareError: String?
    @State var copied = false

    // Inline "New person…" create
    @State var newDisplayName = ""
    @State var newUsername = ""
    @State var newPassword = ""
    @State var isCreating = false
    @State var createError: String?

    // Members
    @State var members: [Components.Schemas.LibraryMember] = []
    @State var isLoadingMembers = false
    @State var membersError: String?
    @State var isApplying = false
    @State var manageError: String?

    let shareRoles = ["owner", "editor", "viewer"]
    static let newPersonTag = "__new_person__"

    var body: some View {
        NavigationStack {
            Form {
                shareSection
                membersSection
            }
            .formStyle(.grouped)
            .navigationTitle("Share Library")
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { dismiss() }
                }
            }
        }
        .frame(minWidth: 420, minHeight: 480)
        .task { await loadEverything() }
    }
}

// MARK: - Sections

extension ShareLibrarySheet {
    @ViewBuilder
    var shareSection: some View {
        Section {
            Picker("Person", selection: $personChoice) {
                Text("Choose a person").tag("")
                ForEach(usersStore.users, id: \.id) { user in
                    Text(displayName(user)).tag(user.id)
                }
                Text("New person…").tag(Self.newPersonTag)
            }

            if personChoice == Self.newPersonTag {
                newPersonFields
            }

            Picker("Role", selection: $role) {
                ForEach(shareRoles, id: \.self) { roleName in
                    Text(roleName.capitalized).tag(roleName)
                }
            }

            Button {
                Task { await share() }
            } label: {
                if isSharing {
                    ProgressView().controlSize(.small)
                } else {
                    Text("Share")
                }
            }
            .disabled(isSharing || !canShare)

            if let shareError {
                Text(shareError)
                    .font(.caption)
                    .foregroundStyle(.red)
            }
        } header: {
            Text("Share With")
        } footer: {
            Text("The person gets the chosen role for this library. Owners manage members; "
                + "editors change content; viewers are read-only.")
                .foregroundStyle(.secondary)
        }

        if didShare {
            shareLinkSection
        }
    }

    /// The link the person you just shared with actually opens.
    ///
    /// It is the SAME `fichero://` payload as the pairing QR and the copyable
    /// pairing link (#3774/#3813): reachable host + SPKI pin + short-lived
    /// single-use pair code. It is NOT the engine's `share_url`, which is a
    /// loopback API URL that 401s and is dead to anyone but this Mac.
    ///
    /// When no reachable address exists (sharing off, loopback only), there is no
    /// working link to make — we say so honestly and point at the switch, rather
    /// than hand out a link that looks valid and isn't. Never a dead control.
    @ViewBuilder
    var shareLinkSection: some View {
        Section("Share Link") {
            if let pairingLink {
                LabeledContent("Link") {
                    Text(pairingLink)
                        .textSelection(.enabled)
                        .font(.caption.monospaced())
                        .lineLimit(1)
                        .truncationMode(.middle)
                }
                HStack {
                    Button(copied ? "Copied" : "Copy Link") { copyPairingLink() }
                    if let url = URL(string: pairingLink) {
                        ShareLink(item: url) {
                            Label("Send…", systemImage: "square.and.arrow.up")
                        }
                    }
                }
                Text("This link lets \(sharedPersonName) connect to your library — "
                    + "it carries a single-use code that expires. Share only with them.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else if let reason = shareLinkUnavailableReason {
                // Honest fallback only — the common "sharing is off" case is now
                // handled by Share itself (it turns hosting on), so this renders for
                // the genuine cannot-proceed cases (remote engine / iOS) or the brief
                // certificate-minting window. reason.detail explains each honestly; no
                // stale "go to Settings, then reopen" breadcrumb (#3811).
                VStack(alignment: .leading, spacing: 6) {
                    Text(reason.headline)
                        .font(.headline)
                    Text(reason.detail)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            } else {
                ProgressView("Preparing link…")
            }
        }
    }

    @ViewBuilder
    var newPersonFields: some View {
        TextField("Full name", text: $newDisplayName)
        TextField("Username", text: $newUsername)
            .textContentType(.username)
        SecureField("Password", text: $newPassword)
            .textContentType(.newPassword)
        Button {
            Task { await createNewPerson() }
        } label: {
            if isCreating {
                ProgressView().controlSize(.small)
            } else {
                Text("Create Person")
            }
        }
        .disabled(isCreating || !canCreatePerson)
        if let createError {
            Text(createError)
                .font(.caption)
                .foregroundStyle(.red)
        }
    }

    @ViewBuilder
    var membersSection: some View {
        Section("Current Members") {
            if isLoadingMembers {
                ProgressView().controlSize(.small)
            } else if let membersError {
                Text(membersError)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else if members.isEmpty {
                Text("No one else has access yet.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else {
                ForEach(members, id: \.userId) { member in
                    memberRow(member)
                }
            }
            if let manageError {
                Text(manageError)
                    .font(.caption)
                    .foregroundStyle(.red)
            }
        }
    }

    @ViewBuilder
    func memberRow(_ member: Components.Schemas.LibraryMember) -> some View {
        HStack(spacing: 8) {
            Image(systemName: member.isOwnerAccount ? "crown" : "person")
                .font(.caption)
                .foregroundStyle(.secondary)
            VStack(alignment: .leading, spacing: 1) {
                Text(member.displayName)
                Text("@\(member.username)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer(minLength: 12)
            Menu(member.role.capitalized) {
                ForEach(shareRoles, id: \.self) { roleName in
                    Button(roleName.capitalized) {
                        Task { await changeRole(userId: member.userId, role: roleName) }
                    }
                }
                Divider()
                Button("Remove", role: .destructive) {
                    Task { await revoke(userId: member.userId) }
                }
            }
            .menuStyle(.borderlessButton)
            .fixedSize()
            .disabled(isApplying)
        }
    }
}

// MARK: - Actions

extension ShareLibrarySheet {
    var canShare: Bool {
        !personChoice.isEmpty && personChoice != Self.newPersonTag
    }

    var canCreatePerson: Bool {
        !newDisplayName.trimmingCharacters(in: .whitespaces).isEmpty
            && !newUsername.trimmingCharacters(in: .whitespaces).isEmpty
            && !newPassword.isEmpty
    }

    func displayName(_ user: Components.Schemas.UserResponse) -> String {
        user.displayName.isEmpty ? user.username : user.displayName
    }

    @MainActor
    func loadEverything() async {
        await usersStore.load()
        await loadMembers()
    }

    @MainActor
    func loadMembers() async {
        isLoadingMembers = true
        membersError = nil
        defer { isLoadingMembers = false }
        do {
            members = try await library.actionsService.listLibraryMembers().members ?? []
        } catch {
            members = []
            membersError = error.localizedDescription
        }
    }

    /// Create the inline "New person…" account, then select it so the next
    /// Share targets the freshly-created user. The username is matched back to
    /// the reloaded account list to resolve its id.
    @MainActor
    func createNewPerson() async {
        isCreating = true
        createError = nil
        defer { isCreating = false }
        let username = newUsername.trimmingCharacters(in: .whitespaces)
        do {
            try await usersStore.createUser(
                username: username,
                displayName: newDisplayName.trimmingCharacters(in: .whitespaces),
                password: newPassword,
                isOwner: false
            )
            if let created = usersStore.users.first(where: { $0.username == username }) {
                personChoice = created.id
                newDisplayName = ""
                newUsername = ""
                newPassword = ""
            }
        } catch {
            createError = error.localizedDescription
        }
    }

    @MainActor
    func share() async {
        guard canShare else { return }
        isSharing = true
        shareError = nil
        didShare = false
        pairingCode = nil
        defer { isSharing = false }
        do {
            // Grant the role — the sheet's actual purpose. We deliberately IGNORE
            // the returned share_url: it is a loopback API URL that 401s and is
            // dead to anyone but this Mac (#3813). The link the recipient opens is
            // the pairing payload built in `pairingLink`.
            _ = try await library.actionsService.shareLibrary(user: personChoice, role: role)
            didShare = true
            // Share by sharing it: if this Mac can host but sharing isn't on yet,
            // turn it on as PART of this one action — mint the cert, start hosting —
            // so the recipient gets a working link without a separate trip to Settings
            // (#3811/#3776). No-op when hosting is already on or this Mac can't host
            // (remote engine / iOS), where the honest fallback card renders instead.
            if !hostingEnabled && canHostFromHere {
                await enableHostingForShare()
            }
            loadSPKIPin()
            await mintPairingCodeIfPossible()
            await loadMembers()
        } catch {
            shareError = error.localizedDescription
        }
    }

    /// Whether this Mac can prepare its own hosting for the share link: the host
    /// services are in scope AND this is the machine that runs the library's engine.
    var canHostFromHere: Bool {
        backendService != nil && appState != nil && libraryManager != nil && EngineConfig.engineIsLocal
    }

    /// Turn on hosting as part of "Share", mirroring `ShareSettingsView.applySharing`
    /// (the ONE pairing surface) so there is a single behaviour, not a divergent one:
    /// derive the address, restart the engine with TLS to mint the certificate, then
    /// load the pin AFTER the health handshake (the #3811 ordering fix).
    /// ponytail: this mirrors applySharing; the durable home is a shared
    /// enable-hosting primitive both call — extract when the engine lane exposes one.
    @MainActor
    func enableHostingForShare() async {
        guard let backendService, let appState, let libraryManager else { return }
        hostingEnabled = true
        bonjourEnabled = true
        if publicBaseURL.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            publicBaseURL = Self.autoLocalBaseURL
        }

        if backendService.isUsingExternalBackend {
            await appState.checkBackendHealth()
            appState.reconfigureGeneratedClientsForCurrentHost()
            libraryManager.reconfigureGeneratedClientsForCurrentHost()
            return
        }

        backendService.stop()
        do {
            try await backendService.start()
            await appState.checkBackendHealth()
            appState.reconfigureGeneratedClientsForCurrentHost()
            libraryManager.reconfigureGeneratedClientsForCurrentHost()
        } catch {
            shareError = error.localizedDescription
        }
    }

    /// Derives https://<hostname>.local:<port> from the system Bonjour name — the
    /// same automatic address `ShareSettingsView` derives, so both agree.
    static var autoLocalBaseURL: String {
        var host = ProcessInfo.processInfo.hostName.lowercased()
        if !host.hasSuffix(".local") {
            host = (host.components(separatedBy: ".").first ?? host) + ".local"
        }
        let port = URL(string: EngineConfig.defaultHostString)?.port ?? 8765
        return "https://\(host):\(port)"
    }

    func loadSPKIPin() {
        spkiPin = RemoteAccessConfig.hostedBackendSPKIPin(hostString: publicBaseURL) ?? ""
    }

    /// Mint the short-lived, single-use pair code — same code semantics as the QR.
    /// Skipped when there is no reachable address to bind it to; the honest
    /// unavailable state renders instead of a dead link.
    @MainActor
    func mintPairingCodeIfPossible() async {
        guard shareLinkUnavailableReason == nil else { return }
        do {
            pairingCode = try await PairingService(apiRoot: EngineConfig.host).createPairingCode()
        } catch {
            shareError = error.localizedDescription
        }
    }

    /// The one link format (#3774/#3813): reachable host + SPKI pin + pair code,
    /// as the `fichero://` payload iOS's `PairingQRCodePayloadDecoder` already
    /// parses. Identical to the QR and the copyable pairing link — not a second
    /// format, and never the loopback share_url.
    var pairingLink: String? {
        guard let pairingCode,
              let reachableURL = try? validatedHostedRemoteURL(from: publicBaseURL),
              let normalizedPin = try? RemoteCertificatePinning.validatedSPKIPin(spkiPin) else { return nil }
        let payload = PairingService(apiRoot: reachableURL).buildQRCodePayload(
            from: pairingCode,
            spki: normalizedPin,
            libraryPath: library.url.path
        )
        return try? RemoteClientPairing.inviteLinkString(from: payload)
    }

    /// Why there is no working share link yet — honest, named, and pointing at the
    /// fix. Mirrors the pairing surface's `PairingBlocker` vocabulary without
    /// coupling this cross-platform sheet to that AppKit-only type.
    var shareLinkUnavailableReason: (headline: String, detail: String)? {
        guard EngineConfig.engineIsLocal else {
            return ("This library is hosted on another machine",
                    "Sharing happens on the Mac that hosts the library, not on this one.")
        }
        guard hostingEnabled else {
            return ("Sharing is off",
                    "Turn sharing on so Fichero can prepare a reachable address and a security code for the link.")
        }
        do {
            _ = try validatedHostedRemoteURL(from: publicBaseURL)
        } catch {
            return ("No reachable address yet",
                    "This Mac only has a loopback address that other devices can't open. "
                    + "Turning sharing on derives a shareable address.")
        }
        guard (try? RemoteCertificatePinning.validatedSPKIPin(spkiPin)) != nil else {
            return ("Preparing the security certificate",
                    "Fichero is still minting the certificate for this address — try again in a moment.")
        }
        return nil
    }

    var sharedPersonName: String {
        usersStore.users.first(where: { $0.id == personChoice }).map { displayName($0) } ?? "this person"
    }

    func copyPairingLink() {
        guard let pairingLink else { return }
        PlatformPasteboard.writeString(pairingLink)
        copied = true
        Task {
            try? await Task.sleep(for: .seconds(2))
            copied = false
        }
    }

    /// Change one member's role in place — update just that row on success so the
    /// list never wholesale re-renders (stable `id: \.userId`).
    @MainActor
    func changeRole(userId: String, role newRole: String) async {
        isApplying = true
        manageError = nil
        defer { isApplying = false }
        do {
            _ = try await library.actionsService.setLibraryRole(userId: userId, role: newRole)
            if let idx = members.firstIndex(where: { $0.userId == userId }) {
                let old = members[idx]
                members[idx] = .init(
                    userId: old.userId,
                    username: old.username,
                    displayName: old.displayName,
                    isOwnerAccount: old.isOwnerAccount,
                    role: newRole
                )
            }
        } catch {
            manageError = error.localizedDescription
        }
    }

    /// Revoke one member — drop just that row on success, no full reload.
    @MainActor
    func revoke(userId: String) async {
        isApplying = true
        manageError = nil
        defer { isApplying = false }
        do {
            _ = try await library.actionsService.revokeLibraryRole(userId: userId)
            members.removeAll { $0.userId == userId }
        } catch {
            manageError = error.localizedDescription
        }
    }
}

// swiftlint:enable file_length
