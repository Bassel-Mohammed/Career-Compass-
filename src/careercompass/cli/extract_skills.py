"""
CareerCompass — Course Syllabus Skill Extraction CLI

Usage:
    python -m careercompass.cli.extract_skills "Robotics Syl.pdf" [--min-weight 0.7]
    python -m careercompass.cli.extract_skills "Robotics Syl.pdf" --match

`--match` runs the RAG taxonomy stage inline. For the full matching
report, the review queue and the database write, use
run_skill_matching.py instead.
"""

import sys
import argparse
from pathlib import Path

from careercompass.config import SKILLS_DIR
from careercompass.parsing.syllabus import parse_syllabus
from careercompass.skills.extractor import extract_skills, save_skills


def main():
    parser = argparse.ArgumentParser(
        description="Extract candidate skills from an MEU course syllabus PDF"
    )
    parser.add_argument(
        "pdf_path",
        help="Path to the course syllabus PDF file",
    )
    parser.add_argument(
        "--min-weight", "-w",
        type=float,
        default=0.0,
        help="Only report skills at or above this weight (default: all)",
    )
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="Output JSON path (default: src/data/extracted/skills/<code>.json)",
    )
    parser.add_argument(
        "--match", "-m",
        action="store_true",
        help="Resolve the extracted terms onto the canonical taxonomy",
    )
    parser.add_argument(
        "--llm",
        action="store_true",
        help="With --match, let Claude resolve ambiguous candidates",
    )

    args = parser.parse_args()

    pdf_path = Path(args.pdf_path)
    if not pdf_path.exists():
        print(f"❌ Error: File not found: {pdf_path}")
        sys.exit(1)

    print(f"Parsing: {pdf_path}")
    print("=" * 60)

    try:
        syllabus = parse_syllabus(str(pdf_path))
    except ValueError as exc:
        print(f"❌ Error: {exc}")
        sys.exit(1)

    skills = extract_skills(syllabus)
    shown = [s for s in skills if s["weight"] >= args.min_weight]

    extra = {}
    if args.match:
        from careercompass.skills.matcher import ACCEPTED, SkillMatcher
        from careercompass.skills.taxonomy import TAXONOMY_VERSION

        try:
            matcher = SkillMatcher.build(use_llm=args.llm)
        except FileNotFoundError as exc:
            print(f"❌ Error: {exc}")
            sys.exit(1)
        matches = matcher.match_skills(skills)
        matcher.attach(skills, matches)
        summary = matcher.summary(matches)
        extra = {
            "taxonomy_version": TAXONOMY_VERSION,
            "match_summary": {
                "by_status": summary["by_status"],
                "by_method": summary["by_method"],
            },
        }

    print(f"\nCourse")
    print(f"   {syllabus['course_code']}  {syllabus['course_title']}")

    print(f"\nSkill Summary")
    print(f"   Candidate skills:    {len(skills)}")
    for level in ("beginner", "intermediate", "advanced"):
        count = sum(1 for s in skills if s["level"] == level)
        print(f"   {level.capitalize():<20} {count}")
    for source in ("clo", "lab", "topic", "description"):
        count = sum(1 for s in skills if source in s["sources"])
        print(f"   from {source:<15} {count}")

    if args.match:
        print(f"\nTaxonomy Match")
        for status, count in sorted(extra["match_summary"]["by_status"].items()):
            print(f"   {status:<20} {count}")

    print(f"\nCandidate Skills ({len(shown)} shown)")
    print(f"{'─' * 110}")
    header = f"   {'Wt':<5} {'Level':<13} {'Sources':<26} {'Ev':<3} {'Term':<30}"
    print(header + (" Canonical" if args.match else ""))
    print(f"{'─' * 110}")
    for skill in shown:
        sources = "+".join(skill["sources"])
        row = (f"   {skill['weight']:<5.2f} {skill['level']:<13} {sources:<26} "
               f"{skill['evidence_count']:<3} {skill['term'][:29]:<30}")
        if args.match:
            canonical = skill.get("canonical")
            row += f" {canonical['label'] if canonical else '—'}"
        print(row)
    print(f"{'─' * 110}")

    if syllabus["warnings"]:
        print(f"\n⚠️  Syllabus warnings ({len(syllabus['warnings'])})")
        for warning in syllabus["warnings"]:
            print(f"   - {warning}")

    if args.output:
        output_path = args.output
    else:
        stem = syllabus["course_code"] or pdf_path.stem
        output_path = str(SKILLS_DIR / f"{stem}.json")

    save_skills(syllabus["course_code"], skills, output_path, extra=extra)

    print(f"\n✅ Done! Extracted {len(skills)} candidate skills.")


if __name__ == "__main__":
    main()
