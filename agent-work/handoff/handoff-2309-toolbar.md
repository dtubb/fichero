# Codex-in-Xcode prompt — #2309 toolbar chrome cleanup

Paste the block below into codex inside Xcode. It's fiddly visual `.principal`
placement + an icon swap — best done with the live canvas in front of you.

---

In `fichero/fichero/Views/ContentView.swift`, fix three things in the toolbar (issue #2309), per Daniel's image-#25 feedback. Build on the existing zoned-toolbar structure — do NOT rewrite the toolbar.

**1. Leading zone — make the first button the Xcode "list" navigator button.**
In `leadingToolbarContent` (~line 497) the first button currently shows `toolbarToggleIcon("sidebar.left", isActive: showSidebar && !sidebarShowsChat)` with help "Show Sidebar". It sits to the LEFT of the chat button. Change ONLY its icon and help to read as the list navigator (like Xcode's navigator selector):
- icon: `"list.bullet"` (keep the `isActive: showSidebar && !sidebarShowsChat` argument and the toolbarToggleIcon wrapper)
- `.help("Show List")`
Leave its action (`showSidebar = true; sidebarShowsChat = false`) unchanged. Leave the chat button (`bubble.left.and.bubble.right`) unchanged. Result: leading zone reads **[list] [chat]** — a navigator selector, like Xcode.

**2. Content zone — keep exactly ONE Mail-style hide, on the right of the boundary.**
In `contentToolbarContent` (~line 553) there is a `ToolbarItem(placement: .primaryAction)` with `toolbarToggleIcon("sidebar.left", isActive: showSidebar)` that TOGGLES `showSidebar` (the Mail-style collapse). KEEP this one — it is the single sidebar hide/show. Confirm there is no OTHER `sidebar.left` toggle button left over after step 1 (step 1 turned the leading one into a list button, so this should now be the only `sidebar.left`). If you find a duplicate hide button, remove the redundant one — Daniel said "the first hide/close sidebar has to go."

**3. Center the title over the CONTENT column, not the sidebar.**
The `ToolbarItem(placement: .principal)` at ~line 474 (`Label(toolbarTitle, systemImage: toolbarIcon)`) currently appears centered over the sidebar / whole window. Daniel wants it centered over the **content column** (Xcode-style, where the title sits above the document area, not the navigator). `.principal` on a NavigationSplitView toolbar centers across the wrong span here. Try, in order, whichever gives a content-centered title in the live canvas:
  a. Keep `.principal` but verify it centers over content once the leading zone holds two compact buttons (sometimes the imbalance is what shifts it).
  b. If still off, move the title out of `.principal` and render it as a centered overlay on the detail/content view itself (a `.toolbar`/`.navigationTitle` on the content column, or an `.overlay(alignment: .top)` title strip on the content pane), so it tracks the content column width — not the window.
Pick the approach that visually centers the title over the content area. Keep `toolbarTitle`/`toolbarIcon` as the source values and the `.headline` font + `.titleAndIcon` label style.

**Constraints:** smallest in-place change; semantic fonts; SF Symbols only (no emoji); macOS 15 deployment target (no macOS-26-only toolbar APIs like `ToolbarSpacer(.flexible)`). After it looks right in the canvas, build in Xcode (⌘B) to confirm green, then commit `feat(toolbar): list navigator button + content-centered title, single sidebar hide (#2309)`.
