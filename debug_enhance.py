#!/usr/bin/env python3

import sys
import os
sys.path.insert(0, os.path.join(os.getcwd(), 'src'))
sys.path.insert(0, os.path.join(os.getcwd(), 'src', 'fichero', 'tools'))

from pathlib import Path
from PIL import Image
import traceback

# Import with proper path setup
from utils.image_format import load_image

# Test the problematic file
test_file = Path("/Users/dtubb/Desktop/demo_processed/demo/assets/rotated/documents/1.jpg")
output_path = Path("/tmp/test_enhanced.jpg")

print(f"Testing file: {test_file}")
print(f"File exists: {test_file.exists()}")

if test_file.exists():
    print(f"File size: {test_file.stat().st_size} bytes")
    
    # Test 1: Try to load with PIL directly
    print("\n=== Test 1: PIL direct load ===")
    try:
        with Image.open(test_file) as img:
            print(f"PIL load successful: {img.size}, mode: {img.mode}")
    except Exception as e:
        print(f"PIL load failed: {e}")
        traceback.print_exc()
    
    # Test 2: Try the load_image utility
    print("\n=== Test 2: load_image utility ===")
    try:
        image, metadata = load_image(test_file)
        print(f"load_image successful: {image.size}, mode: {image.mode}")
        print(f"Metadata: {metadata}")
    except Exception as e:
        print(f"load_image failed: {e}")
        traceback.print_exc()
    
    # Test 3: Check if file might be getting read as text somewhere
    print("\n=== Test 3: Check for text reading attempts ===")
    try:
        # Try reading the file as text to reproduce the error
        with open(test_file, 'r', encoding='utf-8') as f:
            content = f.read()
            print("File was read as text (this should fail for binary images)")
    except UnicodeDecodeError as e:
        print(f"Expected UTF-8 decode error: {e}")
    except Exception as e:
        print(f"Unexpected error reading as text: {e}")
        
    # Test 5: Try to read a few bytes as text to see if file is corrupted
    print("\n=== Test 5: File header check ===")
    try:
        with open(test_file, 'rb') as f:
            header = f.read(20)
            print(f"File header (hex): {header.hex()}")
            print(f"File header (bytes): {list(header)}")
    except Exception as e:
        print(f"Header read failed: {e}")

else:
    print("File does not exist!") 