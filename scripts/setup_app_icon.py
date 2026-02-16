#!/usr/bin/env python3
"""
Generate all required macOS app icon sizes from source PNG.
"""
from PIL import Image
from pathlib import Path
import json

# Paths
project_root = Path(__file__).parent.parent
source_icon = project_root / "fichero-api/src/fichero/resources/icons/fichero-1920.png"
appiconset = project_root / "fichero-swiftui/fichero-swiftui/Resources/Assets.xcassets/AppIcon.appiconset"

# macOS icon sizes needed (actual pixel dimensions)
SIZES = [
    (16, "16x16", "1x"),
    (32, "16x16", "2x"),
    (32, "32x32", "1x"),
    (64, "32x32", "2x"),
    (128, "128x128", "1x"),
    (256, "128x128", "2x"),
    (256, "256x256", "1x"),
    (512, "256x256", "2x"),
    (512, "512x512", "1x"),
    (1024, "512x512", "2x"),
]

def generate_icons():
    """Generate all icon sizes from source."""
    print(f"📦 Loading source icon: {source_icon}")
    img = Image.open(source_icon)

    print(f"   Source size: {img.size}")
    print(f"\n🎨 Generating icon sizes...")

    for pixel_size, size_str, scale in SIZES:
        output_name = f"icon_{size_str}@{scale}.png"
        output_path = appiconset / output_name

        # Resize with high-quality resampling
        resized = img.resize((pixel_size, pixel_size), Image.Resampling.LANCZOS)
        resized.save(output_path, "PNG", optimize=True)

        print(f"   ✓ {output_name} ({pixel_size}x{pixel_size})")

    # Update Contents.json with filenames
    contents = {
        "images": [
            # macOS icons
            {"filename": "icon_16x16@1x.png", "idiom": "mac", "scale": "1x", "size": "16x16"},
            {"filename": "icon_16x16@2x.png", "idiom": "mac", "scale": "2x", "size": "16x16"},
            {"filename": "icon_32x32@1x.png", "idiom": "mac", "scale": "1x", "size": "32x32"},
            {"filename": "icon_32x32@2x.png", "idiom": "mac", "scale": "2x", "size": "32x32"},
            {"filename": "icon_128x128@1x.png", "idiom": "mac", "scale": "1x", "size": "128x128"},
            {"filename": "icon_128x128@2x.png", "idiom": "mac", "scale": "2x", "size": "128x128"},
            {"filename": "icon_256x256@1x.png", "idiom": "mac", "scale": "1x", "size": "256x256"},
            {"filename": "icon_256x256@2x.png", "idiom": "mac", "scale": "2x", "size": "256x256"},
            {"filename": "icon_512x512@1x.png", "idiom": "mac", "scale": "1x", "size": "512x512"},
            {"filename": "icon_512x512@2x.png", "idiom": "mac", "scale": "2x", "size": "512x512"},
        ],
        "info": {
            "author": "xcode",
            "version": 1
        }
    }

    contents_path = appiconset / "Contents.json"
    with open(contents_path, 'w') as f:
        json.dump(contents, f, indent=2)

    print(f"\n✅ All icons generated!")
    print(f"   Location: {appiconset}")
    print(f"\n   Next: Build your app in Xcode - icon will appear automatically")

if __name__ == "__main__":
    generate_icons()
