import FicheroAPIClient
import SwiftUI

// MARK: - Document prototype / class picker (#1377)

struct DocumentPrototypePicker: View {
    let documentId: String
    let initialKey: String?
    /// The entity service of the library that OWNS `documentId`, handed down by
    /// the inspector rather than looked up here (#4461).
    ///
    /// This reached for `LibraryManager.shared.globalLibrary?.entityService`,
    /// which is the #4306 shape: it listed the global library's prototypes and
    /// assigned against the global database, where a non-global document does
    /// not exist. Nil when no library resolves — the picker then shows its
    /// empty state instead of quietly editing another library.
    let entityService: EntityService?

    @State private var selectedKey: String?
    @State private var prototypes: [Components.Schemas.ClassificationValue] = []
    @State private var isAssigning = false
    @State private var showTypeEditor = false

    var body: some View {
        LabeledContent("Prototype") {
            if prototypes.isEmpty && !isAssigning {
                // The old empty state pointed at "Settings → Classification",
                // which never existed — the editor opens right here instead.
                Button("Define Types…") {
                    showTypeEditor = true
                }
                .buttonStyle(.plain)
                .foregroundStyle(.tint)
                .font(.caption)
                .help("Create document types (prototypes) with typed attributes")
            } else {
                Menu {
                    Button("None") {
                        Task { await assign(nil) }
                    }
                    Divider()
                    ForEach(prototypes, id: \.key) { proto in
                        Button {
                            Task { await assign(proto.key) }
                        } label: {
                            Label {
                                Text(proto.label)
                            } icon: {
                                if selectedKey == proto.key {
                                    Image(systemName: "checkmark")
                                }
                            }
                        }
                    }
                    Divider()
                    Button("Edit Types…") {
                        showTypeEditor = true
                    }
                } label: {
                    HStack(spacing: 4) {
                        if isAssigning {
                            ProgressView().controlSize(.mini)
                        }
                        if let key = selectedKey,
                           let proto = prototypes.first(where: { $0.key == key }) {
                            PrototypeBadge(proto: proto)
                        } else {
                            Text("None")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        Image(systemName: "chevron.up.chevron.down")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                }
                .buttonStyle(.plain)
                .help("Assign a document prototype (class) to this file")
            }
        }
        .task {
            selectedKey = initialKey
            await reloadPrototypes()
        }
        .sheet(isPresented: $showTypeEditor) {
            PrototypeEditorSheet(entityService: entityService) {
                Task { await reloadPrototypes() }
            }
        }
    }

    private func reloadPrototypes() async {
        if let svc = entityService {
            prototypes = (try? await svc.listDocumentPrototypes()) ?? []
        }
    }

    private func assign(_ key: String?) async {
        guard let svc = entityService else { return }
        isAssigning = true
        defer { isAssigning = false }
        if let key {
            _ = try? await svc.assignDocumentPrototype(documentId: documentId, prototypeKey: key)
        }
        selectedKey = key
    }
}

// Promoted from `private` so the workspace NodeClassPicker (#1570) can reuse
// the SAME hex parser — no second copy.
extension Color {
    init?(hex: String) {
        let stripped = hex.trimmingCharacters(in: .whitespaces).replacingOccurrences(of: "#", with: "")
        guard stripped.count == 6, let value = UInt64(stripped, radix: 16) else { return nil }
        let red = Double((value >> 16) & 0xFF) / 255
        let green = Double((value >> 8) & 0xFF) / 255
        let blue = Double(value & 0xFF) / 255
        self.init(red: red, green: green, blue: blue)
    }
}

// Promoted from `private` so the workspace NodeClassPicker (#1570) reuses the
// SAME coloured-capsule chip — no parallel badge view.
struct PrototypeBadge: View {
    let proto: Components.Schemas.ClassificationValue

    var body: some View {
        Text(proto.label)
            .font(.caption)
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(badgeColor.opacity(0.18))
            .foregroundStyle(badgeColor)
            .clipShape(Capsule())
    }

    private var badgeColor: Color {
        guard let hex = proto.color, !hex.isEmpty else { return .accentColor }
        return Color(hex: hex) ?? .accentColor
    }
}
