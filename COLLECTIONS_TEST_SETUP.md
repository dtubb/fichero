# Test Collections Setup

Complete setup of 8 test collections for comprehensive library testing.

## Overview

**Total Collections:** 8
**Total Items:** 962
**Test Folders:** Tiny Test, Small Test, Medium Test
**Test URL:** https://eap.bl.uk/archive-file/EAP1299-2-48-29

## Internal Collections (type: local)

### 1. Internal Copied
- **Collection ID:** `1400ad85-58d9-4516-8004-c62e1a1112c7`
- **Type:** local
- **Storage Mode:** Copy (--operation copy)
- **Items:**
  - Tiny Test (ID: ef69e273-3f76-4ccc-b4fc-cdae0f08382a)
  - Small Test (ID: 7fd85980-04ab-4a8d-9c0c-0812f1e06349)
  - Medium Test (ID: a10afadd-d04e-4a28-989b-271e9a77d42f)
- **Purpose:** Test copied files stored in internal library folder

### 2. Internal Linked
- **Collection ID:** `75a62221-996b-41dd-a5a3-4d2a86fed173`
- **Type:** local
- **Storage Mode:** Link (--operation link)
- **Items:**
  - Tiny Test (ID: 950e7311-5bc7-4d01-b753-cd7c2173b0d8)
  - Small Test (ID: 61103843-ad40-44ad-970e-4deab8ff4221)
  - Medium Test (ID: b068e928-9f1f-444b-927a-b242dc43aa1a)
- **Purpose:** Test symlinked files stored in internal library folder

### 3. Internal URL Linked
- **Collection ID:** `8e9d9690-ee86-4696-adc5-08516c1d3baf`
- **Type:** local
- **Storage Mode:** URL reference only (not downloaded)
- **Items:**
  - Carta_p0001 and Carta_p0002 from EAP1299-2-48-29 (2 items)
- **Purpose:** Test URL items without local caching (internal collection)

### 4. Internal URL Downloaded
- **Collection ID:** `2584f0d7-2efb-4469-964a-291d77dcfb53`
- **Type:** local
- **Storage Mode:** URL with download/cache to internal library
- **Items:**
  - 2 images from EAP1299-2-48-29 (Carta_p0001, Carta_p0002)
- **Purpose:** Test URL items with local caching in internal library folder
- **Status:** ✅ Fixed - Files correctly stored in `items/` folder, no temp folder name, no duplication

## External Collections (type: external, source: /Users/dtubb/Documents/fichero/fichero_test)

### 5. External Copied
- **Collection ID:** `ff0d683a-5db8-4b22-befc-82885656ead0`
- **Type:** external
- **Source Path:** /Users/dtubb/Documents/fichero/fichero_test
- **Storage Mode:** Copy (--operation copy)
- **Items:**
  - Tiny Test (ID: 6aa6b80e-3230-4e3a-8485-6363e581610a)
  - Small Test (ID: efc331cb-4077-4c28-a49d-eac5645e4fcb)
  - Medium Test (ID: d1c1fc7e-1656-4fde-a58a-800004882ff9)
- **Purpose:** Test copied files stored in external location

### 6. External Linked
- **Collection ID:** `145b4994-b6f1-4116-ac2a-2bfce5c5f693`
- **Type:** external
- **Source Path:** /Users/dtubb/Documents/fichero/fichero_test
- **Storage Mode:** Link (--operation link)
- **Items:**
  - Tiny Test (ID: c2c6a833-cb5a-4637-a08f-f0f3dc90fe4a)
  - Small Test (ID: 31880d4f-d1e1-4fed-ab83-795c8d30f7f4)
  - Medium Test (ID: 72b16f1d-e7c0-4772-bf99-c979e2601b18)
- **Purpose:** Test symlinked files stored in external location

### 7. External URL Linked
- **Collection ID:** `2d42e325-db82-4ead-91e1-bb092dd2139a`
- **Type:** external
- **Source Path:** /Users/dtubb/Documents/fichero/fichero_test
- **Storage Mode:** URL reference only (not downloaded)
- **Items:**
  - Carta_p0001 and Carta_p0002 from EAP1299-2-48-29 (2 items)
- **Purpose:** Test URL items in external collection without caching

### 8. External URL Downloaded
- **Collection ID:** `58bd1809-542b-43b6-9efe-a80922fbdfe1`
- **Type:** external
- **Source Path:** /Users/dtubb/Documents/fichero/fichero_test
- **Storage Mode:** URL with download/cache to external location
- **Items:**
  - 2 images + folder from EAP1299-2-48-29 (3 items total)
- **Purpose:** Test URL items in external collection with caching to external path, respecting folder hierarchy

## Test Matrix

| Collection | Type | Storage | Source Folders | URL Items | Downloaded | Hierarchy |
|-----------|------|---------|---------------|-----------|------------|-----------|
| Internal Copied | local | copy | Tiny, Small, Medium | No | N/A | Yes |
| Internal Linked | local | link | Tiny, Small, Medium | No | N/A | Yes |
| Internal URL Linked | local | url | No | EAP1299-2-48-29 (2) | No | N/A |
| Internal URL Downloaded | local | url | No | EAP1299-2-48-29 (2) | Yes | Yes |
| External Copied | external | copy | Tiny, Small, Medium | No | N/A | Yes |
| External Linked | external | link | Tiny, Small, Medium | No | N/A | Yes |
| External URL Linked | external | url | No | EAP1299-2-48-29 (2) | No | N/A |
| External URL Downloaded | external | url | No | EAP1299-2-48-29 (2) | Yes | Yes |

## Testing Scenarios Covered

1. **Internal vs External Storage:**
   - Internal: Files stored in ~/Library/Application Support/ca.tubb.fichero/library/
   - External: Files stored in user-specified external path

2. **Storage Operations:**
   - Copy: Files duplicated to library
   - Link: Symbolic links created
   - URL Link: Referenced by URL only (no download)
   - URL Download: Downloaded and cached to collection folder (respecting hierarchy)

3. **File Types:**
   - Folders: Containing document collections
   - URLs: Remote web resources from EAP (IIIF manifests)

4. **Folder Hierarchy:**
   - Download mode preserves folder structure from IIIF manifest
   - Link mode stores metadata for hierarchical navigation

## CLI Commands for Testing

```bash
# List all collections
briefcase dev -- library stats

# View specific collection
briefcase dev -- library items <collection_id>

# Process a collection
briefcase dev -- library process <collection_id> --plan "Test_Images_Only"

# Check cache
briefcase dev -- library cache-info

# Import URL with download mode (internal)
briefcase dev -- library import-url "https://eap.bl.uk/archive-file/EAP1299-2-48-29" "Collection Name" --mode download --type local

# Import URL with link mode (external)
briefcase dev -- library import-url "https://eap.bl.uk/archive-file/EAP1299-2-48-29" "Collection Name" --mode link --type external --source "/path/to/external"
```

## Next Steps for Output Tracking Testing

1. Process one collection from each type
2. Verify ProcessingOutput records created in database
3. Verify ExtractedMetadata records created for transcriptions/catalogues
4. Test query methods (get_item_outputs, search_collection_metadata, etc.)
5. Verify output files appear in correct locations
6. Test dependency tracking and re-running workflows
