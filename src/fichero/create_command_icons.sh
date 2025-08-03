#!/bin/bash

# Multi-platform icon generator for Fichero command icons
# Generates .icns (macOS), .ico (Windows), and .png (Linux/Android/iOS) from source PNG files

set -e  # Exit on any error

ICONS_DIR="src/fichero/resources/icons"
COMMAND_ICONS=(
    "gear/gear.png:gear"
    "plus/plus.png:plus"
    "trash/trash.png:trash"
    "info/info.png:info"
    "activity/activity.png:activity"
    "search/search.png:search"
    "filter/filter.png:filter"
    "help/help.png:help"
    "list_bullet/list_bullet.png:list_bullet"
)

echo "🎨 Generating command icons for all platforms..."

# Function to generate icons for a single command
generate_icon() {
    local input_file="$1"
    local icon_name="$2"
    
    echo "📱 Processing $icon_name..."
    
    # Check if input file exists
    if [ ! -f "$input_file" ]; then
        echo "⚠️  Warning: Input file $input_file not found, skipping..."
        return
    fi
    
    # Create temporary directories
    local iconset_dir="${icon_name}.iconset"
    local temp_ico_dir="temp_ico_${icon_name}"
    
    # Clean up any existing temporary directories
    if [ -d "$iconset_dir" ]; then
        rm -rf "$iconset_dir"
    fi
    if [ -d "$temp_ico_dir" ]; then
        rm -rf "$temp_ico_dir"
    fi
    
    # Create iconset directory for macOS
    mkdir -p "$iconset_dir"
    
    echo "   🍎 Creating macOS iconset..."
    
    # Generate all required sizes for macOS .icns file using sips (built into macOS)
    sips -z 16 16 "$input_file" --out "$iconset_dir/icon_16x16.png" > /dev/null 2>&1
    sips -z 32 32 "$input_file" --out "$iconset_dir/icon_16x16@2x.png" > /dev/null 2>&1
    sips -z 32 32 "$input_file" --out "$iconset_dir/icon_32x32.png" > /dev/null 2>&1
    sips -z 64 64 "$input_file" --out "$iconset_dir/icon_32x32@2x.png" > /dev/null 2>&1
    sips -z 128 128 "$input_file" --out "$iconset_dir/icon_128x128.png" > /dev/null 2>&1
    sips -z 256 256 "$input_file" --out "$iconset_dir/icon_128x128@2x.png" > /dev/null 2>&1
    sips -z 256 256 "$input_file" --out "$iconset_dir/icon_256x256.png" > /dev/null 2>&1
    sips -z 512 512 "$input_file" --out "$iconset_dir/icon_256x256@2x.png" > /dev/null 2>&1
    sips -z 512 512 "$input_file" --out "$iconset_dir/icon_512x512.png" > /dev/null 2>&1
    sips -z 1024 1024 "$input_file" --out "$iconset_dir/icon_512x512@2x.png" > /dev/null 2>&1
    
    # Create .icns file for macOS
    echo "   🍎 Creating macOS .icns file..."
    iconutil -c icns "$iconset_dir" --output "$ICONS_DIR/${icon_name}.icns"
    
    # Create .ico file for Windows
    echo "   🪟 Creating Windows .ico file..."
    mkdir -p "$temp_ico_dir"
    
    # Create standard Windows icon sizes
    sips -z 16 16 "$input_file" --out "$temp_ico_dir/16.png" > /dev/null 2>&1
    sips -z 32 32 "$input_file" --out "$temp_ico_dir/32.png" > /dev/null 2>&1
    sips -z 48 48 "$input_file" --out "$temp_ico_dir/48.png" > /dev/null 2>&1
    sips -z 64 64 "$input_file" --out "$temp_ico_dir/64.png" > /dev/null 2>&1
    sips -z 128 128 "$input_file" --out "$temp_ico_dir/128.png" > /dev/null 2>&1
    sips -z 256 256 "$input_file" --out "$temp_ico_dir/256.png" > /dev/null 2>&1
    
    # Check if ImageMagick is available for .ico creation
    if command -v magick &> /dev/null || command -v convert &> /dev/null; then
        echo "   Using ImageMagick to create .ico file..."
        if command -v magick &> /dev/null; then
            magick "$temp_ico_dir"/*.png "$ICONS_DIR/${icon_name}.ico"
        else
            convert "$temp_ico_dir"/*.png "$ICONS_DIR/${icon_name}.ico"
        fi
    else
        echo "   ⚠️  ImageMagick not found. Creating .ico using largest size only..."
        cp "$temp_ico_dir/256.png" "$ICONS_DIR/${icon_name}.ico"
    fi
    
    # Create optimized PNG for Linux/Android/iOS
    echo "   🐧 Creating optimized .png file..."
    sips -z 512 512 "$input_file" --out "$ICONS_DIR/${icon_name}.png" > /dev/null 2>&1
    
    # Create smaller versions for different use cases
    sips -z 32 32 "$input_file" --out "$ICONS_DIR/${icon_name}_32.png" > /dev/null 2>&1
    sips -z 64 64 "$input_file" --out "$ICONS_DIR/${icon_name}_64.png" > /dev/null 2>&1
    sips -z 128 128 "$input_file" --out "$ICONS_DIR/${icon_name}_128.png" > /dev/null 2>&1
    
    # Clean up temporary directories
    rm -rf "$iconset_dir"
    rm -rf "$temp_ico_dir"
    
    echo "   ✅ $icon_name complete!"
}

# Process each command icon
for icon_spec in "${COMMAND_ICONS[@]}"; do
    IFS=':' read -r input_file icon_name <<< "$icon_spec"
    generate_icon "$ICONS_DIR/$input_file" "$icon_name"
done

echo ""
echo "✅ All command icon generation complete!"
echo ""
echo "📁 Generated files for each command:"
echo "   🍎 macOS:   .icns files"
echo "   🪟 Windows: .ico files"
echo "   🐧 Linux:   .png files (512x512)"
echo "   📱 Mobile:  .png files (32x32, 64x64, 128x128)"
echo ""
echo "🚀 Ready to use in the application!" 