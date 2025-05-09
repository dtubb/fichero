import typer
from pathlib import Path
import torch
import numpy as np
import re
from PIL import Image
import warnings
from transformers import Qwen2VLForConditionalGeneration, AutoProcessor
from rich.console import Console
from utils.batch import BatchProcessor
from utils.processor import process_file
from utils.segment_handler import SegmentHandler
import os

console = Console()

# Set environment variable to avoid parallelism warning
os.environ["TOKENIZERS_PARALLELISM"] = "false"

DEFAULT_PROMPT = "Extract all text line by line. Do not number lines. RETURN ONLY PLAIN TEXT. SAY NOTHING ELSE"

class TranscriptionProcessor:
    _instance = None
    _model = None
    _processor = None

    def __new__(cls, model_name: str = None, prompt: str = DEFAULT_PROMPT):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, model_name: str = None, prompt: str = DEFAULT_PROMPT):
        if not hasattr(self, 'initialized'):
            self.model_name = model_name
            self.prompt = prompt
            self.device = self._get_device()
            self._load_model()
            self.initialized = True

    def _get_device(self) -> str:
        """Device detection with proper MPS support"""
        try:
            if torch.cuda.is_available():
                return "cuda"
            if torch.backends.mps.is_available() and torch.backends.mps.is_built():
                # Verify MPS works
                test_tensor = torch.zeros(1).to("mps")
                del test_tensor
                console.print("[green]Using M1/M2 GPU acceleration (MPS)")
                return "mps"
        except Exception as e:
            console.print(f"[yellow]Falling back to CPU: {e}")
        return "cpu"

    def _load_model(self):
        if self._model is None and self.model_name:
            try:
                console.print(f"[yellow]Loading model {self.model_name}...")
                self._processor = AutoProcessor.from_pretrained(
                    self.model_name,
                    trust_remote_code=True
                )
                self._model = Qwen2VLForConditionalGeneration.from_pretrained(
                    self.model_name,
                    torch_dtype="auto",
                    device_map="auto"  # Keep original device handling
                )
                console.print("[green]Model loaded successfully")
            except Exception as e:
                console.print(f"[red]Error loading model: {e}")
                self._model = None
                self._processor = None

    @property
    def model(self):
        return self._model

    @property
    def processor(self):
        return self._processor

    @property
    def tokenizer(self):
        return self._processor.tokenizer if self._processor else None

    def estimate_text_density(self, image: Image.Image) -> int:
        try:
            img_array = np.array(image.convert('L'))
            height, width = img_array.shape
            mean = np.mean(img_array)
            std_dev = np.std(img_array)
            
            # Improved text detection threshold
            text_mask = img_array < (mean - 0.75 * std_dev)
            text_pixel_count = np.sum(text_mask)
            
            # Adjust pixels per word based on image size
            base_pixels = 5000  # Adjusted for better estimation
            size_factor = (width * height) / 1000000  # Normalize by 1M pixels
            pixels_per_word = base_pixels * (1 + size_factor)
            
            estimated_words = max(int(text_pixel_count / pixels_per_word), 1)
            
            # Scale based on image size
            if width * height < 500000:
                estimated_words = max(10, estimated_words)
            else:
                estimated_words = max(20, estimated_words)
            
            # Apply a higher multiplier to better estimate the word count
            estimated_words = estimated_words * 4  # Increased multiplier
            
            # Add a buffer to account for underestimation
            estimated_words = int(estimated_words * 2)  # Add 20% buffer
            
            return min(estimated_words, 400)  # Increased max from 200
        except Exception:
            return 30

    def count_tokens(self, text: str) -> int:
        if not self.tokenizer:
            return len(text.split())
        return len(self.tokenizer.encode(text))

    def process_image(self, image: Image.Image, max_new_tokens: int) -> str:
        """Enhanced image processing with better generation parameters"""
        if not self.model or not self.processor:
            raise RuntimeError("Model not loaded")

        try:
            # Image preprocessing
            max_size = 1000
            min_size = 32    # Minimum size to prevent processing errors
            width, height = image.size
            
            # Skip if image is too small
            if width < min_size or height < min_size:
                return ""
                
            aspect_ratio = max(width, height) / float(min(width, height))
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

            # Model inputs
            messages = [{"role": "user", "content": [
                {"type": "image", "image": image},
                {"type": "text", "text": self.prompt}
            ]}]

            prompt_text = self.processor.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )

            inputs = self.processor(
                text=prompt_text,
                images=image,
                return_tensors="pt",
                max_length=2048,  # Increased for longer contexts
                truncation=True
            )

            device = next(self.model.parameters()).device
            inputs = {k: v.to(device) if torch.is_tensor(v) else v for k, v in inputs.items()}

            # Improved generation parameters
            with torch.no_grad():
                outputs = self.model.generate(
                    **inputs,
                    max_new_tokens=max_new_tokens,
                    min_new_tokens=10,
                    num_beams=1,          # Reduce beams for faster processing
                    do_sample=True,       # Enable sampling
                    temperature=0.7,      # Moderate temp for balanced output
                    repetition_penalty=1.1,  # Adjust to reduce repetition
                    length_penalty=1.0,
                    top_p=0.9,            # Adjust for better sampling control
                    top_k=50,             # Adjust for better sampling control
                    remove_invalid_values=True,
                    renormalize_logits=True,  # Help with token distribution
                )

            input_len = inputs["input_ids"].shape[1]
            output_text = self.tokenizer.decode(
                outputs[0][input_len:],
                skip_special_tokens=True,
                clean_up_tokenization_spaces=True
            ).strip()

            # Filter non-useful outputs
            if not output_text or output_text.lower() == "blank":
                return ""
            if re.match(r"^\(\d+,\d+\),\(\d+,\d+\)$", output_text):
                return ""
            if output_text in [
                "The text is not visible in the image.",
                "The text on the image is not clear and appears to be a mix of different colors and patterns."
            ]:
                return ""
            return output_text

        except Exception as e:
            console.print(f"[red]Error in vision-language processing: {e}")
            raise

def process_image(img_path: Path, out_path: Path, model_name: str = "Qwen/Qwen2-VL-2B-Instruct") -> dict:
    """Process a single image file, returning manifest-compatible output"""
    try:
        # Ensure output directory exists
        out_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Convert output path to .txt extension but preserve original extension in source
        out_path = out_path.with_suffix('.txt')
        out_path.touch()
        
        try:
            # Initialize transcriber with model
            transcriber = TranscriptionProcessor(
                model_name=model_name,
                prompt=DEFAULT_PROMPT
            )
            
            # Load and process image
            image = Image.open(img_path).convert("RGB")
            
            # Get actual transcription from LLM with text density estimation
            estimated_words = transcriber.estimate_text_density(image)
            max_new_tokens = min(estimated_words * 2, 2048)  # Adjust multiplier as needed
            transcription = transcriber.process_image(image, max_new_tokens)
            token_count = transcriber.count_tokens(transcription)
            
            # Save transcription
            with open(out_path, 'w', encoding='utf-8') as f:
                f.write(transcription)
            
            # Create manifest entry with .txt extension
            rel_path = SegmentHandler.get_relative_path(img_path)
            result = {
                "outputs": [str(rel_path.with_suffix('.txt'))],
                "source": str(rel_path),  # Keep original extension in source
                "details": {
                    "estimated_words": estimated_words,
                    "token_count": token_count,
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

def process_document(file_path: str, output_folder: Path, model_name: str = "Qwen/Qwen2-VL-2B-Instruct") -> dict:
    """Process a document using the process_file utility"""
    file_path = Path(file_path)
    
    def process_fn(f: str, o: Path) -> dict:
        # Process the image and let process_file handle path management
        result = process_image(Path(f), o, model_name)
        
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
    model_name: str = typer.Option(
        "Qwen/Qwen2-VL-2B-Instruct",
        "--model", "-m",
        help="Model name to use"
    ),
    prompt: str = typer.Option(
        DEFAULT_PROMPT,
        "--prompt", "-p",
        help="Prompt for transcription"
    )
):
    """Batch transcription CLI using utils for processing"""
    console.print(f"Using model: {model_name}")
    console.print(f"Using prompt: {prompt}")

    processor = BatchProcessor(
        input_manifest=segment_manifest,
        output_folder=transcribed_folder,
        process_name="transcription",
        processor_fn=lambda f, o: process_document(f, o, model_name),  # Pass model_name to process_document
        base_folder=segment_folder
    )
    return processor.process()

if __name__ == "__main__":
    typer.run(transcribe) 