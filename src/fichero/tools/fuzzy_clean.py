import typer
import json
from pathlib import Path
import re

# Support both standalone CLI usage and workflow executor imports
try:
    # When imported by workflow executor (absolute imports work)
    from fichero.tools.utils.batch import BatchProcessor
    from fichero.tools.utils.segment_handler import SegmentHandler
    from fichero.tools.utils.files import ensure_dirs
    from fichero.tools.utils.tool_logger import get_tool_logger
except ImportError:
    # When run as standalone script (relative imports work)
    from utils.batch import BatchProcessor
    from utils.segment_handler import SegmentHandler
    from utils.files import ensure_dirs
    from utils.tool_logger import get_tool_logger

tool_logger = get_tool_logger('fuzzy_clean')

class TextCleaner:
    @staticmethod
    def calculate_max_phrase_length(text, percentage=0.5):
        """Calculate the maximum phrase length based on percentage of total word count."""
        word_count = len(text.split())
        return max(1, int(word_count * percentage))

    @staticmethod
    def clean_repeated_phrases(text):
        """Remove repeated phrases from the text."""
        max_phrase_length = TextCleaner.calculate_max_phrase_length(text, percentage=0.05)
        lines = text.splitlines()
        clean_lines = []

        for line in lines:
            words = line.split()
            clean_line = []
            i = 0

            while i < len(words):
                phrase = " ".join(words[i:i + max_phrase_length])
                next_phrase = " ".join(words[i + 1:i + 1 + max_phrase_length])
                # Skip short phrases (e.g., two words that are each two letters long)
                if len(phrase.split()) == 2 and all(len(word) <= 2 for word in phrase.split()):
                    clean_line.append(words[i])
                elif phrase != next_phrase:
                    clean_line.append(words[i])
                i += 1

            clean_lines.append(" ".join(clean_line))

        return "\n".join(clean_lines)

    @staticmethod
    def remove_repeated_phrases(text, min_phrase_length=5):
        """Remove long repeated phrases from the text."""
        lines = text.splitlines()
        clean_lines = []
        previous_phrases = set()

        for line in lines:
            words = line.split()
            clean_line = []
            i = 0

            while i < len(words):
                phrase = " ".join(words[i:i + min_phrase_length])
                if phrase not in previous_phrases:
                    clean_line.append(" ".join(words[i:i + min_phrase_length]))
                    previous_phrases.add(phrase)
                i += min_phrase_length

            clean_lines.append(" ".join(clean_line))

        return "\n".join(clean_lines)

    @staticmethod
    def remove_repeated_words(text):
        """Remove repeated words from the text."""
        lines = text.splitlines()
        clean_lines = []

        for line in lines:
            words = line.split()
            clean_line = []
            previous_word = ""

            for word in words:
                if word.lower() != previous_word.lower():
                    clean_line.append(word)
                previous_word = word

            clean_lines.append(" ".join(clean_line))

        return "\n".join(clean_lines)

    @staticmethod
    def remove_repeated_phrases_between_chunks(text):
        """Remove repeated phrases that might appear between chunks."""
        lines = text.splitlines()
        clean_lines = []
        previous_line = ""

        for line in lines:
            # if fuzz.ratio(previous_line, line) < fuzziness_threshold:
            if previous_line != line:
                clean_lines.append(line)
            previous_line = line

        return "\n".join(clean_lines)

    @staticmethod
    def remove_repeated_phrases_regex(text):
        """Remove repeated phrases and numbers at the beginning of the line using regex."""
        # Pattern to match repeated phrases
        pattern = re.compile(r"(\b\w+\b(?:\s+\b\w+\b){2,})(?=.*\1)")
        text = re.sub(pattern, "", text)
        
        # Pattern to match numbers at the beginning of the line
        text = re.sub(r"^\d+\s+", "", text, flags=re.MULTILINE)
        
        return text

    @staticmethod
    def combine_single_word_paragraphs(text):
        """Combine single-word paragraphs into a single line."""
        lines = text.splitlines()
        combined_lines = []
        current_line = []

        for line in lines:
            if len(line.split()) == 1:
                current_line.append(line)
            else:
                if current_line:
                    combined_lines.append(" ".join(current_line))
                    current_line = []
                combined_lines.append(line)

        if current_line:
            combined_lines.append(" ".join(current_line))

        return "\n".join(combined_lines)

    @staticmethod
    def remove_specific_phrases(text: str) -> str:
        """Remove specific unwanted phrases from the text."""
        phrases_to_remove = [
            # Document structure mentions
            "handwritten document with",
            "extracted text is",
            "here is the text",
            "plaintext",
            "say nothing else",
            "image of a sheet",
            "piece of parchment",
            "extracted line by line",
            "note:",
            "here it is",
            "in black ink",
            "visible text on the",
            "original document to be preserved",
            
            # Phrases about unreadable content
            "appears damaged or incomplete",
            "difficult to read",
            "poor resolution",
            "cannot be discerned",
            "parts of the text are damaged",
            "illegible",
            "cannot be fully interpreted",
            
            # Filler lines
            "visible wear and tear",
            "unknown language or script",
            "cursive script",
            "aged and worn",
            "faint lines or patterns",
            "scan of handwritten text",
            
            # Extraneous descriptors
            "line by line",
            "let me know",
            "help analyze",
            "help with that",
            "ayudarte con eso",
            "provide more details",
            "clarify what you",
            
            # Technical repetition
            "text on the parchment",
            "text on the paper",
            "text starts with",
            "document says",
            "extracted text",
            "note mentions",
            "following text",
            "document reads",
            "handwriting is difficult",
            
            # Additional phrases from suggestion
            "historical value",
            "text written in an older period",
            "annotations made by someone using it",
            "additional details about the document's condition",
            "let me know how I can help refine or process this document further",
            
            # French phrases
            "A partir de cette page",
            "Attribution du document abrogé",
            "Monsieur, sur le canal",
            "Vers le de l'hébertel",
            "Décetimber",
            
            # German/Latin phrases
            "Herr, Königlicher Beamter",
            "Unter anachly Contectt",
            "Herrenopilz, Ermland",
            "Nunciamus puncti",
            "Servace duponer",
            "Omnibus liber",
            
            # More document descriptors
            "This appears to be a compilation of complex and fragmented text",
            "The document contains the following information",
            "This is a damaged and old paper",
            "Some sections are faded and unreadable",
            "The document is partially torn",
            "Incomplete transcription due to damage",
            "Sections of the text are missing or blurred",
            
            # Additional transcription phrases
            "The text appears to be written in cursive",
            "contains some symbols or marks",
            "difficult to decipher",
            "transcription of the visible part",
            "due to its age and wear",
            "appears to be in Spanish",
            "Romance language",
            "I am sorry, but I cannot assist with that",
            "from the image",
            "as follows",
            "as follows:",
            "is as follows",
            "is as follows:",
            "are as follows",
            "are as follows:",
            "```",
            
            # Cannot assist variations
            "I am sorry, but I cannot assist with that",
            "I cannot assist with that",
            "sorry, but I cannot assist",
            "I'm sorry, I cannot assist",
            "I am unable to assist",
            "I can't assist with that",
            "Lo siento, no puedo ayudar",
            
            # Additional document descriptors
            "in its entirety, without any modifications or additions",
            "This is an extract from an old manuscript",
            "of the document in plain text format",
            "with visible creases and uneven edges",
            "The text appears to be fragmented and may not be fully readable",
            "considering the lack of context provided in the prompt",
            "The text on the page reads",
            "of the document, extracted one line at a time",
            "Document Text",
            "paper with a small drawing of an owl on the top right corner",
            "reads as follows",
            "plain texture paper",
            "A sheet of paper with horizontal lines",
            "some stains and marks on it",
            "The paper appears to be yellowed and slightly curled at the edges",
            "There is no text visible in this particular image",
            "There are no visible texts or lines in the image",
            "An extract of text, when properly formatted and structured",
            "with a slightly curved edge and a dark background",
            "should be able to be read as follows"
        ]
        
        # Make patterns more flexible
        for phrase in phrases_to_remove:
            # Create flexible pattern with optional words and fuzzy spacing
            pattern = phrase.replace(" ", r'\s+')  # Handle variable whitespace
            pattern = f".*?{pattern}.*?[.:]?"  # Match broader context and optional punctuation
            text = re.sub(pattern, "", text, flags=re.IGNORECASE | re.MULTILINE | re.DOTALL)
        
        # Additional cleanup patterns for common variations
        cleanup_patterns = [
            r"(?:here|this)\s+(?:is|are)\s+(?:the|an?)\s+(?:text|document|image).*?[.:]",
            r"(?:the|this)\s+(?:text|document|image)\s+(?:shows|contains|has|is).*?[.:]",
            r"(?:please|kindly)\s+(?:note|be aware|let me know).*?[.:]",
            r"(?:I can|I will|I could)\s+(?:help|assist).*?[.:]",
            r"(?:due to|because of)\s+(?:the|its)\s+(?:condition|state|quality).*?[.:]",
            r"(?:some|many|several)\s+(?:parts?|sections?|areas?)\s+(?:are|is)\s+(?:damaged|worn|faded).*?[.:]",
            
            # New patterns from suggestion
            r"(?:aging|historical)\s+details\s+like\s+(?:dates|locations)",
            r"(?:would|could)\s+you\s+like\s+assistance",
            r"(?:although|while)\s+(?:the|this)\s+(?:document|text|image)\s+(?:is|appears)",
            r"[A-Z](?:\s*[-,.]\s*[A-Z]){2,}",  # Letter sequences like "A.B.C" or "X,Y,Z"
            r"\d{4}\s*[-,.]\s*\d{4}",  # Year ranges
            r"(?:Em|Sam|Nibl)\s+(?:de|du|la)\s+(?:toise|baya)",  # Common OCR artifacts
            r"R\s+\d{4}",  # Reference numbers
            r"[A-Z]\.[A-Z]\.",  # Initials
            r"F\.C\.",  # Common abbreviations
            
            # New patterns
            r"(?:text|writing)\s+appears\s+to\s+be\s+(?:written\s+)?in\s+(?:cursive|Spanish|a Romance language)",
            r"due\s+to\s+(?:its|the)\s+(?:age|condition|wear)",
            r"(?:contains|has)\s+(?:some|many|several)\s+(?:symbols|marks|characters)",
            r"(?:I am|I'm)\s+sorry.*?(?:assist|help)",
            r"[`]{3,}",  # Match 3 or more backticks
            r'"{2,}',    # Match 2 or more quotes
            r'(?:is|are|reads?|appears?)\s+as\s+follows\s*[:.]*',  # All variations of "as follows"
            r'["`]{1,}',  # Any number of quotes or backticks
            
            # Enhanced cannot assist pattern
            r"(?:I am|I'm)?\s*(?:sorry|apolog[a-z]+),?\s*(?:but|however)?\s*(?:I|we)\s*(?:can(?:no)?t|am unable to)\s*(?:help|assist)",
            
            # Enhanced patterns for common fragments
            r"(?:from|in|on)\s+(?:the|this)\s+(?:image|page|document)[:.]?\s*",
            r"(?:is|are|reads?)\s+as\s+follows[:.]?\s*",
            r"[-]{3,}\s*",  # Remove markdown horizontal rules
            r'(?:^|\n)\s*["`]{1,3}[^`"]*?["`]{1,3}\s*(?:\n|$)',  # Remove code blocks with content
            r'(?:^|\n)\s*[":]\s*(?:\n|$)',  # Remove lone colons/quotes
            r'(?:^|\n)\s+(?:\n|$)',  # Remove lines with only whitespace
            r'\n{3,}',  # Compress multiple newlines
            
            # Enhanced patterns for document formatting
            r"^#{1,3}\s+Document\s+Text\s*$",  # Markdown headers
            r"^line\s+\d+:\s*",  # Line numbers
            r"(?:^|\n)(?:line\s+)?\d+:\s*(?:\n|$)",  # Numbered lines
            r"[-_]{3,}\s*(?:\n|$)",  # Horizontal rules
            r"```.*?```",  # Code blocks
            r'(?:^|\n)\s*[\'"`]{1,3}[^\'"`]*?[\'"`]{1,3}\s*(?:\n|$)',  # Fixed quoted/backticked blocks
            r"(?:line\s+\d+:\s*){2,}",  # Multiple line numbers in sequence
            
            # Enhanced formatting cleanup
            r':\s*\n+\s*"',  # Colon followed by newlines and quote
            r'(?:^|\n)\s*"?\s*$',  # Empty quoted lines
            r'(?:when|if)\s+(?:properly|correctly)\s+(?:formatted|structured)',  # Formatting instructions
            r'with\s+(?:a|some)\s+(?:slightly|partially)?\s+(?:curved|dark|damaged)',  # Physical descriptions
            r'(?:^|\n)\s*---+\s*(?:\n|$)',  # Horizontal rules with optional newlines
            r'(?:^|\n)\s*```[^`]*```\s*(?:\n|$)',  # Code blocks with optional content
        ]
        
        for pattern in cleanup_patterns:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE | re.MULTILINE)
        
        # Preserve paragraph breaks while cleaning up excessive whitespace
        lines = text.splitlines()
        clean_lines = []
        for line in lines:
            clean_line = re.sub(r'\s+', ' ', line).strip()  # Clean up internal whitespace
            if clean_line:  # Only add non-empty lines
                clean_lines.append(clean_line)
            elif clean_lines and clean_lines[-1]:  # Add blank line for paragraph break
                clean_lines.append('')
        
        # Join with double newlines to preserve paragraph structure
        text = '\n\n'.join(line for line in clean_lines if line or clean_lines[-1])
        return text.strip()

    @staticmethod
    def calculate_average_line_length(text: str) -> int:
        """Calculate average line length for paragraph-like lines."""
        lines = text.splitlines()
        # Only consider lines that look like paragraphs (more than 30 chars)
        paragraph_lines = [line for line in lines if len(line) > 30]
        if not paragraph_lines:
            return 72  # Default fallback
        return int(sum(len(line) for line in paragraph_lines) / len(paragraph_lines))

    @staticmethod
    def split_long_lines(text: str, max_length: int = 72) -> str:
        """Simple line wrapper at max_length characters."""
        lines = text.splitlines()
        wrapped_lines = []
        
        for line in lines:
            if len(line) <= max_length:
                wrapped_lines.append(line)
                continue
                
            # Split long line into chunks
            current_line = ""
            words = line.split()
            
            for word in words:
                test_line = current_line + " " + word if current_line else word
                if len(test_line) <= max_length:
                    current_line = test_line
                else:
                    if current_line:
                        wrapped_lines.append(current_line)
                    current_line = word
            
            if current_line:
                wrapped_lines.append(current_line)
                
        return "\n".join(wrapped_lines)  # Fixed the string literal here

    @staticmethod
    def remove_boundary_quotes(text: str) -> str:
        """Remove quotes at the beginning and end of the document."""
        text = text.strip()
        if text.startswith('"'):
            text = text[1:]
        if text.endswith('"'):
            text = text[:-1]
        return text.strip()

    @staticmethod
    def clean_line_spacing(text: str) -> str:
        """Clean up excessive whitespace while preserving paragraph breaks"""
        # First split into lines and clean up internal whitespace
        lines = text.splitlines()
        cleaned_lines = []
        for line in lines:
            # Clean up internal whitespace but preserve the line
            cleaned_line = re.sub(r'\s+', ' ', line).strip()
            cleaned_lines.append(cleaned_line)
        
        # Join lines with newlines, preserving paragraph breaks
        text = '\n'.join(cleaned_lines)
        
        # Replace 3 or more newlines with 2 newlines (preserving paragraph breaks)
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        return text.strip()

    @staticmethod
    def clean_text(text: str) -> str:
        """Apply all cleaning steps to the text"""
        # Pre-process pathological patterns that can cause regex crashes
        text = TextCleaner.remove_pathological_patterns(text)
        
        # Remove unwanted content
        text = TextCleaner.remove_specific_phrases(text)
        text = TextCleaner.remove_boundary_quotes(text)
        text = TextCleaner.combine_single_word_paragraphs(text)
        text = TextCleaner.clean_repeated_phrases(text)
        text = TextCleaner.remove_repeated_phrases(text)
        text = TextCleaner.remove_repeated_words(text)
        text = TextCleaner.remove_repeated_phrases_between_chunks(text)
        text = TextCleaner.remove_repeated_phrases_regex(text)
        
        # Format lines
        avg_length = TextCleaner.calculate_average_line_length(text)
        max_length = min(avg_length * 1.5, 72)
        text = TextCleaner.split_long_lines(text, int(max_length))
        
        # Final cleanup of spacing while preserving paragraph breaks
        text = TextCleaner.clean_line_spacing(text)
        
        return text.strip()

    @staticmethod
    def remove_pathological_patterns(text: str) -> str:
        """Remove patterns that can cause catastrophic backtracking in regex operations"""
        # Remove excessive repetitive patterns like [Guess: m] [Guess: m] [Guess: m]...
        # This prevents regex catastrophic backtracking
        
        # Pattern 1: Remove repetitive [Guess: X] patterns
        text = re.sub(r'(\[Guess:[^\]]*\]\s*){3,}', '', text, flags=re.IGNORECASE)
        
        # Pattern 2: Remove any pattern repeated more than 10 times in a row
        # This is a safety net for other repetitive patterns
        text = re.sub(r'(\b\w+\b\s*){20,}', '', text)
        
        # Pattern 3: Remove lines that are mostly repetitive characters
        lines = text.splitlines()
        clean_lines = []
        for line in lines:
            # If a line has the same short pattern repeated many times, remove it
            if len(line) > 100:  # Only check long lines
                # Check for patterns like "m m m m m m m..."
                words = line.split()
                if len(words) > 50:  # If line has many words
                    # Count occurrences of each word
                    word_counts = {}
                    for word in words:
                        word_counts[word] = word_counts.get(word, 0) + 1
                    
                    # If any single word appears more than 50% of the time, skip this line
                    max_count = max(word_counts.values()) if word_counts else 0
                    if max_count > len(words) * 0.5:
                        continue  # Skip this pathological line
            
            clean_lines.append(line)
        
        return '\n'.join(clean_lines)

def process_document(file_path: str, output_folder: Path) -> dict:
    """Process a single document file"""
    try:
        # Use SegmentHandler for consistent path handling
        source_path = Path(file_path)
        rel_path = SegmentHandler.get_relative_path(source_path)
        
        # Use relative path for output
        out_path = output_folder / "documents" / rel_path.with_suffix('.txt')
        ensure_dirs(out_path)
        
        # Skip if already exists and return proper manifest entry
        if out_path.exists():
            return {
                "source": str(rel_path),  # Preserve original source extension
                "outputs": [str(rel_path.with_suffix('.txt'))],  # TXT as output
                "skipped": True,
                "success": True
            }
        
        # The input file should already be the correct path from BatchProcessor
        input_path = source_path.with_suffix('.txt')
        if not input_path.exists():
            # Create empty output file when input is missing (upstream step failed)
            tool_logger.warning(f"Input file not found: {input_path} - creating empty output file")
            
            # Create empty file
            out_path.write_text("")
            
            return {
                "source": str(rel_path),  # Preserve original source extension
                "outputs": [str(rel_path.with_suffix('.txt'))],  # TXT as output
                "success": True,
                "details": {
                    "original_length": 0,
                    "cleaned_length": 0,
                    "reduction_percent": 0,
                    "empty_due_to_missing_input": True
                }
            }
            
        # Read input text with better error handling
        try:
            text = input_path.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            try:
                text = input_path.read_text(encoding='latin-1')
            except Exception as e:
                tool_logger.error(f"Failed to read file {input_path} with any encoding: {e}")
                # Create empty output file when input can't be read
                out_path.write_text("")
                return {
                    "source": str(rel_path),  # Preserve original source extension
                    "outputs": [str(rel_path.with_suffix('.txt'))],
                    "success": True,
                    "details": {
                        "original_length": 0,
                        "cleaned_length": 0,
                        "reduction_percent": 0,
                        "empty_due_to_encoding_error": True
                    }
                }
        except Exception as e:
            tool_logger.error(f"Unexpected error reading file {input_path}: {e}")
            # Create empty output file when input can't be read
            out_path.write_text("")
            return {
                "source": str(rel_path),  # Preserve original source extension
                "outputs": [str(rel_path.with_suffix('.txt'))],
                "success": True,
                "details": {
                    "original_length": 0,
                    "cleaned_length": 0,
                    "reduction_percent": 0,
                    "empty_due_to_read_error": True
                }
            }
        
        if not text.strip():
            # Create empty output file when input is empty
            tool_logger.info(f"Input file is empty: {input_path} - creating empty output file")
            
            # Create empty file
            out_path.write_text("")
            
            return {
                "source": str(rel_path),  # Preserve original source extension
                "outputs": [str(rel_path.with_suffix('.txt'))],  # TXT as output
                "success": True,
                "details": {
                    "original_length": 0,
                    "cleaned_length": 0,
                    "reduction_percent": 0,
                    "empty_due_to_empty_input": True
                }
            }
        
        # Check for extremely large files that might cause memory issues
        if len(text) > 10_000_000:  # 10MB text limit
            tool_logger.warning(f"File {input_path} is very large ({len(text)} chars), truncating to prevent memory issues")
            text = text[:10_000_000]
        
        # Clean the text with error handling
        try:
            cleaned_text = TextCleaner.clean_text(text)
        except Exception as e:
            tool_logger.error(f"Error cleaning text for {input_path}: {e}")
            # Fall back to minimal cleaning
            try:
                cleaned_text = text.strip()
                # Apply only basic cleaning that's less likely to crash
                cleaned_text = TextCleaner.clean_line_spacing(cleaned_text)
                tool_logger.warning(f"Applied minimal cleaning for {input_path} due to error")
            except Exception as e2:
                tool_logger.error(f"Even minimal cleaning failed for {input_path}: {e2}")
                # Last resort - just use original text
                cleaned_text = text.strip()
        
        # Write cleaned text with error handling
        try:
            out_path.write_text(cleaned_text, encoding='utf-8')
        except Exception as e:
            tool_logger.error(f"Error writing output file {out_path}: {e}")
            return {
                "source": str(rel_path),  # Preserve original source extension
                "error": f"Failed to write output: {str(e)}"
            }
        
        # Get bg_removed from input manifest
        bg_removed = None
        try:
            recombine_manifest = output_folder.parent / "recombined" / "recombine_manifest.jsonl"
            if recombine_manifest.exists():
                with open(recombine_manifest, 'r') as f:
                    for line in f:
                        entry = json.loads(line)
                        if entry.get('source') == str(rel_path.with_suffix('.txt')):
                            bg_removed = entry.get('bg_removed')
                            break
        except Exception as e:
            tool_logger.warning(f"Could not read bg_removed info: {e}")
        
        # Return success manifest entry with proper relative paths
        result = {
            "source": str(rel_path),  # Preserve original source extension
            "outputs": [str(rel_path.with_suffix('.txt'))],  # TXT as output
            "success": True,
            "details": {
                "original_length": len(text),
                "cleaned_length": len(cleaned_text),
                "reduction_percent": round((1 - len(cleaned_text)/len(text)) * 100, 2) if len(text) > 0 else 0
            }
        }
        
        # Add bg_removed if found
        if bg_removed:
            result["bg_removed"] = bg_removed
            
        return result
        
    except Exception as e:
        tool_logger.error(f"Unexpected error processing {file_path}: {e}")
        # Try to get relative path for error reporting
        try:
            rel_path = SegmentHandler.get_relative_path(Path(file_path))
            source_ref = str(rel_path)  # Preserve original source extension
        except:
            source_ref = str(file_path)
        
        return {
            "source": source_ref,
            "error": str(e)
        }

def fuzzy_clean_batch(
    source_folder: Path,
    source_manifest: Path,
    output_folder: Path,
    **kwargs
) -> dict:
    """
    Clean up text from recombined transcriptions - importable function
    
    Args:
        source_folder: Path to the recombined files
        source_manifest: Path to the recombined manifest file
        output_folder: Output folder for cleaned transcriptions
        
    Returns:
        Processing statistics dictionary
    """
    # Validate inputs
    if not source_folder.exists():
        raise FileNotFoundError(f"Recombined folder not found: {source_folder}")
    if not source_manifest.exists():
        raise FileNotFoundError(f"Recombined manifest not found: {source_manifest}")
        
    # Derive process name from output folder to avoid hardcoded names
    process_name = output_folder.name if output_folder.name else "transcription"
    
    processor = BatchProcessor(
        input_manifest=source_manifest,
        output_folder=output_folder,
        process_name=process_name,
        processor_fn=process_document,
        base_folder=source_folder,
        use_source=True
    )
    
    return processor.process()

def fuzzy_clean(
    recombined_folder: Path = typer.Argument(..., help="Path to the recombined files"),
    recombined_manifest: Path = typer.Argument(..., help="Path to the recombined manifest file"),
    transcriptions_folder: Path = typer.Argument(..., help="Output folder for cleaned transcriptions")
):
    """Clean up text from recombined transcriptions"""
    return fuzzy_clean_batch(recombined_folder, recombined_manifest, transcriptions_folder)

if __name__ == "__main__":
    typer.run(fuzzy_clean)