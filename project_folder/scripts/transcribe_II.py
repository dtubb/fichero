import sys
import traceback
import json
import typer
from PIL import Image, ImageDraw
from pathlib import Path
from rich.progress import track
from googleapiclient.discovery import build
from xml.etree.ElementTree import SubElement, tostring, fromstring
from xml.etree import ElementTree as ET
from typing_extensions import Annotated
import io
import base64
import logging

def create_new_alto_xml(image, full_text=None):
    """
    Create a new ALTO XML file with basic structure.
    """
    root = ET.Element("alto")
    description = ET.SubElement(root, "Description")
    source_image_information = ET.SubElement(description, "sourceImageInformation")
    file_name = ET.SubElement(source_image_information, "fileName")
    file_name_text = str(image.name)
    file_name.text = file_name_text
    layout = ET.SubElement(root, "Layout")
    page = ET.SubElement(layout, "Page")
    page.set("WIDTH", "0")
    page.set("HEIGHT", "0")
    page.set("PHYSICAL_IMG_NR", "0")
    page.set("ID", "PAGE_0")
    if full_text:
        text_string = ET.SubElement(page, "String")
        text_string.set("CONTENT", full_text)
    return root

def remove_ruler(img, remove_ruler_flag):
    if remove_ruler_flag:
        img1 = ImageDraw.Draw(img)
        w, h = img.size
        shape = [(w - 50, 100), (w, h)]  # Upper left, lower right
        img1.rectangle(shape, fill="#000000")
    return img

def vision(
    image_content: str,
    APIKEY: str,
    type_: str = "DOCUMENT_TEXT_DETECTION",
    language: str = "en",
    model: str = "builtin/dense",
):
    vservice = build("vision", "v1", developerKey=APIKEY)
    language = language
    request = vservice.images().annotate(
        body={
            "requests": [
                {
                    "image": {"content": image_content.decode("UTF-8")},
                    "imageContext": {"languageHints": [language]},
                    "features": [{"type": type_, "model": model}],
                }
            ]
        }
    )
    return request.execute(num_retries=3)

def get_strings_for_alto_line(
    vision_response: json, hpos: int, vpos: int, width: int, height: int
):
    """
    Given a vision response and the coordinates of an ALTO text line, return a list of ALTO String elements that fit within the line.
    Each ALTO String element is a single word.
    HPOS = Horizontal (x) position upper/left corner
    VPOS = Vertical (y) position upper/left corner
    """

    line_x_min = hpos
    line_x_max = hpos + width
    line_y_min = vpos
    line_y_max = vpos + height

    line_words = []
    for response in vision_response["responses"]:
        for i, annotation in enumerate(response.get("textAnnotations", [])):
            if i == 0:
                full_text = annotation.get("description", None)
                language = annotation.get("locale", None)
            else:
                text = annotation.get("description", None)
                boundingbox = annotation.get("boundingPoly", None)
                try:
                    word_x_min = (
                        boundingbox["vertices"][0]["x"]
                        if boundingbox["vertices"][0]["x"]
                        < boundingbox["vertices"][3]["x"]
                        else boundingbox["vertices"][3]["x"]
                    )
                    word_x_max = (
                        boundingbox["vertices"][1]["x"]
                        if boundingbox["vertices"][1]["x"]
                        > boundingbox["vertices"][2]["x"]
                        else boundingbox["vertices"][2]["x"]
                    )
                    word_y_min = (
                        boundingbox["vertices"][0]["y"]
                        if boundingbox["vertices"][0]["y"]
                        < boundingbox["vertices"][1]["y"]
                        else boundingbox["vertices"][1]["y"]
                    )
                    word_y_max = (
                        boundingbox["vertices"][2]["y"]
                        if boundingbox["vertices"][2]["y"]
                        > boundingbox["vertices"][3]["y"]
                        else boundingbox["vertices"][3]["y"]
                    )
                    if (
                        word_x_min >= line_x_min
                        and word_x_max <= line_x_max
                        and word_y_min >= line_y_min
                        and word_y_max <= line_y_max
                    ):
                        line_words.append(
                            {
                                "content": text,
                                "hpos": word_x_min,
                                "vpos": word_y_min,
                                "width": word_x_max - word_x_min,
                                "height": word_y_max - word_y_min,
                            }
                        )
                except Exception as e:
                    logging.warning(f"Error processing bounding box: {e}")
    line_words = sorted(line_words, key=lambda k: k["hpos"])
    return line_words

def merge_vision_alto(vision_response: json, image: Path):
    try:
        alto_xml = None
        if image.with_suffix(".xml").exists():
            alto_xml = ET.parse(image.with_suffix(".xml")).getroot()
        elif image.with_suffix(".json").exists():
            with open(image.with_suffix(".json"), "r") as f:
                json_data = json.load(f)
            if json_data.get('responses', None) and json_data['responses'][0]:
                if json_data['responses'][0].get('textAnnotations', None):
                    full_text = json_data["responses"][0]["textAnnotations"][0].get("description", None)
                    alto_xml = create_new_alto_xml(image, full_text)
                else:
                    # Create an empty ALTO XML file if there is no text in the JSON
                    alto_xml = create_new_alto_xml(image)
            else:
                # Create an empty ALTO XML file if the JSON is empty
                alto_xml = create_new_alto_xml(image)
        else:
            # Create an empty ALTO XML file if there is no JSON or XML file
            alto_xml = create_new_alto_xml(image)

        alto_page = alto_xml.find(".//{http://www.loc.gov/standards/alto/ns-v4#}Page")

        if vision_response.get("responses", None) and vision_response["responses"][0].get("textAnnotations", None):
            full_text = vision_response["responses"][0]["textAnnotations"][0]["description"]
            text_string = ET.SubElement(alto_page, "String")
            text_string.set("CONTENT", full_text)

        alto_xml_str = ET.tostring(alto_xml, encoding="unicode")
        alto = b'<?xml version="1.0" encoding="UTF-8"?>' + alto_xml_str.encode("utf-8").replace(b"ns0:", b"").replace(b":ns0", b"")

        return alto
    except Exception as e:
        logging.error(f"Error merging vision response and ALTO XML: {e}")
        return None

def transcribe(
    collection_path: Annotated[Path, typer.Argument(help="Path to the collections", exists=True)],
    language: Annotated[str, typer.Argument(help="Language code")],
    txt: Annotated[bool, typer.Argument(help="Transcribe to txt")],
    alto: Annotated[bool, typer.Argument(help="Transcribe to alto")],
    json_output: Annotated[bool, typer.Argument(help="Save JSON output")],
    remove_ruler_flag: Annotated[bool, typer.Argument(help="Remove ruler from images")],
    google_vision_api_key: Annotated[str, typer.Argument(help="Google Vision API key", envvar="GOOGLE_VISION_API_KEY")],
    num_images: int = -1,
):
    extensions = ['jpg', 'jpeg', 'JPG', 'JPEG']
    images = []
    for ext in extensions:
        images.extend(collection_path.glob(f"**/*.{ext}"))

    images = sorted(images)

    if num_images > 0:
        images = images[:num_images]

    skipped_images_count = 0
    processed_images = []

    for image in track(images, description="Transcribing images..."):
        # try:
            if image.with_suffix(".json").exists() and image.with_suffix(".xml").exists() and json_output:
                skipped_images_count += 1
                if skipped_images_count == 1 or (skipped_images_count > 1 and skipped_images_count % 10 == 0):
                    logging.info(f"{skipped_images_count} images skipped so far. Following {len(processed_images)} images processed:")
                    for processed_image in processed_images[:10]:
                        logging.info(f"- {processed_image.name}")
                    if len(processed_images) > 10:
                        logging.info("...")
                continue

            img = Image.open(image)
            img = remove_ruler(img, remove_ruler_flag)
            rgb_im = img.convert("RGB")
            img_byte_arr = io.BytesIO()
            rgb_im.save(img_byte_arr, format="JPEG")
            
            image_b64 = base64.b64encode(bytearray(img_byte_arr.getvalue()))

            vision_response = vision(
                image_b64, google_vision_api_key, language=language, model="builtin/dense"
            )

            if json_output:
                json_response = json.dumps(vision_response, indent=4)
                image.with_suffix(".json").write_text(json_response)

            if not image.with_suffix(".txt").exists() and txt:
                if vision_response.get('responses', None):
                    if vision_response['responses'][0].get('textAnnotations', None):
                        if vision_response['responses'][0]['textAnnotations'][0].get('description', None):
                            text = vision_response['responses'][0]['textAnnotations'][0]['description']
                            image.with_suffix(".txt").write_text(text)
                        else:
                            logging.warning(f"No text description found for {image}")
                    else:
                        logging.warning(f"No text annotations found for {image}")
                else:
                    logging.warning(f"No responses found for {image}")
                
            if alto:
              # Merge vision response with ALTO XML
              merged_alto_xml = merge_vision_alto(vision_response, image)
              if merged_alto_xml:
                  image.with_suffix(".xml").write_bytes(merged_alto_xml)
              else:
                  logging.warning(f"Error merging vision response and ALTO XML for {image}")
            
            processed_images.append(image)
            """# except Exception as e:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            traceback_details = traceback.extract_tb(exc_traceback)
            line_number = traceback_details[-1].lineno
            code_line = traceback_details[-1].line
            logging.error(f"Error processing {image}: {e} (Line {line_number}: {code_line})")"""

            
    if skipped_images_count > 0:
        logging.info(f"{skipped_images_count} images skipped. Following {len(processed_images)} images processed:")
        for image in processed_images[:10]:
            logging.info(f"- {image.name}")
        if len(processed_images) > 10:
            logging.info("...")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    typer.run(transcribe)