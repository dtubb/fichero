# src/sb_slipbox/sb_managers/reference_manager.py

"""Manages reference metadata for sources."""

import os
from sb_common.reference import Reference

class ReferenceManager:
    """Manage reference metadata for sources."""
    
    def __init__(self, ref_dir):
        self.ref_dir = ref_dir

    def save(self, reference):
        """Save a reference object to file."""
        
        filename = f"{reference.id}.bib"
        path = os.path.join(self.ref_dir, filename)
        
        with open(path, "w") as f:
            f.write(str(reference))

    def load(self, ref_id):
        """Load a reference by ID."""
        
        filename = f"{ref_id}.bib"
        path = os.path.join(self.ref_dir, filename)
        
        if os.path.exists(path):
            # Load reference file
            with open(path) as f:
                data = f.read()
                
            return Reference.from_bib(data)

    def load_all(self):
        """Load all references."""
        
        references = []
        for filename in os.listdir(self.ref_dir):
            id = filename.split(".")[0]
            ref = self.load(id)
            if ref:
                references.append(ref)
                
        return references
        
"""
Key points:

Saves Reference objects to BibTeX files
Loads references by ID or loads all refs
BibTeX format allows easy parsing and portability
This provides a simple way to manage metadata for sources as structured Reference objects.

Some improvements:

Support other metadata formats like JSON, XML, etc
Add search, filtering, and lookup methods
Interface with reference managers like Zotero
Store in database instead of filesystem
Overall it enables cleanly separating source metadata from content, while still keeping it organized and connected.

Let me know if you would like me to expand the docs or modify the implementation!
"""