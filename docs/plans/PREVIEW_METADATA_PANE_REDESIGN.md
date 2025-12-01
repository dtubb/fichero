# Preview Metadata Pane Redesign Plan

## Current State
- CollapsibleSection with "Metadata" title
- Disclosure triangle (too large)
- Horizontal fields [Label] [Value]
- Text field at bottom with small margins

## Proposed Redesign

### Layout Structure
```
┌─────────────────────────────────────────┐
│  [Preview]  [Export]                    │  <- Tab bar (like AdjustView)
├─────────────────────────────────────────┤
│ ▾ Document Title Here...          [···] │  <- Small disclosure + file title + tiny settings
├─────────────────────────────────────────┤
│ Title      [editable value]             │  <- Tiny fields (8pt font, 18px rows)
│ Date       [editable value]             │
│ Author     [editable value]             │
│ Description[editable value]             │
│ Language   [editable value]             │
├─────────────────────────────────────────┤  <- 1px grey divider line
│                                         │
│ [Text area - true edge-to-edge]         │
│                                         │
└─────────────────────────────────────────┘
```

### Key Changes

#### 1. Tab System at Top
- Use `toga.OptionContainer` like AdjustView
- Two tabs: **Preview** (current view) and **Export** (future: export options)
- Tab bar style matches macOS native

#### 2. Header Redesign
- **Title**: Show file/item title (truncated with ellipsis if needed), NOT "Metadata"
- **Disclosure triangle**: Smaller (font-size 8, button 18x18px)
- **Settings button**: Smaller (18x18px, "···" text)
- Layout: `[▾ disclosure] [Title...] [spacer] [···]`

#### 3. Even Smaller Fields
| Property | Before | After |
|----------|--------|-------|
| Font size | 9pt | 8pt |
| Row height | 20px | 18px |
| Label width | 80px | 70px |
| Margins | 1px/4px | 0px/2px |

#### 4. Grey Divider
- 1px height grey line (`#E0E0E0`) between metadata fields and text area
- Creates visual separation

#### 5. Text Field Edge-to-Edge
- `margin=0` on all sides (true full bleed)
- No spacer above, just the grey divider

#### 6. Disclosure Triangle Size
| Property | Before | After |
|----------|--------|-------|
| Button size | 24x24px | 18x18px |
| Font size | 10pt | 8pt |
| Margin | 2px/4px | 1px/2px |

### Implementation Order

1. **Phase 1**: Shrink disclosure triangle and settings button
2. **Phase 2**: Change header to show file title instead of "Metadata"
3. **Phase 3**: Reduce field sizes (8pt font, 18px rows)
4. **Phase 4**: Add grey divider, make text edge-to-edge
5. **Phase 5**: Add tab system (Preview/Export)

### Files to Modify

1. `src/fichero/shared/widgets/collapsible_section.py`
   - Shrink button sizes
   - Change font sizes
   - Accept dynamic title

2. `src/fichero/shared/widgets/metadata_field.py`
   - Reduce to 8pt font
   - Reduce row height to 18px
   - Tighter margins

3. `src/fichero/windows/main/views/preview/preview_metadata_pane.py`
   - Add OptionContainer for tabs
   - Pass file title to header
   - Add grey divider
   - Remove text field margins

### Questions to Resolve

1. **Export tab content**: What should the Export tab show?
   - Export format options?
   - Export history?
   - Just a placeholder for now?

2. **Title truncation**: How many characters before truncating?
   - Suggest: ~30 chars with "..." at end

3. **Disclosure behavior**: When collapsed, hide fields AND text, or just fields?
   - Suggest: Just hide fields, always show text
