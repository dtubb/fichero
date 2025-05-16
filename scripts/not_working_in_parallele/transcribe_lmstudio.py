import typer
from pathlib import Path
import requests
import base64
from io import BytesIO
from PIL import Image
import json
from rich.console import Console
from utils.batch import BatchProcessor
from utils.processor import process_file
from utils.segment_handler import SegmentHandler
import os

console = Console()

DEFAULT_PROMPT = "Extract all text line by line. Do not number lines. RETURN ONLY PLAIN TEXT. SAY NOTHING ELSE"

class LMStudioTranscriber:
    def __init__(self, api_url: str, model_name: str, prompt: str = DEFAULT_PROMPT):
        self.api_url = api_url
        self.model_name = model_name
        self.prompt = prompt

    def process_image(self, image: Image.Image) -> str:
        """Process an image using LMStudio's API"""
        try:
            # Convert image to base64
            buffered = BytesIO()
            image.save(buffered, format="PNG")
            img_str = base64.b64encode(buffered.getvalue()).decode()

            # Prepare the request payload
            payload = {
                "model": self.model_name,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": self.prompt},
                            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_str}"}}
                        ]
                    }
                ],
                "max_tokens": 2048,
                "temperature": 0.7
            }

            # Make the API request
            response = requests.post(
                f"{self.api_url}/chat/completions",
                json=payload,
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()

            # Extract the transcription from the response
            result = response.json()
            transcription = result["choices"][0]["message"]["content"].strip()

            return transcription

        except Exception as e:
            console.print(f"[red]Error in LMStudio processing: {e}")
            return ""

def process_image(img_path: Path, out_path: Path, api_url: str, model_name: str) -> dict:
    """Process a single image file, returning manifest-compatible output"""
    try:
        # Ensure output directory exists
        out_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Convert output path to .txt extension but preserve original extension in source
        out_path = out_path.with_suffix('.txt')
        out_path.touch()
        
        try:
            # Initialize transcriber
            transcriber = LMStudioTranscriber(
                api_url=api_url,
                model_name=model_name,
                prompt=DEFAULT_PROMPT
            )
            
            # Load and process image
            image = Image.open(img_path).convert("RGB")
            transcription = transcriber.process_image(image)
            
            # Save transcription
            with open(out_path, 'w', encoding='utf-8') as f:
                f.write(transcription)
            
            # Create manifest entry
            rel_path = SegmentHandler.get_relative_path(img_path)
            result = {
                "outputs": [str(rel_path.with_suffix('.txt'))],
                "source": str(rel_path),
                "details": {
                    "has_content": bool(transcription.strip())
                }
            }
            
            # Add parent image info
            if 'segments' in str(rel_path):
                parent_path = rel_path.parents[1]
                result["parent_image"] = str(parent_path)
            else:
                result["parent_image"] = str(rel_path)
                
            return result
            
        except Exception as e:
            # Return error but keep empty file
            return {
                "error": str(e),
                "outputs": [str(SegmentHandler.get_relative_path(out_path))],
                "source": str(SegmentHandler.get_relative_path(img_path))
            }

    except Exception as e:
        console.print(f"[red]Error processing {img_path}: {e}")
        return {"error": str(e)}

def process_document(file_path: str, output_folder: Path, api_url: str, model_name: str) -> dict:
    """Process a document using the process_file utility"""
    file_path = Path(file_path)
    
    def process_fn(f: str, o: Path) -> dict:
        # Process the image and let process_file handle path management
        result = process_image(Path(f), o, api_url, model_name)
        
        # Add parent image info if needed
        if not result.get("error"):
            rel_path = SegmentHandler.get_relative_path(Path(f))
            if 'segments' in str(rel_path):
                result["parent_image"] = str(rel_path.parents[1])
            else:
                result["parent_image"] = str(rel_path)
                
        return result
    
    return process_file(
        file_path=str(file_path),
        output_folder=output_folder,
        process_fn=process_fn,
        file_types={
            '.png': process_fn,
            '.jpg': process_fn,
            '.jpeg': process_fn
        }
    )

def transcribe(
    segment_folder: Path = typer.Argument(..., help="Input segments folder"),
    segment_manifest: Path = typer.Argument(..., help="Input segments manifest"),
    transcribed_folder: Path = typer.Argument(..., help="Output folder for transcriptions"),
    api_url: str = typer.Option(
        "http://localhost:1234",
        "--api-url",
        help="LMStudio API URL (without /v1)"
    ),
    model_name: str = typer.Option(
        ...,  # No default, must be provided
        "--model", "-m",
        help="Model name in LMStudio (e.g. qwen2.5-vl-7b-instruct)"
    ),
    prompt: str = typer.Option(
        DEFAULT_PROMPT,
        "--prompt", "-p",
        help="Prompt for transcription"
    )
):
    """Batch transcription CLI using LMStudio for processing"""
    # Ensure API URL has /v1 for chat completions
    if not api_url.endswith('/v1'):
        api_url = f"{api_url}/v1"
    
    console.print(f"Using LMStudio API: {api_url}")
    console.print(f"Using model: {model_name}")
    console.print(f"Using prompt: {prompt}")

    processor = BatchProcessor(
        input_manifest=segment_manifest,
        output_folder=transcribed_folder,
        process_name="transcription",
        processor_fn=lambda f, o: process_document(f, o, api_url, model_name),
        base_folder=segment_folder
    )
    return processor.process()

if __name__ == "__main__":
    typer.run(transcribe) 