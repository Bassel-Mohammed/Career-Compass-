"""
CareerCompass — Course Syllabus Extraction CLI

Usage:
    python -m careercompass.cli.parse_syllabus "robotics_programming.pdf" [--output <output_path>]
"""

import sys
import argparse
from pathlib import Path

from careercompass.config import SYLLABI_DIR
from careercompass.parsing.syllabus import parse_syllabus, save_syllabus


def main():
    parser = argparse.ArgumentParser(
        description="Extract structured data from MEU course syllabus PDFs"
    )
    parser.add_argument(
        "pdf_path",
        help="Path to the course syllabus PDF file",
    )
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="Output JSON file path (default: src/data/extracted/syllabi/<code>.json)",
    )

    args = parser.parse_args()

    pdf_path = Path(args.pdf_path)
    if not pdf_path.exists():
        print(f"❌ Error: File not found: {pdf_path}")
        sys.exit(1)

    print(f"Parsing: {pdf_path}")
    print("=" * 60)

    try:
        result = parse_syllabus(str(pdf_path))
    except ValueError as exc:
        print(f"❌ Error: {exc}")
        sys.exit(1)

    clos = result["clos"]
    weeks = result["weeks"]

    print(f"\nCourse Information")
    print(f"   Code:        {result['course_code']}")
    print(f"   Title:       {result['course_title']}")
    print(f"   Credit:      {result['credit_hours']}h "
          f"(theoretical {result['theoretical_hours']}h | "
          f"practical {result['practical_hours']}h)")
    print(f"   JNQF level:  {result['jnqf_level']}")
    print(f"   Prereq:      {', '.join(result['prerequisites']) or '—'}")

    print(f"\nExtraction Summary")
    print(f"   CLOs:                {len(clos)}")
    print(f"   Weeks:               {len(weeks)}")
    print(f"   Topics:              {sum(len(w['topics']) for w in weeks)}")
    print(f"   Labs:                {sum(len(w['labs']) for w in weeks)}")
    print(f"   Description words:   {len(result['description'].split())}")

    print(f"\nJNQF Descriptor Distribution")
    for tier in ("knowledge", "skill", "competency"):
        count = sum(1 for c in clos if c["jnqf_descriptor"] == tier)
        print(f"   {tier.capitalize():<15} {count}")

    print(f"\nCourse Learning Outcomes ({len(clos)})")
    print(f"{'─' * 100}")
    for clo in clos:
        descriptor = clo["jnqf_descriptor"] or "—"
        print(f"   {clo['number']}. [{descriptor:<10}] {clo['text'][:74]}")

    print(f"\nWeekly Schedule ({len(weeks)} weeks)")
    print(f"{'─' * 100}")
    for week in weeks:
        covered = ",".join(str(c) for c in week["clos"]) or "—"
        print(f"   W{week['week']:<3} [CLO {covered:<10}] {'; '.join(week['topics'])[:60]}")
        for lab in week["labs"]:
            print(f"        └─ {lab[:80]}")

    if result["warnings"]:
        print(f"\n⚠️  Warnings ({len(result['warnings'])})")
        for warning in result["warnings"]:
            print(f"   - {warning}")

    if args.output:
        output_path = args.output
    else:
        stem = result["course_code"] or pdf_path.stem
        output_path = str(SYLLABI_DIR / f"{stem}.json")

    save_syllabus(result, output_path)

    print(f"\n✅ Done! Extracted {len(clos)} CLOs and {len(weeks)} weeks.")


if __name__ == "__main__":
    main()
