#!/usr/bin/env python3
"""Repair the automatic table of contents in the graduation report.

The source document contains a valid TOC field, but its cached result predates
Chapter 6 and recent Chapter 5 additions. This script keeps the document's
content and formatting intact while making the field refresh on open, limiting
the TOC to three useful levels, and removing a figure caption from the heading
hierarchy.
"""

from __future__ import annotations

import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "CareerCompass_Graduation_Project_Report.docx"
DEFAULT_BACKUP = ROOT / "CareerCompass_Graduation_Project_Report_Before_TOC_Fix.docx"

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = f"{{{W_NS}}}"

TOC_INSTRUCTION = (
    ' TOC \\o "1-3" \\h \\z '
    '\\t "CC Heading 1,1,CC Heading 2,2,CC Heading 3,3"'
)


def paragraph_text(paragraph: ET.Element) -> str:
    return "".join(node.text or "" for node in paragraph.iter(W + "t")).strip()


def repair_document_xml(data: bytes) -> bytes:
    text = data.decode("utf-8-sig")

    toc_pattern = re.compile(
        r'(<w:instrText\b[^>]*>)(\s*TOC\s+.*?)(</w:instrText>)',
        re.DOTALL,
    )
    matches = list(toc_pattern.finditer(text))
    if len(matches) != 1:
        raise RuntimeError(f"Expected one TOC instruction; found {len(matches)}")

    match = matches[0]
    text = text[: match.start(2)] + TOC_INSTRUCTION + text[match.end(2) :]

    # Mark the outer TOC field as dirty so Word recalculates headings and page
    # numbers instead of continuing to display the obsolete cached result.
    instruction_start = match.start(1)
    paragraph_start = text.rfind("<w:p ", 0, instruction_start)
    if paragraph_start < 0:
        paragraph_start = text.rfind("<w:p>", 0, instruction_start)
    begin_start = text.rfind('<w:fldChar w:fldCharType="begin"', paragraph_start, instruction_start)
    if begin_start < 0:
        raise RuntimeError("Could not find the beginning of the TOC field")
    begin_end = text.find("/>", begin_start, instruction_start)
    if begin_end < 0:
        raise RuntimeError("The TOC field beginning is malformed")
    begin_tag = text[begin_start : begin_end + 2]
    if 'w:dirty="true"' not in begin_tag:
        replacement = begin_tag[:-2].rstrip() + ' w:dirty="true" />'
        text = text[:begin_start] + replacement + text[begin_end + 2 :]

    # This figure caption was accidentally formatted as a level-3 heading.
    # Keeping its direct formatting while changing only its paragraph style
    # prevents it from appearing as a false section in the refreshed TOC.
    caption_marker = "Entity-Relationship Diagram of the"
    marker_index = text.find(caption_marker)
    if marker_index < 0:
        raise RuntimeError("Could not find the PostgreSQL ERD caption")
    caption_start = text.rfind("<w:p ", 0, marker_index)
    caption_end = text.find("</w:p>", marker_index)
    if caption_start < 0 or caption_end < 0:
        raise RuntimeError("Could not isolate the PostgreSQL ERD caption paragraph")
    caption_xml = text[caption_start : caption_end + len("</w:p>")]
    old_style = '<w:pStyle w:val="CCHeading3" />'
    if caption_xml.count(old_style) != 1:
        raise RuntimeError("The PostgreSQL ERD caption is not using the expected heading style")
    caption_xml = caption_xml.replace(
        old_style,
        '<w:pStyle w:val="CCCaption" />',
        1,
    )
    text = text[:caption_start] + caption_xml + text[caption_end + len("</w:p>") :]

    return ("\ufeff" + text).encode("utf-8")


def repair_settings_xml(data: bytes) -> bytes:
    text = data.decode("utf-8-sig")
    pattern = re.compile(r'<w:updateFields\b[^>]*/>')
    matches = list(pattern.finditer(text))
    if matches:
        first = matches[0]
        text = text[: first.start()] + '<w:updateFields w:val="true" />' + text[first.end() :]
    else:
        closing = "</w:settings>"
        if closing not in text:
            raise RuntimeError("word/settings.xml has no closing settings element")
        text = text.replace(closing, '<w:updateFields w:val="true" />' + closing, 1)
    return ("\ufeff" + text).encode("utf-8")


def repair_numbering_xml(data: bytes) -> bytes:
    # The report owner requested that em dashes not appear in paragraph text.
    # Word's chapter-number format would otherwise reintroduce one into every
    # chapter heading and the refreshed TOC.
    text = data.decode("utf-8-sig")
    old = 'w:lvlText w:val="Chapter %1 —"'
    new = 'w:lvlText w:val="Chapter %1"'
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected one chapter numbering format; found {count}")
    text = text.replace(old, new, 1)
    return ("\ufeff" + text).encode("utf-8")


def verify(path: Path) -> tuple[int, list[str]]:
    with ZipFile(path) as archive:
        bad_member = archive.testzip()
        if bad_member:
            raise RuntimeError(f"Corrupt DOCX member: {bad_member}")
        document = ET.fromstring(archive.read("word/document.xml"))
        settings = ET.fromstring(archive.read("word/settings.xml"))
        numbering = ET.fromstring(archive.read("word/numbering.xml"))

    instructions = [
        "".join(node.text or "" for node in paragraph.iter(W + "instrText")).strip()
        for paragraph in document.iter(W + "p")
    ]
    instructions = [value for value in instructions if value.startswith("TOC ")]
    if instructions != [TOC_INSTRUCTION.strip()]:
        raise RuntimeError(f"Unexpected TOC instruction after repair: {instructions}")

    toc_begin_is_dirty = False
    for paragraph in document.iter(W + "p"):
        instruction = "".join(node.text or "" for node in paragraph.iter(W + "instrText"))
        if "TOC " not in instruction:
            continue
        toc_begin_is_dirty = any(
            node.get(W + "fldCharType") == "begin" and node.get(W + "dirty") == "true"
            for node in paragraph.iter(W + "fldChar")
        )
    if not toc_begin_is_dirty:
        raise RuntimeError("The repaired TOC field is not marked for refresh")

    update_fields = settings.find(".//" + W + "updateFields")
    if update_fields is None or update_fields.get(W + "val") != "true":
        raise RuntimeError("Automatic field updating is not enabled")

    caption_style_ok = False
    toc_entries: list[str] = []
    for paragraph in document.iter(W + "p"):
        value = paragraph_text(paragraph)
        style_node = paragraph.find("./" + W + "pPr/" + W + "pStyle")
        style = style_node.get(W + "val") if style_node is not None else ""
        if value.startswith("Figure 5.2:"):
            caption_style_ok = style == "CCCaption"
        if style in {"Heading1", "Heading2", "Heading3", "CCHeading1", "CCHeading2", "CCHeading3"}:
            toc_entries.append(value)
    if not caption_style_ok:
        raise RuntimeError("The PostgreSQL ERD caption still has a heading style")
    if "Implementation" not in toc_entries or "6.3.1 Critical Algorithms" not in toc_entries:
        raise RuntimeError("Chapter 6 headings are not eligible for the repaired TOC")
    if "Appendix B" not in toc_entries or "AI Tool Usage Disclosure" not in toc_entries:
        raise RuntimeError("Appendix B headings are not eligible for the repaired TOC")

    chapter_formats = [
        node.get(W + "val", "")
        for node in numbering.iter(W + "lvlText")
        if node.get(W + "val", "").startswith("Chapter %1")
    ]
    if chapter_formats != ["Chapter %1"]:
        raise RuntimeError(f"Unexpected chapter numbering format: {chapter_formats}")

    return len(toc_entries), instructions


def main() -> int:
    source = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DEFAULT_SOURCE
    backup = source.with_name(source.stem + "_Before_TOC_Fix" + source.suffix)
    if source == DEFAULT_SOURCE:
        backup = DEFAULT_BACKUP

    if not source.is_file():
        raise FileNotFoundError(source)

    # Verify the source before making the recoverable backup.
    with ZipFile(source) as archive:
        bad_member = archive.testzip()
        if bad_member:
            raise RuntimeError(f"Source DOCX is corrupt at {bad_member}")

    if not backup.exists():
        shutil.copy2(source, backup)

    replacements: dict[str, bytes] = {}
    with ZipFile(source) as archive:
        replacements["word/document.xml"] = repair_document_xml(
            archive.read("word/document.xml")
        )
        replacements["word/settings.xml"] = repair_settings_xml(
            archive.read("word/settings.xml")
        )
        replacements["word/numbering.xml"] = repair_numbering_xml(
            archive.read("word/numbering.xml")
        )

    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=source.stem + "_",
        suffix=".docx",
        dir=source.parent,
    )
    os.close(file_descriptor)
    temporary = Path(temporary_name)

    try:
        with ZipFile(source) as source_archive, ZipFile(
            temporary,
            "w",
            compression=ZIP_DEFLATED,
        ) as output_archive:
            for member in source_archive.infolist():
                payload = replacements.get(member.filename, source_archive.read(member.filename))
                output_archive.writestr(member, payload)

        entry_count, instructions = verify(temporary)
        os.replace(temporary, source)
    finally:
        if temporary.exists():
            temporary.unlink()

    print(f"Updated: {source}")
    print(f"Backup:  {backup}")
    print(f"TOC-eligible headings (levels 1-3): {entry_count}")
    print(f"TOC field: {instructions[0]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
