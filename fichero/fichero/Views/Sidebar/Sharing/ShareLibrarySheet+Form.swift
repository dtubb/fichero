import SwiftUI

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
                ForEach(Self.shareRoles, id: \.self) { roleName in
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
            Text("The person gets the chosen role for this library. Editors change content; "
                + "viewers are read-only. To make someone an Owner (full admin), use "
                + "Settings → People.")
                .foregroundStyle(.secondary)
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
}
