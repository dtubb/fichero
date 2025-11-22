"""
Director Output Parser

Parses Fichero Director output folders to extract file-level results.
Director outputs have a structured format:

output_folder/
├── documents/           # Input files (copied and sanitized)
├── assets/
│   ├── manifests/      # documents_manifest.jsonl
│   ├── prepared/       # prepared images + prepare_images_manifest.jsonl
│   ├── transcriptions/ # transcriptions + transcriptions_manifest.jsonl
│   ├── llm_catalogue/  # LLM outputs + llm_process_manifest.jsonl
│   └── word/           # Final Word documents
└── logs/               # workflow logs
"""

import json
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class ProcessingStep:
    """Represents a single processing step with its output"""
    step_number: int
    step_name: str
    file_path: Path
    file_type: str  # "image", "text", "document"
    description: str
    manifest_entry: Optional[Dict] = None  # Enriched manifest with source_image_path

    @property
    def files(self) -> List[Path]:
        """Compatibility property - returns file_path as a single-item list

        This makes ProcessingStep compatible with output_view which expects .files list
        """
        return [self.file_path] if self.file_path else []

    @property
    def tool_name(self) -> str:
        """Compatibility property - returns step_name as tool_name

        This makes ProcessingStep compatible with ToolOutput interface
        """
        return self.step_name


@dataclass
class FileOutput:
    """Represents outputs for a single file"""
    original_file: Optional[Path] = None
    prepared_file: Optional[Path] = None
    transcription_file: Optional[Path] = None
    word_doc: Optional[Path] = None
    llm_output: Optional[Path] = None
    metadata: Dict = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class DirectorOutputParser:
    """Parse Director output folders to extract file-level results"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def parse_output_folder(self, output_path: Path) -> Dict:
        """
        Parse a Director output folder

        Args:
            output_path: Path to the Director output folder

        Returns:
            Dict with structure:
            {
                "input_files": [Path, ...],
                "prepared_files": [Path, ...],
                "transcriptions": [Path, ...],
                "word_docs": [Path, ...],
                "manifests": {
                    "documents": [...],
                    "prepared": [...],
                    "transcriptions": [...],
                    "llm_process": [...]
                }
            }
        """
        if not output_path.exists():
            self.logger.warning(f"Output path does not exist: {output_path}")
            return self._empty_result()

        result = {
            "input_files": [],
            "prepared_files": [],
            "transcriptions": [],
            "word_docs": [],
            "manifests": {}
        }

        # Parse documents folder
        documents_dir = output_path / "documents"
        if documents_dir.exists():
            result["input_files"] = self._list_image_files(documents_dir)

        # Parse assets
        assets_dir = output_path / "assets"
        if not assets_dir.exists():
            return result

        # Parse manifests first (we need them to discover files if folder structure is non-standard)
        manifests_dir = assets_dir / "manifests"
        if manifests_dir.exists():
            result["manifests"] = self._parse_manifests(manifests_dir)

        # Prepared images
        prepared_dir = assets_dir / "prepared"
        if prepared_dir.exists():
            result["prepared_files"] = self._list_image_files(prepared_dir)

        # Transcriptions (support both .json and .txt files)
        transcriptions_dir = assets_dir / "transcriptions"
        if transcriptions_dir.exists():
            result["transcriptions"] = self._list_transcription_files(transcriptions_dir)

        # Word documents
        word_dir = assets_dir / "word"
        if word_dir.exists():
            result["word_docs"] = list(word_dir.glob("*.docx"))

        # If no input_files were found from documents folder, try to discover them from prepared manifest
        # This handles cases where Director output doesn't have a root-level documents folder
        if not result["input_files"] and result["manifests"].get("prepared"):
            self.logger.debug("No documents folder found, trying to discover input files from prepared manifest")
            for entry in result["manifests"]["prepared"]:
                source_path = entry.get("source", "")
                if source_path:
                    # The source path is relative to prepared_dir
                    full_source_path = prepared_dir / source_path
                    if full_source_path.exists():
                        result["input_files"].append(full_source_path)
                        self.logger.debug(f"  Discovered input file from manifest: {full_source_path.name}")

        return result

    def get_file_outputs(self, output_path: Path, original_filename: str) -> List[FileOutput]:
        """
        Get all outputs for a specific input file

        Args:
            output_path: Path to the Director output folder
            original_filename: Name of the original file (e.g., "image001.jpg")

        Returns:
            List of FileOutput objects (usually one, but could be multiple for batch processing)
        """
        parsed = self.parse_output_folder(output_path)

        # Find matching files by name
        base_name = Path(original_filename).stem
        outputs = []

        # Find original
        original = self._find_file_by_stem(parsed["input_files"], base_name)

        # Find prepared
        prepared = self._find_file_by_stem(parsed["prepared_files"], base_name)

        # Find transcription
        transcription = self._find_file_by_stem(parsed["transcriptions"], base_name)

        # Find word doc
        word_doc = self._find_file_by_stem(parsed["word_docs"], base_name)

        # Get metadata from manifests
        metadata = self._get_file_metadata(parsed["manifests"], base_name)

        if any([original, prepared, transcription, word_doc]):
            outputs.append(FileOutput(
                original_file=original,
                prepared_file=prepared,
                transcription_file=transcription,
                word_doc=word_doc,
                metadata=metadata
            ))

        return outputs

    def get_all_file_outputs(self, output_path: Path) -> List[FileOutput]:
        """
        Get outputs for ALL files in the output folder

        Returns:
            List of FileOutput objects, one per processed file
        """
        parsed = self.parse_output_folder(output_path)

        # Use input files as the base list
        file_outputs = []

        for input_file in parsed["input_files"]:
            base_name = input_file.stem

            # Find corresponding outputs
            prepared = self._find_file_by_stem(parsed["prepared_files"], base_name)
            transcription = self._find_file_by_stem(parsed["transcriptions"], base_name)
            word_doc = self._find_file_by_stem(parsed["word_docs"], base_name)
            metadata = self._get_file_metadata(parsed["manifests"], base_name)

            file_outputs.append(FileOutput(
                original_file=input_file,
                prepared_file=prepared,
                transcription_file=transcription,
                word_doc=word_doc,
                metadata=metadata
            ))

        return file_outputs

    def get_processing_steps(self, file_output: FileOutput) -> List[ProcessingStep]:
        """
        Get ordered list of processing steps for a file

        Reads manifests dynamically to discover step names and order.
        Works with any workflow/plan configuration.

        Args:
            file_output: FileOutput object from get_file_outputs()

        Returns:
            List of ProcessingStep objects in workflow order
        """
        steps = []

        # Extract base filename for matching manifest entries
        # Try to get from any available file (original, prepared, transcription, etc.)
        base_file = (file_output.original_file or
                    file_output.prepared_file or
                    file_output.transcription_file or
                    file_output.word_doc)

        if not base_file:
            return steps

        base_name = base_file.stem

        # Define step order based on manifest presence and typical workflow
        # This is generic and works with any plan
        step_configs = [
            {
                'manifest_key': 'documents',
                'file_attr': 'original_file',
                'default_name': 'Input',
                'file_type': 'image'
            },
            {
                'manifest_key': 'prepared',
                'file_attr': 'prepared_file',
                'default_name': 'Prepared',
                'file_type': 'image'
            },
            {
                'manifest_key': 'transcriptions',
                'file_attr': 'transcription_file',
                'default_name': 'Transcription',
                'file_type': 'text'
            },
            {
                'manifest_key': 'llm_process',
                'file_attr': 'llm_output',
                'default_name': 'LLM Processing',
                'file_type': 'text'
            }
        ]

        step_num = 1

        # Process each potential step
        for config in step_configs:
            file_path = getattr(file_output, config['file_attr'], None)
            if not file_path:
                continue

            # Get step name from manifest metadata, or use default
            step_name = config['default_name']
            description = ""

            if config['manifest_key'] in file_output.metadata:
                manifest_entry = file_output.metadata[config['manifest_key']]
                # Try to extract step name from manifest
                step_name = manifest_entry.get('step_name', manifest_entry.get('tool', config['default_name']))
                description = manifest_entry.get('description', '')

            steps.append(ProcessingStep(
                step_number=step_num,
                step_name=step_name,
                file_path=file_path,
                file_type=config['file_type'],
                description=description
            ))
            step_num += 1

        # Add Word document if present (final step)
        if file_output.word_doc:
            steps.append(ProcessingStep(
                step_number=step_num,
                step_name="Word Document",
                file_path=file_output.word_doc,
                file_type="document",
                description="Final output document"
            ))

        return steps

    def _list_image_files(self, directory: Path) -> List[Path]:
        """List all image files in a directory recursively"""
        extensions = {'.jpg', '.jpeg', '.png', '.tiff', '.tif', '.webp'}
        files = []
        for ext in extensions:
            files.extend(directory.glob(f"**/*{ext}"))
            files.extend(directory.glob(f"**/*{ext.upper()}"))
        return sorted(files)

    def _list_json_files(self, directory: Path) -> List[Path]:
        """List all JSON files in a directory"""
        return sorted(directory.glob("*.json"))

    def _list_transcription_files(self, directory: Path) -> List[Path]:
        """List all transcription files (both .json and .txt) in a directory recursively"""
        files = []
        # Search recursively for both .json and .txt files
        files.extend(directory.glob("**/*.json"))
        files.extend(directory.glob("**/*.txt"))
        return sorted(files)

    def _parse_manifests(self, manifests_dir: Path) -> Dict:
        """Parse all manifest.jsonl files"""
        manifests = {}

        manifest_files = {
            "documents": "documents_manifest.jsonl",
            "prepared": "prepare_images_manifest.jsonl",
            "transcriptions": "transcriptions_manifest.jsonl",
            "llm_process": "llm_process_manifest.jsonl"
        }

        for key, filename in manifest_files.items():
            manifest_path = manifests_dir / filename
            if manifest_path.exists():
                manifests[key] = self._read_jsonl(manifest_path)

        return manifests

    def _read_jsonl(self, file_path: Path) -> List[Dict]:
        """Read a JSONL file"""
        entries = []
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        entries.append(json.loads(line))
        except Exception as e:
            self.logger.error(f"Error reading JSONL file {file_path}: {e}")
        return entries

    def _find_file_by_stem(self, files: List[Path], stem: str) -> Optional[Path]:
        """Find a file in a list by its stem (filename without extension)"""
        for file in files:
            if file.stem == stem:
                return file
        return None

    def _get_file_metadata(self, manifests: Dict, base_name: str) -> Dict:
        """Extract metadata for a file from manifests"""
        metadata = {}

        # Search all manifests for entries matching this file
        for manifest_type, entries in manifests.items():
            for entry in entries:
                # Check various possible keys for filename
                file_key = entry.get('file', entry.get('filename', entry.get('path', '')))
                if file_key and Path(file_key).stem == base_name:
                    metadata[manifest_type] = entry

        return metadata

    def _empty_result(self) -> Dict:
        """Return an empty result structure"""
        return {
            "input_files": [],
            "prepared_files": [],
            "transcriptions": [],
            "word_docs": [],
            "manifests": {}
        }
