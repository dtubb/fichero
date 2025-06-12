#!/bin/bash

# Multi-platform icon generator for Fichero app
# Generates .icns (macOS), .ico (Windows), and .png (Linux) from source PNG

set -e  # Exit on any error

INPUT="resources/icons/fichero.png"
ICONSET_DIR="fichero.iconset"
ICONS_DIR="resources/icons"

echo "🎨 Generating icons for all platforms from: $INPUT"

# Check if input file exists
if [ ! -f "$INPUT" ]; then
    echo "❌ Error: Input file $INPUT not found!"
    exit 1
fi

# Clean up any existing iconset directory
if [ -d "$ICONSET_DIR" ]; then
    rm -rf "$ICONSET_DIR"
fi

# Create iconset directory for macOS
mkdir -p "$ICONSET_DIR"

echo "📱 Creating macOS iconset..."

# Generate all required sizes for macOS .icns file using sips (built into macOS)
sips -z 16 16 "$INPUT" --out "$ICONSET_DIR/icon_16x16.png" > /dev/null 2>&1
sips -z 32 32 "$INPUT" --out "$ICONSET_DIR/icon_16x16@2x.png" > /dev/null 2>&1
sips -z 32 32 "$INPUT" --out "$ICONSET_DIR/icon_32x32.png" > /dev/null 2>&1
sips -z 64 64 "$INPUT" --out "$ICONSET_DIR/icon_32x32@2x.png" > /dev/null 2>&1
sips -z 128 128 "$INPUT" --out "$ICONSET_DIR/icon_128x128.png" > /dev/null 2>&1
sips -z 256 256 "$INPUT" --out "$ICONSET_DIR/icon_128x128@2x.png" > /dev/null 2>&1
sips -z 256 256 "$INPUT" --out "$ICONSET_DIR/icon_256x256.png" > /dev/null 2>&1
sips -z 512 512 "$INPUT" --out "$ICONSET_DIR/icon_256x256@2x.png" > /dev/null 2>&1
sips -z 512 512 "$INPUT" --out "$ICONSET_DIR/icon_512x512.png" > /dev/null 2>&1
sips -z 1024 1024 "$INPUT" --out "$ICONSET_DIR/icon_512x512@2x.png" > /dev/null 2>&1

# Create .icns file for macOS
echo "🍎 Creating macOS .icns file..."
iconutil -c icns "$ICONSET_DIR" --output "$ICONS_DIR/fichero.icns"

# Create .ico file for Windows (using sips to create multiple sizes, then combining)
echo "🪟 Creating Windows .ico file..."
TEMP_ICO_DIR="temp_ico"
mkdir -p "$TEMP_ICO_DIR"

# Create standard Windows icon sizes
sips -z 16 16 "$INPUT" --out "$TEMP_ICO_DIR/16.png" > /dev/null 2>&1
sips -z 32 32 "$INPUT" --out "$TEMP_ICO_DIR/32.png" > /dev/null 2>&1
sips -z 48 48 "$INPUT" --out "$TEMP_ICO_DIR/48.png" > /dev/null 2>&1
sips -z 64 64 "$INPUT" --out "$TEMP_ICO_DIR/64.png" > /dev/null 2>&1
sips -z 128 128 "$INPUT" --out "$TEMP_ICO_DIR/128.png" > /dev/null 2>&1
sips -z 256 256 "$INPUT" --out "$TEMP_ICO_DIR/256.png" > /dev/null 2>&1

# Check if ImageMagick is available for .ico creation
if command -v magick &> /dev/null || command -v convert &> /dev/null; then
    echo "   Using ImageMagick to create .ico file..."
    if command -v magick &> /dev/null; then
        magick "$TEMP_ICO_DIR"/*.png "$ICONS_DIR/fichero.ico"
    else
        convert "$TEMP_ICO_DIR"/*.png "$ICONS_DIR/fichero.ico"
    fi
else
    echo "   ⚠️  ImageMagick not found. Creating .ico using largest size only..."
    # Fallback: just copy the 256px version as .ico (not ideal but works)
    cp "$TEMP_ICO_DIR/256.png" "$ICONS_DIR/fichero.ico"
fi

# Linux typically just uses PNG, but let's create a standard 512x512 version
echo "🐧 Creating Linux .png file..."
sips -z 512 512 "$INPUT" --out "$ICONS_DIR/fichero-linux.png" > /dev/null 2>&1

# The original fichero.png is already good for Linux, but let's make sure it's optimized
echo "   Original fichero.png is already suitable for Linux"

# Clean up temporary directories
rm -rf "$ICONSET_DIR"
rm -rf "$TEMP_ICO_DIR"

echo ""
echo "✅ Icon generation complete!"
echo ""
echo "📁 Generated files:"
echo "   🍎 macOS:   $ICONS_DIR/fichero.icns"
echo "   🪟 Windows: $ICONS_DIR/fichero.ico" 
echo "   🐧 Linux:   $ICONS_DIR/fichero.png (original)"
echo "   🐧 Linux:   $ICONS_DIR/fichero-linux.png (512x512 optimized)"
echo ""
echo "🚀 Ready to run: briefcase update --update-resources" 