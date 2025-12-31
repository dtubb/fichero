# Phase 0.6: Backend Multi-Library Testing Plan

**Date:** 2025-12-30
**Status:** Ready for testing

---

## Overview

This document provides a comprehensive testing plan for the Phase 0.6 multi-library backend implementation. All backend code is complete and ready for testing.

---

## Prerequisites

### 1. Start Backend Server

```bash
cd /Users/dtubb/code/fichero_main/fichero
PYTHONPATH=src .venv/bin/uvicorn fichero.api.main:app --port 8765
```

**Verify running**:
```bash
curl http://127.0.0.1:8765/health
# Expected: {"status":"healthy","backend_version":"0.1.0","active_libraries":0}
```

### 2. Create Test Libraries

```bash
# Create test package directories
mkdir -p ~/Desktop/TestLibrary1.fichero
mkdir -p ~/Desktop/TestLibrary2.fichero
```

### 3. Install Testing Tools

```bash
# Install httpie for easier API testing (optional)
brew install httpie

# Or use curl (included with macOS)
```

---

## Test Categories

- [A. Health & Connectivity](#a-health--connectivity)
- [B. Document Operations](#b-document-operations)
- [C. Library Isolation](#c-library-isolation)
- [D. Storage & Thumbnails](#d-storage--thumbnails)
- [E. File Ingestion](#e-file-ingestion)
- [F. Search & Embeddings](#f-search--embeddings)
- [G. Workflows](#g-workflows)
- [H. Error Handling](#h-error-handling)

---

## A. Health & Connectivity

### Test A.1: Health Check

**Purpose**: Verify backend is responding with correct format

```bash
curl http://127.0.0.1:8765/health
```

**Expected**:
```json
{
  "status": "healthy",
  "backend_version": "0.1.0",
  "active_libraries": 0
}
```

**Pass Criteria**:
- ✅ Returns 200 status
- ✅ Contains `backend_version` (not `database`)
- ✅ Contains `active_libraries` (not `documentCount`)

---

### Test A.2: API Documentation

**Purpose**: Verify API docs are accessible

```bash
open http://127.0.0.1:8765/docs
```

**Expected**:
- ✅ Swagger UI loads
- ✅ All routes are listed
- ✅ Can test endpoints from UI

---

## B. Document Operations

### Test B.1: Create Folder (Library 1)

**Purpose**: Verify document creation in specific library

```bash
curl -X POST http://127.0.0.1:8765/api/documents \
  -H "Content-Type: application/json" \
  -H "X-Fichero-Library-Path: $HOME/Desktop/TestLibrary1.fichero" \
  -d '{
    "name": "Folder 1",
    "documentType": "folder"
  }'
```

**Expected**:
```json
{
  "id": "abc123...",
  "name": "Folder 1",
  "documentType": "folder",
  "createdAt": "2025-12-30T...",
  ...
}
```

**Verify**:
```bash
# Check database file was created
ls -la ~/Desktop/TestLibrary1.fichero/
# Should see: fichero.duckdb

# Query database
duckdb ~/Desktop/TestLibrary1.fichero/fichero.duckdb "SELECT name, doc_type FROM documents;"
# Should show: Folder 1 | folder
```

**Pass Criteria**:
- ✅ Returns 200 status
- ✅ Document has valid ID
- ✅ Database file created in correct package
- ✅ Document stored in correct database

---

### Test B.2: List Documents (Library 1)

**Purpose**: Verify document retrieval from specific library

```bash
curl -H "X-Fichero-Library-Path: $HOME/Desktop/TestLibrary1.fichero" \
  http://127.0.0.1:8765/api/documents
```

**Expected**:
```json
{
  "documents": [
    {
      "id": "abc123...",
      "name": "Folder 1",
      "documentType": "folder",
      ...
    }
  ],
  "total": 1
}
```

**Pass Criteria**:
- ✅ Returns created folder
- ✅ total count is 1

---

### Test B.3: Get Document by ID

**Purpose**: Verify individual document retrieval

```bash
# Save doc ID from previous test
DOC_ID="abc123..."

curl -H "X-Fichero-Library-Path: $HOME/Desktop/TestLibrary1.fichero" \
  http://127.0.0.1:8765/api/documents/$DOC_ID
```

**Expected**:
```json
{
  "id": "abc123...",
  "name": "Folder 1",
  ...
}
```

**Pass Criteria**:
- ✅ Returns correct document
- ✅ All fields populated

---

### Test B.4: Update Document

**Purpose**: Verify document updates

```bash
curl -X PUT http://127.0.0.1:8765/api/documents/$DOC_ID \
  -H "Content-Type: application/json" \
  -H "X-Fichero-Library-Path: $HOME/Desktop/TestLibrary1.fichero" \
  -d '{
    "name": "Folder 1 - Updated"
  }'
```

**Expected**:
```json
{
  "id": "abc123...",
  "name": "Folder 1 - Updated",
  ...
}
```

**Pass Criteria**:
- ✅ Name updated
- ✅ Other fields unchanged

---

### Test B.5: Delete Document

**Purpose**: Verify document deletion

```bash
curl -X DELETE \
  -H "X-Fichero-Library-Path: $HOME/Desktop/TestLibrary1.fichero" \
  http://127.0.0.1:8765/api/documents/$DOC_ID
```

**Expected**:
```json
{"message": "Document deleted successfully"}
```

**Verify**:
```bash
# List documents - should be empty
curl -H "X-Fichero-Library-Path: $HOME/Desktop/TestLibrary1.fichero" \
  http://127.0.0.1:8765/api/documents
# Should return: {"documents": [], "total": 0}
```

**Pass Criteria**:
- ✅ Delete succeeds
- ✅ Document no longer in list

---

## C. Library Isolation

### Test C.1: Create Documents in Both Libraries

**Purpose**: Verify libraries are independent

```bash
# Create folder in Library 1
curl -X POST http://127.0.0.1:8765/api/documents \
  -H "Content-Type: application/json" \
  -H "X-Fichero-Library-Path: $HOME/Desktop/TestLibrary1.fichero" \
  -d '{"name": "Library 1 Folder", "documentType": "folder"}'

# Create folder in Library 2
curl -X POST http://127.0.0.1:8765/api/documents \
  -H "Content-Type: application/json" \
  -H "X-Fichero-Library-Path: $HOME/Desktop/TestLibrary2.fichero" \
  -d '{"name": "Library 2 Folder", "documentType": "folder"}'
```

**Pass Criteria**:
- ✅ Both documents created successfully
- ✅ Each gets unique ID

---

### Test C.2: Verify Library Isolation

**Purpose**: Ensure documents don't mix between libraries

```bash
# List Library 1 documents
curl -H "X-Fichero-Library-Path: $HOME/Desktop/TestLibrary1.fichero" \
  http://127.0.0.1:8765/api/documents
# Should return: 1 document ("Library 1 Folder")

# List Library 2 documents
curl -H "X-Fichero-Library-Path: $HOME/Desktop/TestLibrary2.fichero" \
  http://127.0.0.1:8765/api/documents
# Should return: 1 document ("Library 2 Folder")
```

**Verify Databases**:
```bash
# Check Library 1 database
duckdb ~/Desktop/TestLibrary1.fichero/fichero.duckdb \
  "SELECT name FROM documents;"
# Should show: Library 1 Folder

# Check Library 2 database
duckdb ~/Desktop/TestLibrary2.fichero/fichero.duckdb \
  "SELECT name FROM documents;"
# Should show: Library 2 Folder
```

**Pass Criteria**:
- ✅ Library 1 only shows Library 1 documents
- ✅ Library 2 only shows Library 2 documents
- ✅ Separate database files
- ✅ No cross-contamination

---

### Test C.3: Active Libraries Count

**Purpose**: Verify backend tracks active libraries

```bash
# Check health after creating both libraries
curl http://127.0.0.1:8765/health
```

**Expected**:
```json
{
  "status": "healthy",
  "backend_version": "0.1.0",
  "active_libraries": 2
}
```

**Pass Criteria**:
- ✅ active_libraries is 2

---

## D. Storage & Thumbnails

### Test D.1: Storage Stats (Empty)

**Purpose**: Verify storage stats for new library

```bash
curl -H "X-Fichero-Library-Path: $HOME/Desktop/TestLibrary1.fichero" \
  http://127.0.0.1:8765/api/storage/stats
```

**Expected**:
```json
{
  "count": 0,
  "size_mb": 0.0,
  "shards": 0
}
```

**Pass Criteria**:
- ✅ Returns empty stats for new library

---

### Test D.2: Thumbnail Generation

**Purpose**: Verify thumbnail generation in correct package

**Setup**:
```bash
# Create a test image (requires ImageMagick)
convert -size 800x600 xc:blue ~/Desktop/test.jpg

# Or use any existing image
cp ~/Pictures/test.jpg ~/Desktop/test.jpg
```

**Import**:
```bash
curl -X POST http://127.0.0.1:8765/api/ingest/file \
  -H "Content-Type: application/json" \
  -H "X-Fichero-Library-Path: $HOME/Desktop/TestLibrary1.fichero" \
  -d '{
    "path": "'$HOME'/Desktop/test.jpg",
    "extract_text": false,
    "auto_embed": false
  }'
```

**Get Document ID** from response, then:

```bash
DOC_ID="xyz789..."

# Request thumbnail
curl -H "X-Fichero-Library-Path: $HOME/Desktop/TestLibrary1.fichero" \
  http://127.0.0.1:8765/api/storage/thumbnail/$DOC_ID \
  --output /tmp/thumb.jpg

# Verify thumbnail file
ls -la /tmp/thumb.jpg
open /tmp/thumb.jpg
```

**Verify Package Storage**:
```bash
# Check thumbnail exists in package
ls -la ~/Desktop/TestLibrary1.fichero/storage/thumbnails/
# Should see subdirectories with first 2 chars of doc ID

# Find the thumbnail
find ~/Desktop/TestLibrary1.fichero/storage/thumbnails/ -name "*.jpg"
# Should find thumbnail file
```

**Pass Criteria**:
- ✅ Thumbnail generates successfully
- ✅ Thumbnail stored in correct package
- ✅ Thumbnail path is `{package}/storage/thumbnails/{ab}/{doc_id}.jpg`
- ✅ Thumbnail image is valid (can open)

---

### Test D.3: Display Image Generation

**Purpose**: Verify display-size image generation

```bash
# Request display image
curl -H "X-Fichero-Library-Path: $HOME/Desktop/TestLibrary1.fichero" \
  http://127.0.0.1:8765/api/storage/display/$DOC_ID \
  --output /tmp/display.jpg

# Verify larger than thumbnail
ls -lh /tmp/thumb.jpg /tmp/display.jpg
# Display image should be larger
```

**Pass Criteria**:
- ✅ Display image generates
- ✅ Display image larger than thumbnail
- ✅ Stored in same package directory

---

### Test D.4: Storage Stats (After Import)

**Purpose**: Verify storage stats update correctly

```bash
curl -H "X-Fichero-Library-Path: $HOME/Desktop/TestLibrary1.fichero" \
  http://127.0.0.1:8765/api/storage/stats
```

**Expected**:
```json
{
  "count": 2,
  "size_mb": 0.05,
  "shards": 1
}
```

**Pass Criteria**:
- ✅ count shows 2 (thumbnail + display)
- ✅ size_mb > 0
- ✅ shards >= 1

---

### Test D.5: Storage Isolation

**Purpose**: Verify storage is isolated per library

```bash
# Import image to Library 2
curl -X POST http://127.0.0.1:8765/api/ingest/file \
  -H "Content-Type: application/json" \
  -H "X-Fichero-Library-Path: $HOME/Desktop/TestLibrary2.fichero" \
  -d '{
    "path": "'$HOME'/Desktop/test.jpg",
    "extract_text": false
  }'

# Check Library 1 storage
ls ~/Desktop/TestLibrary1.fichero/storage/thumbnails/

# Check Library 2 storage
ls ~/Desktop/TestLibrary2.fichero/storage/thumbnails/

# Should be separate directories
```

**Pass Criteria**:
- ✅ Each library has own storage/ directory
- ✅ Thumbnails don't mix between libraries

---

## E. File Ingestion

### Test E.1: Single File Import (LINK mode)

**Purpose**: Verify LINK mode creates bookmark reference

```bash
curl -X POST http://127.0.0.1:8765/api/ingest/file \
  -H "Content-Type: application/json" \
  -H "X-Fichero-Library-Path: $HOME/Desktop/TestLibrary1.fichero" \
  -d '{
    "path": "'$HOME'/Desktop/test.jpg",
    "copy_mode": false,
    "extract_text": false,
    "auto_embed": false
  }'
```

**Verify**:
```bash
# Check document was created
curl -H "X-Fichero-Library-Path: $HOME/Desktop/TestLibrary1.fichero" \
  http://127.0.0.1:8765/api/documents | jq '.documents[] | select(.name == "test.jpg")'

# Verify file NOT copied (LINK mode)
ls ~/Desktop/TestLibrary1.fichero/files/
# Should be empty or not exist
```

**Pass Criteria**:
- ✅ Document created
- ✅ File not copied to package
- ✅ Metadata includes bookmark

---

### Test E.2: Single File Import (COPY mode)

**Purpose**: Verify COPY mode imports file into package

```bash
curl -X POST http://127.0.0.1:8765/api/ingest/file \
  -H "Content-Type: application/json" \
  -H "X-Fichero-Library-Path: $HOME/Desktop/TestLibrary1.fichero" \
  -d '{
    "path": "'$HOME'/Desktop/test.jpg",
    "copy_mode": true,
    "extract_text": false,
    "auto_embed": false
  }'
```

**Verify**:
```bash
# Check file was copied
find ~/Desktop/TestLibrary1.fichero/files/ -name "*test.jpg"
# Should find imported file

# Verify it's a copy (APFS clone or regular copy)
ls -lh ~/Desktop/test.jpg
ls -lh ~/Desktop/TestLibrary1.fichero/files/*/test.jpg
# Sizes should match
```

**Pass Criteria**:
- ✅ Document created
- ✅ File copied to package
- ✅ File preserved in original location

---

### Test E.3: Folder Import

**Purpose**: Verify batch folder import

**Setup**:
```bash
# Create test folder
mkdir -p ~/Desktop/test_folder
cp ~/Desktop/test.jpg ~/Desktop/test_folder/image1.jpg
cp ~/Desktop/test.jpg ~/Desktop/test_folder/image2.jpg
cp ~/Desktop/test.jpg ~/Desktop/test_folder/image3.jpg
```

**Import**:
```bash
curl -X POST http://127.0.0.1:8765/api/ingest/folder \
  -H "Content-Type: application/json" \
  -H "X-Fichero-Library-Path: $HOME/Desktop/TestLibrary1.fichero" \
  -d '{
    "path": "'$HOME'/Desktop/test_folder",
    "copy_mode": false,
    "recursive": true,
    "extract_text": false,
    "auto_embed": false
  }'
```

**Response**:
```json
{
  "task_id": "abc123...",
  "status": "pending",
  "path": "/Users/.../test_folder"
}
```

**Monitor Progress**:
```bash
TASK_ID="abc123..."

# Poll status
curl -H "X-Fichero-Library-Path: $HOME/Desktop/TestLibrary1.fichero" \
  http://127.0.0.1:8765/api/ingest/status/$TASK_ID

# Expected (in progress):
# {
#   "task_id": "abc123...",
#   "status": "running",
#   "progress": 0.66,
#   "processed": 2,
#   "total": 3,
#   ...
# }

# Expected (completed):
# {
#   "task_id": "abc123...",
#   "status": "completed",
#   "progress": 1.0,
#   "processed": 3,
#   "total": 3,
#   "document_ids": ["id1", "id2", "id3"]
# }
```

**Verify**:
```bash
# Check all documents created
curl -H "X-Fichero-Library-Path: $HOME/Desktop/TestLibrary1.fichero" \
  http://127.0.0.1:8765/api/documents | jq '.total'
# Should show: 4 (folder + 3 images)
```

**Pass Criteria**:
- ✅ Task created with ID
- ✅ Progress updates correctly
- ✅ All files imported
- ✅ Folder hierarchy preserved

---

### Test E.4: Text Extraction

**Purpose**: Verify text extraction from supported files

**Setup**:
```bash
# Create test PDF with text (requires pandoc or similar)
echo "This is test content for extraction" > ~/Desktop/test.txt
```

**Import**:
```bash
curl -X POST http://127.0.0.1:8765/api/ingest/file \
  -H "Content-Type: application/json" \
  -H "X-Fichero-Library-Path: $HOME/Desktop/TestLibrary1.fichero" \
  -d '{
    "path": "'$HOME'/Desktop/test.txt",
    "copy_mode": false,
    "extract_text": true,
    "auto_embed": false
  }'
```

**Verify**:
```bash
# Get document
curl -H "X-Fichero-Library-Path: $HOME/Desktop/TestLibrary1.fichero" \
  http://127.0.0.1:8765/api/documents | \
  jq '.documents[] | select(.name == "test.txt") | .pageContent'

# Should show extracted text
```

**Pass Criteria**:
- ✅ Text extracted successfully
- ✅ pageContent field populated
- ✅ Metadata shows text_extracted: true

---

## F. Search & Embeddings

### Test F.1: Create Embeddings

**Purpose**: Verify vector embeddings work per library

```bash
# Import document with auto_embed
curl -X POST http://127.0.0.1:8765/api/ingest/file \
  -H "Content-Type: application/json" \
  -H "X-Fichero-Library-Path: $HOME/Desktop/TestLibrary1.fichero" \
  -d '{
    "path": "'$HOME'/Desktop/test.txt",
    "extract_text": true,
    "auto_embed": true
  }'
```

**Verify**:
```bash
# Check LanceDB directory created
ls ~/Desktop/TestLibrary1.fichero/lance/
# Should show: documents.lance/

# Check embedding stats
curl -H "X-Fichero-Library-Path: $HOME/Desktop/TestLibrary1.fichero" \
  http://127.0.0.1:8765/api/search/stats
```

**Expected**:
```json
{
  "total_documents": 1,
  "total_embeddings": 1,
  "index_health": "healthy"
}
```

**Pass Criteria**:
- ✅ LanceDB created in correct package
- ✅ Embedding created
- ✅ Stats show 1 embedding

---

### Test F.2: Semantic Search

**Purpose**: Verify search works within library

```bash
curl -X POST http://127.0.0.1:8765/api/search \
  -H "Content-Type: application/json" \
  -H "X-Fichero-Library-Path: $HOME/Desktop/TestLibrary1.fichero" \
  -d '{
    "query": "test content",
    "limit": 10
  }'
```

**Expected**:
```json
{
  "results": [
    {
      "document": {
        "id": "...",
        "name": "test.txt",
        ...
      },
      "score": 0.95,
      "snippet": "This is test content for extraction"
    }
  ],
  "total": 1
}
```

**Pass Criteria**:
- ✅ Search finds relevant document
- ✅ Score is high (> 0.8)
- ✅ Returns correct document

---

### Test F.3: Search Isolation

**Purpose**: Verify search doesn't cross libraries

```bash
# Create document in Library 2
curl -X POST http://127.0.0.1:8765/api/ingest/file \
  -H "Content-Type: application/json" \
  -H "X-Fichero-Library-Path: $HOME/Desktop/TestLibrary2.fichero" \
  -d '{
    "path": "'$HOME'/Desktop/test.txt",
    "extract_text": true,
    "auto_embed": true
  }'

# Search Library 1
curl -X POST http://127.0.0.1:8765/api/search \
  -H "Content-Type: application/json" \
  -H "X-Fichero-Library-Path: $HOME/Desktop/TestLibrary1.fichero" \
  -d '{"query": "test content", "limit": 10}'
# Should return: 1 result

# Search Library 2
curl -X POST http://127.0.0.1:8765/api/search \
  -H "Content-Type: application/json" \
  -H "X-Fichero-Library-Path: $HOME/Desktop/TestLibrary2.fichero" \
  -d '{"query": "test content", "limit": 10}'
# Should return: 1 result

# Verify they're different documents
```

**Pass Criteria**:
- ✅ Each library returns 1 result
- ✅ Results have different document IDs
- ✅ No cross-library search results

---

## G. Workflows

### Test G.1: List Workflow Tools

**Purpose**: Verify workflow tools are accessible

```bash
curl http://127.0.0.1:8765/api/workflows/tools
```

**Expected**:
```json
{
  "tools": [
    {
      "name": "transcribe",
      "display_name": "Transcribe",
      "category": "vision",
      ...
    },
    ...
  ]
}
```

**Pass Criteria**:
- ✅ Returns list of tools
- ✅ Tools have proper metadata

---

### Test G.2: Create Workflow

**Purpose**: Verify workflow creation in library

```bash
curl -X POST http://127.0.0.1:8765/api/workflows \
  -H "Content-Type: application/json" \
  -H "X-Fichero-Library-Path: $HOME/Desktop/TestLibrary1.fichero" \
  -d '{
    "name": "Test Workflow",
    "description": "Test workflow for library isolation",
    "provider": "openai",
    "model": "gpt-4",
    "nodes": [],
    "edges": []
  }'
```

**Pass Criteria**:
- ✅ Workflow created successfully
- ✅ Returns workflow ID

---

### Test G.3: Workflow Isolation

**Purpose**: Verify workflows are library-specific

```bash
# List workflows in Library 1
curl -H "X-Fichero-Library-Path: $HOME/Desktop/TestLibrary1.fichero" \
  http://127.0.0.1:8765/api/workflows
# Should show: Test Workflow

# List workflows in Library 2
curl -H "X-Fichero-Library-Path: $HOME/Desktop/TestLibrary2.fichero" \
  http://127.0.0.1:8765/api/workflows
# Should show: empty list
```

**Pass Criteria**:
- ✅ Library 1 has workflow
- ✅ Library 2 has no workflows
- ✅ Complete isolation

---

## H. Error Handling

### Test H.1: Missing Library Path Header

**Purpose**: Verify error when header missing

```bash
curl -X POST http://127.0.0.1:8765/api/documents \
  -H "Content-Type: application/json" \
  -d '{"name": "Test", "documentType": "folder"}'
```

**Expected**:
```json
{
  "detail": "Missing X-Fichero-Library-Path header"
}
```

**Pass Criteria**:
- ✅ Returns 400 or 422 status
- ✅ Error message is clear

---

### Test H.2: Invalid Library Path

**Purpose**: Verify error handling for bad path

```bash
curl -X POST http://127.0.0.1:8765/api/documents \
  -H "Content-Type: application/json" \
  -H "X-Fichero-Library-Path: /nonexistent/path.fichero" \
  -d '{"name": "Test", "documentType": "folder"}'
```

**Pass Criteria**:
- ✅ Returns appropriate error
- ✅ Error message is helpful

---

### Test H.3: Document Not Found

**Purpose**: Verify 404 handling

```bash
curl -H "X-Fichero-Library-Path: $HOME/Desktop/TestLibrary1.fichero" \
  http://127.0.0.1:8765/api/documents/nonexistent-id
```

**Expected**:
```json
{
  "detail": "Document not found: nonexistent-id"
}
```

**Pass Criteria**:
- ✅ Returns 404 status
- ✅ Error message includes ID

---

### Test H.4: Duplicate Document Handling

**Purpose**: Verify behavior when creating duplicate

```bash
# Create document
curl -X POST http://127.0.0.1:8765/api/documents \
  -H "Content-Type: application/json" \
  -H "X-Fichero-Library-Path: $HOME/Desktop/TestLibrary1.fichero" \
  -d '{"name": "Duplicate Test", "documentType": "folder"}'

# Try to create again with same name (should succeed - names can duplicate)
curl -X POST http://127.0.0.1:8765/api/documents \
  -H "Content-Type: application/json" \
  -H "X-Fichero-Library-Path: $HOME/Desktop/TestLibrary1.fichero" \
  -d '{"name": "Duplicate Test", "documentType": "folder"}'
```

**Pass Criteria**:
- ✅ Both documents created (different IDs)
- ✅ Names can be duplicate

---

## Summary Checklist

After completing all tests, verify:

### Backend Core
- [ ] Health check returns correct format
- [ ] All routes use database dependency
- [ ] No global db imports remain

### Library Isolation
- [ ] Documents isolated per library
- [ ] Storage isolated per library
- [ ] Search isolated per library
- [ ] Workflows isolated per library

### Storage
- [ ] Thumbnails in correct package
- [ ] Display images in correct package
- [ ] Stats work per library
- [ ] No global storage directory used

### Ingestion
- [ ] LINK mode works
- [ ] COPY mode works
- [ ] Folder import works
- [ ] Text extraction works
- [ ] Progress tracking works

### Error Handling
- [ ] Missing header handled gracefully
- [ ] Invalid paths handled gracefully
- [ ] 404s return proper errors
- [ ] Error messages are helpful

---

## Cleanup

After testing:

```bash
# Remove test libraries
rm -rf ~/Desktop/TestLibrary1.fichero
rm -rf ~/Desktop/TestLibrary2.fichero
rm -rf ~/Desktop/test_folder
rm ~/Desktop/test.jpg ~/Desktop/test.txt
```

---

**Created By:** Claude Code
**Last Updated:** 2025-12-30 17:15
**Status:** Ready for execution
