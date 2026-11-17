import Foundation

/// A callback the Preview's folder canvas calls, held in the environment (#6610). A bare closure in an
/// `@Entry` makes SwiftUI treat the value as changed on every redraw; this wrapper compares equal always,
/// because the closures set here only write `@State` of the view that installs them, which is stable
/// across redraws.
struct FolderCanvasAction<Value>: Equatable {
    let run: (Value) -> Void

    init(_ run: @escaping (Value) -> Void) { self.run = run }

    func callAsFunction(_ value: Value) { run(value) }

    static func == (_: Self, _: Self) -> Bool { true }
}
