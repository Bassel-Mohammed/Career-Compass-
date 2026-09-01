#!/usr/bin/env python3
"""Insert Section 6.3.1 algorithm diagrams and code screenshots into the report.

The DOCX is edited directly as WordprocessingML so unrelated formatting and
package parts remain unchanged. Images are inserted inline at page width, with
the report's existing caption style.
"""

from __future__ import annotations

import struct
import sys
from dataclasses import dataclass
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "CareerCompass_Graduation_Project_Report_Chapter6_Corrected (1).docx"
OUTPUT = ROOT / "CareerCompass_Graduation_Project_Report_Chapter6_Corrected (1)_With_Images_v3.docx"

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
WP_NS = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
PIC_NS = "http://schemas.openxmlformats.org/drawingml/2006/picture"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"

W = f"{{{W_NS}}}"
R = f"{{{R_NS}}}"
WP = f"{{{WP_NS}}}"
A = f"{{{A_NS}}}"
PIC = f"{{{PIC_NS}}}"
PKG_REL = f"{{{PKG_REL_NS}}}"

for prefix, uri in {
    "w": W_NS,
    "r": R_NS,
    "wp": WP_NS,
    "a": A_NS,
    "pic": PIC_NS,
    "mc": "http://schemas.openxmlformats.org/markup-compatibility/2006",
    "w14": "http://schemas.microsoft.com/office/word/2010/wordml",
    "w15": "http://schemas.microsoft.com/office/word/2012/wordml",
    "wp14": "http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing",
}.items():
    ET.register_namespace(prefix, uri)


EMU_PER_INCH = 914_400
MAX_IMAGE_WIDTH = int(6.15 * EMU_PER_INCH)
IMAGE_REL_TYPE = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"
)


@dataclass(frozen=True)
class Picture:
    path: Path
    caption: str
    alt_text: str


@dataclass(frozen=True)
class AlgorithmAssets:
    number: int
    diagram: Picture
    listings: tuple[Picture, ...]


ASSETS = (
    AlgorithmAssets(
        1,
        Picture(
            ROOT / "docs/figures/chapter6/algorithm-1-skill-matching-cascade.png",
            "Figure 6.1: Skill matching decision cascade.",
            "Flowchart of the CareerCompass skill matching decision cascade.",
        ),
        (
            Picture(
                ROOT / "1_Skill matching.png",
                "Listing 6.1: Reranking thresholds and deterministic skill-match decisions.",
                "Code screenshot showing skill reranking and deterministic thresholds.",
            ),
            Picture(
                ROOT / "1_2_Skill_matching.png",
                "Listing 6.2: Constrained LLM selection and human-review fallback.",
                "Code screenshot showing constrained LLM selection and review fallback.",
            ),
        ),
    ),
    AlgorithmAssets(
        2,
        Picture(
            ROOT / "docs/figures/chapter6/algorithm-2-student-skill-vector.png",
            "Figure 6.2: Construction of proficiency and evidence coverage in the student skill vector.",
            "Diagram showing construction of the CareerCompass student skill vector.",
        ),
        (
            Picture(
                ROOT / "2_Student_skill_vector.png",
                "Listing 6.3: Separate accumulation of graded proficiency and total evidence coverage.",
                "Code screenshot showing proficiency and evidence coverage accumulation.",
            ),
            Picture(
                ROOT / "2_2_Student_skill_vector.png",
                "Listing 6.4: Quiz results replacing grade-derived proficiency.",
                "Code screenshot showing quiz-score write-back into the skill vector.",
            ),
        ),
    ),
    AlgorithmAssets(
        3,
        Picture(
            ROOT / "docs/figures/chapter6/algorithm-3-skill-gap-priority-hand-drawn-restructured.png",
            "Figure 6.3: Skill-gap calculation, classification, and demand-weighted priority.",
            "Whiteboard diagram of skill-gap calculation and prioritization.",
        ),
        (
            Picture(
                ROOT / "3_Skill_gap_and_priority.png",
                "Listing 6.5: Skill-gap requirement inputs and student-vector lookup.",
                "Code screenshot showing skill-gap inputs and vector lookup.",
            ),
            Picture(
                ROOT / "3_2_Skill_gap_and_priority.png",
                "Listing 6.6: Calculation of gap, classification, and demand-weighted priority.",
                "Code screenshot showing gap, classification, and priority calculation.",
            ),
        ),
    ),
    AlgorithmAssets(
        4,
        Picture(
            ROOT / "docs/figures/chapter6/algorithm-4-course-recommendation-ranking.png",
            "Figure 6.4: Course relevance, language adjustment, and final recommendation ranking.",
            "Diagram showing the CareerCompass course recommendation ranking process.",
        ),
        (
            Picture(
                ROOT / "4_Course_recommendations.png",
                "Listing 6.7: Course relevance and rank-score formulas.",
                "Code screenshot showing course relevance and ranking formulas.",
            ),
        ),
    ),
    AlgorithmAssets(
        5,
        Picture(
            ROOT / "docs/figures/chapter6/algorithm-5-quiz-generation-grading.png",
            "Figure 6.5: Separation of model-based quiz generation from deterministic grading.",
            "Diagram showing quiz generation, validation, and deterministic grading.",
        ),
        (
            Picture(
                ROOT / "5_Quiz_generation_and_grading.png",
                "Listing 6.8: Programmatic validation of generated quiz questions.",
                "Code screenshot showing programmatic quiz-question validation.",
            ),
        ),
    ),
    AlgorithmAssets(
        6,
        Picture(
            ROOT / "docs/figures/chapter6/algorithm-6-mentor-matching-score.png",
            "Figure 6.6: Mentor scoring from skill coverage, evidence confidence, and seniority.",
            "Diagram showing the deterministic mentor matching score.",
        ),
        (
            Picture(
                ROOT / "6_Mentor_matching.png",
                "Listing 6.9: Mentor score calculation from coverage, confidence, and seniority.",
                "Code screenshot showing deterministic mentor score calculation.",
            ),
        ),
    ),
)


def paragraph_text(paragraph: ET.Element) -> str:
    return "".join(node.text or "" for node in paragraph.iter(W + "t")).strip()


def png_dimensions(path: Path) -> tuple[int, int]:
    with path.open("rb") as handle:
        header = handle.read(24)
    if header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        raise RuntimeError(f"Not a supported PNG image: {path}")
    return struct.unpack(">II", header[16:24])


def scaled_extent(path: Path) -> tuple[int, int]:
    width_px, height_px = png_dimensions(path)
    width = MAX_IMAGE_WIDTH
    height = round(width * height_px / width_px)
    return width, height


def image_paragraph(
    relationship_id: str,
    filename: str,
    alt_text: str,
    doc_pr_id: int,
    width: int,
    height: int,
) -> ET.Element:
    paragraph = ET.Element(W + "p")
    p_pr = ET.SubElement(paragraph, W + "pPr")
    ET.SubElement(p_pr, W + "keepNext")
    ET.SubElement(p_pr, W + "jc", {W + "val": "center"})
    ET.SubElement(p_pr, W + "spacing", {W + "before": "120", W + "after": "60"})

    run = ET.SubElement(paragraph, W + "r")
    drawing = ET.SubElement(run, W + "drawing")
    inline = ET.SubElement(
        drawing,
        WP + "inline",
        {"distT": "0", "distB": "0", "distL": "0", "distR": "0"},
    )
    ET.SubElement(inline, WP + "extent", {"cx": str(width), "cy": str(height)})
    ET.SubElement(
        inline,
        WP + "effectExtent",
        {"l": "0", "t": "0", "r": "0", "b": "0"},
    )
    ET.SubElement(
        inline,
        WP + "docPr",
        {"id": str(doc_pr_id), "name": filename, "descr": alt_text},
    )
    frame_properties = ET.SubElement(inline, WP + "cNvGraphicFramePr")
    ET.SubElement(frame_properties, A + "graphicFrameLocks", {"noChangeAspect": "1"})

    graphic = ET.SubElement(inline, A + "graphic")
    graphic_data = ET.SubElement(
        graphic,
        A + "graphicData",
        {"uri": "http://schemas.openxmlformats.org/drawingml/2006/picture"},
    )
    picture = ET.SubElement(graphic_data, PIC + "pic")

    non_visual = ET.SubElement(picture, PIC + "nvPicPr")
    ET.SubElement(non_visual, PIC + "cNvPr", {"id": "0", "name": filename})
    ET.SubElement(non_visual, PIC + "cNvPicPr")

    fill = ET.SubElement(picture, PIC + "blipFill")
    ET.SubElement(fill, A + "blip", {R + "embed": relationship_id})
    stretch = ET.SubElement(fill, A + "stretch")
    ET.SubElement(stretch, A + "fillRect")

    shape = ET.SubElement(picture, PIC + "spPr")
    transform = ET.SubElement(shape, A + "xfrm")
    ET.SubElement(transform, A + "off", {"x": "0", "y": "0"})
    ET.SubElement(transform, A + "ext", {"cx": str(width), "cy": str(height)})
    geometry = ET.SubElement(shape, A + "prstGeom", {"prst": "rect"})
    ET.SubElement(geometry, A + "avLst")
    return paragraph


def caption_paragraph(text: str) -> ET.Element:
    paragraph = ET.Element(W + "p")
    p_pr = ET.SubElement(paragraph, W + "pPr")
    ET.SubElement(p_pr, W + "pStyle", {W + "val": "CCCaption"})
    ET.SubElement(p_pr, W + "keepLines")
    ET.SubElement(p_pr, W + "jc", {W + "val": "center"})
    ET.SubElement(p_pr, W + "spacing", {W + "after": "120"})
    run = ET.SubElement(paragraph, W + "r")
    node = ET.SubElement(run, W + "t")
    node.text = text
    return paragraph


def main() -> int:
    if not SOURCE.exists():
        print(f"Source report not found: {SOURCE}", file=sys.stderr)
        return 1

    pictures = [
        picture
        for algorithm in ASSETS
        for picture in (algorithm.diagram, *algorithm.listings)
    ]
    missing = [picture.path for picture in pictures if not picture.path.exists()]
    if missing:
        for path in missing:
            print(f"Image not found: {path}", file=sys.stderr)
        return 1

    with ZipFile(SOURCE, "r") as source_zip:
        document = ET.fromstring(source_zip.read("word/document.xml"))
        relationships = ET.fromstring(
            source_zip.read("word/_rels/document.xml.rels")
        )

        existing_text = {paragraph_text(p) for p in document.iter(W + "p")}
        if any(picture.caption in existing_text for picture in pictures):
            raise RuntimeError("The report already contains an inserted algorithm caption")

        parent_map = {child: parent for parent in document.iter() for child in parent}
        relationship_ids = {
            relationship.get("Id") for relationship in relationships
        }
        relationship_number = 1
        while f"rIdAlgorithm{relationship_number}" in relationship_ids:
            relationship_number += 1

        doc_pr_ids = [
            int(node.get("id"))
            for node in document.iter(WP + "docPr")
            if (node.get("id") or "").isdigit()
        ]
        next_doc_pr_id = max(doc_pr_ids, default=0) + 1

        zip_names = set(source_zip.namelist())
        media_number = 1
        media_payloads: list[tuple[str, bytes]] = []

        for algorithm in ASSETS:
            heading = next(
                paragraph
                for paragraph in document.iter(W + "p")
                if paragraph_text(paragraph).startswith(
                    f"Algorithm {algorithm.number}:"
                )
            )
            container = parent_map[heading]
            children = list(container)
            heading_index = children.index(heading)
            step_container = next(
                child
                for child in children[heading_index + 1 :]
                if child.tag == W + "sdt"
            )

            def add_picture(picture: Picture, insertion_index: int) -> int:
                nonlocal relationship_number, next_doc_pr_id, media_number

                while f"word/media/chapter6_algorithm_{media_number}.png" in zip_names:
                    media_number += 1
                media_name = f"chapter6_algorithm_{media_number}.png"
                media_path = f"word/media/{media_name}"
                zip_names.add(media_path)

                relationship_id = f"rIdAlgorithm{relationship_number}"
                relationship_number += 1
                ET.SubElement(
                    relationships,
                    PKG_REL + "Relationship",
                    {
                        "Id": relationship_id,
                        "Type": IMAGE_REL_TYPE,
                        "Target": f"media/{media_name}",
                    },
                )

                width, height = scaled_extent(picture.path)
                container.insert(
                    insertion_index,
                    image_paragraph(
                        relationship_id,
                        media_name,
                        picture.alt_text,
                        next_doc_pr_id,
                        width,
                        height,
                    ),
                )
                next_doc_pr_id += 1
                container.insert(
                    insertion_index + 1,
                    caption_paragraph(picture.caption),
                )
                media_payloads.append((media_path, picture.path.read_bytes()))
                media_number += 1
                return insertion_index + 2

            table_index = list(container).index(step_container)
            add_picture(algorithm.diagram, table_index)

            insertion_index = list(container).index(step_container) + 1
            for listing in algorithm.listings:
                insertion_index = add_picture(listing, insertion_index)

        document_bytes = ET.tostring(
            document, encoding="utf-8", xml_declaration=True
        )
        ET.register_namespace("", PKG_REL_NS)
        relationship_bytes = ET.tostring(
            relationships, encoding="utf-8", xml_declaration=True
        )

        with ZipFile(OUTPUT, "w", compression=ZIP_DEFLATED) as output_zip:
            for info in source_zip.infolist():
                if info.filename == "word/document.xml":
                    payload = document_bytes
                elif info.filename == "word/_rels/document.xml.rels":
                    payload = relationship_bytes
                else:
                    payload = source_zip.read(info.filename)
                output_zip.writestr(info, payload)

            for media_path, payload in media_payloads:
                output_zip.writestr(media_path, payload)

    print(OUTPUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
