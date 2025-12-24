#!/usr/bin/env python3

import re

# Read the project file
with open('Fichero/Fichero.xcodeproj/project.pbxproj', 'r') as f:
    content = f.read()

# Find all occurrences of CODE_SIGN_ENTITLEMENTS and add the modification flag before them
# We need to match the exact pattern with proper indentation
pattern = r'(\t{4})CODE_SIGN_ENTITLEMENTS = Fichero/Fichero\.entitlements;'
replacement = r'\1CODE_SIGN_ALLOW_ENTITLEMENTS_MODIFICATION = YES;\n\1CODE_SIGN_ENTITLEMENTS = Fichero/Fichero.entitlements;'

modified_content = re.sub(pattern, replacement, content)

# Write the modified content back
with open('Fichero/Fichero.xcodeproj/project.pbxproj', 'w') as f:
    f.write(modified_content)

print("Fixed entitlements settings in project file")