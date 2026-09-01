"""
CareerCompass — build the course catalog and its skill index (M4)

Fetches courses from the sanctioned sources, tags each with the taxonomy
skills it teaches, and writes the index the recommender reads.

    python -m careercompass.cli.build_course_catalog --platform coursera --limit 500
    python -m careercompass.cli.build_course_catalog --all --db

Sources are Coursera's public `courses.v1`, MIT Learn, and YouTube's Data API.
Udemy is absent: its Affiliate API was discontinued on 1 January 2025 and
scraping the site would breach its terms.

Descriptions are fetched, read by the tagger, and dropped. Only derived skill
ids, titles and URLs are written — the platforms' catalog text is not licensed
for republication, so the product links out instead.

`--cached` re-indexes from data/raw/catalog/ without re-fetching, which is what
you want after changing the tagging rules.
"""
import argparse
import logging
import sys

from careercompass.catalog import SOURCES, get_source
from careercompass.catalog.base import load_raw, save_raw
from careercompass.skills.course_index import (
    build_index, ontology_skill_ids, save_index,
)
from careercompass.skills.taxonomy import load_taxonomy

logger = logging.getLogger(__name__)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--platform", action="append", choices=SOURCES,
                    help="source to ingest; repeatable")
    ap.add_argument("--all", action="store_true", help="ingest every source")
    ap.add_argument("--limit", type=int, default=None,
                    help="stop after roughly this many courses per source")
    ap.add_argument("--cached", action="store_true",
                    help="re-index from data/raw/catalog/ without re-fetching")
    ap.add_argument("--all-skills", action="store_true",
                    help="tag against the whole taxonomy rather than only the "
                         "skills some career path requires. Slower and noisier; "
                         "a skill no path asks for can never appear in a gap.")
    ap.add_argument("--db", action="store_true", help="also write to PostgreSQL")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    platforms = list(SOURCES) if args.all else (args.platform or ["coursera"])

    courses = []
    for platform in platforms:
        if args.cached:
            fetched = load_raw(platform)
            print(f"{platform:<10} {len(fetched):>6} from cache")
        else:
            kwargs = {}
            if platform == "youtube":
                # There is no catalog to page through, only a search index, so
                # the queries come from what the market actually asks for.
                taxonomy = load_taxonomy()
                wanted = ontology_skill_ids()
                kwargs["queries"] = [s["label"] for s in taxonomy.skills
                                     if s["id"] in wanted][:40]
            fetched = get_source(platform)(limit=args.limit, **kwargs)
            if fetched:
                save_raw(platform, fetched)
            print(f"{platform:<10} {len(fetched):>6} fetched")
        courses.extend(fetched)

    if not courses:
        print("no courses ingested", file=sys.stderr)
        sys.exit(1)

    taxonomy = load_taxonomy()
    skill_ids = None if args.all_skills else ontology_skill_ids()
    if skill_ids is not None and not skill_ids:
        print("no ontology on disk; falling back to the whole taxonomy",
              file=sys.stderr)
        skill_ids = None

    index = build_index(courses, taxonomy, skill_ids=skill_ids)
    path = save_index(index)

    covered = {c["course_id"] for courses_ in index.values() for c in courses_}
    print()
    print(f"courses ingested   {len(courses):>6}")
    print(f"courses indexed    {len(covered):>6}")
    print(f"skills covered     {len(index):>6}"
          + (f" of {len(skill_ids)} required" if skill_ids else ""))
    print(f"index              {path}")

    if skill_ids:
        missing = sorted(skill_ids - set(index))
        if missing:
            labels = {s["id"]: s["label"] for s in taxonomy.skills}
            print(f"\n{len(missing)} required skills have no course. The gap "
                  "analysis can name these but not act on them:")
            for skill_id in missing[:15]:
                print(f"   {labels.get(skill_id, skill_id)}")
            if len(missing) > 15:
                print(f"   ... and {len(missing) - 15} more")

    if args.db:
        from careercompass.db.skills import init_catalog_tables, store_catalog_courses
        init_catalog_tables()
        written = store_catalog_courses(index, platforms=platforms)
        print(f"\nwrote {written} course-skill rows to PostgreSQL")


if __name__ == "__main__":
    main()
