# PHASE 5: CLI INTEGRATION AUDIT - AGENT INSTRUCTIONS

**Phase:** 5 of 7
**Agent Type:** general-purpose
**Estimated Duration:** 30 minutes
**Prerequisites:** Read all previous phase outputs

---

## OBJECTIVE

Audit CLI integration to verify all 20 tools are accessible via command-line interface. Document:
1. CLI command structure and organization
2. Which tools have CLI access
3. Parameter passing from CLI to tools
4. Output inspection capabilities
5. CLI documentation completeness

Create `CLI_INTEGRATION_STATUS.md` with complete CLI audit and usage examples.

**IMPORTANT:** This phase is AUDIT ONLY. Do not execute CLI commands. Document current state.

---

## INPUT FILES

**Required Reading:**
1. `TOOL_REFERENCE.md` - Tool parameters
2. `WORKFLOW_STATUS.md` - Plan/workflow coverage
3. `GUI_INTEGRATION_STATUS.md` - GUI integration state

**Files to Audit:**
1. `src/fichero/cli/commands/library/*.py` - Library CLI commands
2. `src/fichero/cli/cli_app.py` - CLI application structure
3. `src/fichero/cli/__main__.py` - CLI entry point
4. CLI help text (via code inspection, not execution)

---

## TASK BREAKDOWN

### Task 1: Map CLI Command Structure

Document the CLI command hierarchy:

```
briefcase dev --
├── library
│   ├── list - List collections
│   ├── add - Add collection
│   ├── add-item - Add item to collection
│   ├── process - Process collection (MAIN TOOL ACCESS)
│   ├── inspect-outputs - Inspect processing outputs
│   ├── steps - List processing steps
│   ├── ... (document all commands)
├── process - Direct folder processing
├── prepare - Prepare folders
└── ... (document all top-level commands)
```

### Task 2: Audit Tool Access via CLI

**Primary tool access method:** `library process`

Document how users access tools:

```bash
# Workflow-based (all 20 tools accessible)
briefcase dev -- library process <collection_id> --plan <plan_name> --workflow <workflow_name>

# Direct processing
briefcase dev -- process <input_folder> <output_folder> --plan <plan_name> --workflow <workflow_name>
```

**For each of the 20 tools, document:**
1. Accessible via which CLI command?
2. Which plan/workflow provides access?
3. Parameters configurable via CLI?
4. Example usage command

### Task 3: Audit Parameter Passing

Document how CLI parameters flow to tools:

1. **Via plan YAML** - Most common
   - User specifies plan + workflow
   - Parameters hard-coded in YAML
   - No CLI override (must edit YAML)

2. **Via CLI flags** - If implemented
   - Tool-specific flags
   - Override YAML defaults
   - Direct parameter control

Document which method(s) are currently implemented.

### Task 4: Audit Output Inspection

Document CLI commands for viewing tool outputs:

```bash
# Inspect outputs
briefcase dev -- library inspect-outputs <collection_id>

# List processing steps
briefcase dev -- library steps <collection_id>

# View step details
briefcase dev -- library step <step_name>
```

For each command, document:
- What information is shown
- Output format (text, JSON, table)
- Usefulness for debugging

### Task 5: Audit CLI Documentation

Check for CLI documentation:

1. **Help text** - `--help` for each command
2. **Examples** - Usage examples in help
3. **Error messages** - Informative error handling
4. **Developer docs** - CLI usage guides

Document completeness and quality.

### Task 6: Compare CLI vs GUI Access

Create comparison table:

| Tool | GUI Access | CLI Access | Parameter Config | Output View | Status |
|------|------------|------------|------------------|-------------|--------|
| crop | ✅ Menu | ✅ library process | YAML only | ✅ inspect-outputs | Complete |
| ... | ... | ... | ... | ... | ... |

---

## OUTPUT FORMAT

Create `CLI_INTEGRATION_STATUS.md` with this structure:

```markdown
# FICHERO CLI INTEGRATION STATUS REPORT

**Generated:** 2025-11-15
**Phase:** 5 of 7
**Purpose:** Audit CLI access for all 20 tools

---

## EXECUTIVE SUMMARY

**CLI Tool Access:**
- All 20 tools accessible via `library process` ✅
- Direct folder processing via `process` command ✅
- Output inspection commands available ✅
- Parameter configuration: YAML-based (no CLI override)
- CLI documentation: [assessment]

**CLI Commands:**
- Total commands: [count]
- Library commands: [count]
- Processing commands: [count]
- Utility commands: [count]

**Gaps:**
- No direct CLI parameter override
- Limited output inspection capabilities
- [Other gaps]

---

## CLI COMMAND STRUCTURE

### Command Hierarchy

```
briefcase dev -- [command] [subcommand] [args]

Top-level commands:
├── library          - Collection management and processing
│   ├── list        - List all collections
│   ├── add         - Add new collection
│   ├── add-item    - Add item to collection
│   ├── items       - List collection items
│   ├── process     - Process collection (PRIMARY TOOL ACCESS)
│   ├── inspect-outputs - View processing outputs
│   ├── steps       - List processing steps
│   ├── step        - View step details
│   ├── export      - Export collection
│   ├── preview     - Preview collection
│   └── cleanup     - Clean up outputs
├── process         - Direct folder processing
├── prepare         - Prepare folders
├── worker-status   - Check worker status
└── example         - Show usage examples
```

### Primary Tool Access Command

**Command:** `library process`

**Signature:**
```bash
briefcase dev -- library process <collection_id> --plan <plan_name> --workflow <workflow_name> [options]
```

**Options:**
- `--plan` - Plan name from resources/config_defaults/plans/
- `--workflow` - Workflow name within plan
- `--output` - Optional output directory
- `--verbose` - Verbose logging

**How it works:**
1. Loads collection from library database
2. Loads plan YAML file
3. Executes workflow via DirectorIntegrationService
4. Saves outputs to collection cache
5. Updates library with processing results

---

## TOOL ACCESS VIA CLI

### Complete Tool Coverage (20/20)

| # | Tool | CLI Command | Plan Name | Workflow | Example |
|---|------|-------------|-----------|----------|---------|
| 1 | crop | library process | Crop | CropTest | `briefcase dev -- library process <id> --plan Crop --workflow CropTest` |
| 2 | rotate | library process | Rotate | RotateTest | `briefcase dev -- library process <id> --plan Rotate --workflow RotateTest` |
| 3 | enhance | library process | Enhance | EnhanceTest | `briefcase dev -- library process <id> --plan Enhance --workflow EnhanceTest` |
| ... | ... | ... | ... | ... | ... |

**CLI Coverage:** 20/20 tools (100%) ✅

**Access Method:** All tools accessible via workflow-based processing

### Direct Folder Processing

**Command:** `process`

**Signature:**
```bash
briefcase dev -- process <input_folder> <output_folder> --plan <plan_name> --workflow <workflow_name>
```

**Difference from `library process`:**
- Works on folders directly (no library database)
- No collection management
- Outputs to specified folder
- No output tracking in library

**Use cases:**
- Quick one-off processing
- Batch processing without library
- Testing workflows on sample data

---

## PARAMETER CONFIGURATION

### Current Method: YAML-Based

**How parameters are set:**
1. Parameters defined in plan YAML files
2. Hard-coded in `commands.args` section
3. No CLI override capability

**Example (Crop.yml):**
```yaml
commands:
  - name: crop
    args:
      contour_template: "auto"
      contour_padding: 30
      output_format: "jpg"
```

**To change parameters:**
1. Edit YAML file in `resources/config_defaults/plans/`
2. Or create custom plan file
3. No dynamic CLI configuration

### Missing: CLI Parameter Override

**Not currently implemented:**
```bash
# This does NOT work (hypothetical):
briefcase dev -- library process <id> --plan Crop --workflow CropTest --param contour_padding=50
```

**Recommendation:** Add CLI parameter override for common parameters

---

## OUTPUT INSPECTION

### inspect-outputs Command

**Command:** `library inspect-outputs`

**Signature:**
```bash
briefcase dev -- library inspect-outputs <collection_id> [--step <step_name>]
```

**What it shows:**
- List of processing steps executed
- Output files for each step
- Manifest entries
- Processing metadata

**Output format:** [Document actual format from code inspection]

**Example output:**
```
[Document example from code]
```

### steps Command

**Command:** `library steps`

**Signature:**
```bash
briefcase dev -- library steps <collection_id>
```

**What it shows:**
- All processing steps available
- Step dependencies
- Step status (pending/running/complete/failed)

### step Command

**Command:** `library step`

**Signature:**
```bash
briefcase dev -- library step <step_name>
```

**What it shows:**
- Step configuration
- Input requirements
- Output products
- Execution status

---

## CLI HELP DOCUMENTATION

### Command Help Text

**Audit results:**
- [x] `--help` available for all commands
- [ ] Examples included in help text
- [ ] Parameter descriptions complete
- [ ] Error messages informative

**Sample help text:**
```
[Include actual help text from code inspection]
```

**Quality assessment:**
- Completeness: [score/10]
- Clarity: [score/10]
- Examples: [score/10]
- Overall: [score/10]

### Developer Documentation

**Documentation found:**
- [ ] CLI usage guide in docs/
- [ ] Command reference
- [ ] Tutorial/examples
- [ ] Troubleshooting guide

**Gap:** No comprehensive CLI documentation

---

## CLI VS GUI COMPARISON

### Feature Parity Analysis

| Feature | GUI | CLI | Notes |
|---------|-----|-----|-------|
| **Collection Management** |
| Create collection | ✅ | ✅ | Both functional |
| Add items | ✅ | ✅ | Both functional |
| Browse items | ✅ | ⚠️ Limited | CLI shows text list only |
| **Processing** |
| Execute workflows | ✅ | ✅ | Identical backend |
| Configure parameters | ⚠️ Via dialog | ❌ Edit YAML | GUI better |
| Monitor progress | ✅ Real-time | ⚠️ Polling | GUI better |
| **Output Viewing** |
| View results | ✅ HTML renderer | ⚠️ Text only | GUI better |
| Interactive editing | ✅ Crop/rotate | ❌ Not available | GUI only |
| Export outputs | ✅ | ✅ | Both functional |

**Strengths of CLI:**
- Automation/scripting
- Batch processing
- No GUI overhead
- Server/headless environments

**Strengths of GUI:**
- Interactive parameter selection
- Visual output preview
- Progress monitoring
- Result editing

---

## TOOL-BY-TOOL CLI ACCESS

### Image Processing Tools

#### 1. crop
**CLI Access:** ✅ `library process --plan Crop --workflow CropTest`
**Parameters:** YAML-configured (contour_template, contour_padding)
**Output Inspection:** ✅ `inspect-outputs` shows cropped images
**Example:**
```bash
briefcase dev -- library process abc123 --plan Crop --workflow CropTest
briefcase dev -- library inspect-outputs abc123
```

#### 2. rotate
**CLI Access:** ✅ `library process --plan Rotate --workflow RotateTest`
**Parameters:** Auto-detected (no configuration needed)
**Output Inspection:** ✅ `inspect-outputs` shows rotated images
**Example:**
```bash
briefcase dev -- library process abc123 --plan Rotate --workflow RotateTest
```

[Continue for all 20 tools...]

---

## CLI USAGE EXAMPLES

### Example 1: Complete Processing Pipeline

```bash
# 1. Create collection
briefcase dev -- library add "My Archive" --type external --source /path/to/scans

# 2. Get collection ID from output
COLLECTION_ID="abc-123-def"

# 3. Add items (optional - auto-discovered from source)
briefcase dev -- library add-item $COLLECTION_ID folder /path/to/scans/box1

# 4. Process with full workflow
briefcase dev -- library process $COLLECTION_ID --plan "Default" --workflow "Default" --verbose

# 5. View outputs
briefcase dev -- library inspect-outputs $COLLECTION_ID

# 6. Export results
briefcase dev -- library export $COLLECTION_ID /path/to/output.zip
```

### Example 2: Single Tool Execution

```bash
# Process with just crop tool
briefcase dev -- library process $COLLECTION_ID --plan "Crop" --workflow "CropTest"

# Process with just transcription
briefcase dev -- library process $COLLECTION_ID --plan "Transcribe" --workflow "TranscribeTest"
```

### Example 3: Direct Folder Processing

```bash
# Process folder without library
briefcase dev -- process /input/folder /output/folder --plan "Enhance" --workflow "EnhanceTest"
```

---

## GAPS & RECOMMENDATIONS

### Current Gaps

1. **No CLI parameter override**
   - Must edit YAML files to change parameters
   - Difficult for quick experiments
   - Recommendation: Add `--param key=value` flag

2. **Limited output inspection**
   - Text-only output viewing
   - No HTML rendering in CLI
   - Recommendation: Add `--format json` option

3. **No interactive mode**
   - Can't select options interactively
   - Everything must be specified upfront
   - Recommendation: Add interactive prompts

4. **Missing documentation**
   - No comprehensive CLI guide
   - Examples scattered
   - Recommendation: Create CLI usage documentation

5. **No progress indicators**
   - Long-running processes appear frozen
   - No ETA display
   - Recommendation: Add progress bars

### Recommended Additions

**High Priority:**
1. Add CLI parameter override:
   ```bash
   briefcase dev -- library process <id> --plan Crop --param contour_padding=50
   ```

2. Add JSON output format:
   ```bash
   briefcase dev -- library inspect-outputs <id> --format json
   ```

3. Create CLI documentation:
   - `docs/CLI_USAGE_GUIDE.md`
   - Command reference
   - Common workflows
   - Troubleshooting

**Medium Priority:**
4. Add interactive mode:
   ```bash
   briefcase dev -- library process <id> --interactive
   # Prompts for plan, workflow, parameters
   ```

5. Add progress indicators:
   ```bash
   Processing: [████████░░] 80% (4/5 steps) - ETA: 2 minutes
   ```

**Low Priority:**
6. Add shell completion:
   - Bash completion script
   - Zsh completion
   - Fish completion

---

## PHASE 5 STATUS

- [x] CLI command structure documented
- [x] Tool access via CLI verified (20/20 tools)
- [x] Parameter configuration method documented
- [x] Output inspection commands audited
- [x] CLI documentation assessed
- [x] GUI vs CLI comparison completed
- [x] Usage examples provided
- [x] Gaps identified with recommendations

**Output:** CLI_INTEGRATION_STATUS.md complete
**Next Phase:** Phase 6 (Implementation - if requested by user)

---

**Generated by:** Claude Code Phase 5 Agent
**Date:** 2025-11-15
**Quality:** Production-ready CLI audit
```

---

## QUALITY CHECKLIST

Before completing, verify:

- [ ] All CLI commands documented
- [ ] Tool access verified for all 20 tools
- [ ] Parameter configuration methods explained
- [ ] Output inspection capabilities described
- [ ] CLI help text assessed
- [ ] GUI vs CLI comparison provided
- [ ] Usage examples included
- [ ] Gaps identified with priorities
- [ ] Status section added to master plan

---

## COMPLETION CRITERIA

**Output file created:** `CLI_INTEGRATION_STATUS.md`

**File contents:**
- CLI command structure
- Tool access documentation
- Parameter configuration analysis
- Output inspection audit
- Help text assessment
- GUI vs CLI comparison
- Usage examples
- Gap analysis with recommendations

**Status update:** Update `TOOL_INTEGRATION_MASTER_PLAN.md`:
```markdown
## CURRENT STATUS

- [x] Phase 0: Architecture investigation complete
- [x] Phase 1: Tool inventory complete
- [x] Phase 2: Renderer audit complete
- [x] Phase 3: GUI integration audit complete
- [x] Phase 4: Workflow audit complete
- [x] Phase 5: CLI integration audit complete
- [ ] Phase 6-7: Documentation and enhancements
```

---

## IMPORTANT NOTES

- **READ-ONLY:** Do not execute CLI commands, only inspect code
- **Code Inspection:** Read CLI command files to understand structure
- **Complete Coverage:** Document access for all 20 tools
- **Practical:** Provide realistic usage examples

---

**When complete, report:** "Phase 5 complete. CLI_INTEGRATION_STATUS.md created with complete audit of CLI integration. All 20 tools accessible via library process command. Parameter configuration and output inspection capabilities documented. Ready to compile final integration report."
