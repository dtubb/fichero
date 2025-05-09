import os
import typer
from rich import print
from rich.progress import track
from typing_extensions import Annotated
from pathlib import Path 
from PIL import Image
from dotenv import load_dotenv 
from io import BytesIO
import base64
from openai import OpenAI
from utils.batch import BatchProcessor
from utils.processor import process_file
from utils.segment_handler import SegmentHandler

# Base 64 encoding format
def encode_image(image: Image.Image) -> str:
    # Resize image if needed
    max_size = 1500  # Slightly larger than 2B/7B models since Max can handle more
    width, height = image.size
    aspect_ratio = max(width, height) / float(min(width, height))
    
    # Skip extremely wide/tall images
    if aspect_ratio > 200:
        return ""
        
    if width > max_size or height > max_size:
        if width > height:
            new_width = max_size
            new_height = int((max_size / width) * height)
        else:
            new_height = max_size
            new_width = int((max_size / height) * width)
        image = image.resize((new_width, new_height), Image.LANCZOS)
    
    # Encode resized image
    buffered = BytesIO()
    image.save(buffered, format="JPEG", quality=85)  # Slightly reduced quality for better compression
    return base64.b64encode(buffered.getvalue()).decode("utf-8")

def process_image(file_path: Path, out_path: Path) -> dict:
    """Process a single image file, returning manifest-compatible output"""
    try:
        # Ensure output directory exists
        out_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Convert output path to .txt extension
        out_path = out_path.with_suffix('.txt')
        out_path.touch()
        
        try:
            print(f"[cyan]Processing image: {file_path}")
            
            # Load and process image
            image = Image.open(file_path).convert("RGB")
            
            # Encode image for API
            base64_image = encode_image(image)
            
            # Initialize OpenAI client with DashScope endpoint
            client = OpenAI(
                api_key=os.getenv("DASHSCOPE_API_KEY"),
                base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
            )
            
            print(f"[cyan]Sending to Qwen API...")
            
            # Get transcription using OpenAI-compatible method
            completion = client.chat.completions.create(
                model="qwen-vl-max",
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}},
                        {"type": "text", "text": "Extract all text line by line. Do not number lines. RETURN ONLY PLAIN TEXT. RETRUN NOTHING IF NOT TEXT. SAY NOTHING ELSE. DO NOT PROCESS REVERSED TEXT, MIRROED TEXT, GIBBERISH, OR TEXT IN LANGUAGE YOU DO NOT RECOGNIZE. RETURN EMTPY IF NOT TEXT."},
                    ]
                }]
            )
            
            print(f"[green]Received response from Qwen API")
            
            # Extract transcription from response
            transcription = completion.choices[0].message.content
            
            # Save transcription
            with open(out_path, 'w', encoding='utf-8') as f:
                f.write(transcription)
            
            # Create manifest entry with .txt extension
            rel_path = SegmentHandler.get_relative_path(file_path)
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
            print(f"[red]Error processing image {file_path}: {str(e)}")
            # Return error but keep empty file
            return {
                "error": str(e),
                "outputs": [str(SegmentHandler.get_relative_path(out_path))],
                "source": str(SegmentHandler.get_relative_path(file_path))
            }

    except Exception as e:
        print(f"[red]Error processing {file_path}: {e}")
        return {"error": str(e)}

def process_document(file_path: str, output_folder: Path) -> dict:
    """Process a document using the process_file utility"""
    file_path = Path(file_path)
    
    def process_fn(f: str, o: Path) -> dict:
        # Process the image and let process_file handle path management
        result = process_image(Path(f), o)
        
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
    background_removed_folder: Path = typer.Argument(..., help="Input background removed images folder"),
    background_removed_manifest: Path = typer.Argument(..., help="Input background removed manifest"),
    transcribed_folder: Path = typer.Argument(..., help="Output folder for transcriptions"),
    testing: bool = typer.Option(False, help="Run on a small subset of data"),
):
    """Batch transcription CLI using Qwen VL Max model"""
    print(f"[green]Transcribing images in {background_removed_folder}")
    print(f"[cyan]Using model qvq-max")
    
    load_dotenv()
    
    if not os.getenv('DASHSCOPE_API_KEY'):
        print("[red]Error: DASHSCOPE_API_KEY environment variable not set")
        return

    processor = BatchProcessor(
        input_manifest=background_removed_manifest,
        output_folder=transcribed_folder,
        process_name="transcription",
        processor_fn=lambda f, o: process_document(f, o),
        base_folder=background_removed_folder
    )
    
    return processor.process()

if __name__ == "__main__":
    typer.run(transcribe) 