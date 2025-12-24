# Context for TODO-002: Complete In Line Rename

## Background
Inline rename functionality is missing from the sidebar. Context menus have "Rename..." options but no implementation exists.

## What you need to know
- Backend API already supports document updates via PUT /documents/{doc_id}

HUMAN: Confirm this. Is this true. Is that what PUT does?
- TODO-001 identified this as a missing feature
- Should work for documents, folders, searches, conversations, and workflows, and other takss in the future.
- Need to handle keyboard interactions (Enter/Escape)

## Ask if unclear
- Request human input if needed