# Import necessary libraries
import torch  # Import PyTorch library for deep learning
import typer  # Import Typer library for creating command-line interfaces
from PIL import Image  # Import PIL library for image processing
from pathlib import Path  # Import Path class from pathlib for file path handling
from rich.progress import track  # Import track function from rich.progress for progress tracking
from spacy.cli._util import Arg  # Import Arg class from spacy.cli._util for argument handling

try:
    import pkg_resources
    kraken_version = pkg_resources.get_distribution("kraken").version
    if not kraken_version.startswith("4.3."):
        raise ImportError(f"kraken version {kraken_version} is not supported. Please install kraken 4.3.0.")

    from kraken import blla  # Import blla module from kraken library for baseline segmentation
    from kraken import serialization  # Import serialization module from kraken library for serializing segmentation results

except ImportError as e:
    print(f"Error: {str(e)}")
    print("Please install kraken 4.3.0 using the following command:")
    print("pip install kraken==4.3.0")
    exit(1)

def segment(
    collection_path: Path = Arg(..., help="Path to the collections", exists=True),
    text_direction: str = Arg("horizontal-lr", help="Text direction of the images"),
    only_generate_xml: bool = typer.Option(False, "--only-generate-xml", help="Only generate XML files without segmentation"),
):
    """
    Segment images in the specified collection path.

    Args:
        collection_path (Path): Path to the directory containing the image collections.
        text_direction (str): Text direction of the images. Default is "horizontal-lr".

    Returns:
        None
    """
    # Check if CUDA is available and set the device accordingly
    if torch.cuda.is_available():
        device = 'cuda'
    else:
        device = 'cpu'

    # Find all image files with supported extensions in the collection path
    extensions = ['jpg', 'jpeg', 'JPG', 'JPEG']
    images = []
    for ext in extensions:
        images.extend(collection_path.glob(f"**/*.{ext}"))
    images = sorted(images)

    # Print the number of images found
    print(f"Found {len(images)} images")

    # Iterate over each image and perform segmentation
    for image in track(images, description="Processing images..."):
        xml_file = image.with_suffix('.xml')
        if xml_file.exists():
            print(f"Skipping image: {image.name} (XML file already exists)")
            continue
    
        img = Image.open(image)
    
        try:
            if only_generate_xml:
                # Generate an empty XML file from the template without segmentation
                empty_xml = serialization.serialize_segmentation({'boxes': []}, image_name=image.name, image_size=img.size, template='alto')
                xml_file.write_text(empty_xml)
                print(f"Generated an empty XML file for: {image.name}")
            else:
                # Perform segmentation and generate XML file
                baseline_seg = blla.segment(img, device=device, text_direction=text_direction)
                alto_xml = serialization.serialize_segmentation(baseline_seg, image_name=image.name, image_size=img.size, template='alto')
                xml_file.write_text(alto_xml)
    
        except Exception as e:
            print(f"Error processing image: {image.name}")
            print(f"Error message: {str(e)}")
    
            # Generate an empty XML file from the template
            empty_xml = serialization.serialize_segmentation({'boxes': []}, image_name=image.name, image_size=img.size, template='alto')
            xml_file.write_text(empty_xml)
            print(f"Generated an empty XML file for: {image.name}")

if __name__ == "__main__":
    # Run the segment function using Typer when the script is executed directly
    typer.run(segment)