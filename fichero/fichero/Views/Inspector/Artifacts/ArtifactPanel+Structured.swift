import SwiftUI

extension ArtifactPanel {
    // MARK: - Structured output

    /// Formatted view for structured outputs (JSON formatted)
    @ViewBuilder
    var structuredOutputView: some View {
        switch kind {
        case .pageContent:
            // Shouldn't happen since isStructuredOutput is false for pageContent
            Text("Unsupported content type")
                .foregroundColor(.red)
        case .artifact(let artifact):
            if let content = artifact.content, !content.isEmpty {
                // Try to parse as JSON first for structured data
                if let jsonData = content.data(using: .utf8),
                   let jsonObject = try? JSONSerialization.jsonObject(with: jsonData, options: []),
                   let formattedJSON = try? JSONSerialization.data(
                       withJSONObject: jsonObject, options: [.prettyPrinted]
                   ) {
                    if let formattedString = String(data: formattedJSON, encoding: .utf8) {
                        ScrollView {
                            Text(formattedString)
                                .font(.system(.body, design: .monospaced))
                                .foregroundColor(.primary)
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .padding()
                                .cornerRadius(4)
                        }
                        .frame(maxWidth: .infinity)
                        .frame(height: 200)
                    } else {
                        fallbackStructuredView(content: content)
                    }
                } else {
                    fallbackStructuredView(content: content)
                }
            } else {
                Text("(no content)")
                    .foregroundColor(.secondary)
                    .italic()
            }
        }
    }

    /// Fallback view for structured content that isn't valid JSON
    @ViewBuilder
    private func fallbackStructuredView(content: String) -> some View {
        ScrollView {
            Text(content)
                .font(.system(.body, design: .monospaced))
                .foregroundColor(.primary)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding()
                .cornerRadius(4)
        }
        .frame(maxWidth: .infinity)
        .frame(height: 200)
    }
}
