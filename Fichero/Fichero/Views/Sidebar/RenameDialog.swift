import SwiftUI

/// Reusable dialog for renaming items in the sidebar
struct RenameDialog: View {
    @Binding var isPresented: Bool
    let title: String
    let currentName: String
    let placeholder: String
    let onRename: (String) async throws -> Void
    let onCancel: (() -> Void)?

    @State private var newName: String = ""
    @State private var isRenaming = false
    @State private var errorMessage: String?

    init(
        isPresented: Binding<Bool>,
        title: String,
        currentName: String,
        placeholder: String = "Enter new name",
        onRename: @escaping (String) async throws -> Void,
        onCancel: (() -> Void)? = nil
    ) {
        self._isPresented = isPresented
        self.title = title
        self.currentName = currentName
        self.placeholder = placeholder
        self.onRename = onRename
        self.onCancel = onCancel
        self._newName = State(initialValue: currentName)
    }

    var body: some View {
        VStack(spacing: 16) {
            // Title
            Text(title)
                .font(.headline)

            // Current name display
            HStack {
                Text("Current name:")
                    .font(.subheadline)
                    .foregroundColor(.secondary)
                Spacer()
                Text(currentName)
                    .font(.subheadline)
                    .fontWeight(.medium)
            }

            // Text field
            TextField(placeholder, text: $newName)
                .textFieldStyle(.roundedBorder)
                .disableAutocorrection(true)
                .onSubmit {
                    renameItem()
                }

            // Error message
            if let errorMessage = errorMessage {
                Text(errorMessage)
                    .font(.caption)
                    .foregroundColor(.red)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }

            // Buttons
            HStack {
                Button("Cancel") {
                    isPresented = false
                    onCancel?()
                }
                .keyboardShortcut(.cancelAction)

                Spacer()

                Button("Rename") {
                    renameItem()
                }
                .keyboardShortcut(.defaultAction)
                .disabled(isRenaming || newName.isEmpty || newName == currentName)
                .overlay {
                    if isRenaming {
                        ProgressView()
                            .scaleEffect(0.7)
                    }
                }
            }
        }
        .padding()
        .frame(width: 300)
        .onAppear {
            // Focus the text field when dialog appears
            DispatchQueue.main.async {
                NSApp.keyWindow?.makeFirstResponder(nil)
            }
        }
    }

    private func renameItem() {
        guard !newName.isEmpty, newName != currentName else { return }

        isRenaming = true
        errorMessage = nil

        Task {
            do {
                try await onRename(newName)
                isPresented = false
            } catch {
                errorMessage = error.localizedDescription
                isRenaming = false
            }
        }
    }
}

// MARK: - Preview

#Preview {
    RenameDialog(
        isPresented: .constant(true),
        title: "Rename Document",
        currentName: "Old Name",
        onRename: { newName in
            print("Renamed to: \(newName)")
        }
    )
    .frame(width: 300, height: 200)
}