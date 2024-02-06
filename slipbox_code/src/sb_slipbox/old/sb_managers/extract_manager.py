# src/sb_slipbox/sb_managers/extract_manager.py

"""Manager for handling extracted text."""

import os
from sb_common.extract import Extract

class ExtractManager:
    """Manage extracted text from sources."""

    def __init__(self, extract_dir):
        self.extract_dir = extract_dir

    def save(self, source_id, text):
        """Save extracted text for a source."""
        
        filename = f"{source_id}.txt"
        path = os.path.join(self.extract_dir, filename)

        with open(path, "w") as f:
            f.write(text)

    def load(self, source_id):
        """Load extracted text for a source."""

        filename = f"{source_id}.txt"
        path = os.path.join(self.extract_dir, filename)

        if os.path.exists(path):
            with open(path) as f:
                text = f.read()
            return Extract(id=source_id, text=text)

    def load_all(self):
        """Load all extracted text."""
        
        extracts = []
        for filename in os.listdir(self.extract_dir):
            id = filename.split(".")[0]  # Remove .txt
            text = self.load(id)
            if text:
                extracts.append(text)

        return extracts
        
"""
Key points:

Saves extracted text to files named by source ID
Loads extracts by ID or loads all
Returns Extract objects containing ID and text
This allows cleanly managing the extracted text from sources as Extract objects.

Some ways to improve:

Use a database instead of filesystem
Add metadata like date, source type etc to Extract
Support searching/filtering extracts
Expose extracts as an iterable instead of just load_all()
Let me know if you would like me to expand the documentation or modify the implementation!
"