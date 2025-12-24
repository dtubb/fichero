#!/usr/bin/env python3
"""
Toolbar Icon Processing Script

This script processes icons from toolbar_original folder:
1. Colorizes them using colors from color_constants.py
2. Resizes them to 32x32 pixels
3. Saves them to the toolbar folder
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

def colorize_and_resize_icon(input_path, output_path, color, target_size=(32, 32)):
    """Colorize an icon with the given color and resize it with consistent visual sizing"""
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
            
            # NORMALIZE VISUAL CONTENT SIZE: Scale all icons to the same content area
            # We want all icons to have the same visual weight, regardless of original size
            target_content_size = 32  # All icons will have 32x32 content area
            
            # Calculate scaling factor to fit the icon within the target content area
            # while maintaining aspect ratio
            scale_factor = min(target_content_size / img.size[0], target_content_size / img.size[1])
            new_width = int(img.size[0] * scale_factor)
            new_height = int(img.size[1] * scale_factor)
            
            # Resize the icon to the normalized content size
            result = result.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            # Create a new 32x32 image with the normalized icon centered
            final_img = Image.new('RGBA', target_size, (0, 0, 0, 0))
            
            # Calculate position to center the normalized icon
            x = (target_size[0] - result.size[0]) // 2
            y = (target_size[1] - result.size[1]) // 2
            
            # Paste the normalized icon onto the center of the final image
            final_img.paste(result, (x, y), result)
            
            # Save the processed icon
            final_img.save(output_path, 'PNG', optimize=True)
            print(f"✓ Processed {input_path.name} -> {output_path.name} ({color}, {target_size[0]}x{target_size[1]}, content {new_width}x{new_height})")
            
    except Exception as e:
        print(f"✗ Failed to process {input_path.name}: {e}")

def create_default_icons(output_dir: Path, color: str = "#0E7AFE"):
    """Create missing default icons"""
    from PIL import Image, ImageDraw
    
    # Create chevron_left icon
    chevron_img = Image.new('RGBA', (42, 42), (255, 255, 255, 0))
    draw = ImageDraw.Draw(chevron_img)
    
    # Draw a simple left-pointing chevron
    points = [(28, 12), (18, 21), (28, 30)]
    draw.polygon(points, outline=color, width=3)
    
    chevron_path = output_dir / "chevron_left.png"
    chevron_img.save(chevron_path)
    print(f"Created default chevron_left icon: {chevron_path}")
    
    # Create text_display icon
    text_img = Image.new('RGBA', (42, 42), (255, 255, 255, 0))
    draw = ImageDraw.Draw(text_img)
    
    # Draw simple text lines
    for i, y in enumerate([14, 22, 30]):
        width = 22 if i == 1 else 16  # Middle line is longer
        draw.rectangle([11, y, 11 + width, y + 3], fill=color)
    
    text_path = output_dir / "text_display.png"
    text_img.save(text_path)
    print(f"Created default text_display icon: {text_path}")

def main():
    parser = argparse.ArgumentParser(description="Process toolbar icons for Fichero")
    parser.add_argument("--input", default="src/fichero/resources/icons/toolbar_original", 
                       help="Input icons directory")
    parser.add_argument("--output", default="src/fichero/resources/icons/toolbar", 
                       help="Output directory for processed icons")
    parser.add_argument("--primary-color", default=ICON_PRIMARY,
                       help="Primary icon color (hex)")
    parser.add_argument("--secondary-color", default=ICON_SECONDARY,
                       help="Secondary icon color (hex)")
    parser.add_argument("--size", default=42, type=int,
                       help="Target icon size in pixels")
    
    args = parser.parse_args()
    
    input_dir = Path(args.input)
    output_dir = Path(args.output)
    target_size = (args.size, args.size)
    
    # Create output directory if it doesn't exist
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Processing icons from {input_dir} to {output_dir}")
    print(f"Primary color: {args.primary_color}")
    print(f"Secondary color: {args.secondary_color}")
    print(f"Target size: {target_size[0]}x{target_size[1]} pixels")
    print()
    
    # Mapping from source filenames to desired output filenames
    # This ensures the toolbars get the icons they expect
    filename_mapping = {
        # Library toolbar icons
        "folder.badge.plus@10x.png": "add_collection.png",
        "folder.badge.gearshape@10x.png": "settings.png",
        
        # Collection toolbar icons - use different source files to avoid conflicts
        "plus.circle@10x.png": "add_file.png",
        "process.png": "process.png",
        "gear.png": "collection_settings.png",  # Use gear.png instead of duplicating folder.badge.gearshape
        "export.png": "export.png",
        
        # For add_folder, we'll create a copy from add_collection
        "folder.png": "add_folder.png",  # Use folder.png as the source for add_folder
        
        # Other icons that might be needed
        "document.png": "document.png",
        "activity.png": "activity.png",
        "help.png": "help.png",
        "filter.png": "filter.png",
        "collection.png": "collection.png",
        "trash.png": "trash.png",
        "plan.png": "plan.png",
        "text.png": "text.png",
        "text_document.png": "text_document.png",
        "list_bullet.png": "list_bullet.png",
        "prompt.png": "prompt.png",
        "archivebox.png": "archivebox.png",
        "magnifyingglass@10x.png": "magnifyingglass.png",
        "folder.badge.minus@10x.png": "folder_minus.png",
    }
    
    # Find all image files in the input directory
    image_extensions = ['.png', '.jpg', '.jpeg', '.gif', '.bmp']
    icon_files = []
    for ext in image_extensions:
        icon_files.extend(input_dir.glob(f"**/*{ext}"))
    
    if not icon_files:
        print("No image files found!")
        return
    
    # Process each icon
    for icon_file in icon_files:
        # Determine which color to use based on filename
        if any(keyword in icon_file.name.lower() for keyword in ['settings', 'gear', 'config', 'preferences']):
            color = args.secondary_color
        else:
            color = args.primary_color
        
        # Get the desired output filename from the mapping, or use the original name
        output_name = filename_mapping.get(icon_file.name, icon_file.name)
        output_path = output_dir / output_name
        
        # Process the icon
        colorize_and_resize_icon(icon_file, output_path, color, target_size)
    
    # Create missing default icons
    create_default_icons(output_dir, args.primary_color)
    
    print(f"\n✓ Processed {len(icon_files)} icons")
    print(f"Processed icons saved to: {output_dir}")

if __name__ == "__main__":
    main() 