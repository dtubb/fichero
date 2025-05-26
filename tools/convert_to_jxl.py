import typer
from pathlib import Path
from PIL import Image
import os
import subprocess
import shutil

def check_cjxl_installed():
    """Check if cjxl (JPEG XL encoder) is installed."""
    if not shutil.which('cjxl'):
        print("Error: cjxl (JPEG XL encoder) is not installed.")
        print("Please install it first:")
        print("  - macOS: brew install libjxl")
        print("  - Ubuntu/Debian: apt-get install libjxl-tools")
        print("  - Windows: Download from https://github.com/libjxl/libjxl/releases")
        return False
    return True

def convert_to_jxl(input_path: Path, output_path: Path = None):
    """
    Convert a PNG file to JPEG XL format using cjxl.
    If output_path is not provided, creates a .jxl file in the same directory.
    """
    try:
        # If no output path specified, use the input path with .jxl extension
        if output_path is None:
            output_path = input_path.with_suffix('.jxl')
        
        # Get original size
        original_size = os.path.getsize(input_path)
        
        # Convert using cjxl with timeout
        # -e: effort (1-9, higher = better compression but slower)
        # -d: distance (0 = lossless)
        cmd = ['cjxl', str(input_path), str(output_path), '-e', '7', '-d', '0']  # Reduced effort from 9 to 7 for better performance
        
        # Run with timeout of 5 minutes
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            stdout, stderr = process.communicate(timeout=300)  # 5 minute timeout
            if process.returncode != 0:
                raise subprocess.CalledProcessError(process.returncode, cmd, stdout, stderr)
        except subprocess.TimeoutExpired:
            process.kill()
            raise Exception("Conversion timed out after 5 minutes")
        
        # Get compressed size
        compressed_size = os.path.getsize(output_path)
        reduction = ((original_size - compressed_size) / original_size) * 100
        
        # Print individual file results
        print(f"{input_path.name}:")
        print(f"  Original: {original_size/1024:.1f} KB")
        print(f"  JXL: {compressed_size/1024:.1f} KB")
        print(f"  Saved: {(original_size - compressed_size)/1024:.1f} KB ({reduction:.1f}%)")
        print()
        
        return {
            "file": str(input_path),
            "original_size": original_size,
            "compressed_size": compressed_size,
            "reduction_percent": reduction
        }
    except subprocess.CalledProcessError as e:
        print(f"Error processing {input_path.name}: {e.stderr.decode()}")
        return {
            "file": str(input_path),
            "error": str(e)
        }
    except Exception as e:
        print(f"Error processing {input_path.name}: {str(e)}")
        return {
            "file": str(input_path),
            "error": str(e)
        }

def process_directory(
    input_dir: Path = typer.Argument(..., help="Directory containing PNG files to convert"),
    output_dir: Path = typer.Option(Path.home() / "Desktop" / "jxl_converted", help="Output directory (defaults to ~/Desktop/jxl_converted)"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed progress")
):
    """
    Recursively find and convert all PNG files in the input directory to JPEG XL format.
    Original PNG files are preserved. JXL files are saved to the output directory.
    """
    if not check_cjxl_installed():
        return
    
    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Converting PNGs to JXL format...")
    print(f"Output will be saved to: {output_dir}")
    
    # Find all PNG files recursively
    png_files = list(input_dir.rglob("*.png"))
    total_files = len(png_files)
    
    print(f"Found {total_files} PNG files to process")
    
    results = []
    total_original_size = 0
    total_compressed_size = 0
    
    for i, png_file in enumerate(png_files, 1):
        print(f"\nProcessing file {i}/{total_files}: {png_file.name}")
        
        # Calculate output path
        rel_path = png_file.relative_to(input_dir)
        out_path = output_dir / rel_path.with_suffix('.jxl')
        out_path.parent.mkdir(parents=True, exist_ok=True)
        
        result = convert_to_jxl(png_file, out_path)
        results.append(result)
        
        if "error" not in result:
            total_original_size += result["original_size"]
            total_compressed_size += result["compressed_size"]
    
    # Print summary
    print("\nConversion Summary:")
    print(f"Total files processed: {total_files}")
    print(f"Total original size: {total_original_size / 1024 / 1024:.2f} MB")
    print(f"Total JXL size: {total_compressed_size / 1024 / 1024:.2f} MB")
    print(f"Total space saved: {(total_original_size - total_compressed_size) / 1024 / 1024:.2f} MB")
    print(f"Average reduction: {((total_original_size - total_compressed_size) / total_original_size * 100):.1f}%")
    print(f"\nJXL files have been saved to: {output_dir}")
    
    # Print any errors
    errors = [r for r in results if "error" in r]
    if errors:
        print("\nErrors encountered:")
        for error in errors:
            print(f"- {error['file']}: {error['error']}")

if __name__ == "__main__":
    typer.run(process_directory) 