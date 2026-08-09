import SwiftUI

// MARK: - Library view-mode preview catalog (Daniel, 2026-08-09)
//
// One canvas per grammar surface, REAL components with inert inputs, so the
// selection/hover-free/focus states of every mode are reviewable without
// running the app. Only components with no required @Environment objects —
// the boundary-crash class — are used bare; see the per-preview notes.

// MARK: The ONE selection grammar — every state of the shared row

#Preview("Row grammar states") {
    VStack(alignment: .leading, spacing: 2) {
        LibrarySelectableRow(identity: "focused-selected", isSelected: true, tint: .accentColor, focused: true) {
            Label("Selected, pane focused", systemImage: "doc.text")
                .foregroundStyle(LibrarySelectionStyle.rowContent(selected: true, focused: true))
        }
        LibrarySelectableRow(identity: "unfocused-selected", isSelected: true, tint: .secondary, focused: false) {
            Label("Selected, pane unfocused", systemImage: "doc.text")
                .foregroundStyle(LibrarySelectionStyle.rowContent(selected: true, focused: false))
        }
        LibrarySelectableRow(identity: "plain", isSelected: false, tint: .accentColor, focused: true) {
            Label("Unselected (and NO hover state exists)", systemImage: "doc.text")
                .foregroundStyle(LibrarySelectionStyle.rowContent(selected: false, focused: true))
        }
    }
    .padding(16)
    .frame(width: 420)
}

// MARK: Selection tokens — the palette at a glance

#Preview("Selection tokens") {
    Grid(alignment: .leading, horizontalSpacing: 12, verticalSpacing: 8) {
        GridRow {
            RoundedRectangle(cornerRadius: LibrarySelectionStyle.cornerRadius)
                .fill(LibrarySelectionStyle.rowFill(selected: true, focused: true))
                .frame(width: 56, height: 24)
            Text("rowFill selected+focused (system accent)")
        }
        GridRow {
            RoundedRectangle(cornerRadius: LibrarySelectionStyle.cornerRadius)
                .fill(LibrarySelectionStyle.rowFill(selected: true, focused: false))
                .frame(width: 56, height: 24)
            Text("rowFill selected, unfocused (system grey)")
        }
        GridRow {
            RoundedRectangle(cornerRadius: LibrarySelectionStyle.cornerRadius)
                .fill(LibrarySelectionStyle.fill)
                .frame(width: 56, height: 24)
            Text("fill — icon-well backdrop / passive column trail")
        }
    }
    .font(.caption)
    .padding(16)
}

// MARK: Entity tile — the icon grammar's second citizen

#Preview("Entity tiles") {
    HStack(alignment: .top, spacing: 12) {
        EntityThumbnailView(
            entity: .init(id: "e1", canonicalName: "Marshall, John", entityType: .person),
            isSelected: true,
            secondaryText: "12 claims",
            kindStyle: EntityThumbnailKindStyle(label: "People", systemName: "person.2.fill", tint: .blue)
        )
        EntityThumbnailView(
            entity: .init(id: "e2", canonicalName: "Fredericton", entityType: .location),
            isSelected: false,
            secondaryText: "3 claims",
            kindStyle: EntityThumbnailKindStyle(label: "Places", systemName: "mappin.and.ellipse", tint: .orange)
        )
    }
    .padding(16)
    .frame(width: 320, height: 240)
}

// MARK: Canvas item — the 2D canvas's selection stroke beside the row grammar

/// CanvasItemDisplay has a custom Codable init (no memberwise), so fixtures
/// decode from JSON — the same path real items take.
private func canvasFixture(_ id: String, _ text: String) -> CanvasItemDisplay {
    let json = #"{"id":"\#(id)","folderId":"f","kind":"note","text":"\#(text)"}"#
    // swiftlint:disable:next force_try
    return try! JSONDecoder().decode(CanvasItemDisplay.self, from: Data(json.utf8))
}

#Preview("Canvas item states") {
    HStack(spacing: 16) {
        CanvasItemView(
            item: canvasFixture("a", "Selected note — the 2D canvas stroke beside the row grammar"),
            isSelected: true
        )
        CanvasItemView(item: canvasFixture("b", "Unselected note"), isSelected: false)
    }
    .padding(20)
    .frame(width: 420, height: 200)
}
