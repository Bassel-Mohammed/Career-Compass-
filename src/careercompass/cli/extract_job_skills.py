"""
CareerCompass — Job Skill Extraction CLI

Drives the whole job side end to end: mine the postings, pool the terms,
match the pool once, and aggregate the result into the career-path
ontology that the skill-gap module compares a student against.

The matching stage takes hours and checkpoints as it goes, so an
interrupted run resumes rather than restarting. Everything before it takes
seconds, and everything after it is arithmetic.

Usage:
    # Mine and pool only — seconds, no model, shows what the cutoff costs
    python -m careercompass.cli.extract_job_skills --pool-only

    # Smoke test before committing to the full run
    python -m careercompass.cli.extract_job_skills --min-df 100 --llm

    # The real thing: match every pooled term and derive the ontology
    python -m careercompass.cli.extract_job_skills --llm --db

    # Continue an interrupted run
    python -m careercompass.cli.extract_job_skills --llm --db --resume
"""

import json
import logging
import argparse
import sys
from collections import Counter
from pathlib import Path

from careercompass.config import CLEAN_DATA_DIR, JOBS_DIR
from careercompass.skills.job_corpus import (
    DEFAULT_MIN_DF, build_term_pool, load_pool, save_pool, to_skills,
)
from careercompass.skills.job_matching import (
    MATCHES_PATH, RECHECK_ACCEPT_SCORE, attach_to_jobs, match_terms,
    recheck_terms, risky_terms, save_checkpoint,
)
from careercompass.skills.matcher import (
    ACCEPTED, NEEDS_REVIEW, UNMATCHED, SkillMatcher,
)
from careercompass.skills.ontology import (
    build_ontology, path_totals, save_ontology,
)
from careercompass.skills.taxonomy import TAXONOMY_VERSION

ALL_JOBS_PATH = CLEAN_DATA_DIR / "all_jobs.json"
STATUS_MARK = {ACCEPTED: "✓", NEEDS_REVIEW: "?", UNMATCHED: "✗"}


def load_jobs(path, limit=0, career_path="") -> list:
    """Read the scraped postings, optionally narrowed for a smoke test."""
    with open(path, encoding="utf-8") as f:
        jobs = json.load(f)
    if career_path:
        wanted = career_path.lower()
        jobs = [j for j in jobs
                if (j.get("career_path") or "").lower() == wanted]
    return jobs[:limit] if limit else jobs


def main():
    parser = argparse.ArgumentParser(
        description="Extract skills from job postings and derive the "
                    "career-path required-skills ontology"
    )
    parser.add_argument("--jobs", default=str(ALL_JOBS_PATH),
                        help=f"Postings JSON to mine (default: {ALL_JOBS_PATH})")
    parser.add_argument("--limit", type=int, default=0,
                        help="Mine only the first N postings")
    parser.add_argument("--career-path", default="",
                        help="Restrict to one career path")
    parser.add_argument("--min-df", type=int, default=DEFAULT_MIN_DF,
                        help=f"Postings a term must appear in to be matched "
                             f"(default: {DEFAULT_MIN_DF})")
    parser.add_argument("--pool-only", action="store_true",
                        help="Mine and pool, then stop before matching")
    parser.add_argument(
        "--llm",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Enable or disable the configured LLM (default: CC_MATCH_LLM)",
    )
    parser.add_argument("--backend", default="",
                        help="Embedding backend: lexical, bge, or auto")
    parser.add_argument("--reranker", default="",
                        help="Reranker: lexical or cross")
    parser.add_argument("--resume", action="store_true",
                        help="Continue from the checkpointed term matches")
    parser.add_argument("--reuse-pool", action="store_true",
                        help="Load the stored term pool instead of re-mining")
    parser.add_argument("--recheck", action="store_true",
                        help="Re-decide reranker-accepted matches below the "
                             "strict threshold, routing them to the LLM")
    parser.add_argument("--db", action="store_true",
                        help="Persist the ontology to PostgreSQL")

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    # This run takes hours and is normally redirected to a file, where
    # print() is block-buffered while logging is not. Without this the
    # configuration header — which reranker, which model, which
    # thresholds — sits in the buffer until the process exits, so the one
    # thing worth checking early is the one thing unreadable.
    sys.stdout.reconfigure(line_buffering=True)

    print("Job skill extraction")
    print("=" * 62)

    # ── Mine and pool ──────────────────────────────────────────
    jobs = load_jobs(args.jobs, args.limit, args.career_path)
    if not jobs:
        print(f"❌ No postings found in {args.jobs}")
        sys.exit(1)
    totals = path_totals(jobs)
    print(f"\nPostings        {len(jobs):>7}  across {len(totals)} career paths")

    if args.reuse_pool:
        pool = load_pool()
        print(f"Term pool       {len(pool):>7}  (loaded)")
    else:
        pool = build_term_pool(jobs)
        save_pool(pool)
        print(f"Term pool       {len(pool):>7}  unique terms")

    skills = to_skills(pool, min_df=args.min_df)
    kept = 100 * len(skills) / len(pool) if pool else 0
    print(f"Above df>={args.min_df:<4}   {len(skills):>7}  terms to match ({kept:.1f}% of the pool)")

    if args.pool_only:
        print("\nCutoff cost at other thresholds:")
        for threshold in (2, 3, 5, 10, 20, 50):
            count = sum(1 for r in pool.values()
                        if r["document_frequency"] >= threshold)
            print(f"   df >= {threshold:<3} {count:>7}")
        print(f"\n✅ Pool written. Match it with --min-df {args.min_df} --llm")
        return

    # ── Match ──────────────────────────────────────────────────
    matcher = SkillMatcher.build(
        backend=args.backend, reranker=args.reranker,
        use_llm=args.llm, domain="job_posting",
    )
    print(f"\nTaxonomy        {len(matcher.taxonomy.skills):>7}  v{TAXONOMY_VERSION}")
    print(f"Retrieval       {matcher.index.backend}")
    print(f"Reranker        {matcher.reranker.name}")
    if matcher.decider.available:
        print(f"LLM             {matcher.decider.display_name}")
    else:
        print(f"LLM             unavailable — {matcher.decider.reason_unavailable}")
        print("                ambiguous terms will go to review")

    print()
    matches = match_terms(skills, matcher, checkpoint=MATCHES_PATH,
                          resume=args.resume)
    save_checkpoint(matches, MATCHES_PATH, min_df=args.min_df,
                    taxonomy_version=TAXONOMY_VERSION)

    # ── Recheck ────────────────────────────────────────────────
    if args.recheck:
        risky = risky_terms(matches)
        print(f"\nRechecking      {len(risky):>7}  reranker-accepted matches "
              f"below the strict threshold")
        if risky:
            # Reuses the built matcher's index and model; building a
            # second one would load a second embedder onto the same GPU.
            strict = matcher.with_thresholds(
                accept_score=RECHECK_ACCEPT_SCORE)
            if not strict.decider.available:
                print("   ⚠️  no LLM available; skipping recheck rather than "
                      "re-deciding on the same scores")
            else:
                changed = recheck_terms(skills, matches, strict)
                print(f"   overturned {changed['overturned']}, "
                      f"kept {changed['kept']}")

    relevant = {s["normalized"]: matches[s["normalized"]]
                for s in skills if s["normalized"] in matches}
    status = Counter(r["review_status"] for r in relevant.values())
    method = Counter(r["match_method"] for r in relevant.values())
    total = sum(status.values()) or 1

    print(f"\nMatched         {total:>7}")
    for name, mark in STATUS_MARK.items():
        count = status.get(name, 0)
        print(f"   {mark} {name:<14} {count:>6}  {100 * count / total:5.1f}%")
    print("   by method")
    for name, count in method.most_common():
        print(f"     {name:<16} {count:>6}")

    # ── Ontology ───────────────────────────────────────────────
    # The match record carries the canonical id and label but not the type,
    # so the taxonomy has to supply it. Without it M3 cannot rank technical
    # requirements separately from soft ones, and soft skills top nearly
    # every path.
    skill_types = {s["id"]: s.get("skill_type") for s in matcher.taxonomy.skills}
    rows = build_ontology(skills, matches, totals, skill_types=skill_types)
    save_ontology(rows, totals)
    print(f"\nOntology        {len(rows):>7}  requirements")

    for path in sorted(totals):
        top = [r for r in rows if r["career_path"] == path][:8]
        print(f"\n   {path}  ({totals[path]} postings)")
        for row in top:
            print(f"      {row['required_score']:5.1f}  {row['skill_label'][:44]:<46}"
                  f" {row['required_level']}")

    if args.db:
        from careercompass.db.connection import get_connection
        from careercompass.db.jobs import get_jobs
        from careercompass.db.skills import (
            init_job_skill_tables, remap_retired_skills,
            store_career_path_skills, store_job_skills,
        )
        print("\nSyncing to PostgreSQL...")
        try:
            init_job_skill_tables()

            # A taxonomy rebuild can retire an id that stored matches
            # still carry, which would split one skill across two ids and
            # break the join this whole pipeline exists to make.
            repair = remap_retired_skills(matcher.taxonomy)
            if repair["remapped"]:
                print(f"   remapped {len(repair['remapped'])} retired skill ids")
            if repair["orphaned"]:
                print(f"   ⚠️  {len(repair['orphaned'])} retired ids could not "
                      f"be resolved: {repair['orphaned'][:5]}")

            stored = store_career_path_skills(rows, totals)
            print(f"   wrote {stored} rows into career_path_skills")

            # Per posting. Read from the database rather than the JSON
            # export, which carries no id to write against.
            #
            # One connection for all of them: store_job_skills opens its
            # own when passed none, and letting it do that here would
            # mean 2,238 connect/close cycles for a single pass.
            db_jobs = get_jobs(limit=args.limit, career_path=args.career_path)
            conn = get_connection()
            try:
                counts = attach_to_jobs(
                    db_jobs, matches,
                    store=lambda job_id, skills: store_job_skills(
                        job_id, skills, conn=conn),
                )
            finally:
                conn.close()
            print(f"   wrote {counts['rows']} rows into job_skills across "
                  f"{counts['postings']} postings "
                  f"({counts['accepted']} resolved)")
        except Exception as exc:  # noqa: BLE001
            print(f"⚠️  Database sync failed: {exc}")
            print(f"   The JSON output in {JOBS_DIR} is still valid.")

    print(f"\n✅ Done. Ontology in {JOBS_DIR}")


if __name__ == "__main__":
    main()
