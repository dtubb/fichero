import SwiftUI

/// Input area for chat messages
struct ChatInputView: View {
    @Binding var inputText: String
    let isLoading: Bool
    let onSend: () -> Void

    var body: some View {
        HStack(spacing: 12) {
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
