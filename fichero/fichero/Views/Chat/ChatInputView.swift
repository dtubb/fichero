import SwiftUI

/// Input area for chat messages
struct ChatInputView: View {
    @Binding var inputText: String
    let isLoading: Bool
    let onSend: () -> Void
    /// Compact touch alternative to the side inspector's drag-drop: present the
    /// document-scope sheet. `nil` hides the button (regular width, where the
    /// inspector is already visible). (#3015)
    var onAttach: (() -> Void)?

    var body: some View {
        HStack(spacing: 12) {
            if let onAttach {
                Button(action: onAttach) {
                    Image(systemName: "paperclip")
                        .font(.title3)
                        .foregroundColor(.secondary)
                }
                .buttonStyle(.plain)
                .help("Add documents to this chat's scope")
            }

            TextField("Ask a question about your documents...", text: $inputText, axis: .vertical)
                .textFieldStyle(.plain)
                .lineLimit(1...5)
                .onSubmit {
                    onSend()
                }

            Button(action: onSend) {
                Image(systemName: "arrow.up.circle.fill")
                    .font(.title2)
                    .foregroundColor(inputText.isEmpty ? .secondary : .accentColor)
            }
            .buttonStyle(.plain)
            .help("Send your message (Return)")
            .disabled(inputText.isEmpty || isLoading)
            .keyboardShortcut(.return, modifiers: [])
        }
        .padding()
        .background(Color(.windowBackgroundColor))
    }
}
