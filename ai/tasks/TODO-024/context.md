# Context for TODO-024: Fix Frontend Import UI and Update Issues

## Background
User reported that file/folder import from SwiftUI app is not working properly. The backend API responds correctly but the frontend shows layout recursion warnings and doesn't update the UI after successful import. This affects the document browser functionality.

## What you need to know
- [Backend API is working (GET /api/providers/models/apple returns 200 OK)]
- [Frontend shows "layoutSubtreeIfNeeded" recursion warnings in SwiftUI]
- [UI doesn't refresh to show newly imported items]
- [Issue affects both file and folder imports]
- [User also wants review of delete functionality]
- [Related to TODO-004 for backend import endpoint completion]

## Ask if unclear
- Request human input if needed