import typer
from pathlib import Path
from rich.console import Console
from utils.batch import BatchProcessor
from utils.files import ensure_dirs
from utils.segment_handler import SegmentHandler
import json
import re
from collections import defaultdict

console = Console()

def load_bg_removal_manifest(manifest_path: Path) -> dict:
    """Load background removal manifest and create source->output mapping"""
    mapping = {}
    with open(manifest_path) as f:
        for line in f:
            entry = json.loads(line)
            if entry.get("success"):
                # Strip any project folder prefix from source
                source = entry["source"]
                if "documents/" in source:
                    source = source.split("documents/")[1]
                output = entry["outputs"][0]
                mapping[source] = output
    return mapping

def numerical_sort(value):
    parts = re.split(r'(\d+)', value)
    return [int(part) if part.isdigit() else part for part in parts]

def group_segments_by_parent(manifest_path: Path) -> dict:
    """Group segment files by their parent image"""
    console.print(f"[blue]Loading segments from manifest: {manifest_path}")
    groups = defaultdict(list)
    try:
        with open(manifest_path) as f:
            for line in f:
                entry = json.loads(line)
                if "source" in entry and entry.get("outputs"):
                    source = entry["source"]
                    # Extract the parent image path from the segment path
                    if "_segments/" in source:
                        parent = source.split("_segments/")[0] + ".jpg"
                        # Use the output path from the manifest
                        output_path = entry["outputs"][0]
                        groups[parent].append(output_path)
                        console.print(f"[blue]Added segment {output_path} to parent {parent}")
    except Exception as e:
        console.print(f"[red]Error reading manifest {manifest_path}: {e}")
        raise
    
    console.print(f"[blue]Found {len(groups)} parent images")
    return dict(groups)

def process_document(file_path: str, output_folder: Path, bg_mapping: dict, segments_mapping: dict, input_folder: Path) -> dict:
    """Process segments belonging to the same source image"""
    try:
        console.print(f"\n[blue]====== Processing document ======")
        console.print(f"[blue]Input file_path: {file_path}")
        
        # Normalize the source path to match manifest entries
        source_path = Path(file_path)
        console.print(f"[blue]Initial source_path: {source_path}")
        
        # Get corresponding segments
        segment_files = segments_mapping.get(str(source_path), [])
        console.print(f"[blue]Found {len(segment_files)} segments for {source_path}")
        
        if not segment_files:
            return {
                "source": str(source_path.with_suffix('.txt')),
                "error": f"No segments found for {source_path}"
            }

        # Get segments folder path and verify files exist
        text_files = []
        missing_segments = 0
        for segment_path in sorted(segment_files, key=lambda x: numerical_sort(Path(x).stem)):
            # Use SegmentHandler to get the correct path
            full_path = input_folder / "documents" / segment_path
            console.print(f"[blue]Looking for segment file: {full_path}")
            if full_path.exists():
                text_files.append(full_path)
            else:
                missing_segments += 1
                console.print(f"[yellow]Skipping missing segment file {full_path} (likely empty region)")
                
        if not text_files:
            return {
                "source": str(source_path.with_suffix('.txt')),
                "error": f"No text segments found for {source_path}"
            }

        # Combine text from all segments
        combined_text = ""
        for text_file in text_files:
            try:
                text = text_file.read_text()
                if text.strip():  # Only add non-empty segments
                    combined_text += text + "\n\n"  # Add double newline for better separation
                    console.print(f"[blue]Added {len(text)} characters from {text_file}")
            except Exception as e:
                console.print(f"[red]Error reading {text_file}: {e}")

        # Create output directory and subdirectories using SegmentHandler
        output_path = output_folder / "documents" / source_path.parent / source_path.name
        output_path = output_path.with_suffix('.txt')
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        console.print(f"[blue]Writing combined output to: {output_path}")
        output_file_text = combined_text.strip()
        if output_file_text:  # Only write if we have content
            output_path.write_text(output_file_text)
            console.print(f"[green]Successfully wrote {len(output_file_text)} characters")

        # Get relative paths using SegmentHandler
        rel_path = SegmentHandler.get_relative_path(source_path)
        output_rel_path = SegmentHandler.get_relative_path(output_path)
            
        return {
            "source": str(rel_path.with_suffix('.txt')),
            "bg_removed": bg_mapping.get(str(rel_path)),
            "outputs": [str(output_rel_path)],
            "segments_joined": len(text_files),
            "segments_skipped": missing_segments,
            "success": True
        }

    except Exception as e:
        console.print(f"[red]Error processing {file_path}: {e}")
        return {
            "source": str(Path(file_path).with_suffix('.txt')),
            "error": str(e)
        }

def recombine_segments(
    input_folder: Path = typer.Argument(..., help="Path to the transcribed segments folder"),
    output_folder: Path = typer.Argument(..., help="Output folder for recombined files"),
    input_manifest: Path = typer.Argument(..., help="Path to the transcriptions manifest file"),
    bg_removal_manifest: Path = typer.Argument(..., help="Path to the background removal manifest file")
):
    """Recombine transcribed segments back into full documents"""
    
    # Create output directories
    ensure_dirs(output_folder)
    ensure_dirs(output_folder / "documents")
    
    # Load manifests
    bg_mapping = load_bg_removal_manifest(bg_removal_manifest)
    segments_mapping = group_segments_by_parent(input_manifest)
    
    # Get unique parent images to process
    parent_images = list(segments_mapping.keys())
    console.print(f"[green]Found {len(parent_images)} parent images to process")
    
    # Process each parent image
    results = []
    for parent in parent_images:
        result = process_document(parent, output_folder, bg_mapping, segments_mapping, input_folder)
        results.append(result)
        
    try:
        # Create manifest directory if needed and write manifest
        manifest_path = output_folder / "recombine_manifest.jsonl"
        ensure_dirs(manifest_path.parent)
        
        with open(manifest_path, 'w') as f:
            for result in results:
                f.write(json.dumps(result) + '\n')
        
        console.print(f"[green]Wrote manifest to {manifest_path}")
    except Exception as e:
        console.print(f"[red]Error writing manifest: {e}")
        raise
    
    stats = {"processed": len([r for r in results if r.get("success")]),
             "failed": len([r for r in results if not r.get("success")])}
    
    console.print(f"[green]\nRecombining completed. Processed: {stats['processed']}, Failed: {stats['failed']}")
    return stats

if __name__ == "__main__":
    typer.run(recombine_segments)
