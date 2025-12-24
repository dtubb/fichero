# Context for TODO-027: Test Proper Ingest Pipeline with Real Workflow

## Background
The current test suite verifies individual components but lacks comprehensive integration testing for the complete ingest pipeline. This task addresses the need for end-to-end testing to ensure the system works correctly in production scenarios.

## What you need to know
- The ingest pipeline includes folder ingestion, parent-child relationships, collection creation, and bookmark functionality
- Both LINK and COPY modes need testing, with COPY mode involving APFS cloning on macOS
- Integration testing should cover database, storage, and metadata extraction
- Error handling needs comprehensive testing for various failure scenarios
- The system should handle nested folder structures and maintain proper document hierarchies

## Ask if unclear
- Request human input if needed