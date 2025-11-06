#!/usr/bin/env python3
"""
Test script for renderer system.

Tests CropRenderer and RotateRenderer with CLI and HTML rendering.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from fichero.library.renderers.base_renderer import RenderContext
from fichero.library.renderers.renderer_registry import RendererRegistry


def test_crop_renderer_cli():
    """Test CropRenderer CLI rendering"""
    print("=" * 70)
    print("TEST: CropRenderer CLI Rendering")
    print("=" * 70)
    print()

    # Create render context for crop step
    context = RenderContext(
        item_id="test-item-123",
        step_index=1,
        step_name="crop",
        tool_name="crop",
        file_path=Path("/path/to/cropped/image.jpg"),
        file_type="image",
        manifest_entry={
            "path": "cropped/image.jpg",
            "type": "file",
            "crop_box": {
                "x": 100,
                "y": 50,
                "width": 800,
                "height": 600
            },
            "padding": 30,
            "method": "contour",
            "template": "auto"
        },
        show_metadata=True,
        show_content=True,
        interactive=False  # CLI rendering
    )

    # Get crop renderer
    renderer = RendererRegistry.get_renderer('crop')

    if not renderer:
        print("❌ FAIL: Could not get CropRenderer")
        return False

    print(f"✅ Got renderer: {renderer.__class__.__name__}")
    print()

    # Render CLI
    try:
        output = renderer.render_cli(context)

        if output.is_error:
            print(f"❌ FAIL: Renderer error: {output.error}")
            return False

        print("CLI Output:")
        print("-" * 70)
        print(output.text)
        print("-" * 70)
        print()

        # Test get_editable_json
        json_data = renderer.get_editable_json(context)
        print("Editable JSON:")
        print("-" * 70)
        import json
        print(json.dumps(json_data, indent=2))
        print("-" * 70)
        print()

        # Test validation
        is_valid, error = renderer.validate_json(json_data)
        if is_valid:
            print("✅ JSON validation passed")
        else:
            print(f"❌ JSON validation failed: {error}")

        print()
        print("✅ CropRenderer CLI test passed")
        return True

    except Exception as e:
        print(f"❌ FAIL: Exception: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_crop_renderer_html():
    """Test CropRenderer HTML rendering"""
    print("=" * 70)
    print("TEST: CropRenderer HTML Rendering")
    print("=" * 70)
    print()

    # Create render context for crop step
    context = RenderContext(
        item_id="test-item-123",
        step_index=1,
        step_name="crop",
        tool_name="crop",
        file_path=Path("/Users/dtubb/Library/Application Support/ca.tubb.fichero/library/collections/24401cf5-79f2-4255-9b4f-21f6521ec1d0/outputs/2025-11-03_19-11-18/CropTest/EAP1740_NP_T19_1700_001_01.tif/assets/cropped/EAP1740_NP_T19_1700_001_01.jpg"),
        file_type="image",
        manifest_entry={
            "path": "cropped/EAP1740_NP_T19_1700_001_01.jpg",
            "type": "file",
            "crop_box": {
                "x": 100,
                "y": 50,
                "width": 800,
                "height": 600
            },
            "padding": 30,
            "method": "contour",
            "template": "auto"
        },
        show_metadata=True,
        show_content=True,
        interactive=True  # GUI rendering
    )

    # Get crop renderer
    renderer = RendererRegistry.get_renderer('crop')

    if not renderer:
        print("❌ FAIL: Could not get CropRenderer")
        return False

    print(f"✅ Got renderer: {renderer.__class__.__name__}")
    print()

    # Render HTML
    try:
        output = renderer.render_html(context)

        if output.is_error:
            print(f"❌ FAIL: Renderer error: {output.error}")
            return False

        print(f"HTML Output: {len(output.html)} bytes")
        print(f"Title: {output.title}")
        print(f"Description: {output.description}")
        print()

        # Check HTML contains expected elements
        checks = [
            ("<!DOCTYPE html>", "DOCTYPE declaration"),
            ("<html>", "HTML tag"),
            ("function zoomIn()", "Zoom function"),
            ("function rotateLeft()", "Rotate function"),
        ]

        all_passed = True
        for check_str, check_name in checks:
            if check_str in output.html:
                print(f"✅ {check_name} found")
            else:
                print(f"❌ {check_name} NOT found")
                all_passed = False

        print()
        if all_passed:
            print("✅ CropRenderer HTML test passed")
            return True
        else:
            print("❌ CropRenderer HTML test FAILED")
            return False

    except Exception as e:
        print(f"❌ FAIL: Exception: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_renderer_registry():
    """Test RendererRegistry"""
    print("=" * 70)
    print("TEST: RendererRegistry")
    print("=" * 70)
    print()

    # Test registered tools
    tools = RendererRegistry.list_registered_tools()
    print(f"Registered tools: {tools}")

    if 'crop' in tools:
        print("✅ 'crop' tool registered")
    else:
        print("❌ 'crop' tool NOT registered")
        return False

    if 'rotate' in tools:
        print("✅ 'rotate' tool registered")
    else:
        print("❌ 'rotate' tool NOT registered")
        return False

    # Test registered types
    types = RendererRegistry.list_registered_types()
    print(f"Registered types: {types}")

    if 'image' in types:
        print("✅ 'image' type registered")
    else:
        print("❌ 'image' type NOT registered")
        return False

    print()

    # Test get_renderer_for_step with fallback
    print("Testing get_renderer_for_step:")
    print()

    # Test 1: crop tool (should get CropRenderer)
    renderer = RendererRegistry.get_renderer_for_step('crop', 'image')
    print(f"  crop tool → {renderer.__class__.__name__}")
    if renderer.__class__.__name__ == 'CropRenderer':
        print("  ✅ Correct renderer")
    else:
        print("  ❌ Wrong renderer")
        return False

    # Test 2: rotate tool (should get RotateRenderer)
    renderer = RendererRegistry.get_renderer_for_step('rotate', 'image')
    print(f"  rotate tool → {renderer.__class__.__name__}")
    if renderer.__class__.__name__ == 'RotateRenderer':
        print("  ✅ Correct renderer")
    else:
        print("  ❌ Wrong renderer")
        return False

    # Test 3: unknown tool, image type (should get ImageRenderer)
    renderer = RendererRegistry.get_renderer_for_step('unknown_tool', 'image')
    print(f"  unknown_tool + image → {renderer.__class__.__name__}")
    if renderer.__class__.__name__ == 'ImageRenderer':
        print("  ✅ Correct fallback")
    else:
        print("  ❌ Wrong fallback")
        return False

    # Test 4: unknown tool, unknown type (should get FallbackRenderer)
    renderer = RendererRegistry.get_renderer_for_step('unknown_tool', 'unknown_type')
    print(f"  unknown_tool + unknown_type → {renderer.__class__.__name__}")
    if renderer.__class__.__name__ == 'FallbackRenderer':
        print("  ✅ Correct fallback")
    else:
        print("  ❌ Wrong fallback")
        return False

    print()
    print("✅ RendererRegistry test passed")
    return True


def test_enhance_renderer_cli():
    """Test EnhanceRenderer CLI rendering"""
    print("=" * 70)
    print("TEST: EnhanceRenderer CLI Rendering")
    print("=" * 70)
    print()

    # Create render context for enhance step
    context = RenderContext(
        item_id="test-item-123",
        step_index=1,
        step_name="enhance",
        tool_name="enhance",
        file_path=Path("/path/to/enhanced/image.jpg"),
        file_type="image",
        manifest_entry={
            "path": "enhanced/image.jpg",
            "type": "file",
            "contrast": 1.5,
            "brightness": 1.1,
            "sharpness": 1.2,
            "method": "auto"
        },
        show_metadata=True,
        show_content=True,
        interactive=False
    )

    # Get enhance renderer
    renderer = RendererRegistry.get_renderer('enhance')

    if not renderer:
        print("❌ FAIL: Could not get EnhanceRenderer")
        return False

    print(f"✅ Got renderer: {renderer.__class__.__name__}")
    print()

    # Render CLI
    try:
        output = renderer.render_cli(context)

        if output.is_error:
            print(f"❌ FAIL: Renderer error: {output.error}")
            return False

        print("CLI Output:")
        print("-" * 70)
        print(output.text)
        print("-" * 70)
        print()

        # Test get_editable_json
        json_data = renderer.get_editable_json(context)
        print("Editable JSON:")
        print("-" * 70)
        import json
        print(json.dumps(json_data, indent=2))
        print("-" * 70)
        print()

        # Test validation
        is_valid, error = renderer.validate_json(json_data)
        if is_valid:
            print("✅ JSON validation passed")
        else:
            print(f"❌ JSON validation failed: {error}")

        print()
        print("✅ EnhanceRenderer CLI test passed")
        return True

    except Exception as e:
        print(f"❌ FAIL: Exception: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests"""
    print()
    print("╔" + "═" * 68 + "╗")
    print("║" + " " * 20 + "RENDERER SYSTEM TESTS" + " " * 27 + "║")
    print("╚" + "═" * 68 + "╝")
    print()

    results = []

    # Test 1: RendererRegistry
    results.append(("RendererRegistry", test_renderer_registry()))
    print()

    # Test 2: CropRenderer CLI
    results.append(("CropRenderer CLI", test_crop_renderer_cli()))
    print()

    # Test 3: CropRenderer HTML
    results.append(("CropRenderer HTML", test_crop_renderer_html()))
    print()

    # Test 4: EnhanceRenderer CLI
    results.append(("EnhanceRenderer CLI", test_enhance_renderer_cli()))
    print()

    # Summary
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print()

    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")

    print()
    all_passed = all(result for _, result in results)
    if all_passed:
        print("✅ ALL TESTS PASSED")
        return 0
    else:
        print("❌ SOME TESTS FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
