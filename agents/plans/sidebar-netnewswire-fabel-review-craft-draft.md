# Fabel Review — NetNewsWire sidebar → Fichero sidebar

**Reference:** NetNewsWire (Ranchero Software, MIT), `Mac/MainWindow/Sidebar/`.
**Target:** Fichero sidebar, SwiftUI on macOS 26 "Golden Gate".
**Rule:** translate ideas, don't transliterate. NNW is AppKit/`NSOutlineView`; every
adopted idea below is restated in modern SwiftUI terms.

**Licence note:** NNW is MIT. Ideas are free to take. Nothing in this plan proposes
lifting literal NNW code. If that changes, the MIT attribution must be added to the
source file header and to the third-party notices.

---

## Part 1 — What NetNewsWire does well (evidence-based)

### 1.1 `Cell/SidebarCellAppearance.swift` — one immutable appearance value

Every visual constant for a row lives in a single `Equatable` struct whose properties
are all `let`, constructed from one input (`NSTableView.RowSizeStyle`). Verbatim values:

| property | `.small` | default | `.large` |
|---|---|---|---|
| `imageSize` | 16×16 | 19×19 | 22×22 |
| `textFieldFontSize` | 11 | 13 | 15 |

Fixed, not style-dependent:
- `imageMarginRight = 4.0`
- `unreadCountMarginLeft = 10.0`

**Why it's good craft:** the row's entire look is one comparable value. Density is a
single input, not a scattering of magic numbers at call sites. Because it's `Equatable`,
a re-layout can be skipped when the appearance hasn't changed.

**Caveat — do NOT copy this part:** the font is `NSFont.systemFont(ofSize:)` on a raw
point size. That is explicitly against Fichero's semantic-font rule, and it also means
NNW's sidebar does not respond to the system text-size setting. Fichero should take the
*structure* (one appearance value, density as a single input) and reject the
*mechanism* (hardcoded point sizes).

### 1.2 `Cell/SidebarCellLayout.swift` — deliberate, ordered layout with clamping

Layout is computed as a value, not imperatively poked into views. Order:

1. floor the cell box: `NSRect(x:0, y:0, width: floor(cellSize.width), height: floor(cellSize.height))`
2. favicon: `imageSize`, x = 0, then `centeredVertically(in: bounds)`
3. title: x = `faviconRect.maxX + imageMarginRight` (or 0 with no image); width from a
   **measuring cache** — `SingleLineTextFieldSizer.size(for:font:)`; then centered vertically
4. unread badge: size = `intrinsicContentSize`, right-aligned at `bounds.maxX - width`,
   centered vertically
5. **title width clamped** to `unreadCountRect.minX - unreadCountMarginLeft`
6. second clamp of title width against the cell's right edge for the no-badge case

Three craft details worth stealing:

- **The badge never reserves space up-front — the title is clipped after the fact.**
  Result: a title only gives up width when a badge is actually present, and only as much
  as it must. No permanently-reserved dead gutter on the right of every row.
- **Only `width` is adjusted when clamping; the origin is never moved.** The title's left
  edge is rock-stable regardless of badge presence or width. Rows don't shimmy
  horizontally when a count appears or changes.
- **Vertical centring is geometric on the full cell height** via `centeredVertically(in:)`,
  applied identically to all three elements — so icon, title and badge share one centre
  line by construction rather than by three separately-tuned offsets.
- Text measurement goes through a **cache** (`SingleLineTextFieldSizer`), so scrolling a
  long list doesn't re-measure strings.

### 1.3 `Cell/SidebarCell.swift` — state-driven appearance, and truncation policy

- `isFlipped = true` (top-left origin), and layout is invalidated by setting
  `needsLayout = true` on exactly four inputs: `shouldShowImage`, `cellAppearance`,
  `unreadCount`, `name`. Nothing else triggers a re-layout. This is the AppKit spelling of
  Fichero's "no wholesale re-render on a minor change" rule.
- **Selection is a real appearance state, not just a system-supplied highlight.** The cell
  overrides `backgroundStyle`; on change it rebuilds the icon and sets
  `unreadCountView.isSelected = (backgroundStyle != .normal)`. For symbol icons the tint
  swaps explicitly: `NSColor.white` when selected, otherwise `iconImage.preferredColor`
  falling back to `NSColor.controlAccentColor`. **The icon and the badge are re-tinted for
  contrast against the selection fill — they don't just sit there in their normal colour.**
- **Truncation policy is explicit and deliberate:** `lineBreakMode = .byTruncatingTail`
  *and* `allowsDefaultTighteningForTruncation = false`. Long names clip cleanly rather
  than being letter-squeezed. A long feed name never changes the apparent typography of
  the row.
- Badge visibility is a hard binary: hidden when `unreadCount < 1`. No zero-badges.
- Accessibility label appends a localized "unread" suffix when the count is positive —
  the badge is not left as an unlabelled visual.

**Not applicable to Fichero:** the `IconImage`/`isBackgroundSuppressed` favicon machinery
is feed-domain specific.
