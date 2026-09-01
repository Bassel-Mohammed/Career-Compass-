#!/usr/bin/env python3
"""Audit and repair the abbreviations section in the CareerCompass report.

The source document already contains an abbreviations section with three
tables. This script rebuilds only the general-terms table, preserving the
table's Word formatting, and leaves the actor and NFR-category code tables
unchanged. It also marks Word fields for refresh because the longer corrected
table can change the page numbers cached in the table of contents.
"""

from __future__ import annotations

import copy
import io
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "CareerCompass_Graduation_Project_Report (1) (1).docx"

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = f"{{{W_NS}}}"
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"


# Entries are alphabetical for quick lookup. Product names without an
# expansion (for example, FastAPI, MySQL, OpenAPI, and PostgreSQL) are not
# treated as abbreviations. Reference-only publisher and URL fragments are
# also excluded.
GENERAL_TERMS: tuple[tuple[str, str], ...] = (
    ("AHP", "Analytic Hierarchy Process"),
    ("AI", "Artificial Intelligence"),
    ("API", "Application Programming Interface"),
    ("ASGI", "Asynchronous Server Gateway Interface"),
    ("BERT", "Bidirectional Encoder Representations from Transformers"),
    (
        "BGE-M3",
        "BAAI General Embedding M3 (Multi-Functionality, Multi-Linguality, and Multi-Granularity)",
    ),
    ("CLI", "Command-Line Interface"),
    ("CORS", "Cross-Origin Resource Sharing"),
    ("CPU", "Central Processing Unit"),
    ("CUDA", "Compute Unified Device Architecture"),
    ("DB", "Database"),
    ("DTO", "Data Transfer Object"),
    ("ER", "Entity Relationship"),
    ("ERD", "Entity Relationship Diagram"),
    ("ESCO", "European Skills, Competences, Qualifications and Occupations"),
    ("FAISS", "Facebook AI Similarity Search"),
    ("FK", "Foreign Key"),
    ("FR", "Functional Requirement"),
    ("GB", "Gigabyte"),
    ("GDPR", "General Data Protection Regulation"),
    ("GHz", "Gigahertz"),
    ("GPT", "Generative Pre-trained Transformer"),
    ("GPU", "Graphics Processing Unit"),
    ("H2", "H2 Database"),
    ("HMAC", "Hash-Based Message Authentication Code"),
    ("HTTP", "Hypertext Transfer Protocol"),
    ("HTTPS", "Hypertext Transfer Protocol Secure"),
    ("ID", "Identifier"),
    ("ILO", "International Labour Organization"),
    ("IP", "Internet Protocol"),
    (
        "ISO/IEC",
        "International Organization for Standardization / International Electrotechnical Commission",
    ),
    ("JDBC", "Java Database Connectivity"),
    ("JJWT", "Java JWT Library"),
    ("JOD", "Jordanian Dinar"),
    ("JPA", "Jakarta Persistence API"),
    ("JSON", "JavaScript Object Notation"),
    ("JWT", "JSON Web Token"),
    ("JVM", "Java Virtual Machine"),
    ("KB", "Kilobyte"),
    ("KNN", "K-Nearest Neighbours"),
    ("LLM", "Large Language Model"),
    ("LOC", "Lines of Code"),
    ("LTS", "Long-Term Support"),
    ("MB", "Megabyte"),
    ("MIT", "Massachusetts Institute of Technology"),
    ("ML", "Machine Learning"),
    ("MOOC", "Massive Open Online Course"),
    ("MVC", "Model-View-Controller"),
    ("NFR", "Non-Functional Requirement"),
    ("NLTK", "Natural Language Toolkit"),
    ("NLP", "Natural Language Processing"),
    ("NVMe", "Non-Volatile Memory Express"),
    ("OCR", "Optical Character Recognition"),
    ("OECD", "Organisation for Economic Co-operation and Development"),
    ("OOM", "Out of Memory"),
    ("O*NET", "Occupational Information Network"),
    ("ORM", "Object-Relational Mapping"),
    ("PaaS", "Platform as a Service"),
    ("PDF", "Portable Document Format"),
    ("PEP", "Python Enhancement Proposal"),
    ("PERT", "Program Evaluation and Review Technique"),
    ("PK", "Primary Key"),
    ("QA", "Quality Assurance"),
    ("RAG", "Retrieval-Augmented Generation"),
    ("RAM", "Random Access Memory"),
    ("RBAC", "Role-Based Access Control"),
    ("REST", "Representational State Transfer"),
    ("RFC", "Request for Comments"),
    ("SBERT", "Sentence-BERT"),
    ("SDK", "Software Development Kit"),
    ("SDLC", "Software Development Life Cycle"),
    ("SHA-256", "Secure Hash Algorithm 256-bit"),
    ("SQL", "Structured Query Language"),
    ("SSD", "System Sequence Diagram"),
    ("TB", "Terabyte"),
    ("TLS", "Transport Layer Security"),
    ("TOPSIS", "Technique for Order Preference by Similarity to Ideal Solution"),
    ("UI", "User Interface"),
    ("URL", "Uniform Resource Locator"),
    ("USD", "US Dollar"),
    ("UX", "User Experience"),
    ("VPS", "Virtual Private Server"),
    ("WBS", "Work Breakdown Structure"),
    ("WCAG", "Web Content Accessibility Guidelines"),
    ("XSS", "Cross-Site Scripting"),
)

REMOVED_UNUSED = {
    "CI/CD",
    "CRUD",
    "JSP",
    "RSA",
    "TOC",
    "UAT",
    "UML",
    "VPN",
}

EXPECTED_ACTOR_CODES = {"JS", "EMP", "SA", "CM", "EX"}
EXPECTED_NFR_CODES = {
    "PERF",
    "REL",
    "USE",
    "SEC",
    "PRIV",
    "MNT",
    "SCAL",
    "COMP",
    "COST",
    "LEG",
}


def register_namespaces(data: bytes) -> None:
    """Keep the source prefixes, especially those in mc:Ignorable."""
    seen_prefixes: set[str] = set()
    seen_uris: set[str] = set()
    for _event, value in ET.iterparse(io.BytesIO(data), events=("start-ns",)):
        prefix, uri = value
        prefix = prefix or ""
        if prefix in seen_prefixes or uri in seen_uris or prefix == "xml":
            continue
        ET.register_namespace(prefix, uri)
        seen_prefixes.add(prefix)
        seen_uris.add(uri)


def element_text(element: ET.Element) -> str:
    return "".join(node.text or "" for node in element.iter(W + "t")).strip()


def set_paragraph_text(paragraph: ET.Element, value: str) -> None:
    text_nodes = list(paragraph.iter(W + "t"))
    if not text_nodes:
        run = paragraph.find(W + "r")
        if run is None:
            run = ET.SubElement(paragraph, W + "r")
        text_nodes = [ET.SubElement(run, W + "t")]

    text_nodes[0].text = value
    if value.startswith(" ") or value.endswith(" "):
        text_nodes[0].set(XML_SPACE, "preserve")
    else:
        text_nodes[0].attrib.pop(XML_SPACE, None)
    for node in text_nodes[1:]:
        node.text = ""


def set_cell_text(cell: ET.Element, value: str) -> None:
    paragraphs = list(cell.iter(W + "p"))
    if not paragraphs:
        paragraphs = [ET.SubElement(cell, W + "p")]
    set_paragraph_text(paragraphs[0], value)
    for paragraph in paragraphs[1:]:
        set_paragraph_text(paragraph, "")


def table_rows(table: ET.Element) -> list[ET.Element]:
    return table.findall(W + "tr")


def row_values(row: ET.Element) -> tuple[str, ...]:
    return tuple(element_text(cell) for cell in row.findall(W + "tc"))


def find_direct_paragraph(body: ET.Element, text: str) -> int:
    matches = [
        index
        for index, child in enumerate(list(body))
        if child.tag == W + "p" and element_text(child) == text
    ]
    if len(matches) != 1:
        raise RuntimeError(f"Expected one direct paragraph {text!r}; found {len(matches)}")
    return matches[0]


def find_next_table(body: ET.Element, after_index: int) -> ET.Element:
    for child in list(body)[after_index + 1 :]:
        if child.tag == W + "tbl":
            return child
    raise RuntimeError("Could not find the table following the abbreviations heading")


def rebuild_general_terms_table(root: ET.Element) -> tuple[set[str], set[str]]:
    body = root.find(W + "body")
    if body is None:
        raise RuntimeError("word/document.xml has no document body")

    general_heading_index = find_direct_paragraph(body, "General Terms")
    table = find_next_table(body, general_heading_index)
    rows = table_rows(table)
    if len(rows) < 2 or row_values(rows[0])[:2] != ("Abbreviation", "Meaning"):
        raise RuntimeError("The General Terms table has an unexpected structure")

    existing: dict[str, ET.Element] = {}
    for row in rows[1:]:
        values = row_values(row)
        if len(values) < 2 or not values[0]:
            continue
        if values[0] in existing:
            raise RuntimeError(f"Duplicate abbreviation in source table: {values[0]}")
        existing[values[0]] = row

    source_terms = set(existing)
    template = rows[1]
    for row in rows[1:]:
        table.remove(row)

    for abbreviation, meaning in GENERAL_TERMS:
        row = copy.deepcopy(existing.get(abbreviation, template))
        cells = row.findall(W + "tc")
        if len(cells) < 2:
            raise RuntimeError("A General Terms data row has fewer than two cells")
        set_cell_text(cells[0], abbreviation)
        set_cell_text(cells[1], meaning)
        table.append(row)

    final_terms = {abbreviation for abbreviation, _meaning in GENERAL_TERMS}
    return source_terms - final_terms, final_terms - source_terms


def mark_toc_dirty(root: ET.Element) -> None:
    for paragraph in root.iter(W + "p"):
        instruction = "".join(
            node.text or "" for node in paragraph.iter(W + "instrText")
        )
        if not instruction.lstrip().startswith("TOC "):
            continue
        for field_char in paragraph.iter(W + "fldChar"):
            if field_char.get(W + "fldCharType") == "begin":
                field_char.set(W + "dirty", "true")


def repair_document_xml(data: bytes) -> tuple[bytes, set[str], set[str]]:
    register_namespaces(data)
    root = ET.fromstring(data)
    removed, added = rebuild_general_terms_table(root)
    mark_toc_dirty(root)
    payload = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    return payload, removed, added


def repair_settings_xml(data: bytes) -> bytes:
    text = data.decode("utf-8-sig")
    update_pattern = re.compile(r"<w:updateFields\b[^>]*/>")
    if update_pattern.search(text):
        text = update_pattern.sub('<w:updateFields w:val="true" />', text, count=1)
    else:
        closing = "</w:settings>"
        if closing not in text:
            raise RuntimeError("word/settings.xml has no closing settings element")
        text = text.replace(
            closing,
            '<w:updateFields w:val="true" />' + closing,
            1,
        )
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' +
            re.sub(r"^<\?xml[^>]*>\s*", "", text)).encode("utf-8")


def section_tables(root: ET.Element) -> tuple[ET.Element, ET.Element, ET.Element]:
    body = root.find(W + "body")
    if body is None:
        raise RuntimeError("word/document.xml has no document body")
    children = list(body)
    general_index = find_direct_paragraph(body, "General Terms")
    actor_index = find_direct_paragraph(body, "Actors")
    nfr_index = find_direct_paragraph(body, "NFR categories:")
    return (
        find_next_table(body, general_index),
        find_next_table(body, actor_index),
        find_next_table(body, nfr_index),
    )


def table_codes(table: ET.Element) -> list[str]:
    rows = table_rows(table)
    return [row_values(row)[0] for row in rows[1:] if row_values(row)]


def report_text_excluding_abbreviations(root: ET.Element) -> str:
    body = root.find(W + "body")
    if body is None:
        raise RuntimeError("word/document.xml has no document body")
    children = list(body)
    start = find_direct_paragraph(body, "Abbreviations")
    end = find_direct_paragraph(body, "Abstract")
    kept = children[:start] + children[end:]
    blocks: list[str] = []
    for child in kept:
        if child.tag == W + "p":
            blocks.append(element_text(child))
        else:
            # Preserve a token boundary between adjacent table cells. A flat
            # descendant-text join would turn cells such as "JJWT" and
            # "0.12.6" into the false token "JJWT0.12.6".
            blocks.extend(element_text(paragraph) for paragraph in child.iter(W + "p"))
    return "\n".join(blocks)


def term_occurs(text: str, term: str) -> bool:
    # Optional plural forms cover prose such as APIs, DTOs, GPUs, LLMs, MOOCs,
    # NFRs, PDFs, and URLs without duplicating singular list entries.
    pattern = r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?:s)?(?![A-Za-z0-9])"
    return re.search(pattern, text) is not None


def verify(path: Path) -> None:
    with ZipFile(path) as archive:
        bad_member = archive.testzip()
        if bad_member:
            raise RuntimeError(f"Corrupt DOCX member: {bad_member}")
        document_data = archive.read("word/document.xml")
        document = ET.fromstring(document_data)
        settings = ET.fromstring(archive.read("word/settings.xml"))

    general, actors, nfr = section_tables(document)
    expected_general = [abbreviation for abbreviation, _meaning in GENERAL_TERMS]
    actual_general = table_codes(general)
    if actual_general != expected_general:
        raise RuntimeError("The rebuilt General Terms table is incomplete or out of order")
    if len(actual_general) != len(set(actual_general)):
        raise RuntimeError("The rebuilt General Terms table contains duplicate entries")

    actual_meanings = {
        values[0]: values[1]
        for values in (row_values(row) for row in table_rows(general)[1:])
        if len(values) >= 2
    }
    if actual_meanings != dict(GENERAL_TERMS):
        raise RuntimeError("One or more abbreviation meanings were not written correctly")
    if REMOVED_UNUSED & set(actual_general):
        raise RuntimeError("An unused abbreviation remains in the General Terms table")
    if set(table_codes(actors)) != EXPECTED_ACTOR_CODES:
        raise RuntimeError("The actor abbreviation table changed unexpectedly")
    if set(table_codes(nfr)) != EXPECTED_NFR_CODES:
        raise RuntimeError("The NFR-category abbreviation table changed unexpectedly")

    report_text = report_text_excluding_abbreviations(document)
    missing_occurrences = [
        term for term in actual_general if not term_occurs(report_text, term)
    ]
    if missing_occurrences:
        raise RuntimeError(
            "Listed general terms not found in the report: "
            + ", ".join(missing_occurrences)
        )
    used_removed = [
        term for term in sorted(REMOVED_UNUSED) if term_occurs(report_text, term)
    ]
    if used_removed:
        raise RuntimeError(
            "Terms marked unused now occur in the report: " + ", ".join(used_removed)
        )

    update_fields = settings.find(".//" + W + "updateFields")
    if update_fields is None or update_fields.get(W + "val") != "true":
        raise RuntimeError("Word fields are not marked for update")


def main() -> int:
    source = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DEFAULT_SOURCE
    if not source.is_file():
        raise FileNotFoundError(source)
    backup = source.with_name(source.stem + "_Before_Abbreviations_Fix" + source.suffix)

    with ZipFile(source) as archive:
        bad_member = archive.testzip()
        if bad_member:
            raise RuntimeError(f"Source DOCX is corrupt at {bad_member}")
        document_xml, removed, added = repair_document_xml(
            archive.read("word/document.xml")
        )
        settings_xml = repair_settings_xml(archive.read("word/settings.xml"))

    if not backup.exists():
        shutil.copy2(source, backup)

    replacements = {
        "word/document.xml": document_xml,
        "word/settings.xml": settings_xml,
    }
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
                payload = replacements.get(
                    member.filename,
                    source_archive.read(member.filename),
                )
                output_archive.writestr(member, payload)

        verify(temporary)
        os.replace(temporary, source)
    finally:
        if temporary.exists():
            temporary.unlink()

    print(f"Updated: {source}")
    print(f"Backup:  {backup}")
    print(f"General terms: {len(GENERAL_TERMS)}")
    print("Removed unused: " + ", ".join(sorted(removed)))
    print("Added missing: " + ", ".join(sorted(added)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
