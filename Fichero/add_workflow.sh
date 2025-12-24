#!/bin/bash
# Add Workflow.swift to Xcode project

# Generate UUIDs
FILE_REF_ID=$(uuidgen | tr 'A-F' '0-9' | cut -c1-3)
BUILD_FILE_ID=$(uuidgen | tr 'A-F' '0-9' | cut -c1-3)

echo "Adding Workflow.swift with FileRef=$FILE_REF_ID, BuildFile=$BUILD_FILE_ID"

# Backup project file
cp Fichero.xcodeproj/project.pbxproj Fichero.xcodeproj/project.pbxproj.backup

# Add file reference (after WorkflowTypes.swift entry)
perl -i -pe "s|(134 /\* WorkflowTypes.swift \*/ =.*)|$&\n\t\t$FILE_REF_ID /* Workflow.swift */ = {isa = PBXFileReference; lastKnownFileType = sourcecode.swift; path = Workflow.swift; sourceTree = \"<group>\"; };|" Fichero.xcodeproj/project.pbxproj

# Add build file (after WorkflowTypes.swift Sources entry)
perl -i -pe "s|(035 /\* WorkflowTypes.swift in Sources \*/ =.*)|$&\n\t\t$BUILD_FILE_ID /* Workflow.swift in Sources */ = {isa = PBXBuildFile; fileRef = $FILE_REF_ID /* Workflow.swift */; };|" Fichero.xcodeproj/project.pbxproj

# Add to Models group children (after WorkflowTypes.swift)
perl -i -pe "s|(134 /\* WorkflowTypes.swift \*/,)|$&\n\t\t\t\t$FILE_REF_ID /* Workflow.swift */,|" Fichero.xcodeproj/project.pbxproj

# Add to Sources build phase (after WorkflowTypes.swift)
perl -i -pe "s|(035 /\* WorkflowTypes.swift in Sources \*/,)|$&\n\t\t\t\t$BUILD_FILE_ID /* Workflow.swift in Sources */,|" Fichero.xcodeproj/project.pbxproj

echo "Workflow.swift added to project"
