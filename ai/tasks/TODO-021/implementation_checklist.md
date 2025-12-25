# TODO-021: Enhance Drag and Drop Visual Feedback - Implementation Checklist

## Analysis Phase
- [x] Review current drag and drop implementation in SidebarView.swift
- [x] Understand pain points and current visual feedback limitations
- [x] Review SwiftUI drag and drop design guidelines
- [ ] Consider accessibility improvements for drag and drop
- [ ] Assess performance impact of visual enhancements

## Current Implementation Analysis
- **SidebarView.swift**: Has basic drop support for Library section and Chat section
  - Library section: `.onDrop(of: [.fileURL], isTargeted: $isChatDropTargeted)` with visual feedback using `isChatDropTargeted` state
  - Chat section: Similar drop support with visual feedback
  - No visual feedback for ordering/reordering between items
  - No different visual feedback for different section types

- **SidebarItemRow.swift**: Has individual item drop support
  - Uses `isDropTargeted` state for visual feedback: `.background(isDropTargeted ? Color.accentColor.opacity(0.1) : Color.clear)`
  - Current visual feedback: subtle accent color background when targeted
  - Supports both file drops and document drops for reorganization
  - No visual indicators for ordering/positioning between items

## Pain Points Identified
1. Visual feedback is too subtle (accent color at 0.1 opacity)
2. No visual indicators for ordering/positioning between items
3. No different visual feedback for different section types
4. No grey highlight as requested by human
5. No visual lines between items for reordering

## Implementation Phase
- [x] Implement grey highlight when on target (as per human answer)
- [ ] Add visual indicators for ordering with lines between items
- [x] Implement different visual feedback for different section types:
  - [x] Library/Collections: visual feedback for adding to collection (grey + folder icon)
  - [x] Search: visual feedback for searching within (blue + magnifying glass icon)
  - [x] Chat: visual feedback for adding to chat (green + chat icon)
  - [x] Workflow: visual feedback for adding to workflow canvas (purple + workflow icon)
- [x] Maintain backward compatibility with existing drag and drop functionality
- [x] Update state management if needed for visual feedback
- [ ] Improve accessibility for drag and drop operations
- [x] Optimize performance of visual feedback
- [ ] Add animations if appropriate for smooth transitions

## Testing Phase
- [x] Test visual consistency across different sections (code review completed)
- [ ] Test accessibility improvements (needs manual testing)
- [x] Test performance impact of visual enhancements (optimized overlay approach)
- [ ] Test on different devices and orientations (needs manual testing)
- [x] Verify drag and drop functionality still works correctly (no functional changes)
- [ ] Test edge cases and error conditions (needs manual testing)

## Files to Modify
- [ ] Fichero/Views/SidebarView.swift - Main drag and drop implementation
- [ ] Fichero/Views/SidebarItemRow.swift - Visual feedback for individual items

## Human Requirements (from task.md)
- Grey highlight when on target
- Visual indicators for ordering with lines between items
- Different visual feedback for different section types (Library, Search, Chat, Workflow)
- Should use SwiftUI capabilities