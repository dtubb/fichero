# Sidebar row heights: two mechanisms, one decision (#4476)

**For Daniel, Tuesday. Five minutes of looking at the sidebar settles it.**

Nothing here is implemented. `SidebarRowMetricsTests.testVerticalStillDisagreesAndThatIsDeliberateForNow` pins today's values on purpose, so the day someone harmonises them the test fails and the change has to be a decision rather than a side effect.

---

## 1. The two mechanisms, and where they live

| row kind | list inset (vertical) | padding on its own content | defined at |
|---|---|---|---|
| library disclosure group | **2** | none | `SidebarRowMetrics.vertical(.library)` |
| item row inside a library | **0** | **`.padding(.vertical, 1)`** | `SidebarItemRow.swift:494` |
| inline notice row | **2** | none | `SidebarRowMetrics.vertical(.inlineNotice)` |

Two rows reach their height through `listRowInsets`. One reaches it through padding on the label. Nothing forces them to agree, and they are edited in different files by people solving different problems.

## 2. What the heights actually are — they are NOT equal

The issue says item rows reach "roughly the same total height". Measured from the code, they do not:

```
library row  = content + 2 + 2  = content + 4pt
item row     = content + 1 + 1  = content + 2pt
notice row   = content + 2 + 2  = content + 4pt
```

Both labels render body-weight system text with a leading icon, so `content` is the same for the library and item rows.

**Item rows are 2pt tighter than library rows.** That may well be correct — a library row is a section header and a slightly taller header reads as hierarchy. But it is currently an accident of two mechanisms, not a decision anyone made.

## 3. The part that is not about pixels

**Where the vertical space lives decides what the hover and selection highlights cover.**

- The hover wash is `.background(...)` applied to the item row's content *after* its `.padding(.vertical, 1)` (`SidebarItemRow.swift:513`), so the wash covers the padded content — but **not** the `listRowInsets` area.
- Selection is the native `List` treatment (the app draws no selection fill of its own — #4371), and it covers the **full row**, insets included.

So today, on an item row, **the hover highlight and the selection highlight are different sizes.** Hover fills content + 2pt; selection fills the whole row. Move that padding into `listRowInsets` and the hover wash gets *smaller* still, leaving a visible gap above and below it inside the selected row.

This is the thing that cannot be reconstructed by reading one file, and it is why "just put it all in one place" has two opposite answers depending on which place you pick.

## 4. The candidates

### Option A — all vertical space in `SidebarRowMetrics`

Delete `.padding(.vertical, 1)`; set `vertical(.libraryItem) = 1`.

- Row heights: **unchanged**, exactly.
- Hover wash: **shrinks by 2pt** and no longer touches the row edges. Visible regression against selection.
- Verdict: pixel-neutral for layout, not for the wash.

### Option B — all vertical space in the row's own padding ← **recommended**

Set `vertical(...) = 0` for every depth; each row kind pads its own content (item 1, library 2, notice 2).

- Row heights: **unchanged**, exactly.
- Hover wash: **grows to fill the whole row**, so hover and selection finally describe the same rectangle.
- Verdict: pixel-neutral for layout, and fixes the hover/selection mismatch as a side effect rather than needing its own pass.

### Option C — harmonise the heights too

Either of the above, plus making all three rows the same total height (all 2, or all 4).

- Row heights: **changed**. Flattens the header/child distinction.
- Verdict: this is the only option that needs eyes on the running app. A and B do not.

## 5. Recommendation

**Option B, and treat the height question separately.**

The reason is that A and B are *mechanical* — they change nothing about layout and can be reviewed as pure consolidation — while C is *aesthetic* and needs someone looking at the sidebar. Bundling them is exactly what #4096 refused to do, for the same reason: a consolidation that also restyles cannot be reviewed as either, and cannot be reverted separately if the restyle is wrong.

B is preferred over A because of §3: it makes the hover wash and the selection cover the same rectangle, which is a real visible improvement, and it does so without a separate decision. A actively makes that mismatch worse.

**What I would like from you, in one sentence each:**

1. Is a library row *supposed* to be taller than its item rows (today: +2pt)? If yes, C is closed and B is the whole fix.
2. If they should be equal — 2pt or 4pt of vertical space?

Constraint to carry either way, from #4097: hovering must not change metrics. Both A and B keep hover a fill-only change, so neither breaks Every Frame Perfect.

## 6. Scope note

This is smaller than it looks — the mechanical part is a three-line change plus updating the pinning test. What is *not* small is question 1 above, which no amount of code reading answers.

Related visual decisions in the same surface, worth one look-at-it pass together: #4095 (`.badge()`), #4097 (hover), #4371 (selection weight — now closed, the sidebar draws no selection fill of its own).
