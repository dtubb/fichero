#!/usr/bin/env python3
"""
Test script for LangGraph transcription workflow.

This demonstrates how to run the LangGraph workflow for transcription.

Usage:
    # From the fichero directory:
    PYTHONPATH=src python sample_code/test_langgraph_workflow.py

    # Or with a specific folder:
    PYTHONPATH=src python sample_code/test_langgraph_workflow.py /path/to/project

Requirements:
    - pip install langgraph
    - DASHSCOPE_API_KEY environment variable set
"""

import asyncio
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


def test_langgraph_availability():
    """Check if LangGraph is available."""
    print("=" * 60)
    print("Testing LangGraph Availability")
    print("=" * 60)

    try:
        from langgraph.graph import StateGraph, START, END
        print("✅ LangGraph is installed and importable")
        return True
    except ImportError as e:
        print(f"❌ LangGraph not available: {e}")
        print("   Install with: pip install langgraph")
        return False


def test_workflow_import():
    """Test importing the workflow module."""
    print("\n" + "=" * 60)
    print("Testing Workflow Import")
    print("=" * 60)

    try:
        from fichero.tools.transcribe_providers.langgraph_workflow import (
            build_transcribe_workflow,
            run_transcribe_workflow_async,
            run_transcribe_workflow_sync,
            LANGGRAPH_AVAILABLE
        )
        print(f"✅ Workflow module imported")
        print(f"   LANGGRAPH_AVAILABLE: {LANGGRAPH_AVAILABLE}")
        return True
    except ImportError as e:
        print(f"❌ Failed to import workflow: {e}")
        return False


def test_build_workflow():
    """Test building the workflow graph."""
    print("\n" + "=" * 60)
    print("Testing Workflow Build")
    print("=" * 60)

    try:
        from fichero.tools.transcribe_providers.langgraph_workflow import (
            build_transcribe_workflow,
            LANGGRAPH_AVAILABLE
        )

        if not LANGGRAPH_AVAILABLE:
            print("❌ LangGraph not available, skipping")
            return False

        # Build async workflow
        workflow_async = build_transcribe_workflow(use_async=True)
        print(f"✅ Async workflow built: {type(workflow_async)}")

        # Build sync workflow
        workflow_sync = build_transcribe_workflow(use_async=False)
        print(f"✅ Sync workflow built: {type(workflow_sync)}")

        # Compile to runnable
        app = workflow_async.compile()
        print(f"✅ Compiled to runnable app: {type(app)}")

        # Print workflow structure
        print("\n📊 Workflow Structure:")
        print("   START → load_images → process_images → save_results → END")

        return True

    except Exception as e:
        print(f"❌ Failed to build workflow: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_provider_creation():
    """Test creating a transcription provider."""
    print("\n" + "=" * 60)
    print("Testing Provider Creation")
    print("=" * 60)

    try:
        from fichero.tools.transcribe import ProviderFactory
        from fichero.tools.utils.api_keys import get_qwen_key

        # Check API key
        api_key = get_qwen_key()
        if not api_key:
            print("⚠️  DASHSCOPE_API_KEY not set")
            print("   Set it in .env or environment")
            return False

        print(f"✅ API key found: {api_key[:8]}...")

        # Create provider
        provider = ProviderFactory.create(
            "dashscope",
            model="qwen-vl-ocr",
            api_key=api_key
        )
        print(f"✅ Provider created: {provider.name}")
        print(f"   Model: {provider.model}")
        print(f"   Supports async: {provider.supports_async}")

        return provider

    except Exception as e:
        print(f"❌ Failed to create provider: {e}")
        import traceback
        traceback.print_exc()
        return None


async def test_workflow_run(project_folder: Path = None):
    """Test running the complete workflow."""
    print("\n" + "=" * 60)
    print("Testing Workflow Execution")
    print("=" * 60)

    # Use sample folder if not specified
    if project_folder is None:
        # Look for a test project
        test_paths = [
            Path("projects/demo"),
            Path("projects/test"),
            Path("sample_projects/demo"),
        ]
        for test_path in test_paths:
            if test_path.exists():
                project_folder = test_path
                break

    if project_folder is None or not project_folder.exists():
        print("⚠️  No project folder found for testing")
        print("   Create a project with documents/ folder and manifest")
        print("   Or specify a path: python test_langgraph_workflow.py /path/to/project")
        return False

    print(f"📂 Project folder: {project_folder}")

    # Check for required files
    documents_folder = project_folder / "documents"
    manifest_path = project_folder / "assets" / "manifests" / "documents_manifest.jsonl"

    if not documents_folder.exists():
        print(f"⚠️  No documents/ folder in {project_folder}")
        return False

    if not manifest_path.exists():
        print(f"⚠️  No manifest at {manifest_path}")
        print("   Run build_documents_manifest first")
        return False

    print(f"✅ Documents folder: {documents_folder}")
    print(f"✅ Manifest: {manifest_path}")

    # Create provider
    provider = test_provider_creation()
    if not provider:
        return False

    # Import workflow
    from fichero.tools.transcribe_providers.langgraph_workflow import (
        run_transcribe_workflow_async
    )

    # Setup output folder
    output_folder = project_folder / "assets" / "transcriptions_langgraph"
    output_folder.mkdir(parents=True, exist_ok=True)
    print(f"📤 Output folder: {output_folder}")

    # Run workflow
    print("\n🚀 Running async LangGraph workflow...")
    print("-" * 40)

    try:
        result = await run_transcribe_workflow_async(
            source_folder=documents_folder,
            source_manifest=manifest_path,
            output_folder=output_folder,
            provider=provider,
            max_concurrent=5,  # Conservative for testing
            skip_existing=True
        )

        print("-" * 40)
        print("\n📊 Results:")
        print(f"   Stats: {result.get('stats', {})}")
        print(f"   Elapsed: {result.get('elapsed_time', 0):.2f}s")
        print(f"   Output manifest: {result.get('output_manifest')}")

        if result.get('error'):
            print(f"   ⚠️  Error: {result['error']}")

        return True

    except Exception as e:
        print(f"❌ Workflow execution failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("LangGraph Workflow Test Suite")
    print("=" * 60)

    # Parse arguments
    project_folder = None
    if len(sys.argv) > 1:
        project_folder = Path(sys.argv[1])
        if not project_folder.exists():
            print(f"❌ Project folder not found: {project_folder}")
            sys.exit(1)

    # Run tests
    results = {
        "langgraph_available": test_langgraph_availability(),
        "workflow_import": test_workflow_import(),
        "workflow_build": test_build_workflow(),
    }

    # Run async workflow test
    if all(results.values()):
        results["workflow_run"] = asyncio.run(test_workflow_run(project_folder))

    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status}: {name}")

    print(f"\n  Total: {passed}/{total} passed")

    if passed == total:
        print("\n🎉 All tests passed!")
    else:
        print("\n⚠️  Some tests failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
