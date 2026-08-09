# Sidebar and toolbars review (2026-08-09)

Read-only review for Daniel, third in the set. `file:line` for every mechanism;
inferences marked. Paths relative to `fichero/fichero/`.

**Short version: the sidebar is in good shape** — the expensive things
(per-row forest copies, eager context menus) were found and fixed today, and the
fixes are real. What is left is one open bug with a known mechanism, two
conditions that cannot vary, and one genuine keyboard collision.

---

## Confirmed and worth fixing

### S1. #4568 — the stuck drop highlight, with its mechanism

`isDropTargeted` (`Views/Sidebar/ItemRow/SidebarItemRow.swift:77`) is cleared in
exactly three places: `dropExited`
(`ItemRow/LibraryItemDropDelegate.swift:116-118`), `performDrop` (`:135`), and on
commit in the handler (`ItemRow/SidebarItemRow+Drop.swift:31`).

All three require the drag to *end somewhere this row can see*. The code already
names the hole it leaves — `SidebarItemRow+Drop.swift:25-30`: *"If the row
rebuilds mid-drag (tree reload) SwiftUI can drop the trailing
`isTargeted=false`, leaving the accent wash stuck on."*

So: hover a folder, its children arrive and rebuild the row, move away — the
delegate that owed you the `false` no longer exists, and the wash stays. A drag
cancelled with Esc, or released outside the window, reaches no row either.

The current mitigation (clear on commit) only helps the case where the user
completes a drop *on that same row*. **There is no drag-session-ended reset and
no timeout**, which is why the bug is open rather than fixed.

**Suggested shape:** the reset needs an owner that outlives the row. A single
window-scoped "a drag is in progress" flag that every row's highlight reads,
cleared once when the session ends, replaces N per-row resets that can each be
missed. Rows would then have no stuck state to get stuck in — the highlight
becomes derived rather than stored. Offered as a direction, not a design; the
code lane owns it.

### S2. "New Workflow" is disabled exactly when it would work

`Views/Sidebar/Sections/SidebarBottomToolbar.swift:192` gates the button with
`.disabled(!hasSelection)` (mirrored in the overflow menu at `:221-228`).

`createNewWorkflow()` (`Views/Sidebar/Components/SidebarCreationHandlers.swift:70-91`)
takes no selection input at all — it creates the workflow in
`libraryManager.globalLibrary` and hard-codes `folderPath: "/"`.

So the button requires a selection it never reads, and is dead in the most
natural state to press it: nothing selected, wanting a new workflow. Finder's
"New X" commands never require a selection. **INFERRED**: that
`itemRegistry.createWorkflow?()` routes to `createNewWorkflow()` — I did not
trace the registry binding, though both halves of the mismatch are clear
independently. Cheap fix: drop the `.disabled`.

### T1. ⌘⌥F is claimed twice, by two unrelated live actions

- `Views/Shell/ContentView/Layout/ContentView+RootLayout.swift:88-91` — a hidden
  zero-opacity `Button("Enter Full-Screen Reading")` with
  `.keyboardShortcut("f", modifiers: [.command, .option])`, disabled only when
  `immersiveReadingDocument == nil`.
- `App/Menus/ViewMenuPaneSections.swift:211` — `ShowFindBarButton`, the same
  `("f", [.command, .option])`, included unconditionally in the View menu
  (`App/Menus/ViewMenuCommands.swift:98`).

Whenever a document is open, both are enabled simultaneously and which one wins
is a matter of menu ordering rather than intent. This is **not** the same as the
deliberate ⌘' mirroring between the toolbar and the View menu — those two route
to the *same* action and say so
(`App/Menus/FocusedCommandButtons+UndoNavigation.swift:21-23`). Here two
different features want the same chord.

Needs your ruling on which keeps ⌘⌥F. Finder and most Mac apps use ⌘F for find
and leave ⌥⌘F to the app; "Find in Artifact" arguably has the weaker claim since
it is already reachable from the View menu by name.

---

## The pattern, part two: conditions that cannot vary

The library-views review named today's habit as *rules written where they cannot
fire* — a `Set.first` prohibition living in a comment, a guardrail whose host
list held one entry. The sidebar and toolbar code shows the sibling form: **code
shaped like a decision that cannot decide.**

- `shouldShowBottomToolbar` (`Views/Sidebar/Sections/SidebarView+ViewComponents.swift:38-40`)
  returns `true`, unconditionally. It reads as a policy hook; it is a constant.
  (You have already said you want this bar gone or library-scoped, and #3404 is
  filed — so the constant is also the wrong answer.)
- `showInspectorToggle` (`Views/Shell/ContentView/ContentView+StateSelection.swift:75-77`)
  returns `true`, unconditionally — and it is used to wrap a **`ToolbarItem`
  itself** in an `if` at `Layout/ContentView+InspectorContainer.swift:47` and
  `:64`.

That second one deserves attention, because the project states the opposing rule
as load-bearing. `Views/Shell/Toolbar/EngineStatusToolbarItem.swift:31-35`:

> The `ToolbarItem` that hosts this view is declared unconditionally […] Never
> gate the `ToolbarItem` itself on phase: doing so re-triggers NSToolbar's
> first-layout insert path and risks the #3163 double-insert crash.

`StatusIslandToolbarItem.swift:16-17` repeats it. The inspector toggle breaks it
— and is saved *only* by the accident that its condition is a hardcoded `true`.

**So it is not a live crash; it is a loaded one.** The day anyone gives
`showInspectorToggle` a real implementation — which its name invites, and which
the neighbouring `showViewModePicker` (`:81-87`) actually has — the #3163
double-insert path comes back. Marking **CONFIRMED as a latent trap, not a live
bug**, since I verified the condition is constant.

The remedy is the same one that worked for the guardrails: make the rule
enforceable. A check that no `ToolbarItem(id:)` is declared inside a conditional
would have caught this, and would keep catching it. Both of these constants
would also be caught by a much cruder rule — *a `Bool` property whose body is
`true`* — which is worth considering on its own, since two of them turned up in
one evening in two unrelated files.

---

## Confirmed healthy — the things I expected to find broken

Recording these so nobody re-audits them:

- **Row weight (#4545) is genuinely fixed.** `SidebarItemRow`
  (`ItemRow/SidebarItemRow.swift:41-49`) stores `item` plus a
  `lookupItem: (String) -> SidebarItem?` closure. The whole-forest
  `allCachedItems` array is gone, backed now by the O(1) `cachedItemIndex`
  (`Views/Sidebar/SidebarView.swift:67`). This was the largest slice in the
  earlier profile; the fix landed.
- **Context menus are deferred.** `SidebarDeferredMenuContent`
  (`ItemRow/SidebarDeferredMenuContent.swift`), applied at
  `ItemRow/SidebarItemRow+Presentation+Body.swift:161, 195, 205`. This is the
  506-sample item from the Time Profiler, and it is the pattern the *library*
  views still need (per the companion review).
- **`Set.first` in the sidebar is deliberate and correct.**
  `Views/Sidebar/State/SidebarStateManagers.swift:189, 195` — for a
  single-element set `.first` is unambiguous, and the multi-selection fallback
  says why any selected row is a valid route. This is *not* an instance of the
  library's hash-order defect; the sidebar routes, it does not preview.
- **Structural rows can't be renamed or deleted.**
  `ItemRow/SidebarItemContextMenu.swift:186, 204`, with a comment (`:176-185`)
  recording that Rename used to be silently enabled-but-broken for them. Correct
  Finder parity, and a good example of the "errors must say why" rule being
  applied.
- **Option-click expands the whole subtree**, Finder-style
  (`ItemRow/SidebarItemRow.swift:193-204`).
- **The pane toggles encode the ≥1-visible-pane invariant** in their enabled
  state (`Views/Library/LibraryToolbarPolicy.swift:15-58`) — the equivalent of
  Finder refusing to hide the last column. Well modelled.
- **Toolbar items are customizable.** Every `ToolbarItem` carries an `id:`
  except the pane-toggle `ToolbarItemGroup`
  (`Views/Shell/ContentView/ContentView+Toolbar.swift:131-149`), which
  structurally cannot have one — and the comment (`:127-130`) says so and treats
  the three as one unit deliberately.

---

## Smaller notes

- **Rename fails silently.** `ItemRow/SidebarItemRow+Rename.swift:18-26`
  validates empty and over-long names and then just cancels, reverting the row
  with no message. Finder shows *"The name … can't be used."* This is the
  "errors must say why" rule unmet — small, but it is the same class as the
  structural-row fix two files away that was explicitly celebrated for removing
  a silent no-op. **INFERRED** that no error path exists elsewhere; I found none.
- **`containerActivity` recomputes per row per render.**
  `ItemRow/SidebarItemRow.swift:143-163` calls `store.childActivityCounts(of:)`
  for every container row on every render, with no visible memoisation.
  **INFERRED** as a cost worth measuring on a large tree; the sampler would
  settle it, and I cannot run it.
- **Toolbar environment reads look safe.** `StatusIslandToolbarItem`,
  `EngineStatusToolbarItem` and `ActivityStatusToolbarItem` read `AppState`,
  `WorkflowExecutionObserver` and `ActivityStore`; their `.toolbar` modifiers
  hang off `navigationSplitColumn` and `detailColumn`
  (`Layout/ContentView+RootLayout.swift:275, 140`), inside ContentView's tree, so
  the environment flows. No crash site found. **INFERRED residual risk**: the
  macOS *Customize Toolbar* palette can instantiate item content outside the
  normal hierarchy, which is exactly the hosting boundary that produced three
  crashes last night. Worth one manual test — right-click the toolbar, choose
  Customize Toolbar, and drag the status island around.

---

---

# Addendum — three questions added after the first pass

## A. The status island against #4536

Daniel wants separate indicators: backend connection, remote connections,
agent/MCP/test/other sessions, and activity.

What exists today (`Views/Shell/Toolbar/StatusIslandToolbarItem.swift:31-70`):
`[EngineStatusToolbarItem] [message area] [ActivityStatusToolbarItem]` — so
**two of the four**, backend connection and activity, plus an import-progress
message that is genuinely good (real counts and a Cancel, #4203/#4235).

The other two are not a layout problem. **The data does not exist to render
them:**

- Searched the Swift side for `activeSessions`, `connectedClients`,
  `remoteConnections`, `sessionCount`, `mcpSession` — **no hits at all**.
- The engine does expose `GET /api/auth/sessions`
  (`fichero-server/src/fichero_server/api/routes/auth/accounts.py:596`),
  returning `SessionResponse{id, user, device_label, created, last_seen}`
  (`:94-104`), with a revoke sibling at `:629`.

So "who is connected" is answerable *today* — by user and device label. What is
**not** answerable is the part Daniel actually asked for: there is no `kind` on
a session, so agent / MCP / test / human cannot be distinguished, and there is
no remote-connection concept separate from a session.

**This reframes #4536 from a toolbar task into a backend-then-toolbar task.** In
rough order: add a client-kind to the session record and surface it on
`/api/auth/sessions`; then the island can carry a third indicator whose popover
lists sessions by kind, reusing the revoke that already exists. Worth saying
before someone tries to build four indicators over two data sources and invents
the missing two.

*Inferred:* that `device_label` is not already being used as a de-facto kind
marker (e.g. clients writing "mcp" into it). I did not read the clients that
create sessions.

## B. `.searchable` duplication — enforced by construction, but not guarded

This is in better shape than the history suggests. There is exactly **one**
`.searchable(` call in the entire app —
`Views/Components/MiniToolbar.swift:250` — and it sits inside
`conditionalSearchable(text:placement:prompt:isActive:)` (`:238-254`), which
applies it only when `isActive`. The policy behind `isActive` is a single
predicate, `ToolbarSearchRegistration.shouldRegister(isSecondarySplitPane:)`
(`Views/Components/SplittablePane.swift:57-61`), fed by an environment key
(`:33-46`) that marks every non-primary split-pane copy.

That is the right shape: one call site, one predicate, one testable rule. The
duplicate-identifier crash cannot happen from the current code.

**The gap is that nothing stops the next one.** The rule lives in doc comments
(`SplittablePane.swift:29-32`, `:48-56`) and in the fact that everyone has so
far used the helper. A new mode view writing `.searchable(placement: .toolbar)`
directly compiles, ships, and crashes the toolbar subsystem in a split pane.

This is the *fireable* version of today's pattern, and it is cheap: a
`check_*.py` that fails on any raw `.searchable(` outside
`conditionalSearchable`'s own definition. One rule, one fixture, and the
invariant stops depending on everyone remembering. **Ready to fix**, and I have
added it to the cross-cutting list.

## C. Is the sidebar coherent as a whole?

Tonight put a lot of individually-correct changes into one surface — hover wash
and name tooltip removed on Daniel's direction, native selection material, the
full-row drop platter, per-row tap fallback deleted, AnyView erasure at two
levels. Read as a whole rather than as a changelog:

**It hangs together, and the direction is consistent.** Every one of those
changes moves the same way — *stop drawing our own thing, let the platform draw
it.* The selection platter is the native source-list material
(`bc36d39bd`), the drop target is the full row like Finder's
(`be75fa424`), the removed hover wash was a custom affordance AppKit does not
have, and deleting the per-row tap fallback (`22424f614`) handed clicks back to
the native `List`. That is one idea applied five times, not five ideas.

Two places where the whole is now less coherent than the parts:

1. **The sidebar went native while the library did not.** The sidebar now draws
   Finder's grey; list and columns modes still draw the custom Mail-style fill,
   and Table draws AppKit's own (companion review, G1). So the *same window*
   now shows three selection languages, and tonight's work is what widened the
   gap — correctly, but it makes settling G1 more urgent rather than less. If
   the answer is "native everywhere", the sidebar has already shown what that
   looks like and the library should follow it.

2. **The bottom bar is now the least-Finder-like thing in the column.** With the
   rows quieted down — no hover wash, no tooltip, native platter — an
   always-present bar of six controls (`SidebarBottomToolbar.swift:104-195`) is
   the loudest remaining element, and Finder has nothing equivalent. It is also
   the one piece still hardcoded on (`shouldShowBottomToolbar`, §pattern above)
   while #3404 says it should go or be scoped. The visual case for resolving
   #3404 is stronger after tonight than before it.

Neither is a regression. Both are "the surface improved enough to expose what
had been hiding behind the noise", which is a good position to be in.

## Summary for triage

**Cheap and certain:**
- S2 — delete `.disabled(!hasSelection)` on New Workflow (`SidebarBottomToolbar.swift:192` and `:221-228`)
- Rename should say why it refused a name

**Needs your ruling:**
- T1 — who keeps ⌘⌥F, immersive reading or Find in Artifact?
- `shouldShowBottomToolbar` is hardcoded `true` while #3404 says the bar should go or be library-scoped — one decision, already yours to make

**Real work:**
- S1 — #4568 needs an owner for the drag session that outlives the row; the per-row reset cannot be made reliable
- Unwrap the conditional `ToolbarItem` (`InspectorContainer.swift:47, 64`) before someone gives `showInspectorToggle` a body, and consider a guardrail forbidding a `ToolbarItem(id:)` inside a conditional

**Worth measuring, not guessing:**
- `containerActivity` per-row recomputation
- The Customize Toolbar palette against the status island
