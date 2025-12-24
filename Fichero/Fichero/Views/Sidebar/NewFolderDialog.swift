import SwiftUI

/// Reusable dialog for creating new folders in the sidebar
struct NewFolderDialog: View {
    @Binding var isPresented: Bool
    let title: String
    let placeholder: String
    let onCreate: (String) async throws -> Void
    let onCancel: (() -> Void)?

    @State private var folderName: String = ""
    @State private var isCreating = false
    @State private var errorMessage: String?

    init(
        isPresented: Binding<Bool>,
        title: String,
        placeholder: String = "Enter folder name",
        onCreate: @escaping (String) async throws -> Void,
        onCancel: (() -> Void)? = nil
    ) {
        self._isPresented = isPresented
        self.title = title
        self.placeholder = placeholder
        self.onCreate = onCreate
        self.onCancel = onCancel
    }

    var body: some View {
        VStack(spacing: 16) {
            // Title
            Text(title)
                .font(.headline)

            // Text field
            TextField(placeholder, text: $folderName)
                .textFieldStyle(.roundedBorder)
                .disableAutocorrection(true)
                .onSubmit {
                    createFolder()
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

                Button("Create") {
                    createFolder()
                }
                .keyboardShortcut(.defaultAction)
                .disabled(isCreating || folderName.isEmpty)
                .overlay {
                    if isCreating {
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

    private func createFolder() {
        guard !folderName.isEmpty else { return }

        isCreating = true
        errorMessage = nil

        Task {
            do {
                try await onCreate(folderName)
                isPresented = false
            } catch {
                errorMessage = error.localizedDescription
                isCreating = false
            }
        }
    }
}

// MARK: - Preview

#Preview {
    NewFolderDialog(
        isPresented: .constant(true),
        title: "New Folder",
        onCreate: { folderName in
            print("Create folder: \(folderName)")
        }
    )
    .frame(width: 300, height: 200)
}