#!/usr/bin/env python3
"""
Generate iOS app icons for Fichero from the main icon file.

This script takes the main fichero.png icon and generates all the required
iOS icon sizes that Briefcase expects for proper iOS packaging.
"""

import os
import sys
from pathlib import Path
from PIL import Image, ImageOps

# iOS icon sizes required by Briefcase
IOS_ICON_SIZES = [
    20,   # 20px
    29,   # 29px  
    40,   # 40px
    58,   # 58px
    60,   # 60px
    76,   # 76px
    80,   # 80px
    87,   # 87px
    120,  # 120px
    152,  # 152px
    167,  # 167px
    180,  # 180px
    640,  # 640px
    1024, # 1024px
    1280, # 1280px
    1920, # 1920px
]

def generate_ios_icons(source_icon_path, output_dir):
    """
    Generate iOS app icons in all required sizes.
    
    Args:
        source_icon_path: Path to the source icon file
        output_dir: Directory to save the generated icons
    """
    try:
        # Open the source image
        with Image.open(source_icon_path) as img:
            print(f"✅ Loaded source icon: {source_icon_path}")
            print(f"   Original size: {img.size}")
            
            # Convert to RGBA if not already
            if img.mode != 'RGBA':
                img = img.convert('RGBA')
            
            # Create output directory if it doesn't exist
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # Generate each size
            for size in IOS_ICON_SIZES:
                # Resize the image using high-quality resampling
                resized = img.resize((size, size), Image.Resampling.LANCZOS)
                
                # Create the output filename
                output_filename = f"fichero-{size}.png"
                output_path = output_dir / output_filename
                
                # Save the resized image
                resized.save(output_path, 'PNG', optimize=True)
                print(f"✅ Generated: {output_filename} ({size}x{size})")
                
    except Exception as e:
        print(f"❌ Error generating icons: {e}")
        return False
    
    return True

def main():
    """Main function to generate iOS icons."""
    # Get the project root (assuming script is in tools/)
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    
    # Define paths
    source_icon = project_root / "src" / "fichero" / "resources" / "icons" / "fichero.png"
    output_dir = project_root / "src" / "fichero" / "resources" / "icons"
    
    print("🚀 Fichero iOS Icon Generator")
    print("=" * 40)
    
    # Check if source icon exists
    if not source_icon.exists():
        print(f"❌ Source icon not found: {source_icon}")
        print("   Please ensure fichero.png exists in the icons directory.")
        return 1
    
    print(f"📁 Source icon: {source_icon}")
    print(f"📁 Output directory: {output_dir}")
    print()
    
    # Generate the icons
    success = generate_ios_icons(source_icon, output_dir)
    
    if success:
        print()
        print("🎉 Successfully generated all iOS icons!")
        print(f"📁 Icons saved to: {output_dir}")
        print()
        print("The following files were created:")
        for size in IOS_ICON_SIZES:
            print(f"   - fichero-{size}.png")
        print()
        print("✅ You can now run 'briefcase dev' without icon warnings.")
        return 0
    else:
        print("❌ Failed to generate icons.")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 