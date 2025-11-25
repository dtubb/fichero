#!/usr/bin/env python3
"""
Debug script to trace file type detection
"""

import json
import tempfile
from pathlib import Path

# Add src to path
import sys
sys.path.insert(0, str(Path(__file__).parent / "src"))

def test_type_detection():
    """Test the _determine_output_type method directly"""

    # Import the method directly to avoid initialization issues
    import logging
    logging.basicConfig(level=logging.DEBUG, format='%(name)s - %(levelname)s - %(message)s')

    # Test the exact file path from the failing test
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create the file structure
        cat_dir = Path(temp_dir) / "assets" / "catalogue"
        cat_dir.mkdir(parents=True)

        cat_file = cat_dir / "adjust_doc_catalogue.json"

        # Create content similar to the test
        catalogue_data = {
            "title": "Document: adjust_doc.jpg",
            "document_type": "Letter",
            "date": "1965-03-15",
            "author": "María González",
            "language": "Spanish",
            "description": "Personal letter discussing family matters"
        }
        cat_file.write_text(json.dumps(catalogue_data, indent=2))

        print(f"Testing file: {cat_file}")
        print(f"File exists: {cat_file.exists()}")

        # Test different step names to see how they affect detection
        test_cases = [
            ("", "Empty step name"),
            ("assets", "assets step name"),  # This is likely what the failing test uses
            ("catalogue", "catalogue step name"),
            ("unknown_step", "Unknown step name")
        ]

        for step_name, description in test_cases:
            print(f"\n=== {description} ===")
            result = determine_output_type_debug(cat_file, step_name, "Transcribir y Catalogar")
            print(f"Step: '{step_name}' -> Output type: '{result}'")

def determine_output_type_debug(file_path: Path, step_name: str, plan_name: str = None) -> str:
    """Debug version of _determine_output_type with detailed logging"""

    # Track confidence scores for different detection methods
    type_scores = {}

    # Method 1: Folder structure analysis (highest confidence)
    parts = [p.lower() for p in file_path.parts]

    folder_patterns = {
        'transcription': ['transcriptions', 'txt', 'text'],
        'prepared_image': ['prepared', 'prepared_images', 'processed_images', 'enhanced'],
        'word_doc': ['word_output', 'docx', 'documents', 'word'],
        'catalogue': ['llm_catalogue', 'catalogue', 'catalog', 'llm_catalog'],
        'json_data': ['json_output', 'data', 'manifests'],  # More specific patterns
        'markdown': ['markdown', 'md']
    }

    print(f"File path parts: {parts}")

    for output_type, patterns in folder_patterns.items():
        for pattern in patterns:
            if any(pattern in part for part in parts):
                type_scores[output_type] = type_scores.get(output_type, 0) + 3
                print(f"[OUTPUT_TYPE] Folder match: '{pattern}' -> {output_type} (+3)")

    # Method 2: File extension analysis (medium confidence)
    suffix = file_path.suffix.lower()
    extension_mapping = {
        '.txt': 'transcription',
        '.text': 'transcription',
        '.docx': 'word_doc',
        '.doc': 'word_doc',
        '.json': 'json_data',
        '.jsonl': 'json_data',
        '.jpg': 'prepared_image',
        '.jpeg': 'prepared_image',
        '.png': 'prepared_image',
        '.tif': 'prepared_image',
        '.tiff': 'prepared_image',
        '.md': 'markdown',
        '.markdown': 'markdown'
    }

    if suffix in extension_mapping:
        output_type = extension_mapping[suffix]
        type_scores[output_type] = type_scores.get(output_type, 0) + 2
        print(f"[OUTPUT_TYPE] Extension match: '{suffix}' -> {output_type} (+2)")

    # Method 3: Step name analysis (medium confidence)
    step_lower = step_name.lower()
    step_patterns = {
        'transcription': ['transcribe', 'transcript'],
        'catalogue': ['catalogue', 'catalog'],
        'prepared_image': ['prepare', 'crop', 'enhance', 'process_image'],
        'word_doc': ['word', 'docx', 'document'],
        'json_data': ['manifest', 'documents_manifest', 'build_documents']
    }

    for output_type, patterns in step_patterns.items():
        for pattern in patterns:
            if pattern in step_lower:
                type_scores[output_type] = type_scores.get(output_type, 0) + 2
                print(f"[OUTPUT_TYPE] Step name match: '{pattern}' -> {output_type} (+2)")

    # Method 6: Filename pattern analysis (high confidence for specific patterns)
    filename_lower = file_path.name.lower()
    if '_catalogue.json' in filename_lower or '_catalog.json' in filename_lower:
        type_scores['catalogue'] = type_scores.get('catalogue', 0) + 4
        print(f"[OUTPUT_TYPE] Catalogue filename pattern detected (+4)")
    elif 'catalogue' in filename_lower and suffix == '.json':
        type_scores['catalogue'] = type_scores.get('catalogue', 0) + 3
        print(f"[OUTPUT_TYPE] Catalogue filename detected (+3)")

    # Method 7: Content-based detection for text files (when available)
    if suffix in ['.txt', '.text', '.md', '.json']:
        try:
            # Quick content peek for additional confidence
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content_sample = f.read(1000).lower()  # First 1KB

            # Catalogue patterns
            if any(keyword in content_sample for keyword in ['título:', 'title:', 'author:', 'date:', 'summary:']):
                type_scores['catalogue'] = type_scores.get('catalogue', 0) + 2
                print(f"[OUTPUT_TYPE] Catalogue content detected (+2)")

        except Exception as e:
            print(f"[OUTPUT_TYPE] Content analysis failed for {file_path}: {e}")

    # Determine best match
    print(f"[OUTPUT_TYPE] All scores: {type_scores}")

    if type_scores:
        best_type = max(type_scores.items(), key=lambda x: x[1])
        best_score = best_type[1]
        result_type = best_type[0]

        # Log confidence level
        confidence = "high" if best_score >= 3 else "medium" if best_score >= 2 else "low"
        print(f"[OUTPUT_TYPE] Decision: {result_type} (confidence: {confidence}, score: {best_score})")

        return result_type

    # Fallback to unknown with diagnostic info
    print(f"[OUTPUT_TYPE] Unable to determine type for {file_path} (step: {step_name})")

    return 'unknown'

if __name__ == "__main__":
    test_type_detection()