@testable import Fichero
import Foundation
import Testing

/// The edit-steps stack behaves the way Aperture/Lightroom taught everyone it
/// does (Daniel, 2026-09-02): re-opening a step edits it WHERE IT IS, deleting
/// one reapplies the rest, and reverting is a labelled, confirmed action.
///
/// The editing surface is a SwiftUI view that cannot be instantiated in-process,
/// so the load-bearing properties are pinned against the source. The pure
/// helpers underneath (`numericParam`, clipboard sanitising) are exercised for
/// real below.
struct ImageEditStepEditingTests {
    private func source(_ relative: String) throws -> String {
        let url = try AppSource.root().appendingPathComponent(relative)
        return try String(contentsOf: url, encoding: .utf8)
    }

    private func modelSource() throws -> String {
        try source("Views/Preview/ImageEditor/ImageEditorModel.swift")
    }

    // MARK: - In-place step editing

    @Test("re-editing a step rewrites it in place instead of appending a new one")
    func updateOperationKeepsPosition() throws {
        let model = try modelSource()
        #expect(model.contains("func updateOperation(at index: Int, params: [String: Any]) async"))
        // The whole point: ONE chain PUT with the step replaced at its own
        // index — not a remove followed by an append.
        #expect(model.contains("ops[index] = AnyCodable(dict)"))
        #expect(model.contains("service.setOperations(documentId: self.documentId, operations: ops)"))
        // A cached render of the step's OLD settings must not survive the edit.
        #expect(model.contains("dict.removeValue(forKey: \"derived_path\")"))
        // Out-of-range indices are refused rather than crashing the editor.
        #expect(model.contains("guard chain.operations.indices.contains(index) else { return }"))
    }

    @Test("the panel routes every Re-apply through one helper, and says which it did")
    func panelRoutesThroughReapplyHelper() throws {
        let steps = try source("Views/Preview/ImageEditor/ImageEditChainPanel+Steps.swift")
        #expect(steps.contains("func reapplyStep(at index: Int, params: [String: Any], legacy: () -> Void)"))
        #expect(steps.contains("if let onUpdateStep {"))
        // The fallback for a host that has not wired in-place editing is the
        // old remove-then-re-add, kept so the button is never dead.
        #expect(steps.contains("onRemove(index)"))
        #expect(steps.contains("legacy()"))
        // Wording follows capability: it only promises "Update Step" when the
        // step will actually stay put.
        #expect(steps.contains("var editsStepsInPlace: Bool { onUpdateStep != nil }"))
        #expect(steps.contains("editsStepsInPlace ? \"Update Step\" : \"Re-apply\""))
        // Exactly one `onRemove(index)` in the whole file: the fallback inside
        // the helper. A second one means a step editor went back to
        // hand-rolling remove-then-re-add, which is the reordering bug.
        #expect(steps.components(separatedBy: "onRemove(index)").count == 2)
    }

    @Test("the editor hosts the steps stack and wires in-place editing")
    func editorHostsAndWiresTheStack() throws {
        let panel = try source("Views/Preview/ImageEditor/ImageEditorView+Steps.swift")
        #expect(panel.contains("onUpdateStep: { index, params in"))
        #expect(panel.contains("await model.updateOperation(at: index, params: params)"))
        #expect(panel.contains("accessibilityIdentifier(\"imageEditStepsPanel\")"))
        // …and it is actually in the editor's body, beside the canvas.
        let view = try source("Views/Preview/ImageEditor/ImageEditorView.swift")
        #expect(view.contains("stepsPanel"))
    }

    @Test("delete-a-step and revert-to-original stay reachable and confirmed")
    func deleteAndRevertStayReachable() throws {
        let panel = try source("Views/Preview/ImageEditor/ImageEditChainPanel.swift")
        #expect(panel.contains("Remove step \\(index + 1), \\(operation.title)"))
        // Revert is a labelled button, not a bare trash can, and asks first.
        #expect(panel.contains("Label(\"Revert\", systemImage: \"arrow.counterclockwise.circle\")"))
        #expect(panel.contains("isPresented: $showRevertConfirm"))
        #expect(panel.contains("Button(\"Revert to Original\", role: .destructive)"))
        #expect(panel.contains("accessibilityIdentifier(\"imageEditChainReset\")"))
    }

    // MARK: - Parameter decoding (real behaviour)

    @Test("a saved parameter re-seeds its control whatever JSON shape it took")
    func numericParamAcceptsEveryJSONShape() {
        // A brightness of exactly 1 round-trips through JSON as an Int; the
        // old `as? Double` missed it and re-opened the step showing a default.
        #expect(ImageEditChainPanel.numericParam(["brightness": 1], "brightness") == 1.0)
        #expect(ImageEditChainPanel.numericParam(["brightness": 1.25], "brightness") == 1.25)
        #expect(ImageEditChainPanel.numericParam(["angle": NSNumber(value: -90)], "angle") == -90)
        #expect(ImageEditChainPanel.numericParam(["angle": "12.5"], "angle") == 12.5)
        // Absent and unparseable stay nil so the caller's own default wins
        // rather than a silent zero.
        #expect(ImageEditChainPanel.numericParam([:], "angle") == nil)
        #expect(ImageEditChainPanel.numericParam(["angle": "banana"], "angle") == nil)
    }
}
