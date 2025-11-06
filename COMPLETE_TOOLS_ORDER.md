# Complete Tools Menu - Correct Processing Order

## Standard Processing Pipeline

Based on `Enhance_Images_and_Catalogue.yml` workflow:

### Phase 1: Image Preparation (order 0-4)
1. **Crop** - Detect and crop documents from scans
2. **Split** - Split double-page scans into individual pages
3. **Rotate** - Correct orientation
4. **Enhance** - Improve image quality (contrast, clarity)
5. **Remove Background** - Clean backgrounds

### Phase 2: Advanced Processing (order 5-7)
6. **Segment** - Segment images into regions (alternative path)
7. **Prepare Images** - Standardize image format/size
8. **Recombine Segments** - Merge segments back together

### Phase 3: AI/Content Analysis (order 8-10)
9. **Transcribe** - Extract text using OCR/AI
10. **Describe** - Generate AI descriptions
11. **LLM Process** - Catalogue generation with LLM

### Phase 4: Output Generation (order 11-14)
12. **Convert to Word** - Generate Word documents
13. **Convert to SVG** - SVG conversion
14. **JSON to Word** - Convert catalogue JSON to Word
15. **JSON to Excel** - Export to spreadsheet

### Utility Tools (order 15+)
16. **Analyze Document Groups** - Group analysis
17. **Extract Metadata** - Library metadata extraction
18. **Fuzzy Clean** - Text cleanup
19. **Build Manifest** - Already exists, not needed as quick tool

## Implementation Plan

### Currently Have (8 tools):
- ✅ Crop
- ✅ Split
- ✅ Rotate
- ✅ Enhance
- ✅ Remove Background
- ✅ Segment
- ✅ Transcribe
- ✅ Describe

### Need to Add (7 core tools):
1. **Prepare Images** (order 6)
2. **Recombine Segments** (order 7)
3. **LLM Process** (order 10)
4. **Convert to Word** (order 11)
5. **Convert to SVG** (order 12)
6. **JSON to Word** (order 13)
7. **JSON to Excel** (order 14)

### Skip (utility, not workflow tools):
- Analyze Document Groups (too specialized)
- Extract Metadata (library function)
- Fuzzy Clean (text processing utility)
- Build Manifest (internal, always runs)
- Transcribe LMStudio (duplicate of Transcribe Qwen)

## Corrected Order Values

The order should be:
```
0: Crop
1: Split
2: Rotate
3: Enhance
4: Remove Background
5: Segment
6: Prepare Images
7: Recombine Segments
8: Transcribe
9: Describe
10: LLM Process
11: Convert to Word
12: Convert to SVG
13: JSON to Word
14: JSON to Excel
```

This ensures the menu displays in processing pipeline order, not alphabetically!
