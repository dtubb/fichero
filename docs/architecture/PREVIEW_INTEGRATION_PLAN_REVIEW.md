# Preview Pane Integration Plan Review

**Reviewer**: Plan Review Agent
**Review Date**: 2025-11-15
**Review Type**: Critical Architecture Review
**Status**: **MAJOR CONCERNS - PLAN REQUIRES SIGNIFICANT REVISION**

---

## Executive Summary

### Overall Assessment: **INSUFFICIENT - MISSING CRITICAL PLAN**

After thorough analysis of the Fichero codebase, I cannot locate the "comprehensive 5-phase implementation plan" referenced in the review request. The existing documents (`PREVIEW_FOCUS_PLAN.md` and `PREVIEW_FOCUS_ARCHITECTURE.md`) address **focus system issues** within preview panes, NOT the broader **preview pane integration with selection tracking and navigation architecture**.

**Critical Finding**: **NO COMPREHENSIVE INTEGRATION PLAN EXISTS**

The referenced plan should address:
1. Integration with SelectionManager (Phases 1-4)
2. Integration with NavigationController (Phase 6)
3. Integration with PreviewContent shared component
4. Mobile vs Desktop preview workflows
5. OutputsManager and step-by-step navigation
6. Inspector pane coordination

**What Actually Exists**:
- `PREVIEW_FOCUS_PLAN.md` - Tactical fixes for click-to-focus and pane navigation (NOT integration plan)
- `PREVIEW_FOCUS_ARCHITECTURE.md` - Focus border architecture documentation (NOT integration plan)

---

## Critical Analysis: What's Missing

### Missing Plan Section 1: Requirements Analysis

**Expected**: Clear requirements document covering:
- User stories for preview workflows
- Integration points with existing systems (SelectionManager, NavigationController, etc.)
- Mobile vs Desktop UX differences
- Performance requirements
- Accessibility requirements

**Actual**: NO requirements document found

**Impact**: **CRITICAL** - Without requirements, any implementation will be incomplete

---

### Missing Plan Section 2: Architecture Integration

**Expected**: Detailed architecture showing:
- How PreviewView integrates with Phase 1-4 selection tracking
- How PreviewContent (shared component) fits into MainWindow
- Event flow diagrams showing selection → preview loading
- State management (who owns preview state?)
- Cache invalidation strategies

**Actual**: The existing architecture documents only cover:
- Focus border system (PREVIEW_FOCUS_ARCHITECTURE.md)
- OutputPane focus tracking within PreviewView

**Missing Critical Integration Points**:

#### Integration Point 1: SelectionManager → Preview Loading ❌
**Question**: When user selects item in CollectionView, how does preview load?

**Current State** (from code inspection):
```python
# collection_view.py
def _on_collection_tree_select(self, widget, row):
    # ... extracts item_id ...
    from fichero.shared.navigation.navigation_event_bus import emit_navigation
    emit_navigation('show_preview', {
        'item_id': item_id,
        'collection_id': self.collection_id
    })
```

```python
# preview_view.py line 110
subscribe_to_navigation('show_preview', self._on_show_preview_event)
```

**Analysis**:
- Event-based integration EXISTS
- Uses NavigationEventBus
- But NO PLAN documents this integration strategy
- No discussion of alternative approaches (direct calls vs events)

**Gap**: Plan should evaluate if event-driven is the right approach vs direct service calls

---

#### Integration Point 2: OutputsManager Discovery ❌
**Question**: How does PreviewView discover processing outputs for an item?

**From Code** (`preview_view.py` lines 885-920):
```python
async def _load_output_async(self, item_id: str):
    # Get item from library
    item = self.library_manager.get_collection_item(item_id)

    # Load steps using StepManager
    await self.step_manager.load_item(item_id)
```

**From StepManager**:
```python
def load_item(self, item_id):
    # Uses OutputsManager to discover steps
    self.outputs_manager.discover_outputs(item_path)
```

**Missing from Plan**:
- How does OutputsManager know where to look for outputs?
- Does it use item metadata `['output_path']`?
- What if output_path is missing or invalid?
- What if multiple output folders exist?
- How does it handle partial processing (some steps complete, others failed)?

**Current Implementation** (from OutputsManager):
- Scans filesystem for `.fichero_processing/` folders
- Reads `manifest.json` files
- Builds step tree from tool outputs

**Gap**: Plan should document output discovery strategy and edge cases

---

#### Integration Point 3: PreviewContent vs PreviewView ❌
**Question**: What's the relationship between these two classes?

**From Code**:
- `PreviewContent` (`src/fichero/windows/preview/preview_content.py`) - Shared component
- `PreviewView` (`src/fichero/windows/main/views/preview/preview_view.py`) - Main window column

**PreviewContent Features**:
- File preview (images, PDFs, text)
- Step navigation toolbar
- Edit buttons
- System app integration

**PreviewView Features**:
- Multi-pane layout (split view)
- OutputPane components
- StepManager integration
- Zoom/rotate/crop tools

**Missing from Plan**:
- Should PreviewView USE PreviewContent?
- Should they be merged?
- Who owns what functionality?
- How do they coordinate?

**Gap**: Plan should clarify component responsibilities and potential refactoring

---

#### Integration Point 4: Mobile vs Desktop Preview ❌
**Question**: How does preview work differently on mobile?

**From Code**:
```python
# main_window.py mobile layout
if self.is_mobile:
    self._create_mobile_layout()  # Single-pane stack
else:
    self._create_desktop_layout()  # 5-column layout
```

**Mobile Preview Flow** (should be documented):
1. User taps item in CollectionView
2. NavigationController pushes PreviewView onto stack
3. Back button returns to CollectionView
4. Preview is full-screen (no split panes)

**Desktop Preview Flow** (should be documented):
1. User clicks item in CollectionView
2. Preview loads in Column 4 (in-place)
3. Preview can split into multiple panes
4. Preview stays visible while navigating collections

**Missing from Plan**:
- Detailed mobile navigation flow
- Back button handling
- State preservation when navigating away and back
- Mobile toolbar layout differences

**Gap**: Plan should document mobile-specific behaviors and constraints

---

### Missing Plan Section 3: Implementation Phases

**Expected**: Clear phase breakdown with:
- Phase objectives
- Dependencies between phases
- Success criteria
- Testing strategy per phase
- Risk mitigation per phase

**Actual**: PREVIEW_FOCUS_PLAN.md has phases, but they're about **focus system fixes**, not integration:
- Phase 1: Fix click-to-focus
- Phase 2: Add keyboard shortcuts
- Phase 3: Route navigation to focused pane
- Phase 4: Route commands to focused pane
- Phase 5: Update toolbar states

**These are NOT integration phases** - they're tactical fixes within existing PreviewView.

**Missing Phases**:

#### Missing Phase 1: SelectionManager Integration ❌
**Objective**: Wire PreviewView to respond to SelectionManager events

**Tasks Should Include**:
1. Subscribe to `selection_changed` events
2. Extract item metadata from selection
3. Load preview based on selection
4. Handle multi-selection (preview first? preview all in split panes?)
5. Handle empty selection (clear preview? show placeholder?)

**Dependencies**: SelectionManager (Phase 1-4 complete ✅)

**Not Documented**: Plan doesn't address this integration

---

#### Missing Phase 2: OutputsManager Integration ❌
**Objective**: Reliably discover and load processing outputs

**Tasks Should Include**:
1. Define output discovery strategy (metadata vs filesystem scan)
2. Handle missing outputs gracefully
3. Cache output manifests for performance
4. Invalidate cache when processing completes
5. Show partial outputs (some steps failed)

**Dependencies**: OutputsManager, LibraryManager

**Not Documented**: Plan doesn't address output discovery

---

#### Missing Phase 3: Inspector Coordination ❌
**Objective**: Coordinate preview and inspector (adjust) panes

**Tasks Should Include**:
1. Show metadata for previewed item in inspector
2. Allow editing step parameters from inspector
3. Re-run processing when parameters change
4. Keep preview and inspector in sync

**Dependencies**: InspectorWindow, AdjustView, MetadataViewer

**Current State**:
- InspectorWindow exists (`src/fichero/windows/inspector/inspector_window.py`)
- AdjustView exists (`src/fichero/windows/main/views/adjust/adjust_view.py`)
- Coordination is UNCLEAR

**Not Documented**: Plan doesn't address inspector integration

---

#### Missing Phase 4: Process Button Integration ❌
**Objective**: Add "Process" button to toolbar that processes selected item

**Requirements Mentioned**:
- User selects item
- Clicks "Process" in toolbar
- Preview shows processing progress
- Preview updates when complete

**Tasks Should Include**:
1. Add Process command to PreviewView
2. Get selected item from SelectionManager
3. Show processing dialog with plan selection
4. Monitor Director task progress
5. Auto-refresh preview when processing completes
6. Handle processing errors

**Current State**:
- CollectionView has process workflow (Phase 4 complete)
- PreviewView does NOT have process button
- Toolbar has "Process" but it's defined in CollectionView

**Not Documented**: Plan doesn't address process button in preview context

---

### Missing Plan Section 4: Event Flow Diagrams

**Expected**: Visual diagrams showing:
- Selection → Preview load flow
- Process → Preview update flow
- Inspector → Preview interaction
- Mobile navigation flow

**Actual**: NO diagrams exist

**Impact**: MEDIUM-HIGH - Team members will have different mental models without shared diagrams

---

### Missing Plan Section 5: State Management

**Expected**: Clear documentation of:
- Who owns preview state (what item is shown)?
- Who owns step state (which step is selected)?
- Who owns layout state (split configuration)?
- How state persists across app restarts?

**Current State** (from code):
- StepManager owns step navigation state ✅
- LayoutManager owns split layout state ✅
- PreviewView owns... what exactly? ❌

**Gap**: Plan should define state ownership boundaries

---

### Missing Plan Section 6: Testing Strategy

**Expected**: Comprehensive testing approach:
- Unit tests for each component
- Integration tests for event flows
- UI tests for user workflows
- Performance tests for large outputs
- Mobile-specific tests

**Actual**: Phase 4 test report exists, but NO preview integration tests planned

**Gap**: Plan should include test strategy and acceptance criteria

---

## Strengths of Existing Work

Despite missing comprehensive plan, the codebase has solid foundations:

### Strength 1: Modular Architecture ✅
**Evidence**:
- StepManager: Clean separation of step navigation logic
- LayoutManager: Clean separation of layout logic
- OutputPane: Reusable pane component

**Quality**: EXCELLENT - Manager pattern is well-implemented

---

### Strength 2: Event-Driven Integration ✅
**Evidence**:
```python
# NavigationEventBus used for decoupling
emit_navigation('show_preview', {'item_id': ...})
subscribe_to_navigation('show_preview', handler)
```

**Quality**: GOOD - Loose coupling enables flexibility

**But**: Plan should document WHY event-driven was chosen vs alternatives

---

### Strength 3: Selection Tracking (Phases 1-4 Complete) ✅
**Evidence**:
- SelectionManager working
- Multi-selection supported
- StatusBar integration
- Phase 4 test report shows comprehensive testing

**Quality**: EXCELLENT - Foundation is solid

---

### Strength 4: Mobile-Desktop Separation ✅
**Evidence**:
```python
if self.is_mobile:
    self._create_mobile_layout()
else:
    self._create_desktop_layout()
```

**Quality**: GOOD - Platform differences handled explicitly

**But**: Plan should document mobile preview UX in detail

---

## Weaknesses and Risks

### Critical Weakness 1: No Integration Plan ❌
**Issue**: Tactical fixes (focus system) are NOT a strategic integration plan

**Risk**: **HIGH** - Team will discover integration issues during implementation

**Recommendation**: Create comprehensive integration plan BEFORE implementing preview features

---

### Critical Weakness 2: Unclear Component Boundaries ❌
**Issue**: PreviewContent vs PreviewView - which does what?

**Risk**: MEDIUM - Duplicate functionality or missed features

**Evidence**:
- PreviewContent has edit buttons
- PreviewView has crop/rotate/zoom tools
- Both have step navigation
- Unclear which should own each feature

**Recommendation**: Define clear component responsibilities

---

### Critical Weakness 3: Missing Output Discovery Strategy ❌
**Issue**: How does preview know where to find outputs?

**Current Approach** (inferred from code):
1. Get item from LibraryManager
2. Extract item path
3. Look for `.fichero_processing/` subfolder
4. Scan for manifest.json files

**Risks**:
- What if `.fichero_processing/` is in parent folder?
- What if multiple processing runs exist?
- What if manifest is corrupted?
- Performance: Filesystem scanning on every load?

**Recommendation**: Document output discovery strategy with edge case handling

---

### Critical Weakness 4: No Mobile Navigation Documentation ❌
**Issue**: Mobile preview workflow unclear

**Questions**:
- How does user navigate back from preview?
- What if user processes item while previewing?
- Does preview refresh on return to view?
- What about preview state preservation?

**Risk**: MEDIUM - Mobile UX may be confusing or broken

**Recommendation**: Document complete mobile user journey

---

### Critical Weakness 5: Inspector Integration Unclear ❌
**Issue**: How do preview and inspector (adjust) panes coordinate?

**Current State**:
- Both MainWindow and PreviewView reference inspector
- Unclear who controls inspector visibility
- Unclear how inspector gets preview state

**From Code**:
```python
# main_window.py line 70
'inspector': False  # Controlled by layout_manager

# preview_view.py line 115
self.inspector_visible = False  # Also tracking visibility
```

**Conflict**: Two sources of truth for inspector visibility!

**Risk**: MEDIUM - State synchronization bugs

**Recommendation**: Clarify inspector ownership and state management

---

## Missing Critical Questions

These questions MUST be answered in the integration plan:

### Question 1: Hybrid Event-Driven + Direct Loading ❓
**Plan Proposal**: "Hybrid event-driven + direct loading"

**Missing Analysis**:
- What does "hybrid" mean exactly?
- When to use events vs direct calls?
- What are the benefits/drawbacks of each?
- Could this lead to confusion or bugs?

**Recommendation**: Either commit to event-driven OR direct calls, not both. Document rationale.

---

### Question 2: MainWindow vs PreviewView Inspector ❓
**Observation**: MainWindow has inspector panel, PreviewView references inspector

**Missing Clarification**:
- Who owns the inspector UI component?
- Who controls visibility toggles?
- Who populates inspector content?
- How does PreviewView → Inspector communication work?

**Current Code Conflict**:
```python
# main_window.py - Creates inspector in Adjust column
# preview_view.py line 115 - Also tracks inspector_visible

# Who is source of truth?
```

**Recommendation**: Define clear ownership hierarchy

---

### Question 3: Adjust View Integration ❓
**Mentioned in Requirements**: "Adjust view mentioned in requirements"

**Missing from Plan**: Complete absence of Adjust view discussion

**Questions**:
- What IS the Adjust view?
- Is it same as Inspector?
- What features does it provide?
- How does it integrate with preview?

**From Code** (`adjust_view.py`):
- JSON editor for step parameters
- Toolbar with rotate/crop/zoom buttons
- Calls PreviewView methods

**Missing Documentation**: Complete Adjust view integration strategy

**Recommendation**: Document Adjust view clearly, including:
- Relationship to Inspector
- Relationship to PreviewView
- Feature ownership (who has crop button?)

---

### Question 4: Library Sidebar List Integration ❓
**Plan Mentions**: "Library sidebar list selections"

**Missing Details**:
- When user selects collection in library sidebar, what happens?
- Does preview clear?
- Does preview show collection-level view?
- Or does nothing happen until item selected?

**Recommendation**: Document library-level selection behavior

---

### Question 5: Performance - Rapid Scrolling ❓
**Missing Analysis**: "Loading on every selection change - performance implications?"

**Scenario**: User rapidly scrolls through collection (arrow key down held)

**Current Behavior** (inferred):
- SelectionManager fires event on EVERY selection change
- PreviewView subscribes to events
- Preview loads on EVERY event
- Could trigger 50+ loads/second

**Missing from Plan**:
- Debouncing strategy
- Cancel previous load when new selection made
- Loading indicator during rapid changes
- Cache previous previews

**Recommendation**: Add performance section with debouncing/caching strategy

---

### Question 6: Concurrent Edits ❓
**Scenario**: User has item open in Preview AND external app

**Questions**:
- Does preview detect external changes?
- Does preview reload automatically?
- What if user edited in preview AND external app?
- How are conflicts resolved?

**Missing from Plan**: Complete absence of concurrent edit handling

**Recommendation**: Document conflict resolution strategy (or explicitly state "not supported")

---

### Question 7: Process Button Location ❓
**Requirements**: "Process button integration"

**Confusion**:
- CollectionView has Process commands
- PreviewView should have Process button too?
- Or are they same button?
- Where does it appear in toolbar?

**Missing**: Clear button placement and ownership

**Recommendation**: Document which views have Process button and what it does in each context

---

### Question 8: Timeline Realism ❓
**Plan Estimate**: "13 days"

**Concerns**:
- Phase 4 multi-selection took ~4 days (simpler scope)
- Preview integration touches MORE components:
  - PreviewView, PreviewContent, MainWindow
  - SelectionManager, NavigationController
  - OutputsManager, LibraryManager
  - InspectorWindow, AdjustView
- Mobile-specific testing
- Cross-component integration testing

**Missing**: Realistic time estimates with buffer for unknowns

**Recommendation**: Re-estimate with 50% buffer, expect 20-25 days not 13

---

## Recommendations

### Immediate Actions (Before Implementation)

#### 1. Create Comprehensive Integration Plan ⚠️ CRITICAL
**Priority**: **URGENT**

**Contents Required**:
1. **Requirements Section**:
   - User stories for all preview workflows
   - Mobile vs Desktop UX differences
   - Performance requirements
   - Integration constraints

2. **Architecture Section**:
   - Component diagram showing all integrations
   - Event flow diagrams
   - State management boundaries
   - Cache strategies

3. **Implementation Phases** (suggested 6 phases):
   - Phase 1: SelectionManager → Preview Loading
   - Phase 2: OutputsManager Integration & Discovery
   - Phase 3: Inspector/Adjust Pane Coordination
   - Phase 4: Process Button & Director Integration
   - Phase 5: Mobile Navigation & UX
   - Phase 6: Performance & Polish (debouncing, caching)

4. **Testing Strategy**:
   - Unit tests per component
   - Integration tests per phase
   - Mobile-specific tests
   - Performance benchmarks

5. **Risk Mitigation**:
   - Identify risks per phase
   - Mitigation strategies
   - Rollback plans

**Deliverable**: `PREVIEW_INTEGRATION_PLAN.md` (30-50 pages, comprehensive)

---

#### 2. Clarify Component Responsibilities ⚠️ HIGH PRIORITY

**Action**: Create component responsibility matrix

| Component | Owns What | Integrates With |
|-----------|-----------|----------------|
| PreviewView | Multi-pane layout, tool commands | StepManager, LayoutManager, SelectionManager |
| PreviewContent | Single file preview, basic editing | OutputsManager, EditorRegistry |
| StepManager | Step navigation state | OutputsManager, LibraryManager |
| LayoutManager | Split pane layouts | OutputPane, renderer system |
| OutputPane | Individual pane rendering | WebView, PathBar |
| AdjustView | Parameter editing, toolbar | PreviewView (method calls) |
| InspectorWindow | Metadata viewer (desktop) | PreviewView, LibraryManager |

**Question to Resolve**: Should PreviewView USE PreviewContent or replace it?

**Recommendation**: Either:
- **Option A**: PreviewView delegates to PreviewContent for single-pane rendering
- **Option B**: Merge PreviewContent into OutputPane, deprecate PreviewContent

**Deliverable**: Component architecture diagram with clear boundaries

---

#### 3. Document Output Discovery Strategy ⚠️ HIGH PRIORITY

**Action**: Create detailed output discovery specification

**Topics to Cover**:
1. **Primary Strategy**: Use metadata `['output_path']` or filesystem scan?
2. **Fallback Strategy**: What if primary method fails?
3. **Edge Cases**:
   - Missing output folder
   - Multiple output folders
   - Corrupted manifests
   - Partial processing (some steps complete)
4. **Performance**:
   - Cache manifest contents
   - Invalidate cache on processing complete
   - Debounce rapid reloads
5. **Error Handling**:
   - Show "Processing not started" placeholder
   - Show "Processing failed" with error details
   - Allow re-processing from preview

**Deliverable**: `OUTPUT_DISCOVERY_SPEC.md` (8-10 pages)

---

#### 4. Define Event vs Direct Call Strategy ⚠️ MEDIUM PRIORITY

**Action**: Document when to use events vs direct method calls

**Proposed Strategy**:

**Use Events When**:
- Cross-component communication (CollectionView → PreviewView)
- One-to-many broadcasting (selection change → multiple listeners)
- Loose coupling desired (components don't know about each other)

**Use Direct Calls When**:
- Parent-child relationships (PreviewView → StepManager)
- Synchronous operations (get current state)
- Performance critical (avoid event overhead)

**Example**:
```python
# EVENT: Collection → Preview (loose coupling)
emit_navigation('show_preview', {'item_id': ...})

# DIRECT: PreviewView → StepManager (tight coupling)
self.step_manager.load_item(item_id)
```

**Deliverable**: Add section to integration plan: "Communication Patterns"

---

#### 5. Document Mobile Navigation Flow ⚠️ MEDIUM PRIORITY

**Action**: Create mobile user journey documentation

**Scenarios to Document**:

1. **Preview from Collection**:
   - User: Tap item in CollectionView
   - System: Push PreviewView onto navigation stack
   - PreviewView: Full-screen, single pane
   - User: Tap back button
   - System: Pop PreviewView, return to CollectionView
   - State: CollectionView preserves scroll position

2. **Process from Preview**:
   - User: In PreviewView, tap Process button
   - System: Show process dialog (plan selection)
   - User: Select plan, confirm
   - System: Start processing, show progress
   - PreviewView: Updates live as steps complete
   - User: Tap back when done
   - System: Return to CollectionView with updated status

3. **Edit from Preview**:
   - User: Tap Edit button in preview
   - System: Open external app
   - User: Make changes, save
   - System: Return to Fichero
   - PreviewView: Detects changes, reloads preview

**Deliverable**: Mobile UX flow diagrams (Figma or Mermaid)

---

### Implementation Strategy Recommendations

#### Recommendation 1: Start with Read-Only Preview
**Rationale**: Reduce complexity for initial integration

**Phase 1 Scope** (reduced):
- Load preview when item selected ✅
- Display processing steps ✅
- Navigate between steps ✅
- NO editing (defer to Phase 4)
- NO processing (defer to Phase 4)

**Benefits**:
- Faster delivery of core value
- Simpler integration testing
- Lower risk of breaking existing features

---

#### Recommendation 2: Commit to Event-Driven Architecture
**Rationale**: Consistency, testability, loose coupling

**Pattern**:
```python
# All cross-view communication uses events
emit_navigation('show_preview', {'item_id': ...})
emit_navigation('update_preview', {'item_id': ...})
emit_navigation('close_preview', {})

# Within-view communication uses direct calls
self.step_manager.load_item(item_id)
self.layout_manager.split_vertical()
```

**Benefits**:
- Predictable patterns
- Easy to test (mock event bus)
- Easy to add new listeners

**Drawbacks**:
- Slight performance overhead
- Less obvious code flow (have to search for subscribers)

**Verdict**: Benefits outweigh drawbacks for this use case

---

#### Recommendation 3: Use Metadata for Output Discovery
**Rationale**: Performance, reliability

**Strategy**:
```python
# Store output_path in item metadata when processing starts
item['metadata']['output_path'] = str(output_folder)

# Preview uses metadata to find outputs
output_path = item.get('metadata', {}).get('output_path')
if output_path and Path(output_path).exists():
    outputs = OutputsManager.load_from_path(output_path)
else:
    # Fallback: scan for .fichero_processing folders
    outputs = OutputsManager.discover_outputs(item_path)
```

**Benefits**:
- Fast (no filesystem scanning)
- Reliable (direct path lookup)
- Supports multiple processing runs (use timestamp in path)

**Implementation**:
- Update Director to write output_path to metadata
- Update PreviewView to read from metadata first
- Fallback to discovery for legacy items

---

#### Recommendation 4: Defer Inspector Integration to Phase 3
**Rationale**: Reduce initial complexity

**Phase 1-2**: Preview works standalone
**Phase 3**: Add inspector coordination

**Why Defer**:
- Inspector ownership unclear (MainWindow vs PreviewView)
- Inspector implementation incomplete (AdjustView is placeholder)
- Preview has value without inspector
- Can ship Phase 1-2 to users without inspector

**Phase 3 Scope** (when ready):
- Clarify inspector ownership
- Implement metadata display
- Implement parameter editing
- Implement preview ↔ inspector sync

---

#### Recommendation 5: Add Debouncing for Rapid Selection
**Rationale**: Performance

**Implementation**:
```python
# preview_view.py
def __init__(self, ...):
    self._load_debounce_task = None

async def _on_show_preview_event(self, data):
    # Cancel previous load
    if self._load_debounce_task:
        self._load_debounce_task.cancel()

    # Debounce: wait 150ms before loading
    self._load_debounce_task = asyncio.create_task(
        self._debounced_load(data['item_id'])
    )

async def _debounced_load(self, item_id):
    await asyncio.sleep(0.15)  # 150ms debounce
    await self._load_output_async(item_id)
```

**Benefits**:
- Prevents loading 50 previews when user scrolls rapidly
- Improves perceived performance
- Reduces filesystem I/O

---

## Risk Analysis

### Additional Risks Not in Original Plan

#### Risk 1: State Synchronization Bugs
**Scenario**: Preview shows Item A, SelectionManager has Item B selected

**Causes**:
- Event race conditions
- Failed loads (preview stays on old item)
- User actions while loading

**Mitigation**:
- Defensive checks: "Is current preview == current selection?"
- Show loading states clearly
- Allow manual refresh

**Severity**: MEDIUM

---

#### Risk 2: Memory Leaks from Event Subscriptions
**Scenario**: PreviewView instances created/destroyed but event subscriptions remain

**Causes**:
```python
# Common mistake:
subscribe_to_navigation('show_preview', self._handler)
# If PreviewView is destroyed without unsubscribing, _handler keeps reference
```

**Mitigation**:
```python
def on_close(self):
    unsubscribe_from_navigation('show_preview', self._handler)
```

**Severity**: LOW (but common bug in event-driven systems)

---

#### Risk 3: Platform-Specific Bugs (Mobile)
**Scenario**: Feature works on desktop but breaks on mobile

**Causes**:
- Different view lifecycle on mobile
- Different gesture handling
- Different toolbar layout

**Mitigation**:
- Test EVERY feature on mobile
- Add mobile-specific unit tests
- Use is_mobile flag defensively

**Severity**: MEDIUM (has happened before with toolbar issues)

---

#### Risk 4: Performance Degradation with Large Collections
**Scenario**: Collection has 1000 items, user scrolls through

**Causes**:
- No debouncing → 1000 loads triggered
- No caching → every load scans filesystem
- No cleanup → memory usage grows

**Mitigation**:
- Implement debouncing (see Recommendation 5)
- Cache manifests (LRU cache, max 50 items)
- Cleanup old OutputPane instances

**Severity**: MEDIUM-HIGH (affects usability)

---

## Conclusion

### Summary of Findings

**What's Good**:
- ✅ Solid foundation (SelectionManager, NavigationController, modular PreviewView)
- ✅ Clean architecture (Manager pattern, event-driven)
- ✅ Mobile-desktop separation
- ✅ Existing focus system (tactical fixes)

**What's Missing (CRITICAL)**:
- ❌ NO comprehensive integration plan
- ❌ Unclear component boundaries (PreviewContent vs PreviewView)
- ❌ Undocumented output discovery strategy
- ❌ Missing mobile navigation documentation
- ❌ Unclear inspector/adjust integration
- ❌ No performance considerations (debouncing, caching)
- ❌ No concurrent edit handling
- ❌ Incomplete testing strategy

**What's Risky**:
- ⚠️ Timeline too optimistic (13 days → 20-25 days realistic)
- ⚠️ Hybrid event/direct approach (should commit to one)
- ⚠️ State synchronization bugs (multiple sources of truth)
- ⚠️ Platform-specific bugs (mobile testing critical)

---

### Recommendation: **DO NOT PROCEED WITH IMPLEMENTATION**

**Rationale**:
1. **No comprehensive plan exists** - Current documents address only focus system
2. **Too many unanswered questions** - 10+ critical questions identified
3. **Integration points unclear** - Component boundaries need clarification
4. **High risk of rework** - Discovering issues during implementation = wasted time

**Required Before Implementation**:
1. ✅ Complete comprehensive integration plan (30-50 pages)
2. ✅ Create component responsibility matrix
3. ✅ Document output discovery strategy
4. ✅ Document mobile navigation flow
5. ✅ Clarify inspector/adjust ownership
6. ✅ Define event vs direct call patterns
7. ✅ Add performance considerations (debouncing, caching)
8. ✅ Create testing strategy per phase

**Estimated Time to Create Plan**: **3-5 days** (worth the investment to avoid 10+ days of rework)

---

### Next Steps

#### Immediate (This Week)
1. **Create Requirements Document**
   - User stories
   - Integration constraints
   - Performance requirements

2. **Document Current State**
   - Component inventory
   - Integration points (what exists today)
   - Known issues

3. **Design Architecture**
   - Component diagrams
   - Event flow diagrams
   - State management design

#### Next Week
4. **Write Integration Plan**
   - 6 phases with clear objectives
   - Dependencies per phase
   - Testing strategy per phase
   - Risk mitigation per phase

5. **Review with Team**
   - Technical review
   - UX review
   - Risk review

6. **Finalize Plan**
   - Incorporate feedback
   - Get sign-off
   - Begin implementation

---

### Confidence Level: **20% (Very Low)**

**Why Low Confidence**:
- Plan does not exist (reviewing a hypothetical)
- Many unknowns uncovered during analysis
- Integration complexity high
- Mobile testing burden significant
- Timeline likely underestimated

**What Would Increase Confidence**:
- ✅ Comprehensive integration plan created
- ✅ Component boundaries clarified
- ✅ Mobile UX documented
- ✅ Performance strategy defined
- ✅ Testing strategy comprehensive
- ✅ Team review and sign-off

**Target Confidence**: **85%+ after comprehensive planning**

---

**Status**: **PLAN REJECTED - COMPREHENSIVE REVISION REQUIRED**

**Sign-off**: Plan Review Agent
**Date**: 2025-11-15

---

**END OF REVIEW**
