# Workflow Chaining Design

## Problem Statement

Users want to incrementally process items in quick steps:
1. First run: Crop images → output to `assets/crops`
2. Second run: Use `assets/crops` as input, run Rotate → output to `assets/rotated`
3. Third run: Use `assets/rotated` as input, run Split → output to `assets/split`
4. And so on...

**Current limitation**: Each quick tool (`Crop.yml`, `Rotate.yml`, `Split.yml`) always starts from `documents` folder and can't use previous outputs.

## Requirements

From user: "you shpuld be able to give the previous output folder as the new input folder, and then ask it to do all the preuvosu steps, and then ew one."

Translation:
- Use previous step's output as next step's input
- Optionally re-run all previous steps + new one (full pipeline mode)
- Quick tools menu should support this automatically

## Architecture Options

### Option 1: Dynamic Plan Generation ⭐ RECOMMENDED
Generate temporary plan files that chain from the last output.

**How it works**:
1. User clicks "Crop Images" → runs Crop.yml normally
2. Item metadata stores: `last_output_folder='assets/crops'`, `last_manifest='assets/crops/crop_manifest.jsonl'`, `completed_steps=['crop']`
3. User clicks "Rotate Images" → system detects previous output
4. Generate temporary `Rotate_Chained.yml` that uses `assets/crops` as source
5. Run workflow with chained plan
6. Update metadata: `last_output_folder='assets/rotated'`, `completed_steps=['crop', 'rotate']`

**Advantages**:
- No changes to existing plans
- Works with current Director system
- Clear separation: base plans vs chained plans

**Implementation**:
```python
# In DirectorIntegrationService or new ChainManager
class WorkflowChainer:
    def create_chained_plan(
        self,
        item: CollectionItem,
        next_tool: str  # 'crop', 'rotate', 'split', etc.
    ) -> str:
        """
        Creates temporary chained plan based on item's processing history.

        Returns path to generated plan file.
        """
        # Get last output from metadata
        last_output = item.metadata.get('director_output_path', 'documents')
        last_manifest = item.metadata.get('director_manifest_path', 'assets/manifests/documents_manifest.jsonl')

        # Load base plan for next_tool
        base_plan = self.load_plan(f'{next_tool}.yml')

        # Modify command args to use last_output as source
        chained_plan = base_plan.copy()
        for cmd in chained_plan['commands']:
            if cmd['name'] == next_tool:
                cmd['args']['source_folder'] = last_output
                cmd['args']['source_manifest'] = last_manifest

        # Write temporary plan
        temp_path = f'/tmp/fichero_chained_{item.id}_{next_tool}.yml'
        self.write_plan(temp_path, chained_plan)

        return temp_path
```

### Option 2: Smart Source Detection
Modify each tool to auto-detect if previous output exists.

**How it works**:
- Each tool checks for `assets/rotated`, `assets/crops`, etc.
- Uses most recent folder as source if found
- Falls back to `documents` if none found

**Advantages**:
- Automatic chaining
- No plan generation

**Disadvantages**:
- Tools need modification
- Less explicit/predictable
- Harder to debug

### Option 3: Progressive Workflows
Single plan with all steps, run incrementally.

**How it works**:
- User runs workflow with `--start-from=rotate` flag
- Director skips completed steps

**Disadvantages**:
- Requires Director changes
- Complex state management

## Recommended Implementation: Option 1

### Phase 1: Core Chaining System

**File**: `src/fichero/library/workflow_chainer.py`

```python
"""
Workflow Chaining System

Enables incremental processing by chaining tool outputs.
"""

import logging
import yaml
from pathlib import Path
from typing import Dict, Any, Optional, List

from .models import CollectionItem
from ..config import ConfigManager

logger = logging.getLogger(__name__)


class WorkflowChainer:
    """
    Manages workflow chaining for incremental processing.

    Tracks processing history and generates chained plans
    that use previous outputs as inputs.
    """

    def __init__(self, config_manager: ConfigManager):
        self.config_manager = config_manager
        self.temp_dir = Path('/tmp/fichero_chained_plans')
        self.temp_dir.mkdir(exist_ok=True)

    def get_last_output(self, item: CollectionItem) -> Dict[str, str]:
        """
        Get the last processing output for an item.

        Returns dict with 'folder' and 'manifest' paths.
        """
        metadata = item.metadata

        return {
            'folder': metadata.get('director_output_path', 'documents'),
            'manifest': metadata.get('director_manifest_path', 'assets/manifests/documents_manifest.jsonl'),
            'step': metadata.get('director_last_step', None)
        }

    def update_output_tracking(
        self,
        item: CollectionItem,
        output_folder: str,
        manifest_path: str,
        step_name: str
    ):
        """
        Update item metadata with latest output location.

        This is called after successful workflow completion.
        """
        if 'completed_steps' not in item.metadata:
            item.metadata['completed_steps'] = []

        item.metadata['completed_steps'].append(step_name)
        item.metadata['director_output_path'] = output_folder
        item.metadata['director_manifest_path'] = manifest_path
        item.metadata['director_last_step'] = step_name

    def create_chained_plan(
        self,
        base_plan_name: str,
        workflow_name: str,
        source_folder: str,
        source_manifest: str,
        output_suffix: str = ''
    ) -> str:
        """
        Create a temporary chained plan file.

        Args:
            base_plan_name: Name of base plan (e.g., 'Crop', 'Rotate')
            workflow_name: Workflow to run (e.g., 'CropTest')
            source_folder: Previous output folder to use as input
            source_manifest: Previous manifest to use as input
            output_suffix: Optional suffix for output folder (for versioning)

        Returns:
            Path to generated temporary plan file
        """
        # Load base plan
        base_plan_path = self.config_manager.get_plan_path(f'{base_plan_name}.yml')

        with open(base_plan_path, 'r') as f:
            plan_data = yaml.safe_load(f)

        # Find the workflow
        if workflow_name not in plan_data.get('workflows', {}):
            raise ValueError(f"Workflow '{workflow_name}' not found in plan '{base_plan_name}'")

        workflow_steps = plan_data['workflows'][workflow_name]

        # Modify all commands in the workflow to use chained source
        for cmd in plan_data.get('commands', []):
            if cmd['name'] in workflow_steps:
                # Skip manifest builders - they always use original documents
                if 'build_documents_manifest' in cmd['name']:
                    continue

                # Update source folder and manifest
                if 'source_folder' in cmd['args']:
                    cmd['args']['source_folder'] = source_folder

                if 'source_manifest' in cmd['args']:
                    cmd['args']['source_manifest'] = source_manifest

                # Update output folder with suffix if provided
                if output_suffix and 'output_folder' in cmd['args']:
                    original_output = cmd['args']['output_folder']
                    cmd['args']['output_folder'] = f"{original_output}{output_suffix}"

        # Write temporary plan
        temp_plan_name = f"{base_plan_name}_Chained_{output_suffix or 'tmp'}.yml"
        temp_plan_path = self.temp_dir / temp_plan_name

        with open(temp_plan_path, 'w') as f:
            yaml.dump(plan_data, f, default_flow_style=False, allow_unicode=True)

        logger.info(f"Created chained plan: {temp_plan_path}")
        logger.info(f"  Source folder: {source_folder}")
        logger.info(f"  Source manifest: {source_manifest}")

        return str(temp_plan_path)

    def should_chain(self, item: CollectionItem) -> bool:
        """
        Determine if item has previous processing that can be chained.
        """
        return (
            'director_output_path' in item.metadata and
            item.metadata['director_output_path'] != 'documents'
        )
```

### Phase 2: Integration with Quick Tools

Modify `collection_view.py` to use chaining:

```python
async def _on_quick_process(self, plan_name: str, workflow_name: str):
    """Quick process handler with workflow chaining support"""
    # ... existing code to get item_ids ...

    # Get first item to check for chaining
    if item_ids:
        first_item = self.app.library_manager.get_item(item_ids[0])

        # Check if we should chain
        if self.app.workflow_chainer.should_chain(first_item):
            last_output = self.app.workflow_chainer.get_last_output(first_item)

            # Generate chained plan
            chained_plan_path = self.app.workflow_chainer.create_chained_plan(
                base_plan_name=plan_name,
                workflow_name=workflow_name,
                source_folder=last_output['folder'],
                source_manifest=last_output['manifest']
            )

            # Use chained plan instead
            plan_name = chained_plan_path

    # Process with (possibly chained) plan
    task_ids = await self.app.director_integration.process_items(
        collection_id=self.collection_id,
        item_ids=item_ids,
        plan_name=plan_name,
        workflow_name=workflow_name
    )
```

### Phase 3: Update Metadata After Processing

Modify `DirectorIntegrationService` to update metadata:

```python
async def process_items(self, ...):
    # ... existing processing code ...

    # After workflow completes successfully
    for item_id in item_ids:
        item = self.library_manager.get_item(item_id)

        # Determine output folder from workflow
        # (This requires parsing plan to find output_folder)
        output_folder = self._get_workflow_output_folder(plan_name, workflow_name)
        manifest_path = f"{output_folder}/{workflow_name}_manifest.jsonl"

        # Update tracking
        self.app.workflow_chainer.update_output_tracking(
            item=item,
            output_folder=output_folder,
            manifest_path=manifest_path,
            step_name=workflow_name.lower()
        )

        # Save updated item
        self.library_manager.update_item(item)
```

## Available Tools for Quick Menu

Based on existing plans, we should create quick tools for:

1. ✅ **Crop** - Document cropping
2. ✅ **Rotate** - Image rotation
3. ✅ **Split** - Split double-page images
4. **Enhance** - Image quality enhancement
5. **Remove Background** - Background removal
6. **Transcribe** - OCR/transcription
7. **Catalogue** - LLM cataloguing
8. **Convert to Word** - Generate Word docs

Each tool needs:
- Base plan YAML file (like `Crop.yml`)
- Menu command in collection_view.py
- Handler method (`_on_quick_process_xxx`)

## Testing Plan

1. Create item with document
2. Run "Crop Images" → Check `assets/crops` created
3. Run "Rotate Images" → Should use `assets/crops` as input
4. Verify `assets/rotated` exists
5. Run "Split Images" → Should use `assets/rotated` as input
6. Verify metadata tracking

## Migration Notes

Existing items won't have metadata tracking. Options:
- Auto-detect by scanning `assets/` folders (find most recent)
- Start fresh (no chaining for old items)
- Provide "Detect Previous Processing" button

## Implementation Order

1. ✅ Fix async menu execution (completed)
2. ✅ Rename to "Toolks" (completed)
3. Create `WorkflowChainer` class
4. Add chaining to `_on_quick_process`
5. Add metadata update to `DirectorIntegrationService`
6. Test with Crop → Rotate → Split chain
7. Add remaining quick tools (Enhance, Remove Background, etc.)
8. Add UI indicator showing last processed step
9. Add "Reset Chain" option to start from documents again

## Future Enhancements

- **Chain Visualization**: Show processing pipeline in UI
- **Branching**: Allow multiple output paths (e.g., try different enhance settings)
- **Rollback**: Undo last step, go back to previous output
- **Batch Chaining**: Chain different tools for different items
- **Auto-Chain**: Automatically detect optimal next step
