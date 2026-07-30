@testable import Fichero
import Foundation
import Testing

/// #4386: an inspector row's hit target must be the ROW, not the label.
///
/// The reported symptom — "you must click to the left of the name" — is the
/// signature of a target that is the label's intrinsic width sitting at the
/// leading edge of a wider row.
///
/// The subtlety worth recording, because it is what made the half-fix look
/// like a fix: **`.contentShape(Rectangle())` alone is not enough.** It makes a
/// view's OWN frame hittable, and an unstretched row's frame is exactly its
/// content's width. The stretch has to come first. `inspectorListRowTarget()`
/// does both, in that order:
///
///     frame(maxWidth: .infinity, alignment: .leading)
///         .contentShape(Rectangle())
///
/// So the class-level rule is not "add a contentShape" — it is "use the shared
/// modifier", and these tests enforce that rather than the weaker thing.
struct InspectorRowTargetTests {
    private static func appSource(_ relativePath: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero")
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }

    /// The modifier must stretch BEFORE it shapes. Reversed, it would shape the
    /// intrinsic frame and then stretch a non-hittable one — the exact bug,
    /// reintroduced while looking correct.
    @Test("the shared row target stretches before it shapes")
    func rowTargetStretchesBeforeShaping() throws {
        let source = try Self.appSource("Views/Inspector/Document/DocumentInspector.swift")
        #expect(source.contains("func inspectorListRowTarget()"))
        let body = source.components(separatedBy: "func inspectorListRowTarget()")[1]
        let frameIndex = body.range(of: "frame(maxWidth: .infinity")
        let shapeIndex = body.range(of: "contentShape(Rectangle())")
        #expect(frameIndex != nil)
        #expect(shapeIndex != nil)
        if let frameIndex, let shapeIndex {
            #expect(frameIndex.lowerBound < shapeIndex.lowerBound)
        }
    }

    /// Every selectable inspector row goes through the shared modifier. A row
    /// that reaches for a bare `contentShape` has the half-fix, whose target is
    /// still the label's width.
    @Test("no inspector row uses a bare contentShape as its row target")
    func noRowUsesABareContentShapeAsItsTarget() throws {
        let files = [
            "Views/Inspector/Source/DocumentInspectorContentV2.swift",
            "Views/Inspector/Source/Info/DocumentInspectorInfoTab.swift",
            "Views/Chat/Inspector/ChatInspector+Search.swift",
            "Views/Inspector/Artifacts/ArtifactListView.swift",
            "Views/Inspector/Document/DocumentInspectorRelatedTab.swift",
            "Views/Inspector/Knowledge/Citations/CitationListView.swift",
            "Views/Inspector/Notes/Annotations/AnnotationListView.swift",
            "Views/Inspector/Knowledge/Entities/DocumentInspectorEntitiesTab+Rows.swift",
        ]
        for file in files {
            let source = try Self.appSource(file)
            #expect(
                source.contains(".inspectorListRowTarget()"),
                "\(file) has a selectable row without the shared full-width target"
            )
            // The half-fix: a contentShape immediately before the row's tap,
            // with no stretch in between.
            #expect(
                !source.contains(".contentShape(Rectangle())\n        .onTapGesture"),
                "\(file) still shapes an unstretched row"
            )
        }
    }
}
