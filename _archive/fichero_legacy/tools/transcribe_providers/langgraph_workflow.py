"""
LangGraph workflow for transcription processing.

Provides a clear, visual workflow definition using LangGraph StateGraph.
This makes the transcription pipeline explicit and easy to understand/modify.

Following Andy's pattern of using LangGraph for workflow clarity.
"""

from typing import TypedDict, List, Dict, Any, Optional
from pathlib import Path
import json
import time
from datetime import datetime

try:
    from langgraph.graph import StateGraph, START, END
    LANGGRAPH_AVAILABLE = True
except ImportError:
    LANGGRAPH_AVAILABLE = False

try:
    from fichero.tools.utils.tool_logger import get_tool_logger
    tool_logger = get_tool_logger('langgraph_workflow')
except ImportError:
    import logging
    tool_logger = logging.getLogger('langgraph_workflow')


class TranscribeState(TypedDict):
    """
    State for transcription workflow.

    This TypedDict defines all data that flows through the workflow nodes.
    """
    # Input
    source_folder: Path
    source_manifest: Path
    output_folder: Path
    provider: Any  # Transcription provider instance
    use_async: bool
    max_concurrent: int
    skip_existing: bool

    # Intermediate
    image_paths: List[Path]
    results: List[Dict[str, Any]]

    # Output
    stats: Dict[str, int]
    output_manifest: Path
    elapsed_time: float
    error: Optional[str]


def load_images_node(state: TranscribeState) -> TranscribeState:
    """
    Load image paths from manifest.

    This node reads the source manifest and extracts all image paths
    that need to be processed.
    """
    tool_logger.info("Node: load_images")

    try:
        source_folder = state['source_folder']
        source_manifest = state['source_manifest']

        # Read manifest
        image_paths = []
        with open(source_manifest, 'r') as f:
            for line in f:
                if line.strip():
                    entry = json.loads(line)
                    if entry.get('type') == 'file' and 'outputs' in entry:
                        # Get first output file
                        img_name = entry['outputs'][0]
                        # Try direct path first, fallback to documents/
                        img_path = source_folder / img_name
                        if not img_path.exists():
                            alt_path = source_folder / "documents" / img_name
                            if alt_path.exists():
                                img_path = alt_path
                        if img_path.exists():
                            image_paths.append(img_path)

        tool_logger.info(f"Loaded {len(image_paths)} images from manifest")

        state['image_paths'] = image_paths
        return state

    except Exception as e:
        error_msg = f"Error loading images: {e}"
        tool_logger.error(error_msg)
        state['error'] = error_msg
        state['image_paths'] = []
        return state


async def process_images_async_node(state: TranscribeState) -> TranscribeState:
    """
    Process images using async batch processor.

    This node uses async/await with semaphores for high-concurrency
    processing (15+ concurrent requests).
    """
    tool_logger.info("Node: process_images_async")

    try:
        from .async_batch_processor import process_batch_async

        start_time = time.time()

        # Process all images
        results = await process_batch_async(
            provider=state['provider'],
            image_paths=state['image_paths'],
            output_folder=state['output_folder'],
            max_concurrent=state['max_concurrent'],
            skip_existing=state['skip_existing']
        )

        elapsed = time.time() - start_time

        tool_logger.info(f"Processed {len(results)} images in {elapsed:.2f}s")

        state['results'] = results
        state['elapsed_time'] = elapsed
        return state

    except Exception as e:
        error_msg = f"Error processing images: {e}"
        tool_logger.error(error_msg)
        state['error'] = error_msg
        state['results'] = []
        return state


def process_images_sync_node(state: TranscribeState) -> TranscribeState:
    """
    Process images using sync ThreadPoolExecutor.

    This node uses traditional thread-based parallelism for providers
    that don't support async processing.
    """
    tool_logger.info("Node: process_images_sync")

    try:
        from concurrent.futures import ThreadPoolExecutor
        import time

        start_time = time.time()

        provider = state['provider']
        image_paths = state['image_paths']
        output_folder = state['output_folder']
        skip_existing = state['skip_existing']
        max_workers = min(state['max_concurrent'], 5)  # Limit for thread pool

        # Filter existing
        images_to_process = []
        for img_path in image_paths:
            if skip_existing:
                output_txt = output_folder / "documents" / img_path.with_suffix('.txt').name
                if output_txt.exists():
                    continue
            images_to_process.append(img_path)

        tool_logger.info(f"Processing {len(images_to_process)} images with {max_workers} workers")

        # Process with ThreadPoolExecutor
        results = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(provider.process_image, img_path)
                for img_path in images_to_process
            ]

            for future in futures:
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    tool_logger.error(f"Task failed: {e}")
                    results.append({
                        "text": "",
                        "success": False,
                        "error": str(e),
                        "details": {}
                    })

        elapsed = time.time() - start_time

        tool_logger.info(f"Processed {len(results)} images in {elapsed:.2f}s")

        state['results'] = results
        state['elapsed_time'] = elapsed
        return state

    except Exception as e:
        error_msg = f"Error processing images: {e}"
        tool_logger.error(error_msg)
        state['error'] = error_msg
        state['results'] = []
        return state


def save_results_node(state: TranscribeState) -> TranscribeState:
    """
    Save transcription results to files and manifest.

    This node writes output .txt files and creates the output manifest.
    """
    tool_logger.info("Node: save_results")

    try:
        output_folder = state['output_folder']
        results = state['results']
        image_paths = state['image_paths']

        # Create output directories
        output_docs = output_folder / "documents"
        output_docs.mkdir(parents=True, exist_ok=True)

        # Save transcriptions
        manifest_entries = []
        processed = 0
        failed = 0
        skipped = 0

        for i, result in enumerate(results):
            if i >= len(image_paths):
                break

            img_path = image_paths[i]
            output_txt = output_docs / img_path.with_suffix('.txt').name

            if result.get('skipped'):
                skipped += 1
                continue

            if result.get('success'):
                # Save transcription
                output_txt.write_text(result['text'], encoding='utf-8')
                processed += 1

                # Add to manifest
                manifest_entries.append({
                    "source": img_path.name,
                    "outputs": [output_txt.name],
                    "type": "transcription",
                    "details": result.get('details', {})
                })
            else:
                failed += 1

        # Write manifest
        output_manifest = output_folder / "transcriptions_manifest.jsonl"
        with open(output_manifest, 'w') as f:
            for entry in manifest_entries:
                f.write(json.dumps(entry) + '\n')

        tool_logger.info(f"Saved {processed} transcriptions to {output_folder}")

        state['output_manifest'] = output_manifest
        state['stats'] = {
            'total': len(image_paths),
            'processed': processed,
            'failed': failed,
            'skipped': skipped
        }

        return state

    except Exception as e:
        error_msg = f"Error saving results: {e}"
        tool_logger.error(error_msg)
        state['error'] = error_msg
        return state


def build_transcribe_workflow(use_async: bool = True) -> StateGraph:
    """
    Build the transcription workflow graph.

    This creates a StateGraph with nodes for each processing step.
    The graph can be visualized and modified easily.

    Args:
        use_async: Use async processing node if True, else sync

    Returns:
        StateGraph for transcription
    """
    if not LANGGRAPH_AVAILABLE:
        raise ImportError("LangGraph not available. Install with: pip install langgraph")

    # Create graph
    workflow = StateGraph(TranscribeState)

    # Add nodes
    workflow.add_node("load_images", load_images_node)

    if use_async:
        workflow.add_node("process_images", process_images_async_node)
    else:
        workflow.add_node("process_images", process_images_sync_node)

    workflow.add_node("save_results", save_results_node)

    # Define edges
    workflow.add_edge(START, "load_images")
    workflow.add_edge("load_images", "process_images")
    workflow.add_edge("process_images", "save_results")
    workflow.add_edge("save_results", END)

    return workflow


async def run_transcribe_workflow_async(
    source_folder: Path,
    source_manifest: Path,
    output_folder: Path,
    provider: Any,
    max_concurrent: int = 15,
    skip_existing: bool = True
) -> Dict[str, Any]:
    """
    Run transcription workflow with async processing.

    Args:
        source_folder: Folder with source images
        source_manifest: Path to source manifest
        output_folder: Output folder for transcriptions
        provider: Transcription provider instance
        max_concurrent: Maximum concurrent requests
        skip_existing: Skip existing output files

    Returns:
        Stats dictionary
    """
    tool_logger.info("Running async transcription workflow")

    # Build workflow
    workflow = build_transcribe_workflow(use_async=True)
    app = workflow.compile()

    # Initial state
    initial_state = {
        'source_folder': source_folder,
        'source_manifest': source_manifest,
        'output_folder': output_folder,
        'provider': provider,
        'use_async': True,
        'max_concurrent': max_concurrent,
        'skip_existing': skip_existing,
        'image_paths': [],
        'results': [],
        'stats': {},
        'output_manifest': None,
        'elapsed_time': 0.0,
        'error': None
    }

    # Run workflow
    final_state = await app.ainvoke(initial_state)

    # Return stats
    return {
        'stats': final_state.get('stats', {}),
        'output_manifest': final_state.get('output_manifest'),
        'elapsed_time': final_state.get('elapsed_time', 0.0),
        'error': final_state.get('error')
    }


def run_transcribe_workflow_sync(
    source_folder: Path,
    source_manifest: Path,
    output_folder: Path,
    provider: Any,
    max_concurrent: int = 5,
    skip_existing: bool = True
) -> Dict[str, Any]:
    """
    Run transcription workflow with sync processing.

    Args:
        source_folder: Folder with source images
        source_manifest: Path to source manifest
        output_folder: Output folder for transcriptions
        provider: Transcription provider instance
        max_concurrent: Maximum concurrent threads
        skip_existing: Skip existing output files

    Returns:
        Stats dictionary
    """
    tool_logger.info("Running sync transcription workflow")

    # Build workflow
    workflow = build_transcribe_workflow(use_async=False)
    app = workflow.compile()

    # Initial state
    initial_state = {
        'source_folder': source_folder,
        'source_manifest': source_manifest,
        'output_folder': output_folder,
        'provider': provider,
        'use_async': False,
        'max_concurrent': max_concurrent,
        'skip_existing': skip_existing,
        'image_paths': [],
        'results': [],
        'stats': {},
        'output_manifest': None,
        'elapsed_time': 0.0,
        'error': None
    }

    # Run workflow
    final_state = app.invoke(initial_state)

    # Return stats
    return {
        'stats': final_state.get('stats', {}),
        'output_manifest': final_state.get('output_manifest'),
        'elapsed_time': final_state.get('elapsed_time', 0.0),
        'error': final_state.get('error')
    }
