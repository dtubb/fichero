# Review and Improve AI Context Documents

## Description
The current context documents (`ai/contexts/backend.md` and `ai/contexts/frontend.md`) are quite lengthy and contain a mix of technical details, best practices, and feature planning. The human is concerned they may be overwhelming for AI and wants to explore better organization.

## Current Analysis

### Current Structure Issues:
- **Length**: Both files are quite long (131 and 214 lines respectively)
- **Mixed Content**: Contains technical patterns, best practices, testing, and feature planning all in one place
- **Potential Overwhelm**: AI may need to process irrelevant context when working on specific tasks

### Current Content Breakdown:

**backend.md (131 lines)**:
- Overview and key components
- Development patterns (API structure, error handling, database ops)
- Testing patterns (unit and integration)
- Best practices
- Feature planning context

**frontend.md (214 lines)**:
- Overview and key components  
- Development patterns (SwiftUI, state management, API integration)
- Testing patterns (unit and UI)
- Best practices
- Style guide (code organization, SwiftUI patterns, formatting, documentation)
- Feature planning context

## Potential Improvements

### Option 1: Split by Content Type
```
ai/contexts/
├── backend/
│   ├── technical.md          # Technical patterns and code examples
│   ├── best_practices.md     # Best practices and conventions
│   ├── testing.md            # Testing approaches
│   └── roadmap.md            # Feature planning and architecture evolution
└── frontend/
    ├── technical.md          # Technical patterns and code examples
    ├── best_practices.md     # Best practices and conventions
    ├── style_guide.md         # Code formatting and organization
    ├── testing.md            # Testing approaches
    └── roadmap.md            # Feature planning and architecture evolution
```

### Option 2: Split by Purpose
```
ai/contexts/
├── backend/
│   ├── development.md        # Technical patterns and best practices
│   └── planning.md           # Feature planning and architecture
└── frontend/
    ├── development.md        # Technical patterns and best practices
    ├── style_guide.md        # Code formatting and organization
    └── planning.md           # Feature planning and architecture
```

### Option 3: Keep Current Structure but Add Summary Files
```
ai/contexts/
├── backend.md                # Current comprehensive file
├── frontend.md               # Current comprehensive file  
├── backend_summary.md        # Short summary for quick reference
└── frontend_summary.md       # Short summary for quick reference
```

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

## Related Files/Components
- `ai/contexts/backend.md` - Current backend context (131 lines)
- `ai/contexts/frontend.md` - Current frontend context (214 lines)
- `ai/AI_README.md` - References the contexts folder structure
- Any AI workflows that reference these context files

## Notes
- The goal is to make context more accessible and relevant for AI tasks
- We want to avoid overwhelming AI with irrelevant information
- The organization should support quick reference and deep dives as needed
- Consider that AI may need different context for different types of tasks (implementation vs planning)