#!/usr/bin/env python3
"""Update heading semantics and functional-requirement priorities in a DOCX.

The script intentionally edits only the XML parts that need to change. This
keeps the report's images, relationships, embedded fonts, and other package
parts byte-for-byte unchanged.
"""

from __future__ import annotations

import argparse
import html
import os
import re
import tempfile
import zipfile
from pathlib import Path


PARAGRAPH_RE = re.compile(r"<w:p(?:\s[^>]*)?>.*?</w:p>", re.DOTALL)
TEXT_RE = re.compile(r"<w:t(?:\s[^>]*)?>(.*?)</w:t>", re.DOTALL)
FR_ID_RE = re.compile(r"FR-(?:JS|CM|EMP|SA|EX|AI)-(?:0?\d+)")


# Requirements that improve convenience, management, or supporting workflows
# after the principal student analysis flow is available.
MEDIUM_PRIORITY = {
    "FR-JS-24",
    "FR-JS-29",
    "FR-JS-30",
    "FR-JS-31",
    "FR-JS-32",
    "FR-CM-08",
    "FR-CM-09",
    "FR-CM-10",
    "FR-CM-11",
    "FR-CM-12",
    "FR-CM-13",
    "FR-EMP-06",
    "FR-EMP-9",
    "FR-EMP-12",
    "FR-EMP-13",
    "FR-EMP-16",
    "FR-SA-04",
    "FR-SA-09",
    "FR-SA-10",
    "FR-SA-14",
    "FR-SA-16",
    "FR-SA-17",
    "FR-SA-18",
    "FR-EX-08",
    "FR-EX-09",
    "FR-EX-10",
    "FR-EX-11",
    "FR-EX-12",
    "FR-AI-10",
    "FR-AI-11",
}


# Production AI job scoring is deliberately deferred in the implementation.
# The student match, employer candidate ranking, dependent candidate views, and
# the two AI-service integration directions therefore share Low priority.
LOW_PRIORITY = {
    "FR-JS-23",
    "FR-EMP-11",
    "FR-EMP-19",
    "FR-AI-12",
    "FR-AI-13",
}


PRIORITY_LEGEND = (
    "Priority codes: [H] High (must-have), [M] Medium (should-have), and [L] "
    "Low (nice-to-have or deferred). Priority indicates implementation/release "
    "importance, not completion status. Production AI-based job matching is "
    "classified as [L]."
)


OLD_FUTURE_WORK = (
    "The first priority is to implement real job-candidate scoring in the AI "
    "service and connect it to the existing backend and frontend workflow."
)
NEW_FUTURE_WORK = (
    "A low-priority future enhancement is to implement real job-candidate "
    "scoring in the AI service and connect it to the existing backend and "
    "frontend workflow."
)


def paragraph_text(paragraph_xml: str) -> str:
    """Return visible paragraph text, retaining tabs and line breaks."""
    parts: list[str] = []
    cursor = 0
    token_re = re.compile(
        r"<w:t(?:\s[^>]*)?>(.*?)</w:t>|<w:tab\s*/>|<w:br(?:\s[^>]*)?\s*/>",
        re.DOTALL,
    )
    for match in token_re.finditer(paragraph_xml):
        cursor = match.end()
        token = match.group(0)
        if match.group(1) is not None:
            parts.append(html.unescape(match.group(1)))
        elif token.startswith("<w:tab"):
            parts.append("\t")
        else:
            parts.append("\n")
    _ = cursor
    return "".join(parts)


def set_paragraph_style(paragraph_xml: str, style: str) -> str:
    """Set the structural style while retaining direct formatting."""
    style_re = re.compile(r'<w:pStyle\s+w:val="[^"]+"\s*/>')
    outline_re = re.compile(r"<w:outlineLvl(?:\s[^>]*)?\s*/>")
    paragraph_xml = outline_re.sub("", paragraph_xml)

    if style_re.search(paragraph_xml):
        return style_re.sub(f'<w:pStyle w:val="{style}"/>', paragraph_xml, count=1)

    ppr_match = re.search(r"<w:pPr(?:\s[^>]*)?>", paragraph_xml)
    if ppr_match:
        insert_at = ppr_match.end()
        return (
            paragraph_xml[:insert_at]
            + f'<w:pStyle w:val="{style}"/>'
            + paragraph_xml[insert_at:]
        )

    p_open = re.match(r"<w:p(?:\s[^>]*)?>", paragraph_xml)
    if not p_open:
        raise ValueError("Malformed Word paragraph")
    insert_at = p_open.end()
    return (
        paragraph_xml[:insert_at]
        + f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>'
        + paragraph_xml[insert_at:]
    )


def legend_paragraph_xml() -> str:
    text = html.escape(PRIORITY_LEGEND)
    return (
        "<w:p>"
        "<w:pPr>"
        '<w:pStyle w:val="Normal"/>'
        '<w:spacing w:after="120" w:line="276" w:lineRule="auto"/>'
        '<w:jc w:val="both"/>'
        '<w:rPr><w:color w:val="000000"/><w:sz w:val="24"/>'
        '<w:szCs w:val="24"/></w:rPr>'
        "</w:pPr>"
        "<w:r>"
        '<w:rPr><w:color w:val="000000"/><w:sz w:val="24"/>'
        '<w:szCs w:val="24"/></w:rPr>'
        f'<w:t xml:space="preserve">{text}</w:t>'
        "</w:r>"
        "</w:p>"
    )


def priority_for(requirement_id: str) -> str:
    if requirement_id in LOW_PRIORITY:
        return "L"
    if requirement_id in MEDIUM_PRIORITY:
        return "M"
    return "H"


def functional_ids(document_xml: str) -> list[str]:
    """Collect requirement IDs only from Section 4.1."""
    ids: list[str] = []
    in_functional_requirements = False
    for match in PARAGRAPH_RE.finditer(document_xml):
        paragraph = match.group(0)
        text = paragraph_text(paragraph).strip()
        is_toc_entry = "<w:hyperlink" in paragraph

        if text == "Functional Requirements" and not is_toc_entry:
            in_functional_requirements = True
            continue
        if text == "Non-Functional Requirements" and not is_toc_entry:
            in_functional_requirements = False
            break
        if in_functional_requirements:
            ids.extend(FR_ID_RE.findall(text))
    return ids


def edit_document_xml(document_xml: str) -> tuple[str, dict[str, object]]:
    source_ids = functional_ids(document_xml)
    if len(source_ids) != len(set(source_ids)):
        duplicates = sorted({item for item in source_ids if source_ids.count(item) > 1})
        raise ValueError(f"Duplicate functional-requirement IDs: {duplicates}")
    if not source_ids:
        raise ValueError("No functional requirements found")

    unknown_configured = (MEDIUM_PRIORITY | LOW_PRIORITY) - set(source_ids)
    if unknown_configured:
        raise ValueError(
            "Priority configuration references missing requirements: "
            + ", ".join(sorted(unknown_configured))
        )

    in_functional_requirements = False
    prioritized: dict[str, str] = {}
    converted_labels: set[str] = set()
    removed_toc_entries: set[str] = set()
    preserved_toc_heading = False
    future_work_updated = 0
    legend_count = 0

    def edit_paragraph(match: re.Match[str]) -> str:
        nonlocal in_functional_requirements, legend_count
        nonlocal preserved_toc_heading, future_work_updated
        paragraph = match.group(0)
        visible = paragraph_text(paragraph)
        stripped = visible.strip()
        is_toc_entry = "<w:hyperlink" in paragraph

        # Remove the two stale TOC result lines immediately. Word is also told
        # to refresh fields on open so its page numbers can be recalculated.
        compact = re.sub(r"\s+", " ", stripped)
        for label in ("Actors", "Non-Functional Requirement Categories"):
            if is_toc_entry and re.fullmatch(re.escape(label) + r"\s*\d+", compact):
                removed_toc_entries.add(label)
                return ""

        if (
            stripped in {"Actors", "Non-Functional Requirement Categories"}
            and not is_toc_entry
        ):
            paragraph = set_paragraph_style(paragraph, "Normal")
            converted_labels.add(stripped)

        # Keep General Terms as the one Heading 2 subsection under
        # Abbreviations. It is present in the existing TOC, so materialising
        # that style prevents it from disappearing when Word refreshes fields.
        if stripped == "General Terms" and not is_toc_entry:
            paragraph = set_paragraph_style(paragraph, "Heading2")
            preserved_toc_heading = True

        if OLD_FUTURE_WORK in stripped:
            if paragraph.count(OLD_FUTURE_WORK) != 1:
                raise ValueError("Could not update the conflicting future-work priority")
            paragraph = paragraph.replace(OLD_FUTURE_WORK, NEW_FUTURE_WORK, 1)
            future_work_updated += 1

        if stripped == "Functional Requirements" and not is_toc_entry:
            in_functional_requirements = True
            legend_count += 1
            return paragraph + legend_paragraph_xml()

        if stripped == "Non-Functional Requirements" and not is_toc_entry:
            in_functional_requirements = False
            return paragraph

        if in_functional_requirements:
            found_ids = FR_ID_RE.findall(stripped)
            for requirement_id in found_ids:
                priority = priority_for(requirement_id)
                if paragraph.count(requirement_id) != 1:
                    raise ValueError(f"Could not annotate {requirement_id}")
                paragraph = paragraph.replace(
                    requirement_id, f"{requirement_id} [{priority}]", 1
                )
                prioritized[requirement_id] = priority
        return paragraph

    edited = PARAGRAPH_RE.sub(edit_paragraph, document_xml)

    expected_labels = {"Actors", "Non-Functional Requirement Categories"}
    if converted_labels != expected_labels:
        raise ValueError(
            "Did not convert all requested labels to Normal: "
            + ", ".join(sorted(expected_labels - converted_labels))
        )
    if removed_toc_entries != expected_labels:
        raise ValueError(
            "Did not remove all stale TOC entries: "
            + ", ".join(sorted(expected_labels - removed_toc_entries))
        )
    if legend_count != 1:
        raise ValueError(f"Expected one priority legend, inserted {legend_count}")
    if not preserved_toc_heading:
        raise ValueError("Could not preserve General Terms as a Heading 2 entry")
    if future_work_updated != 1:
        raise ValueError(
            f"Expected one future-work priority correction, made {future_work_updated}"
        )
    if set(prioritized) != set(source_ids):
        missing = sorted(set(source_ids) - set(prioritized))
        raise ValueError("Requirements not assigned a priority: " + ", ".join(missing))

    counts = {level: list(prioritized.values()).count(level) for level in "HML"}
    summary: dict[str, object] = {
        "requirement_count": len(source_ids),
        "priority_counts": counts,
        "low_priority_ids": sorted(LOW_PRIORITY),
        "converted_labels": sorted(converted_labels),
        "removed_toc_entries": sorted(removed_toc_entries),
        "preserved_toc_heading": "General Terms",
        "future_work_updated": future_work_updated,
    }
    return edited, summary


def mark_toc_dirty(document_xml: str) -> str:
    """Mark the existing TOC field dirty so Word refreshes it on open."""
    instruction_index = document_xml.find("TOC \\h \\u \\z")
    if instruction_index < 0:
        raise ValueError("Could not find the existing TOC field instruction")
    begin_index = document_xml.rfind("<w:fldChar", 0, instruction_index)
    tag_end = document_xml.find("/>", begin_index)
    if begin_index < 0 or tag_end < 0:
        raise ValueError("Could not find the TOC field-begin marker")
    begin_tag = document_xml[begin_index : tag_end + 2]
    if 'w:fldCharType="begin"' not in begin_tag:
        raise ValueError("Nearest TOC field marker is not a begin marker")
    if "w:dirty=" in begin_tag:
        updated_tag = re.sub(r'w:dirty="[^"]*"', 'w:dirty="true"', begin_tag)
    else:
        updated_tag = begin_tag[:-2] + ' w:dirty="true"/>'
    return document_xml[:begin_index] + updated_tag + document_xml[tag_end + 2 :]


def request_field_update(settings_xml: str) -> str:
    update_re = re.compile(r'<w:updateFields(?:\s[^>]*)?\s*/>')
    if update_re.search(settings_xml):
        return update_re.sub('<w:updateFields w:val="true"/>', settings_xml, count=1)
    if "</w:settings>" not in settings_xml:
        raise ValueError("Malformed word/settings.xml")
    return settings_xml.replace(
        "</w:settings>", '<w:updateFields w:val="true"/></w:settings>', 1
    )


def update_docx(source: Path, destination: Path) -> dict[str, object]:
    if source.resolve() == destination.resolve():
        raise ValueError("Source and destination must be different files")

    with zipfile.ZipFile(source, "r") as archive:
        names = archive.namelist()
        if "word/document.xml" not in names or "word/settings.xml" not in names:
            raise ValueError("Input is not a supported Word DOCX package")
        document_xml = archive.read("word/document.xml").decode("utf-8")
        settings_xml = archive.read("word/settings.xml").decode("utf-8")
        source_ids = functional_ids(document_xml)
        edited_document, summary = edit_document_xml(document_xml)
        edited_document = mark_toc_dirty(edited_document)
        edited_settings = request_field_update(settings_xml)

        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            prefix=destination.stem + "-", suffix=".docx", dir=destination.parent, delete=False
        ) as temporary:
            temporary_path = Path(temporary.name)

        try:
            with zipfile.ZipFile(temporary_path, "w") as output:
                for info in archive.infolist():
                    if info.filename == "word/document.xml":
                        payload = edited_document.encode("utf-8")
                    elif info.filename == "word/settings.xml":
                        payload = edited_settings.encode("utf-8")
                    else:
                        payload = archive.read(info.filename)
                    output.writestr(info, payload)

            with zipfile.ZipFile(temporary_path, "r") as check:
                corrupt = check.testzip()
                if corrupt is not None:
                    raise ValueError(f"Corrupt output package member: {corrupt}")
                check_document = check.read("word/document.xml").decode("utf-8")
                annotated_ids = functional_ids(check_document)
                if annotated_ids != source_ids:
                    raise ValueError("Requirement IDs changed while applying priorities")

            temporary_path.replace(destination)
            os.chmod(destination, source.stat().st_mode & 0o777)
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise

    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = update_docx(args.source, args.destination)
    print(f"Created: {args.destination}")
    print(f"Functional requirements: {summary['requirement_count']}")
    print(f"Priority counts: {summary['priority_counts']}")
    print("Low-priority requirements: " + ", ".join(summary["low_priority_ids"]))
    print("Converted to Normal: " + ", ".join(summary["converted_labels"]))
    print("Removed from TOC result: " + ", ".join(summary["removed_toc_entries"]))
    print(f"Preserved in TOC: {summary['preserved_toc_heading']}")
    print("Future-work job-matching priority corrected")


if __name__ == "__main__":
    main()
