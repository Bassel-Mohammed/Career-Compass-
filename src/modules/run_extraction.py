"""
CareerCompass — Academic Plan Extraction CLI

Usage:
    python -m src.modules.run_extraction CS_AI_plan_mohammed_EN.pdf [--output <output_path>]
"""

import sys
import json
import argparse
from pathlib import Path

from src.modules.transcript_parser import parse_academic_plan, save_extraction


def main():
    parser = argparse.ArgumentParser(
        description="Extract structured data from MEU academic plan PDFs"
    )
    parser.add_argument(
        "pdf_path",
        help="Path to the academic plan PDF file",
    )
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="Output JSON file path (default: src/data/extracted/<filename>.json)",
    )

    args = parser.parse_args()

    pdf_path = Path(args.pdf_path)
    if not pdf_path.exists():
        print(f"❌ Error: File not found: {pdf_path}")
        sys.exit(1)

    print(f"Parsing: {pdf_path}")
    print("=" * 60)

    result = parse_academic_plan(str(pdf_path))

    student = result["student"]
    summary = result["summary"]

    print(f"\nStudent Information")
    print(f"   Name:      {student.get('student_name', '')}")
    print(f"   ID:        {student.get('student_id', '')}")
    print(f"   GPA:       {student.get('cumulative_gpa', '')}")
    print(f"   Rating:    {student.get('rating', '')}")
    print(f"   Level:     {student.get('level', '')}")
    print(f"   Plan:      {student.get('plan_hours', 0)}h | "
          f"Passed: {student.get('passed_hours', 0)}h | "
          f"Remaining: {student.get('remaining_hours', 0)}h")

    print(f"\nExtraction Summary")
    print(f"   Total courses:       {summary['total_courses']}")
    print(f"   Passed:              {summary['passed_courses']}")
    print(f"   Transferred:         {summary['transferred_courses']}")
    print(f"   Exempted:            {summary['exempted_courses']}")
    print(f"   In progress:         {summary['in_progress_courses']}")
    print(f"   Not registered:      {summary['not_registered_courses']}")
    print(f"   Computed GPA:        {summary['computed_gpa']}")
    print(f"   Reported GPA:        {summary['reported_gpa']}")

    dist = summary["grade_distribution"]
    print(f"\nGrade Distribution")
    print(f"   Strong (≥B):    {dist['strong']}")
    print(f"   Moderate (B-~C): {dist['moderate']}")
    print(f"   Weak (<C):      {dist['weak']}")
    print(f"   No grade:       {dist['unknown']}")

    print(f"\nRequirement Categories ({len(result['categories'])})")
    for cat in result["categories"]:
        print(f"   [{cat['passed_hours']}/{cat['required_hours']}h] "
              f"{cat['category_name']} — {len(cat['courses'])} courses")

    print(f"\n{'─' * 100}")
    print(f"{'Code':<10} {'Course Name':<45} {'Hrs':>3} {'Grade':>5} "
          f"{'Pts':>5} {'Str':>8} {'Status':<12} {'Sem':<6}")
    print(f"{'─' * 100}")

    for course in result["all_courses"]:
        pts = f"{course['grade_points']:.2f}" if course['grade_points'] is not None else "  —"
        grade = course['grade'] or "  —"
        name = course['course_name'][:43]
        print(f"{course['course_code']:<10} {name:<45} {course['credit_hours']:>3} "
              f"{grade:>5} {pts:>5} {course['grade_strength']:>8} "
              f"{course['status']:<12} {course['semester'] or '':>6}")

    print(f"{'─' * 100}")

    if args.output:
        output_path = args.output
    else:
        output_dir = Path("src/data/extracted")
        output_path = str(output_dir / f"{pdf_path.stem}.json")

    save_extraction(result, output_path)

    print(f"\n✅ Done! Extracted {summary['total_courses']} courses.")


if __name__ == "__main__":
    main()
