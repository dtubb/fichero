# TODO-050: Comprehensive Sidebar Improvements Plan

## What to do
Create detailed tasks to fix sidebar contextual menu, inline rename, delete functionality, drag and drop hierarchy, visual improvements, and menu/toolbar integration.

## Steps
- [ ] Step 1: Review human_note.md and create breakdown of all required fixes
- [ ] Step 2: Create individual TODO tasks for each major improvement area
- [ ] Step 3: Update TODO.md with new tasks in proper order
- [ ] Step 4: Review sample_code for SwiftUI best practices
- [ ] Step 5: Ensure SwiftLint compliance is part of each task

## Files
- File to update: ai/TODO.md
- Files to create: ai/tasks/TODO-051/ through TODO-058/ (estimated)

## Questions for Human
- [ ] Question 1: Should these tasks be prioritized as P0 (critical) or P1 (high)?
    Answer: Based on user emphasis on fixing sidebar, treating as P1 (high priority)
- [ ] Question 2: Should menu commands use standard macOS patterns?
    Answer: Yes, use SwiftUI CommandMenu and standard keyboard shortcuts

## Answers and Implementation
- Breaking down sidebar fixes into 8 focused tasks
- Each task will reference sample_code for best practices
- All tasks will require SwiftLint compliance
- Tasks will be sequential where dependencies exist

## Task Breakdown

### TODO-051: Remove "Move to Folder" from Context Menu (P1, Medium)
- Remove unused menu item from sidebar context menu
- Dependencies: None

### TODO-052: Fix Inline Rename to Use SwiftUI Default Pattern (P1, High)
- Implement native SwiftUI inline editing for folder/file rename
- Reference sample_code for text field editing patterns
- Dependencies: None

### TODO-053: Fix Delete Functionality in Sidebar and Backend (P1, High)
- Ensure delete removes items from sidebar UI
- Ensure delete persists to backend API
- Add confirmation dialog
- Dependencies: None

### TODO-054: Fix Drag and Drop Folder Hierarchy (P1, High)
- Fix folders not dropping into other folders (hierarchy issue)
- Implement proper parent-child relationship handling
- Reference sample_code/AdoptingDragAndDropUsingSwiftUI
- Dependencies: None

### TODO-055: Improve Section Title Indentation (P2, Low)
- Increase indentation spacing for better visual hierarchy
- Dependencies: None

### TODO-056: Enable Drop on Search, Chat, and Workflow Sections (P1, Medium)
- Allow files/folders to be dropped on section headers
- Implement appropriate actions for each section
- Dependencies: TODO-054

### TODO-057: Enable Drag from Finder to Ingest Files (P1, High)
- Implement external drag and drop from macOS Finder
- Handle file and folder ingestion
- Reference sample_code/AdoptingDragAndDropUsingSwiftUI
- Dependencies: None

### TODO-058: Add Menu Commands and Toolbar Items (P1, Medium)
- Add macOS menu bar commands for sidebar operations
- Add toolbar items for common actions
- Use CommandMenu and .toolbar modifiers
- Dependencies: None

## Need help?
- Review human_note.md for original requirements
- Check sample_code directory for implementation patterns
- Ensure SwiftLint compliance
