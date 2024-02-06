# src/sb_slipbox/sb_generators/reference_generator.py

"""Generate reference strings for sources."""

import re

class ReferenceGenerator:
    """Generate citation style references for sources."""

    def generate(self, source):
        """Generate a reference string for a source.
        
        Args:
            source (Source): The source object.
            
        Returns:
            str: The generated reference string.
        """

        if source.type == "book":
            return self._generate_book_reference(source)
        elif source.type == "article":
            return self._generate_article_reference(source)
        # Other source types
        
    def _generate_book_reference(self, source):
        """Generate a book reference."""
        
        template = "{author}. ({year}). {title} ({edition} ed.). {publisher}."
        
        return template.format(
            author=source.author,
            year=source.year,
            title=source.title,
            edition=source.edition,
            publisher=source.publisher
        )

    def _generate_article_reference(self, source):
        """Generate an article reference."""
        
        template = "{author} ({year}). {title}. {journal}, {pages}."
        
        return template.format(
            author=source.author, 
            year=source.year,
            title=source.title,
            journal=source.journal,
            pages=source.pages
        )
        
"""
This ReferenceGenerator creates citation style reference strings for sources.

It checks the source type and delegates to specific template generation methods for books vs articles. The templates are filled out using the metadata from the source object.

This allows standardizing the reference format for sources in the slipbox.

Some ways to improve it:

Support more source types like websites, reports, etc.
Make the templates configurable
Generate references in different styles like APA, MLA, etc.
Let me know if you would like any changes to the code or documentation!

"""