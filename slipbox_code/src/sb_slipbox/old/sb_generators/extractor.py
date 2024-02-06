# src/sb_slipbox/sb_generators/extractor.py

"""Text extraction generator."""

from summarizer import Summarizer

class Extractor:
    """Extract key points from text."""
    
    def __init__(self, model="distilbart-cnn-12-6"):
        """Initialize summarizer."""
        self.summarizer = Summarizer(model)
        
    def extract(self, text, ratio=0.2):
        """Extract key points from text.
        
        Args:
            text (str): Text to extract from.
            ratio (float): Ratio of text length for extraction.
            
        Returns:
            list: Extracted key phrases.
        """
        
        summary = self.summarizer(text, ratio=ratio)
        
        # Parse summary into key phrases
        key_phrases = summary.split(".")  
        
        return key_phrases
        
"""
The key points:

Uses the Summarizer module for extraction
extract() method takes a text and summarizes it
Summary is parsed into key phrase extracts
Ratio controls length of extraction
This provides a simple extraction workflow to get key points. Additional enhancements could include:

Supporting different extraction strategies beyond summarization
Extracting quotes, facts, keywords, etc
Returning Extract objects with metadata instead of just strings
"""