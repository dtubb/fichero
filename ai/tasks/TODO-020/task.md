# TODO-020: Review and Improve AI Context Documents Organization

## What to do
Review current context documents and reorganize them based on human feedback to make them more accessible and relevant for AI tasks.

## Steps
- [x] Step 1: Review human answers to questions in inbox_note.md
- [x] Step 2: Based on human feedback, reorganize context documents using preferred approach
- [x] Step 3: Update AI_README.md if folder structure changes
- [x] Step 4: Ensure all references to context files are updated
- [x] Step 5: Test that AI can access the new context structure effectively
- [x] Step 6: Review actual codebase and improve context to explain what Fichero does
- [x] Step 7: Create focused overview files that explain system purpose and architecture
- [x] Step 8: Add essential development workflow information
- [x] Step 9: Remove redundant code examples and focus on essential patterns
- [x] Step 10: Replace patterns files with more useful key_files.md references
- [x] Step 11: Add development tips and file navigation guidance
- [x] Step 12: Add development standards with best practices and testing guidelines
- [x] Step 13: Create implementation checklists for common development tasks
- [x] Step 14: Separate checklists into dedicated workflow_checklist.md files
- [x] Step 15: Create comprehensive workflows for API endpoints, features, and bug fixes

## Files
- File to change: ai/contexts/backend.md
- File to change: ai/contexts/frontend.md  
- File to change: ai/AI_README.md (if structure changes)
- New files: Various context files based on chosen organization approach

## Questions for Human
- [ ] Question 1: Do you think the current context files are too overwhelming for AI use?
    Answer: I like the proposed edits. I prpefer option 1. mirro both. not sure if we need roadmap there or in another folder? maybe thats in ai/roadmap? 

- [ ] Question 2: Which organization option do you prefer (1, 2, 3, or other)?
    Answer: option 1.

- [ ] Question 3: Should we keep the comprehensive files and add summaries, or split them up completely?
    Answer: follow ioption 1

- [ ] Question 4: Are there specific sections that should be prioritized or deprecated?
    Answer: [Human to provide guidance]

- [ ] Question 5: Should we rename "contexts" to "docs" for clarity?
    Answer: no. be concise. 


## Answers and Implementation

### Summary of Decisions Made
- **Organization Approach**: Implemented Option 1 - Split by Content Type, then refined based on codebase review
- **Folder Structure**: Created focused backend/ and frontend/ subdirectories with essential context
- **Content Focus**: Shifted from exhaustive documentation to essential system understanding
- **Naming**: Kept "contexts" folder name as requested by human

### Implementation Details

**Phase 1: Initial Organization**
- Split content into technical, best_practices, testing, and roadmap files
- Created separate backend/ and frontend/ subdirectories
- Preserved all original content organized by topic

**Phase 2: Codebase Review and Refinement**
- **Added System Architecture**: Created `architecture.md` explaining how Fichero works
- **Added Overview Files**: Created focused overview files explaining what each component does
- **Simplified Patterns**: Reduced code examples to essential patterns only
- **Added Development Workflow**: Included how to run and test the system
- **Removed Redundant Content**: Eliminated excessive code examples and historical context

### Key Improvements
- **System Understanding**: Now explains what Fichero actually does (document management + AI processing)
- **Architecture Clarity**: Clear high-level architecture diagrams and component breakdowns
- **Development Focus**: Essential information for AI to work effectively without overwhelming details
- **Codebase Alignment**: Context now matches actual codebase structure and purpose
- **Practical References**: Replaced generic patterns with specific key file lists and navigation tips
- **Self-Documenting Approach**: Added commands to explore and understand the codebase structure
- **Development Standards**: Added comprehensive best practices and testing guidelines
- **Implementation Checklists**: Provided clear checklists for common development tasks
- **Dedicated Workflow Files**: Created separate workflow_checklist.md files for focused reference
- **Comprehensive Workflows**: Added detailed step-by-step workflows for API endpoints, features, views, and bug fixes

## Need help?
- Ask if anything is unclear about the reorganization approach
- Keep it simple and focused on making context more accessible