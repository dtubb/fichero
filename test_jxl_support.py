#!/usr/bin/env python3
"""
Test script to verify JPEG XL support in Fichero
"""

import subprocess
import shutil
from pathlib import Path
from PIL import Image
import numpy as np

def check_jxl_tools():
    """Check if JXL tools are installed"""
    cjxl_installed = shutil.which('cjxl') is not None
    djxl_installed = shutil.which('djxl') is not None
    
    print("JXL Tools Status:")
    print(f"  cjxl (encoder): {'✓ Installed' if cjxl_installed else '✗ Not installed'}")
    print(f"  djxl (decoder): {'✓ Installed' if djxl_installed else '✗ Not installed'}")
    
    if not cjxl_installed or not djxl_installed:
        print("\nTo install JXL tools:")
        print("  macOS: brew install libjxl")
        print("  Ubuntu/Debian: apt-get install libjxl-tools")
        print("  Windows: Download from https://github.com/libjxl/libjxl/releases")
    
    return cjxl_installed and djxl_installed

def test_jxl_conversion():
    """Test JXL conversion with a sample image"""
    if not check_jxl_tools():
        print("\nSkipping conversion test - JXL tools not installed")
        return False
    
    print("\nTesting JXL conversion:")
    
    # Create a test image with transparency
    test_img = Image.new('RGBA', (100, 100), (255, 0, 0, 255))
    # Add transparent area
    pixels = np.array(test_img)
    pixels[25:75, 25:75, 3] = 128  # Semi-transparent center
    test_img = Image.fromarray(pixels)
    
    # Save as PNG
    test_png = Path("test_image.png")
    test_img.save(test_png)
    print(f"  Created test PNG: {test_png}")
    
    # Convert to JXL
    test_jxl = Path("test_image.jxl")
    cmd = ['cjxl', str(test_png), str(test_jxl), '-e', '7', '-d', '0']
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode == 0:
        print(f"  ✓ Converted to JXL: {test_jxl}")
        png_size = test_png.stat().st_size
        jxl_size = test_jxl.stat().st_size
        print(f"  Size comparison: PNG={png_size} bytes, JXL={jxl_size} bytes")
        print(f"  Compression ratio: {(1 - jxl_size/png_size)*100:.1f}% smaller")
        
        # Test decoding
        decoded_png = Path("test_decoded.png")
        cmd = ['djxl', str(test_jxl), str(decoded_png)]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            print(f"  ✓ Decoded JXL back to PNG: {decoded_png}")
            
            # Verify transparency preserved
            decoded_img = Image.open(decoded_png)
            if decoded_img.mode == 'RGBA':
                print("  ✓ Transparency preserved in JXL")
            else:
                print("  ✗ Transparency lost in JXL conversion")
        else:
            print(f"  ✗ Failed to decode JXL: {result.stderr}")
    else:
        print(f"  ✗ Failed to convert to JXL: {result.stderr}")
    
    # Cleanup
    for f in [test_png, test_jxl]:
        if f.exists():
            f.unlink()
    if 'decoded_png' in locals() and decoded_png.exists():
        decoded_png.unlink()
    
    return True

def test_project_config():
    """Test project.yml configuration"""
    print("\nChecking project.yml configuration:")
    
    project_yml = Path("project.yml")
    if project_yml.exists():
        content = project_yml.read_text()
        if 'background_removed_format:' in content:
            print("  ✓ background_removed_format variable found in project.yml")
            if '--format "${vars.background_removed_format}"' in content:
                print("  ✓ Format parameter correctly added to remove_background command")
            else:
                print("  ✗ Format parameter not found in remove_background command")
        else:
            print("  ✗ background_removed_format variable not found in project.yml")
    else:
        print("  ✗ project.yml not found")

if __name__ == "__main__":
    print("=== Fichero JXL Support Test ===\n")
    
    check_jxl_tools()
    print()
    test_jxl_conversion()
    test_project_config()
    
    print("\n=== Test Complete ===") 