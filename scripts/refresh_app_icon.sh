#!/bin/bash
# Refresh macOS app icon by clearing caches

echo "🧹 Clearing macOS icon cache..."

# Kill Dock and Finder to refresh icons
killall Dock
killall Finder

# Clear icon services cache
sudo rm -rfv /Library/Caches/com.apple.iconservices.store
rm -rfv ~/Library/Caches/com.apple.iconservices

# Touch the icon files to force re-read
touch /Users/dtubb/code/fichero_main/fichero/Fichero/Fichero/Resources/Assets.xcassets/AppIcon.appiconset/*.png

echo "✅ Icon cache cleared!"
echo ""
echo "Next steps:"
echo "1. In Xcode: Product → Clean Build Folder (⇧⌘K)"
echo "2. Build and run (⌘R)"
echo "3. Icon should now appear correctly"
