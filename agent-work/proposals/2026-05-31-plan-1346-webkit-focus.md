# Plan: #1346 — Fix WebKit Scroll Reset + Attribute Focus Navigation

**Status:** Ready for implementation  
**Effort estimate:** 1 sitting (3–5 hours)  
**Risk level:** Low–medium. The WKWebView load guard is already correct; this plan adds JS APIs and eliminates the one remaining re-render that resets scroll.

---

## Root Cause: `renderAll()` Re-renders the DOM on Every State Change

The scroll reset has a single root cause: **`renderAll()` is called on every state change inside the WebKit page**, and `renderAll()` replaces the `innerHTML` of every panel. `innerHTML` assignment discards scroll position for the whole `.content` scroller because it forces a DOM reflow. Every highlight call from Swift (`highlightClaim`, `setActivePage`, `showTab`) triggers `renderAll()` via `window.fichero.*`, which re-renders the entire transcript, digest, and graph panels. That wipes `scrollTop`.

**The Swift reload path is already guarded correctly.** `Coordinator.loadIfNeeded` only calls `webView.load(request)` when `documentId` or `libraryPath` changes. The WKWebView itself does not reload on selection changes. The problem is entirely inside the JS rendering loop.

---

## Key Files

| File | Role |
|---|---|
| `fichero-engine/src/fichero/api/templates/document_view.html` | The HTML + JS surface. All `renderAll()`, `highlightClaim`, `showTab`, transcript markup live here. |
| `fichero/fichero/Views/Library/DocumentKGWebPane.swift` | NSViewRepresentable wrapper. `Coordinator.syncSelection` calls `evaluateJavaScript` for highlights, tab switches, and scroll-to-page. `loadIfNeeded` guards actual page loads. |
| `fichero/fichero/Views/Library/DocumentKGSurface.swift` | Hosts `DocumentKGWebPane` inside a `switch activeTab`. `@State private var activeTab` drives which view is shown. `DocumentScrollSyncState` mediates bidirectional scroll sync. |
| `fichero/fichero/Views/ContentView+KnowledgeSurface.swift` | Passes `kgFocusState.focusedEntityId` / `focusedClaimId` as props to `DocumentKGSurface` → `DocumentKGWebPane`. |
| `fichero/fichero/Models/KGFocusState.swift` | `@Observable` state object with `focusedEntityId`, `focusedClaimId`, `sourcePageLabel`. `focusClaim`/`focusEntity` have equality guards so they only fire when something actually changes. |

---

## Secondary Issue: `highlightEntity` Is Missing from `window.fichero`

`Coordinator.syncSelection` calls `window.fichero?.highlightEntity?.(literal)` with optional chaining — meaning it silently no-ops today because `highlightEntity` is not defined in the HTML's `window.fichero` object. This must be added.

---

## Implementation Plan

### Step 1 — Fix the Root Cause: Surgical DOM Updates Instead of `renderAll()`

**File:** `fichero-engine/src/fichero/api/templates/document_view.html`

The fix is to make each `window.fichero.*` method update **only what changed** in the DOM, preserving `scrollTop` of `.content`.

#### 1a. Preserve scroll across any full re-render (safety net)

Wrap `renderAll()` to save/restore scroll at the `.content` level:

```javascript
function renderAll() {
    const scroller = document.querySelector('.content');
    const savedScroll = scroller ? scroller.scrollTop : 0;

    renderTranscript();
    renderDigest();
    renderGraph();
    // ... tab visibility ...

    if (scroller) {
        scroller.scrollTop = savedScroll;
    }
}
```

This is a cheap safety net that makes `renderAll()` scroll-neutral. It does not fix per-element jitter on the transcript highlight (text nodes shift) but it prevents total position loss.

#### 1b. Make `highlightClaim` surgical (no full re-render)

Replace:
```javascript
highlightClaim(claimId) {
    state.activeClaimId = claimId;
    ...
    renderAll();   // <-- problem
},
```

With:
```javascript
highlightClaim(claimId) {
    const prev = state.activeClaimId;
    state.activeClaimId = claimId;
    const claim = claims.find(item => item.id === claimId);
    if (claim?.entity_ids?.length) {
        state.activeEntityId = claim.entity_ids[0];
    }
    // Only update claim-row active classes in the digest — no re-render
    document.querySelectorAll('.claim-row').forEach(row => {
        row.classList.toggle('active', row.dataset.claimId === claimId);
    });
    // Only update transcript highlight if claim changed
    if (prev !== claimId) {
        renderTranscript();
    }
    // Update graph dim/active state without full re-render
    _syncGraphActive();
},
```

Add a `_syncGraphActive()` helper that only updates `.node` `active`/`dimmed` class attributes (no `innerHTML` replacement of the SVG).

#### 1c. Add `highlightEntity` (currently missing)

```javascript
highlightEntity(entityId) {
    state.activeEntityId = entityId;
    state.activeClaimId = null;
    document.querySelectorAll('.claim-row').forEach(row => {
        row.classList.remove('active');
    });
    _syncGraphActive();
},
```

#### 1d. Make `setActivePage` surgical

`setActivePage` currently calls `renderAll()` to dim off-page graph nodes. Replace with:
```javascript
setActivePage(pageNumber) {
    state.activePage = pageNumber;
    _syncGraphActive();   // only updates graph node classes
},
```

#### 1e. Make `showTab` surgical

`showTab` calls `renderAll()` only to toggle panel visibility. Replace with:
```javascript
showTab(tab) {
    if (!['transcript', 'digest', 'graph'].includes(tab)) return;
    state.tab = tab;
    ['transcript', 'digest', 'graph'].forEach(t => {
        document.getElementById(`${t}-panel`).classList.toggle('hidden', t !== tab);
    });
    document.querySelectorAll('.tabs button').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.tab === tab);
    });
},
```

No DOM replacement; scroll is untouched.

---

### Step 2 — Add Per-Span/Per-Claim Anchors for Transcript Focus Navigation

**File:** `fichero-engine/src/fichero/api/templates/document_view.html`  
**File:** `fichero-engine/src/fichero/api/routes/views.py` (minor — `source_char_start`/`source_char_end` already emitted)

#### 2a. Add `window.ficheroScrollToSpan(claimId)` API

When a claim/entity is highlighted, we want to scroll the transcript to the relevant excerpt. The transcript currently renders as a single text block. Change `renderTranscript()` to wrap each claim's source_excerpt span with an anchor:

```javascript
function renderTranscript() {
    const panel = document.getElementById('transcript-panel');
    const transcript = documentData.page_content || '';
    if (!transcript) {
        panel.innerHTML = `<div class="empty">No transcript...</div>`;
        return;
    }
    // Build a list of all claim excerpts with their ids, sorted by char_start
    const spans = claims
        .filter(c => c.source_excerpt && c.source_char_start != null)
        .sort((a, b) => a.source_char_start - b.source_char_start);

    let result = '';
    let cursor = 0;
    spans.forEach(claim => {
        const start = claim.source_char_start;
        const end = claim.source_char_end || start + claim.source_excerpt.length;
        if (start > cursor) {
            result += escapeHtml(transcript.slice(cursor, start));
        }
        const isActive = state.activeClaimId === claim.id;
        result += `<mark id="claim-${escapeAttr(claim.id)}" class="claim-span${isActive ? ' active-claim' : ''}" data-claim-id="${escapeAttr(claim.id)}">${escapeHtml(transcript.slice(start, end))}</mark>`;
        cursor = end;
    });
    result += escapeHtml(transcript.slice(cursor));

    panel.innerHTML = `<div class="transcript">${result}</div>`;
}
```

Add CSS for `.claim-span` (subtle underline) and `.claim-span.active-claim` (yellow highlight).

Add `escapeAttr(text)` helper (replaces `"` → `&quot;`).

#### 2b. Add `window.ficheroScrollToSpan(claimId)` JS function

```javascript
window.ficheroScrollToSpan = function(claimId) {
    // Switch to transcript tab first if needed
    if (state.tab !== 'transcript') {
        window.fichero.showTab('transcript');
    }
    const el = document.getElementById('claim-' + claimId);
    if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
};
```

#### 2c. Surgical transcript highlight update (no full re-render)

When `highlightClaim` is called surgically (Step 1b), after updating claim-row classes, also update `<mark>` active classes in the transcript:
```javascript
document.querySelectorAll('.claim-span').forEach(el => {
    el.classList.toggle('active-claim', el.dataset.claimId === claimId);
});
```

Only call `renderTranscript()` (which replaces innerHTML) on the **first** highlight (when spans don't exist yet) or when `claimId` is null (clear). Track with a flag `transcriptRendered`.

---

### Step 3 — Wire `ficheroScrollToSpan` from Swift on Claim/Entity Tap

**File:** `fichero/fichero/Views/Library/DocumentKGWebPane.swift`

In `Coordinator.syncSelection`, after calling `highlightClaim`, also call `ficheroScrollToSpan`:

```swift
if lastSelectedClaimId != parent.selectedClaimId {
    lastSelectedClaimId = parent.selectedClaimId
    if let claimId = parent.selectedClaimId {
        let literal = DocumentKGPaneRoute.jsStringLiteral(claimId)
        webView.evaluateJavaScript("window.fichero?.highlightClaim('\(literal)');")
        // NEW: scroll the transcript to the highlighted claim span
        webView.evaluateJavaScript("window.ficheroScrollToSpan?.('\(literal)');")
    }
}
```

For entity focus, also scroll to the first claim belonging to that entity:
```swift
if lastSelectedEntityId != parent.selectedEntityId {
    lastSelectedEntityId = parent.selectedEntityId
    if let entityId = parent.selectedEntityId {
        let literal = DocumentKGPaneRoute.jsStringLiteral(entityId)
        webView.evaluateJavaScript("window.fichero?.highlightEntity?.('\(literal)');")
        // NEW: scroll transcript to first claim of that entity
        webView.evaluateJavaScript("window.ficheroScrollToEntitySpan?.('\(literal)');")
    }
}
```

Add `window.ficheroScrollToEntitySpan` in the HTML:
```javascript
window.ficheroScrollToEntitySpan = function(entityId) {
    const firstClaim = claims.find(c => (c.entity_ids || []).includes(entityId) && c.source_char_start != null);
    if (firstClaim) {
        window.ficheroScrollToSpan(firstClaim.id);
    }
};
```

---

### Step 4 — Add `highlightEntity` to `window.fichero` (Missing Method)

**File:** `fichero-engine/src/fichero/api/templates/document_view.html`

Add to `window.fichero`:
```javascript
highlightEntity(entityId) {
    state.activeEntityId = entityId;
    state.activeClaimId = null;
    document.querySelectorAll('.claim-row').forEach(row => row.classList.remove('active'));
    document.querySelectorAll('.claim-span').forEach(el => el.classList.remove('active-claim'));
    _syncGraphActive();
},
```

---

### Step 5 — Verify No Other `renderAll()` Calls on Click Events Reset Scroll

In the digest click handler (`renderDigest`, claim-row click):
```javascript
row.addEventListener('click', () => {
    ...
    renderAll();   // <-- must be fixed
});
```

Replace `renderAll()` in click handlers with surgical updates (same pattern as Step 1b). The user clicking inside the web pane should not reset scroll.

In the graph click handler (`renderGraph`, node click):
```javascript
nodeEl.addEventListener('click', async () => {
    ...
    renderAll();   // <-- must be fixed
});
```

Same: replace with surgical graph + digest updates only, preserving scroll.

---

### Step 6 — Page Navigation: Verify `ficheroScrollToPage` Does Not Reset on Click

**Already mostly correct.** `ficheroScrollToPage` in `DocumentKGPaneRoute.scrollSyncScript` sets `scroller.scrollTop` directly — this is fine for scroll sync. The issue reported ("clicking in the view resets scroll") is the `renderAll()` in click handlers (Step 5), not `ficheroScrollToPage`.

**No change needed here** unless testing reveals a regression.

---

## Summary of Changes

### `document_view.html`

1. `renderAll()`: save/restore `scrollTop` (safety net).
2. `window.fichero.showTab`: surgical panel visibility toggle — no `innerHTML`.
3. `window.fichero.highlightClaim`: surgical class update on `.claim-row` elements; surgical `active-claim` class on `.claim-span`; call `_syncGraphActive()`.
4. Add `window.fichero.highlightEntity`: surgical class update.
5. `window.fichero.setActivePage`: call `_syncGraphActive()` only — no `renderAll()`.
6. `renderTranscript()`: wrap claim excerpts with `<mark id="claim-{id}">` anchors using `source_char_start`/`source_char_end` from the claim payload.
7. Add `window.ficheroScrollToSpan(claimId)`: switch to transcript tab + `scrollIntoView`.
8. Add `window.ficheroScrollToEntitySpan(entityId)`: find first claim by entity, delegate to `ficheroScrollToSpan`.
9. Add `_syncGraphActive()` helper: update `.node` `active`/`dimmed` classes without SVG re-render.
10. Digest click handler: replace `renderAll()` with surgical updates.
11. Graph click handler: replace `renderAll()` with surgical updates.

### `DocumentKGWebPane.swift`

1. `syncSelection`: after `highlightClaim` call, add `evaluateJavaScript("window.ficheroScrollToSpan?.(literal)")`.
2. `syncSelection`: after `highlightEntity` call, add `evaluateJavaScript("window.ficheroScrollToEntitySpan?.(literal)")`.

### No backend changes required.

`source_char_start` and `source_char_end` are already emitted in `views.py` → `claim_payload`. The HTML already receives them in the `claims` JS array.

---

## Risks

| Risk | Mitigation |
|---|---|
| `source_char_start`/`source_char_end` are null for many claims (older ingestion) | `ficheroScrollToSpan` falls back to no-op; `renderTranscript` renders without anchor if no `source_char_start`. |
| SVG re-render is still needed for graph clicks (force layout runs) | Graph re-render on graph tab click is acceptable — user is looking at graph, not transcript. Only block re-render when the user is reading the transcript/digest. |
| Surgical DOM manipulation could diverge from full-render state | Unit test: after N claim selections, compare active classes to what `renderAll()` would produce. |
| `scrollIntoView` behavior differs in WKWebView vs Safari | Use `{ behavior: 'smooth', block: 'center' }` — well supported. Test on macOS 14+. |
| Transcript with overlapping claim excerpts (char ranges overlap) | Sort by `source_char_start`, skip overlapping spans (cursor check). |

---

## Test Checklist (Worker)

- [ ] Scroll transcript to position ~70% → click a claim in digest pane → verify scroll stays within 10% of original position.
- [ ] Click entity in graph → transcript switches and scrolls to entity's first claim excerpt.
- [ ] Tap `onNavigateToSource` from ClaimSummaryCard in Inspector → WebKit pane switches to transcript tab + highlights + scrolls to excerpt.
- [ ] Switch tabs (Transcript → Digest → Graph → Transcript) → scroll position in each panel is preserved.
- [ ] `pageSelected` scroll sync still works (scroll the transcript, page indicator updates).
- [ ] Claims with null `source_char_start` do not cause JS errors.
- [ ] `highlightEntity` no longer silently no-ops (add a `console.log` in dev; check via Xcode debugger WebInspector).
