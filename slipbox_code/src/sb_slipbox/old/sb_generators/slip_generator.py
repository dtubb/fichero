# src/sb_slipbox/sb_generators/slip_generator.py

"""Generates slips from extracts."""

"""
The SlipGenerator takes Extract objects and generates Slip objects from them.

It uses a summarizer model to summarize the extract text. The summary is then split into individual sentences, each sentence becoming a separate slip.

This allows condensing longer extracts down to atomic slips.

Some ways to improve:

Support generating multiple slips per extract
Allow customizing slip length instead of full sentences
Return Slip objects with more metadata
"""

from summarizer import Summarizer

class SlipGenerator:
    """Generate slips from extracts."""

    def __init__(self, model="distilbart-cnn-12-6"):
        self.summarizer = Summarizer(model)

    def generate(self, extract):
        """Generate slips from an extract.
        
        Args:
            extract (Extract): Extract object to generate slips for.
            
        Returns:
            list[Slip]: Generated slips for the extract.
        """
        
        # Summarize extract text
        summary = self.summarizer(extract.text)
        
        # Split summary into sentences
        slip_texts = self._split_to_sentences(summary)
        
        # Create Slip objects
        slips = [Slip(text=t) for t in slip_texts]
        
        return slips

    def _split_to_sentences(self, text):
        """Split text into list of sentences."""
        # Sentence splitting logic
        return sentences