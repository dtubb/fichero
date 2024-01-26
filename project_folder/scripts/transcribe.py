import json
import typer
from PIL import Image
from pathlib import Path
from rich.progress import track
from spacy.cli._util import Arg
from googleapiclient.discovery import build
from xml.etree.ElementTree import SubElement, tostring, fromstring

import base64


def vision(
    image_content: str,
    APIKEY: str,
    type_: str = "DOCUMENT_TEXT_DETECTION",
    language: str = "es",
):
    vservice = build("vision", "v1", developerKey=APIKEY)
    language = language
    request = vservice.images().annotate(
        body={
            "requests": [
                {
                    "image": {"content": image_content.decode("UTF-8")},
                    "imageContext": {"languageHints": [language]},
                    "features": [{"type": type_}],
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
                # The bounding box for the word. The vertices are in the order of top-left, top-right, bottom-right, bottom-left.
                # https://cloud.google.com/distributed-cloud/hosted/docs/latest/gdch/apis/vertex-ai/ocr/rpc/google.cloud.vision.v1
                boundingbox = annotation.get(
                    "boundingPoly", None
                )  #'boundingPoly': {'vertices': [{'x': 22, 'y': 453}, {'x': 22, 'y': 342}, {'x': 39, 'y': 342}, {'x': 39, 'y': 453}]}
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
                    # if the word is within the line coordinates, add it to the list of words
                    if (
                        word_x_min >= line_x_min
                        and word_x_max <= line_x_max
                        and word_y_min >= line_y_min
                        and word_y_max <= line_y_max
                    ):
                        # <String CONTENT="Par " HPOS="220" VPOS="369" WIDTH="3" HEIGHT="22" />
                        line_words.append(
                            {
                                "content": text,
                                "hpos": word_x_min,
                                "vpos": word_y_min,
                                "width": word_x_max - word_x_min,
                                "height": word_y_max - word_y_min,
                            }
                        )
                except:
                    # One or more x and/or y coordinates may not be generated in the BoundingPoly
                    # https://stackoverflow.com/questions/39378862/incomplete-coordinate-values-for-google-vision-ocr
                    pass
    # sort the words by x coordinate
    line_words = sorted(line_words, key=lambda k: k["hpos"])
    return line_words


def merge_vision_alto(vision_response: json, alto_xml: str):
    # read the alto xml into an ElementTree
    # alto = etree.XML(alto_xml)
    alto = fromstring(alto_xml)
    # get filename from alto xml
    filename = alto.find(".//{http://www.loc.gov/standards/alto/ns-v4#}fileName").text
    filename = filename.split("/")[-1]
    # find all TextLine elements
    text_lines = alto.findall(".//{http://www.loc.gov/standards/alto/ns-v4#}TextLine")
    # assert that the page has been segmented, otherwise no text will post
    assert (
        len(text_lines) > 0
    ), "Please segment your images in eScriptorium. No TextLine elements found in ALTO XML"

    for line in text_lines:
        line_attrib = (
            line.attrib
        )  # {'ID': 'eSc_line_3f31ece7', 'TAGREFS': 'LT15', 'BASELINE': '1029 797 2255 780', 'HPOS': '1026', 'VPOS': '724', 'WIDTH': '1229', 'HEIGHT': '118'}
        id = line_attrib.get("ID", None)
        baseline = line_attrib.get("BASELINE", None)
        hpos = int(
            float(line_attrib.get("HPOS", None))
        )  # Horizontal position upper/left corner (1/10 mm)
        vpos = int(
            float(line_attrib.get("VPOS", None))
        )  # Vertical position upper/left corner (1/10 mm)
        width = int(float(line_attrib.get("WIDTH", None)))
        height = int(float(line_attrib.get("HEIGHT", None)))
        text = line.text

        # remove any existing String elements from the TextLine
        # <String CONTENT="Par " HPOS="220" VPOS="369" WIDTH="3" HEIGHT="22" />
        strings = line.findall(".//{http://www.loc.gov/standards/alto/ns-v4#}String")
        for string in strings:
            line.remove(string)

        # add new String elements from the vision response
        line_strings = get_strings_for_alto_line(
            vision_response, hpos, vpos, width, height
        )
        alto_line = alto.find(
            ".//{http://www.loc.gov/standards/alto/ns-v4#}TextLine" + f'[@ID="{id}"]'
        )
        for string in line_strings:
            # add new string element to alto_line
            SubElement(
                alto_line,
                "String",
                {
                    "CONTENT": string["content"],
                    "HPOS": str(string["hpos"]),
                    "VPOS": str(string["vpos"]),
                    "WIDTH": str(string["width"]),
                    "HEIGHT": str(string["height"]),
                },
            )
    # save alto to disk
    alto = b'<?xml version="1.0" encoding="UTF-8"?>' + tostring(
        alto, encoding="unicode"
    ).encode("utf-8").replace(b"ns0:", b"").replace(b":ns0", b"")
    return alto


def transcribe(
    collection_path: Path = Arg(..., help="Path to the collections", exists=True),
    google_vision_api_key: str = Arg(..., help="Google Vision API key"),
    language: str = Arg(..., help="Language code"),
):
    images = list(collection_path.glob("**/*.jpg"))
    for image in track(images, description="Transcribing images..."):
        if not image.with_suffix(".xml").exists():
            print(f"Images need to be segmented first ")
            typer.Exit()

        else:
            img = Image.open(image)
            image_b64 = base64.b64encode(img.tobytes())
            vision_response = vision(
                image_b64, google_vision_api_key, language=language
            )
            alto_xml = image.with_suffix(".xml").read_text()
            alto_xml = merge_vision_alto(vision_response, alto_xml)
            image.with_suffix(".xml").write_text(alto_xml)


if __name__ == "__main__":
    typer.run(transcribe)
