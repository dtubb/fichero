import Foundation

// MARK: - Where you have been on this board (§16, R10 step 4)

/// A bounded Back/Forward stack of camera POSES for one canvas window.
///
/// R10 settles what navigation is: **the camera cuts, the user never flies.**
/// A jump-cut is cheap to make and cheap to undo, but only if you can get back
/// — zoom to fit, jump into a hit, then return to exactly where you were
/// looking. That return trip is this type.
///
/// **View state, not document state.** A pose is where a window's camera was
/// pointing, which is not a fact about the library: it is not saved, not
/// shared between windows, and never reaches `CanvasLayoutStore` or
/// `UserDefaults`. Two windows on the same folder keep their own histories, and
/// closing one loses nothing anyone would miss. `historyIsWindowLocal` pins
/// that as a test rather than a promise.
///
/// **Only jumps are recorded** — zoom-to-fit, a double-click focus, a jump to a
/// search hit. Continuous pan and zoom are not jumps: the user drives them
/// frame by frame and already knows where they went, and recording them would
/// fill the stack with poses nobody asked to return to.
///
/// Generic over the pose because the two renderers describe a camera
/// differently — 2D by plane position and ortho scale, 3D by look-at and
/// distance — and neither should have to flatten into the other's vocabulary
/// to be remembered.
struct CanvasJumpHistory<Pose> {
    /// How many poses back you can walk. Twenty is a session's worth of
    /// looking; an unbounded stack is a leak with good manners.
    static var capacity: Int { 20 }

    private var back: [Pose] = []
    private var forward: [Pose] = []

    init() {}

    var canJumpBack: Bool { !back.isEmpty }
    var canJumpForward: Bool { !forward.isEmpty }

    /// How many poses are held, for tests and for the bound.
    var count: Int { back.count + forward.count }

    /// Remember where the camera IS, immediately before jumping it somewhere
    /// else.
    ///
    /// Truncates the forward branch — the browser rule. Once you go back and
    /// then somewhere new, the path you abandoned is not somewhere you can
    /// return "forward" to any more, and pretending otherwise makes ⌘] land
    /// somewhere the user never was.
    mutating func record(_ pose: Pose) {
        back.append(pose)
        forward.removeAll()
        if back.count > Self.capacity {
            back.removeFirst(back.count - Self.capacity)
        }
    }

    /// Step back one pose. `current` is where the camera is now, so it becomes
    /// the forward step. Nil when there is nowhere to go — an empty history is
    /// a no-op, never a jump to the origin.
    mutating func jumpBack(from current: Pose) -> Pose? {
        guard let previous = back.popLast() else { return nil }
        forward.append(current)
        if forward.count > Self.capacity {
            forward.removeFirst(forward.count - Self.capacity)
        }
        return previous
    }

    /// Step forward again, undoing a `jumpBack`.
    mutating func jumpForward(from current: Pose) -> Pose? {
        guard let next = forward.popLast() else { return nil }
        back.append(current)
        if back.count > Self.capacity {
            back.removeFirst(back.count - Self.capacity)
        }
        return next
    }
}
