"""
CareerCompass — Skill Matching CLI

Runs the RAG taxonomy stage over a course's extracted skills and reports
what was matched, what needs a human, and what nothing in the taxonomy
covers.

Usage:
    # Parse, extract and match in one go
    python -m careercompass.cli.match_skills "robotics_programming.pdf"

    # Match skills already extracted
    python -m careercompass.cli.match_skills --skills data/extracted/skills/0432405.json

    # Let the configured LLM resolve ambiguous cases, and store the results
    python -m careercompass.cli.match_skills "robotics_programming.pdf" --llm --db
"""

import sys
import json
import logging
import argparse
from pathlib import Path

from careercompass.config import SKILLS_DIR
from careercompass.parsing.syllabus import parse_syllabus
from careercompass.skills.extractor import extract_skills, save_skills
from careercompass.skills.matcher import (
    ACCEPTED, NEEDS_REVIEW, UNMATCHED, SkillMatcher,
)
from careercompass.skills.taxonomy import TAXONOMY_VERSION



STATUS_MARK = {ACCEPTED: "✓", NEEDS_REVIEW: "?", UNMATCHED: "✗"}


def load_skills_file(path):
    """Read a skills JSON produced by run_skill_extraction."""
    with open(path, encoding="utf-8") as f:
        payload = json.load(f)
    return payload.get("course_code", ""), payload.get("skills", [])


def main():
    parser = argparse.ArgumentParser(
        description="Match extracted course skills onto the canonical taxonomy"
    )
    parser.add_argument("pdf_path", nargs="?", default=None,
                        help="Course syllabus PDF (parsed and extracted first)")
    parser.add_argument("--skills", default=None,
                        help="Skills JSON to match instead of parsing a PDF")
    parser.add_argument(
        "--llm",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Enable or disable the configured LLM (default: CC_MATCH_LLM)",
    )
    parser.add_argument("--backend", default="",
                        help="Embedding backend: lexical, bge, or auto")
    parser.add_argument("--reranker", default="",
                        help="Reranker: lexical, cross, or auto")
    parser.add_argument("--rebuild-index", action="store_true",
                        help="Re-embed the taxonomy before matching")
    parser.add_argument("--min-weight", "-w", type=float, default=0.0,
                        help="Only report skills at or above this weight")
    parser.add_argument("--review-only", action="store_true",
                        help="Only print the terms a human needs to look at")
    parser.add_argument("--db", action="store_true",
                        help="Store the results in PostgreSQL")
    parser.add_argument("--output", "-o", default=None,
                        help="Output JSON path (default: alongside the extracted skills)")

    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(message)s")

    if not args.pdf_path and not args.skills:
        parser.error("Give a PDF path or --skills")

    # ── Load the skills ────────────────────────────────────────
    if args.skills:
        skills_path = Path(args.skills)
        if not skills_path.exists():
            print(f"❌ Error: File not found: {skills_path}")
            sys.exit(1)
        course_code, skills = load_skills_file(skills_path)
        default_output = skills_path
        print(f"Matching: {skills_path}")
    else:
        pdf_path = Path(args.pdf_path)
        if not pdf_path.exists():
            print(f"❌ Error: File not found: {pdf_path}")
            sys.exit(1)
        print(f"Parsing: {pdf_path}")
        try:
            syllabus = parse_syllabus(str(pdf_path))
        except ValueError as exc:
            print(f"❌ Error: {exc}")
            sys.exit(1)
        course_code = syllabus["course_code"]
        skills = extract_skills(syllabus)
        default_output = SKILLS_DIR / f"{course_code or pdf_path.stem}.json"

    print("=" * 60)

    # ── Match ──────────────────────────────────────────────────
    try:
        matcher = SkillMatcher.build(
            backend=args.backend,
            reranker=args.reranker,
            use_llm=args.llm,
            rebuild=args.rebuild_index,
        )
    except FileNotFoundError as exc:
        print(f"❌ Error: {exc}")
        sys.exit(1)

    print(f"\nTaxonomy")
    print(f"   {len(matcher.taxonomy)} skills  "
          f"({', '.join(f'{k} {v}' for k, v in sorted(matcher.taxonomy.counts().items()))})")
    print(f"   retrieval: {matcher.index.backend}   reranker: {matcher.reranker.name}")
    if matcher.decider.enabled:
        llm_status = (
            matcher.decider.display_name
            if matcher.decider.available
            else "unavailable — " + matcher.decider.reason_unavailable
        )
        print(f"   llm:       {llm_status}")

    matches = matcher.match_skills(skills)
    matcher.attach(skills, matches)
    summary = matcher.summary(matches)

    # ── Report ─────────────────────────────────────────────────
    print(f"\nMatch Summary")
    print(f"   Terms matched:       {summary['total']}")
    for status in (ACCEPTED, NEEDS_REVIEW, UNMATCHED):
        count = summary["by_status"].get(status, 0)
        share = (100.0 * count / summary["total"]) if summary["total"] else 0.0
        print(f"   {status:<20} {count:>4}  ({share:.0f}%)")
    print("   by method")
    for method, count in sorted(summary["by_method"].items(), key=lambda kv: -kv[1]):
        print(f"      {method:<20} {count:>4}")

    shown = [
        (skill, match) for skill, match in zip(skills, matches)
        if skill["weight"] >= args.min_weight
        and (not args.review_only or match["review_status"] == NEEDS_REVIEW)
    ]

    print(f"\nCanonical Skills ({len(shown)} shown)")
    print("─" * 110)
    print(f"   {'':<2} {'Wt':<5} {'Score':<6} {'Method':<19} {'Term':<34} Canonical")
    print("─" * 110)
    for skill, match in shown:
        mark = STATUS_MARK.get(match["review_status"], " ")
        canonical = match["canonical_label"] or "—"
        term = skill["term"][:33]
        print(f"   {mark:<2} {skill['weight']:<5.2f} {match['match_score']:<6.3f} "
              f"{match['match_method']:<19} {term:<34} {canonical}")
    print("─" * 110)
    print("   ✓ accepted    ? needs review    ✗ no match")

    review = summary["review_queue"]
    if review and not args.review_only:
        print(f"\n⚠️  Manual review queue ({len(review)})")
        for match in review[:15]:
            options = ", ".join(f"{c['label']} ({c['score']})" for c in match["candidates"])
            print(f"   {match['original_term']}")
            print(f"      → {options or 'no candidates'}")
        if len(review) > 15:
            print(f"   ... and {len(review) - 15} more")

    # ── Save ───────────────────────────────────────────────────
    output_path = Path(args.output) if args.output else default_output
    save_skills(course_code, skills, str(output_path), extra={
        "taxonomy_version": TAXONOMY_VERSION,
        "match_backend": {
            "retrieval": matcher.index.backend,
            "reranker": matcher.reranker.name,
            "llm_provider": (matcher.decider.provider
                             if matcher.decider.available else None),
            "llm": matcher.decider.model if matcher.decider.available else None,
        },
        "match_summary": {
            "by_status": summary["by_status"],
            "by_method": summary["by_method"],
        },
    })

    if args.db:
        from careercompass.db.skills import store_course_skills
        try:
            stored = store_course_skills(course_code, skills)
            print(f"✅ Stored {stored} course skills in PostgreSQL")
        except Exception as exc:
            print(f"⚠️  Could not store results: {exc}")
            print("   If this is a foreign-key error, the database taxonomy is "
                  "stale: rerun build_taxonomy with --db.")

    print(f"\n✅ Done. {summary['by_status'].get(ACCEPTED, 0)}/{summary['total']} terms canonicalized.")


if __name__ == "__main__":
    main()
