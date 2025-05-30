#!/bin/bash

# Directory containing the files
DIR="/Users/dtubb/code/fichero_main/fichero/projects/1967/1967 Municipio de Istmina/documents"

# Check if directory exists
if [ ! -d "$DIR" ]; then
    echo "Error: Directory does not exist!"
    exit 1
fi

# Process all JPG files
for file in "$DIR"/*.JPG; do
    if [ -f "$file" ]; then
        # Get the filename without path
        filename=$(basename "$file")
        
        # Get the numeric part and extension
        numeric_part=$(echo "$filename" | sed 's/[^0-9]//g')
        extension=".JPG"
        
        # Create new filename
        new_filename="${numeric_part}${extension}"
        
        # Only rename if the filename would change
        if [ "$filename" != "$new_filename" ]; then
            echo "Renaming: $filename -> $new_filename"
            mv "$file" "$DIR/$new_filename"
        fi
    fi
done

echo "Processing complete!" 