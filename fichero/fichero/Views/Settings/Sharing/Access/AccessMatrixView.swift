import FicheroAPIClient
import SwiftUI

/// What a person's role on a library reads as in the access view (#2083): owner, editor, viewer, or no access.
enum AccessWords {
    static func role(_ raw: String?) -> String {
        switch raw {
        case "owner": "Owner"
        case "editor": "Editor"
        case "viewer": "Viewer"
        default: "No access"
        }
    }
}

/// Settings › Sharing › Accounts: each person's access across every library, in a grid (`sharing.people.settings-screen`).
/// Read-only here; a person's role on one library is still set from that project's Share sheet.
struct AccessMatrixView: View {
    let matrix: Components.Schemas.AccessMatrixResponse

    var body: some View {
        if matrix.libraries.isEmpty || matrix.people.isEmpty {
            Text("No libraries to show access for yet.")
                .font(.caption)
                .foregroundStyle(.secondary)
        } else {
            Grid(alignment: .leading, horizontalSpacing: 16, verticalSpacing: 6) {
                GridRow {
                    Text("Person").font(.caption).foregroundStyle(.secondary)
                    ForEach(matrix.libraries, id: \.libraryPath) { library in
                        Text(library.libraryName).font(.caption).foregroundStyle(.secondary)
                    }
                }
                ForEach(matrix.people, id: \.userId) { person in
                    GridRow {
                        Text(person.displayName)
                        ForEach(matrix.libraries, id: \.libraryPath) { library in
                            let role = person.access.first { $0.libraryPath == library.libraryPath }?.role
                            Text(AccessWords.role(role))
                                .foregroundStyle(role == nil ? .secondary : .primary)
                        }
                    }
                }
            }
            .accessibilityIdentifier("accounts.accessMatrix")
        }
    }
}

#Preview("Access across libraries") {
    AccessMatrixView(matrix: .init(
        libraries: [.init(libraryPath: "/l1", libraryName: "Marshall"), .init(libraryPath: "/l2", libraryName: "Diaries")],
        people: [.init(
            userId: "u1", username: "maya", displayName: "Maya", isOwnerAccount: false, active: true,
            access: [.init(libraryPath: "/l1", role: "editor"), .init(libraryPath: "/l2", role: nil)])]
    ))
    .padding()
}
