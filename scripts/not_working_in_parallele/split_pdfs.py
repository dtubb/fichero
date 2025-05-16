#!/usr/bin/env python3
import logging
from pathlib import Path
import typer
from PyPDF2 import PdfReader, PdfWriter
from tqdm import tqdm

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = typer.Typer()

def split_pdf(pdf_path: Path, output_folder: Path) -> bool:
    """Split a PDF into individual pages."""
    try:
        # Open the PDF
        reader = PdfReader(str(pdf_path))
        num_pages = len(reader.pages)
        
        if num_pages <= 1:
            logger.info(f"Skipping {pdf_path} - already single page")
            return True
        
        # Create output filename template
        base_name = pdf_path.stem
        output_template = output_folder / f"{base_name}_page_{{:03d}}.pdf"
        
        # Split each page
        for page_num in range(num_pages):
            writer = PdfWriter()
            writer.add_page(reader.pages[page_num])
            
            # Save the page
            output_path = output_template.format(page_num + 1)
            with open(output_path, 'wb') as output_file:
                writer.write(output_file)
        
        return True
        
    except Exception as e:
        logger.error(f"Error splitting {pdf_path}: {str(e)}")
        return False

def process_folder(input_folder: Path, output_folder: Path):
    """Process all PDFs in a folder."""
    # Create output folder if it doesn't exist
    output_folder.mkdir(parents=True, exist_ok=True)
    
    # Get all PDF files
    pdf_files = list(input_folder.glob('**/*.pdf'))
    logger.info(f"Found {len(pdf_files)} PDFs to process")
    
    # Process each PDF
    success_count = 0
    for pdf_path in tqdm(pdf_files, desc="Splitting PDFs"):
        # Create output path maintaining folder structure
        rel_path = pdf_path.relative_to(input_folder)
        output_path = output_folder / rel_path.parent
        
        if split_pdf(pdf_path, output_path):
            success_count += 1
    
    logger.info(f"Successfully split {success_count} of {len(pdf_files)} PDFs")

@app.command()
def main(
    input_folder: Path = typer.Argument(..., help="Folder containing PDF files"),
    output_folder: Path = typer.Argument(..., help="Folder to save split PDFs")
):
    """Split PDFs into individual pages."""
    try:
        logger.info(f"Processing PDFs from {input_folder}")
        process_folder(input_folder, output_folder)
        logger.info("Splitting completed")
        
    except Exception as e:
        logger.error(f"Error during splitting: {str(e)}")
        raise typer.Exit(1)

if __name__ == "__main__":
    app() 