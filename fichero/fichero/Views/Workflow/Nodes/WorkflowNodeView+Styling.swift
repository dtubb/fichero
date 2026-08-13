import SwiftUI

// Extracted from WorkflowNodeView.swift (type-body/file-length limits,
// 2026-08-13): the static tool icon/color tables and their lookups —
// self-contained, reused by other views through the two static funcs.

extension WorkflowNodeView {
    // MARK: - Static Helpers (reusable by other views)

    private static let toolIcons: [String: String] = [
        "files": "doc.on.doc",
        "collection": "folder",
        "search": "magnifyingglass",
        "transcribe": "text.viewfinder",
        "describe": "eye",
        "analyze": "doc.text.magnifyingglass",
        "enhance": "wand.and.stars",
        "crop": "crop",
        "rotate": "rotate.right",
        "segment": "rectangle.split.3x1",
        "summarize": "text.quote",
        "translate": "globe",
        "extract_entities": "person.text.rectangle",
        "classify": "tag",
        "custom_llm": "text.bubble",
        "if": "arrow.triangle.branch",
        "switch": "arrow.triangle.swap",
        "loop": "repeat",
        "filter": "line.3.horizontal.decrease.circle",
        "merge": "arrow.triangle.merge",
        "to_pdf": "doc.richtext",
        "to_word": "doc.text",
        "to_excel": "tablecells",
        "to_json": "curlybraces",
        "save_to_library": "square.and.arrow.down",
        "export": "folder.badge.plus"
    ]

    private static let toolColors: [String: Color] = [
        // Sources (green)
        "files": .green,
        "collection": .green,
        "search": .green,
        // Vision (blue)
        "transcribe": .blue,
        "describe": .blue,
        "analyze": .blue,
        // Transform (pink)
        "enhance": .pink,
        "crop": .pink,
        "rotate": .pink,
        "segment": .pink,
        // LLM (purple)
        "summarize": .purple,
        "translate": .purple,
        "extract_entities": .purple,
        "classify": .purple,
        "custom_llm": .purple,
        // Logic (yellow)
        "if": .yellow,
        "switch": .yellow,
        "loop": .yellow,
        "filter": .yellow,
        "merge": .yellow,
        // Convert (orange)
        "to_pdf": .orange,
        "to_word": .orange,
        "to_excel": .orange,
        "to_json": .orange,
        // Sink (red)
        "save_to_library": .red,
        "export": .red
    ]

    static func iconForTool(_ tool: String) -> String {
        return toolIcons[tool] ?? "gearshape"
    }

    static func colorForTool(_ tool: String) -> Color {
        return toolColors[tool] ?? .gray
    }
}
