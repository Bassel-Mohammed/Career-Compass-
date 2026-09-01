#!/usr/bin/env python3
"""Add a coding and debugging AI-use disclosure table to Appendix B."""

from __future__ import annotations

import argparse
import html
import os
import re
import tempfile
import zipfile
from pathlib import Path


TABLE_RE = re.compile(r"<w:tbl>.*?</w:tbl>", re.DOTALL)
TEXT_RE = re.compile(r"<w:t(?:\s[^>]*)?>(.*?)</w:t>", re.DOTALL)


DISCLOSURE_ROWS = [
    ("Item", "Description"),
    ("Tool Used", "OpenAI Codex (AI coding assistant)"),
    (
        "Purpose",
        "Used to assist with code review, debugging, error diagnosis, "
        "implementation fixes, refactoring suggestions, and test design.",
    ),
    (
        "Prompts Used",
        "Review this code, identify the cause of the error, and suggest or "
        "implement an appropriate fix that preserves the intended behavior. "
        "Propose tests for the corrected code.",
    ),
    (
        "Human Modifications",
        "The project team reviewed and adapted every accepted suggestion, "
        "reproduced the reported issue, and validated the affected behavior "
        "through relevant automated or manual tests before integration. AI "
        "output was advisory; final technical decisions and responsibility "
        "remained with the authors.",
    ),
]


def visible_text(xml: str) -> str:
    return "".join(html.unescape(value) for value in TEXT_RE.findall(xml))


def replace_cell_text(cell_xml: str, new_text: str) -> str:
    """Replace visible cell text while retaining its paragraph/run formatting."""
    matches = list(TEXT_RE.finditer(cell_xml))
    if not matches:
        raise ValueError("Template table cell has no text node")

    escaped = html.escape(new_text)
    first = matches[0]
    result = cell_xml[: first.start(1)] + escaped + cell_xml[first.end(1) :]

    # Template cells contain one visible text node. Keep this defensive path so
    # any later split-run version does not retain fragments of the old value.
    if len(matches) > 1:
        offset = len(escaped) - (first.end(1) - first.start(1))
        for match in reversed(matches[1:]):
            start = match.start(1) + offset
            end = match.end(1) + offset
            result = result[:start] + result[end:]
    return result


def build_disclosure_table(template_table: str) -> str:
    rows = re.findall(r"<w:tr(?:\s[^>]*)?>.*?</w:tr>", template_table, re.DOTALL)
    if len(rows) != len(DISCLOSURE_ROWS):
        raise ValueError(
            f"Expected a five-row disclosure template, found {len(rows)} rows"
        )

    updated_rows: list[str] = []
    for row_xml, expected_values in zip(rows, DISCLOSURE_ROWS, strict=True):
        cells = re.findall(r"<w:tc(?:\s[^>]*)?>.*?</w:tc>", row_xml, re.DOTALL)
        if len(cells) != 2:
            raise ValueError("Disclosure template row does not have two cells")

        updated_cells = [
            replace_cell_text(cell, value)
            for cell, value in zip(cells, expected_values, strict=True)
        ]
        rebuilt = row_xml
        for old_cell, new_cell in zip(cells, updated_cells, strict=True):
            rebuilt = rebuilt.replace(old_cell, new_cell, 1)
        updated_rows.append(rebuilt)

    table = template_table
    for old_row, new_row in zip(rows, updated_rows, strict=True):
        table = table.replace(old_row, new_row, 1)
    return table


def renew_paragraph_ids(table_xml: str, document_xml: str) -> str:
    """Give cloned table paragraphs unique Word paragraph identifiers."""
    used = {
        int(value, 16)
        for value in re.findall(r'w14:paraId="([0-9A-Fa-f]{8})"', document_xml)
    }
    next_id = max(used, default=0) + 1

    def replace_id(_match: re.Match[str]) -> str:
        nonlocal next_id
        while next_id in used:
            next_id += 1
        value = next_id
        used.add(value)
        next_id += 1
        return f'w14:paraId="{value:08X}"'

    return re.sub(r'w14:paraId="[0-9A-Fa-f]{8}"', replace_id, table_xml)


def edit_document_xml(document_xml: str) -> str:
    if "OpenAI Codex (AI coding assistant)" in document_xml:
        raise ValueError("The coding/debugging disclosure table already exists")

    tables = list(TABLE_RE.finditer(document_xml))
    claude_matches = [
        match
        for match in tables
        if visible_text(match.group(0)).startswith(
            "ItemDescriptionTool UsedClaudePurpose"
        )
    ]
    gemini_matches = [
        match
        for match in tables
        if "Gemmini AI" in visible_text(match.group(0))
        or "Gemini AI" in visible_text(match.group(0))
    ]
    if len(claude_matches) != 1:
        raise ValueError(f"Expected one Claude disclosure table, found {len(claude_matches)}")
    if len(gemini_matches) != 1:
        raise ValueError(f"Expected one Gemini disclosure table, found {len(gemini_matches)}")

    appendix_b_index = document_xml.rfind(">Appendix B<", 0, claude_matches[0].start())
    appendix_c_index = document_xml.find(">Appendix C:", gemini_matches[0].end())
    if appendix_b_index < 0 or appendix_c_index < 0 or appendix_b_index >= appendix_c_index:
        raise ValueError("Could not locate the Appendix B insertion region")

    claude = claude_matches[0]
    gemini = gemini_matches[0]
    if not (appendix_b_index < claude.start() < gemini.start() < appendix_c_index):
        raise ValueError("Existing AI disclosure tables are not in the expected order")

    new_table = build_disclosure_table(claude.group(0))
    new_table = renew_paragraph_ids(new_table, document_xml)
    spacer = "<w:p><w:pPr><w:pStyle w:val=\"Normal\"/></w:pPr></w:p>"
    insertion = spacer + new_table
    return document_xml[: gemini.end()] + insertion + document_xml[gemini.end() :]


def update_docx(source: Path, destination: Path) -> None:
    if source.resolve() == destination.resolve():
        raise ValueError("Source and destination must be different files")

    with zipfile.ZipFile(source, "r") as archive:
        if "word/document.xml" not in archive.namelist():
            raise ValueError("Input is not a supported Word DOCX package")
        document_xml = archive.read("word/document.xml").decode("utf-8")
        edited_document = edit_document_xml(document_xml)

        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            prefix=destination.stem + "-",
            suffix=".docx",
            dir=destination.parent,
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)

        try:
            with zipfile.ZipFile(temporary_path, "w") as output:
                for info in archive.infolist():
                    payload = (
                        edited_document.encode("utf-8")
                        if info.filename == "word/document.xml"
                        else archive.read(info.filename)
                    )
                    output.writestr(info, payload)

            with zipfile.ZipFile(temporary_path, "r") as check:
                corrupt = check.testzip()
                if corrupt is not None:
                    raise ValueError(f"Corrupt output package member: {corrupt}")
                check_xml = check.read("word/document.xml").decode("utf-8")
                if check_xml.count("OpenAI Codex (AI coding assistant)") != 1:
                    raise ValueError("Output disclosure table validation failed")

            temporary_path.replace(destination)
            os.chmod(destination, source.stat().st_mode & 0o777)
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    update_docx(args.source, args.destination)
    print(f"Created: {args.destination}")
    print("Added Appendix B coding/debugging AI disclosure table")


if __name__ == "__main__":
    main()
