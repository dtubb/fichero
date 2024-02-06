# src/sb_slipbox/sb_generators/link_generator.py

"""Generator for identifying links between slips."""

import spacy

class LinkGenerator:
    """Generate links between slips."""

    def __init__(self, model="en_core_web_sm"):
        """Initialize spaCy model."""
        self.nlp = spacy.load(model)

    def generate(self, slips):
        """Generate links between slips.
        
        Args:
            slips (list): List of Slip objects.
            
        Returns:
            list: List of (src_slip, dest_slip) tuples representing links.
        """
        
        links = []
        
        for slip1 in slips:
            for slip2 in slips:
                if self._has_similarity(slip1, slip2):
                    links.append((slip1, slip2))
        
        return links
        
    def _has_similarity(self, slip1, slip2):
        """Check if two slips are similar using spaCy."""
        
        doc1 = self.nlp(slip1.text)
        doc2 = self.nlp(slip2.text)
        
        return doc1.similarity(doc2) > 0.8
   
"""
The LinkGenerator uses spaCy and its document similarity function to identify slips that have high semantic similarity and should be linked.

Key points:

Initialize spaCy English model
generate() takes a list of slips
Checks similarity of each slip vs every other slip
Adds link if similarity exceeds threshold
_has_similarity() compares two slips using spaCy
This provides a simple way to generate links between slips based on content similarity. Some potential enhancements:

Support different linking strategies beyond just similarity
Link based on references, tags, dates, etc
Use alternative similarity measures like Word2Vec
Allow configuring the similarity threshold
Let me know if you would like me to modify or expand the documentation or implementation!
"""