# Image Preview Interactions Plan

## Status: IMPLEMENTED

## Issues Fixed

1. ✅ **Loupe auto-appears** - When toggling loupe on via toolbar/menu, it appears immediately at center of visible area (or last position if previously placed).

2. ✅ **Scroll/zoom is context-aware** - Pinch/scroll only zooms loupe when cursor is directly over the loupe. Otherwise affects main image.

3. ✅ **Mini-map rectangle fixed** - Now properly accounts for image aspect ratio within the map frame.

---

## Proposed Interaction Model

### Areas

```
┌─────────────────────────────────────────────────────┐
│  Toolbar: [Zoom +/-] [Fit] [100%] [Magnifier] [Loupe] │
├─────────────────────────────────────────────────────┤
│                                          ┌────────┐ │
│                                          │Mini-Map│ │
│              MAIN IMAGE AREA             └────────┘ │
│                                                     │
│                    ┌─────────┐                      │
│                    │  LOUPE  │ (when enabled)       │
│                    │  (3.0x) │                      │
│                    └─────────┘                      │
│                                                     │
├─────────────────────────────────────────────────────┤
│  ═══════════════════════════════════════════════════│ ← Resize handle
│               MAGNIFIER PANEL (4x)                  │
│                                                     │
└─────────────────────────────────────────────────────┘
```

---

## Loupe Behavior

### Toggle On (from toolbar/menu)
- Loupe appears immediately at **center of visible area** OR **last position** if previously placed
- No click required to show it
- Loupe tracks cursor position for what it magnifies

### Toggle Off
- Loupe disappears
- Position is remembered for next toggle on

### While Active
| Action | Behavior |
|--------|----------|
| Click on image | Move loupe to click location (both view position and what it shows) |
| Click on loupe | Start drag mode |
| Drag loupe | Move loupe display position (keeps showing original spot) |
| Right-click on loupe | Remove loupe (same as toggle off) |
| Scroll wheel over loupe | Adjust loupe magnification (1.5x - 10x) |
| Pinch over loupe | Adjust loupe magnification |
| Move cursor | Loupe shows area under cursor (unless dragged away) |

---

## Main Image Area Behavior

| Action | When Loupe Hidden | When Loupe Visible (cursor NOT over loupe) |
|--------|-------------------|-------------------------------------------|
| Pinch to zoom | Zoom main image | Zoom main image |
| Two-finger scroll | Pan main image | Pan main image |
| Scroll wheel | Zoom main image | Zoom main image |
| Click | None | Place loupe at click position |
| Double-click | Toggle fit/100% | Toggle fit/100% |

---

## Magnifier Panel Behavior

| Action | Behavior |
|--------|----------|
| Pinch to zoom | Adjust magnifier zoom (1x - 16x) |
| Two-finger scroll | Pan the magnified view (move what area is shown) |
| Scroll wheel | Adjust magnifier zoom |
| Drag resize handle | Change panel height |

---

## Mini-Map Behavior

| Action | Behavior |
|--------|----------|
| Click | Jump main image to that location |
| Drag | Pan main image by dragging visible rect |
| Scroll/pinch | Pass through to main image |

---

## Implementation Changes Needed

### 1. Loupe Auto-Appear on Toggle

**File**: `EditorView.swift` - `ZoomableImagePreview`

```swift
// Track loupe position separately from "placed" state
@AppStorage("imagePreview.loupeX") private var loupeX: Double = 0.5  // Normalized 0-1
@AppStorage("imagePreview.loupeY") private var loupeY: Double = 0.5

// When loupeEnabled changes to true, set initial position
.onChange(of: loupeEnabled) { _, newValue in
    if newValue {
        // Signal to TrackingImageView to show loupe at stored position
        NotificationCenter.default.post(name: .showLoupeAtPosition, object: nil)
    }
}
```

**File**: `TrackingImageView`

```swift
// On toggle on: place loupe at center or last position
func showLoupeAtStoredPosition() {
    let centerX = bounds.width * 0.5  // or stored position
    let centerY = bounds.height * 0.5
    loupePosition = CGPoint(x: centerX, y: centerY)
    loupeViewPosition = CGPoint(x: centerX, y: centerY)
    needsDisplay = true
}
```

### 2. Scroll Wheel Context Detection

**File**: `TrackingImageView`

Current: Scroll wheel always zooms loupe if loupe is visible
Needed: Only zoom loupe if cursor is OVER the loupe

```swift
override func scrollWheel(with event: NSEvent) {
    let location = convert(event.locationInWindow, from: nil)

    // Check if over loupe
    if loupeEnabled, let viewPos = loupeViewPosition {
        let loupeRect = loupeRect(at: viewPos)
        if loupeRect.contains(location) {
            // Zoom loupe
            let delta = event.scrollingDeltaY
            let newMag = loupeMagnification + delta * 0.05
            loupeMagnification = max(minLoupeMagnification, min(maxLoupeMagnification, newMag))
            onLoupeMagnificationChanged?(loupeMagnification)
            return
        }
    }

    // Not over loupe - pass to scroll view for image pan/zoom
    super.scrollWheel(with: event)
}
```

### 3. Magnifier Panel Scroll = Pan

**File**: `MagnifierPanelNSView`

Add panning with two-finger scroll:

```swift
var panOffset: CGPoint = .zero  // How much we've panned from cursor position
var onPanChanged: ((CGPoint) -> Void)?

override func scrollWheel(with event: NSEvent) {
    if event.phase == .changed {
        if event.modifierFlags.contains(.option) || abs(event.scrollingDeltaX) > abs(event.scrollingDeltaY) {
            // Two-finger horizontal scroll = pan
            panOffset.x += event.scrollingDeltaX * 0.5
            panOffset.y += event.scrollingDeltaY * 0.5
            onPanChanged?(panOffset)
            needsDisplay = true
        } else {
            // Vertical scroll = zoom
            let newMag = magnification + event.scrollingDeltaY * 0.1
            magnification = max(minMagnification, min(maxMagnification, newMag))
            onMagnificationChanged?(magnification)
            needsDisplay = true
        }
    }
}
```

### 4. Mini-Map Click to Navigate

**File**: `NavigatorMiniMap`

Add click gesture to jump main image:

```swift
var onNavigate: ((CGPoint) -> Void)?  // Normalized position to jump to

.gesture(
    DragGesture(minimumDistance: 0)
        .onEnded { value in
            // Convert click to normalized position
            let normalizedX = value.location.x / geometry.size.width
            let normalizedY = value.location.y / geometry.size.height
            onNavigate?(CGPoint(x: normalizedX, y: normalizedY))
        }
)
```

---

## Priority Order

1. **Loupe auto-appear** - Most impactful UX fix
2. **Scroll context detection** - Fix scroll over main image vs loupe
3. **Mini-map click navigation** - Nice to have
4. **Magnifier pan** - Nice to have

---

## Questions for User

1. Should loupe follow cursor by default, or stay where placed until moved?
   - Option A: Always follows cursor (shows what's under cursor)
   - Option B: Stays where placed, shows that fixed spot
   - Option C: Follows cursor unless dragged, then shows original spot (current behavior when dragged)

2. For mini-map, should dragging the visible rect pan the image in real-time?

3. Should there be a keyboard shortcut to cycle loupe magnification presets?
