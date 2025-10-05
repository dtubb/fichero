#!/usr/bin/env python3
"""
Icon Colorization Script

This script pre-colorizes all icons using the colors from color_constants.py.
Run this once to generate colored versions of all icons, then the UI can
simply load the pre-colored icons without any runtime processing.
"""

import os
import sys
from pathlib import Path
from PIL import Image
import argparse

# Add the src directory to the path so we can import fichero modules
src_dir = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_dir))

from fichero.shared.toolbars.color_constants import ICON_PRIMARY, ICON_SECONDARY

def hex_to_rgb(hex_color):
    """Convert hex color string to RGB tuple"""
    if hex_color.startswith('#'):
        hex_color = hex_color[1:]
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    return (r, g, b)

def colorize_icon(input_path, output_path, color):
    """Colorize an icon with the given color while preserving transparency"""
    try:
        with Image.open(input_path) as img:
            # Convert to RGBA if not already
            if img.mode != 'RGBA':
                img = img.convert('RGBA')
            
            # Get the alpha channel (transparency)
            alpha = img.split()[-1]
            
            # Create new image with target color and original alpha
            rgb_color = hex_to_rgb(color)
            result = Image.new('RGBA', img.size, rgb_color + (0,))
            result.putalpha(alpha)
            
            # Save the colored icon
            result.save(output_path, 'PNG')
            print(f"✓ Colorized {input_path.name} with {color}")
            
    except Exception as e:
        print(f"✗ Failed to colorize {input_path.name}: {e}")

def main():
    parser = argparse.ArgumentParser(description="Colorize icons for Fichero")
    parser.add_argument("--input", default="src/fichero/resources/icons", 
                       help="Input icons directory")
    parser.add_argument("--output", default="src/fichero/resources/icons/colored", 
                       help="Output directory for colored icons")
    parser.add_argument("--primary-color", default=ICON_PRIMARY,
                       help="Primary icon color (hex)")
    parser.add_argument("--secondary-color", default=ICON_SECONDARY,
                       help="Secondary icon color (hex)")
    
    args = parser.parse_args()
    
    input_dir = Path(args.input)
    output_dir = Path(args.output)
    
    # Create output directory if it doesn't exist
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Colorizing icons from {input_dir} to {output_dir}")
    print(f"Primary color: {args.primary_color}")
    print(f"Secondary color: {args.secondary_color}")
    print()
    
    # Find all PNG files in the input directory
    icon_files = list(input_dir.glob("**/*.png"))
    
    if not icon_files:
        print("No PNG files found!")
        return
    
    # Colorize each icon
    for icon_file in icon_files:
        # Determine which color to use based on filename
        if any(keyword in icon_file.name.lower() for keyword in ['settings', 'gear', 'config']):
            color = args.secondary_color
        else:
            color = args.primary_color
        
        # Create output path
        relative_path = icon_file.relative_to(input_dir)
        output_path = output_dir / relative_path
        
        # Create output subdirectories if needed
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Colorize the icon
        colorize_icon(icon_file, output_path, color)
    
    print(f"\n✓ Colorized {len(icon_files)} icons")
    print(f"Colored icons saved to: {output_dir}")

if __name__ == "__main__":
    main() 